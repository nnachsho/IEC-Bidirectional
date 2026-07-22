"""Config flow for the Israel Electric Company integration."""

from __future__ import annotations

from dataclasses import asdict
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from iec_api.iec_client import IecClient

from .const import CONF_CONTRACT_ID, CONF_ID_NUMBER, CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)


class IECConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle IEC authentication using its SMS/email OTP flow."""

    VERSION = 1
    _client: IecClient | None = None
    _id_number: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Request the Israeli ID and send the one-time code."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._id_number = user_input[CONF_ID_NUMBER].strip()
            try:
                self._client = IecClient(self._id_number, async_get_clientsession(self.hass))
                await self._client.login_with_id(prefer_sms=True)
            except ValueError:
                errors["base"] = "invalid_id"
            except Exception:
                _LOGGER.debug("IEC OTP request failed", exc_info=True)
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_otp()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ID_NUMBER): str}),
            errors=errors,
        )

    async def async_step_otp(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Verify an IEC one-time passcode and validate the account."""
        errors: dict[str, str] = {}
        if user_input is not None and self._client and self._id_number:
            try:
                await self._client.verify_otp(user_input["otp"])
                # The customer endpoint is the stable IEC account-discovery route.
                # The newer accounts/outages route can return HTTP 500 for valid
                # residential accounts, so do not use it during initial setup.
                customer = await self._client.get_customer()
                contracts = await self._client.get_contracts(customer.bp_number) if customer else []
                contract = contracts[0] if contracts else None
                if not customer or not contract:
                    errors["base"] = "no_contract"
                else:
                    await self.async_set_unique_id(f"iec_{customer.bp_number}_{contract.contract_id}")
                    self._abort_if_unique_id_configured()
                    token = asdict(self._client.get_token())
                    return self.async_create_entry(
                        title=f"IEC {contract.address}",
                        data={
                            CONF_ID_NUMBER: self._id_number,
                            CONF_TOKEN: token,
                            "bp_number": customer.bp_number,
                            CONF_CONTRACT_ID: contract.contract_id,
                        },
                    )
            except Exception:
                _LOGGER.debug("IEC OTP verification failed", exc_info=True)
                errors["base"] = "invalid_auth"

        return self.async_show_form(
            step_id="otp",
            data_schema=vol.Schema({vol.Required("otp"): str}),
            errors=errors,
            description_placeholders={"delivery": "SMS or email"},
        )
