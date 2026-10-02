"""Config and options flow for the Voltronic Solar Inverter integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlowWithReload
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_FAST_INTERVAL,
    CONF_SLOW_INTERVAL,
    DEFAULT_FAST_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_SLOW_INTERVAL,
    DOMAIN,
    LOGGER,
    MAX_FAST_INTERVAL,
    MAX_SLOW_INTERVAL,
    MIN_FAST_INTERVAL,
    MIN_SLOW_INTERVAL,
)
from .coordinator import VoltronicConfigEntry
from .protocol import InverterClient, InverterError


def _seconds(minimum: int, maximum: int) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=1,
            mode=selector.NumberSelectorMode.BOX,
            unit_of_measurement="s",
        )
    )


def _interval_fields(fast: int, slow: int) -> dict[Any, Any]:
    return {
        vol.Required(CONF_FAST_INTERVAL, default=fast): _seconds(MIN_FAST_INTERVAL, MAX_FAST_INTERVAL),
        vol.Required(CONF_SLOW_INTERVAL, default=slow): _seconds(MIN_SLOW_INTERVAL, MAX_SLOW_INTERVAL),
    }


async def _probe(host: str, port: int) -> tuple[str, str]:
    """Return (model, serial number) using read-only queries (QPI, QMN, QID)."""
    client = InverterClient(host, port)
    try:
        protocol_id = (await client.query("QPI")).strip()
        model = (await client.query("QMN")).strip()
        serial = (await client.query("QID")).strip()
    finally:
        await client.close()
    LOGGER.debug("Found %s inverter, protocol %s", model, protocol_id)
    return model, serial


class VoltronicConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ask for the gateway address and verify the inverter answers."""

    VERSION = 1
    MINOR_VERSION = 2  # 1.2: see async_migrate_entry

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            try:
                model, serial = await _probe(host, port)
            except InverterError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                LOGGER.exception("Unexpected error while probing %s:%s", host, port)
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
                return self.async_create_entry(
                    title=f"Inverter {model}",
                    data={CONF_HOST: host, CONF_PORT: port},
                    options={
                        CONF_FAST_INTERVAL: int(user_input[CONF_FAST_INTERVAL]),
                        CONF_SLOW_INTERVAL: int(user_input[CONF_SLOW_INTERVAL]),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                **_interval_fields(DEFAULT_FAST_INTERVAL, DEFAULT_SLOW_INTERVAL),
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: VoltronicConfigEntry) -> VoltronicOptionsFlow:
        return VoltronicOptionsFlow()


class VoltronicOptionsFlow(OptionsFlowWithReload):
    """Poll intervals."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={
                    CONF_FAST_INTERVAL: int(user_input[CONF_FAST_INTERVAL]),
                    CONF_SLOW_INTERVAL: int(user_input[CONF_SLOW_INTERVAL]),
                }
            )
        options = self.config_entry.options
        schema = vol.Schema(
            {
                **_interval_fields(
                    options.get(CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL),
                    options.get(CONF_SLOW_INTERVAL, DEFAULT_SLOW_INTERVAL),
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
