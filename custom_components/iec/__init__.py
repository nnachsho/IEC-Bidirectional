"""Israel Electric Company integration."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

from iec_api.iec_client import IecClient
from iec_api.models.jwt import JWT

from .const import CONF_ID_NUMBER, CONF_TOKEN, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import IECCoordinator

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR]

type IECConfigEntry = ConfigEntry[IECCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: IECConfigEntry) -> bool:
    """Set up IEC from a config entry."""
    client = IecClient(entry.data[CONF_ID_NUMBER], async_get_clientsession(hass))
    try:
        await client.load_jwt_token(JWT(**entry.data[CONF_TOKEN]))
    except Exception as err:  # IEC's client exposes several authentication exceptions.
        _LOGGER.debug("Unable to restore IEC session", exc_info=True)
        raise ConfigEntryAuthFailed("IEC session expired; reauthenticate the integration") from err

    coordinator = IECCoordinator(
        hass,
        entry,
        client,
        timedelta(seconds=entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)),
    )
    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed as err:
        raise ConfigEntryNotReady(f"Unable to retrieve IEC meter data: {err}") from err

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IECConfigEntry) -> bool:
    """Unload an IEC config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
