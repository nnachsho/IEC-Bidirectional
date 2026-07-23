"""Data coordinator for IEC meter readings."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from iec_api.iec_client import IecClient
from iec_api.models.remote_reading import ReadingResolution

from .const import CONF_BP_NUMBER, CONF_CONTRACT_ID, CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class IECMeterData:
    """The IEC values exposed by one meter refresh."""

    meter_serial: str | None = None
    meter_code: str | None = None
    total_import: float | None = None
    total_export: float | None = None
    period_import: float | None = None
    period_export: float | None = None
    period_start: str | None = None
    period_end: str | None = None
    last_readings: list[dict[str, Any]] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


class IECCoordinator(DataUpdateCoordinator[IECMeterData]):
    """Fetch IEC data once and share it between all sensors."""

    def __init__(self, hass: HomeAssistant, entry, client: IecClient, interval: timedelta) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=interval, config_entry=entry)
        self.entry = entry
        self.client = client

    async def _async_update_data(self) -> IECMeterData:
        """Read the current cumulative and daily smart-meter values."""
        try:
            devices = await self.client.get_devices(self.entry.data[CONF_CONTRACT_ID])
            if not devices:
                raise UpdateFailed("IEC returned no meters for this contract")
            device = next((item for item in devices if item.is_active), devices[0])

            last = await self.client.get_last_meter_reading(
                self.entry.data[CONF_BP_NUMBER], self.entry.data[CONF_CONTRACT_ID]
            )
            last_meter = (last.last_meters or [None])[0] if last else None
            if not last_meter:
                raise UpdateFailed("IEC returned no meter-register data")

            invoices = await self.client.get_electric_bill(
                self.entry.data[CONF_BP_NUMBER], self.entry.data[CONF_CONTRACT_ID]
            )
            latest_invoice = next((invoice for invoice in (invoices.invoices if invoices else []) if invoice.to_date), None)
            last_invoice_date = latest_invoice.to_date if latest_invoice else datetime.now() - timedelta(days=31)

            # IEC enables RemoteReadingRange only for some smart-meter accounts.
            # A server-side 500 from that optional endpoint must not make the
            # standard LastMeterReading endpoint unavailable in Home Assistant.
            remote_error: str | None = None
            try:
                report = await self.client.get_remote_reading(
                    meter_kind="Consumption",
                    meter_serial_number=last_meter.serial_number,
                    meter_code=int(device.device_code or 0),
                    last_invoice_date=last_invoice_date,
                    from_date=datetime.now() - timedelta(days=2),
                    resolution=ReadingResolution.DAILY,
                    contract_id=self.entry.data[CONF_CONTRACT_ID],
                )
            except Exception as err:
                _LOGGER.warning(
                    "IEC remote import/export readings are unavailable; using meter-register readings instead: %s",
                    err,
                )
                report = None
                remote_error = str(err)
            meter = report.meter_list[0] if report and report.meter_list else None
            future = meter.future_consumption_info if meter else None
            readings = [
                {
                    "reading": reading.reading,
                    "reading_code": reading.reading_code,
                    "reading_date": reading.reading_date.isoformat() if reading.reading_date else None,
                    "usage": reading.usage,
                    "serial_number": reading.serial_number or last_meter.serial_number,
                }
                for reading in last_meter.meter_readings
            ]
            result = IECMeterData(
                meter_serial=last_meter.serial_number,
                meter_code=device.device_code,
                # IEC's documented LastMeterReading sample uses code 01 for the
                # cumulative import register. It provides a useful fallback when
                # the optional smart-meter remote-reading service is disabled.
                total_import=(future.total_import if future else None)
                or (meter.total_import if meter else None)
                or next((item.reading for item in last_meter.meter_readings if item.reading_code == "01"), None),
                # IEC returns export under futureBackStream for some accounts
                # and under totalExport for others. Prefer the explicit total,
                # then use the equivalent back-stream field as a fallback.
                total_export=(future.total_export if future else None)
                or (future.future_back_stream if future else None)
                or (meter.total_export if meter else None)
                or (meter.total_back_stream_for_period if meter else None),
                period_import=meter.total_consumption_for_period if meter else None,
                period_export=meter.total_back_stream_for_period if meter else None,
                period_start=meter.start_date.isoformat() if meter and meter.start_date else None,
                period_end=meter.end_date.isoformat() if meter and meter.end_date else None,
                last_readings=readings,
                attributes={
                    "report_status": report.report_status if report else None,
                    "report_status_text": report.report_status_text if report else None,
                    "remote_reading_available": report is not None,
                    "remote_reading_error": remote_error,
                    "remote_import": future.total_import if future else None,
                    "remote_export": future.total_export if future else None,
                    "remote_back_stream": future.future_back_stream if future else None,
                    "period_count": meter.number_of_period_aggregated if meter else None,
                    "period_status": meter.status_for_period if meter else None,
                    "intervals": [
                        {"start": item.interval.isoformat(), "import": item.consumption, "export": item.back_stream, "status": item.status}
                        for item in (meter.period_consumptions if meter else [])
                    ],
                },
            )
            self.hass.config_entries.async_update_entry(
                self.entry, data={**self.entry.data, CONF_TOKEN: asdict(self.client.get_token())}
            )
            return result
        except UpdateFailed:
            raise
        except Exception as err:
            _LOGGER.debug("IEC meter refresh failed", exc_info=True)
            raise UpdateFailed(f"IEC API error: {err}") from err
