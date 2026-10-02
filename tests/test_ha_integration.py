"""Home Assistant level tests: config flow, entities, control entities, diagnostics.

Needs pytest-homeassistant-custom-component; skipped otherwise. The inverter is
replaced by a fake gateway answering from recorded fixtures (no real socket).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import FakeGateway, answered
from custom_components.voltronic_solar_inverter import diagnostics
from custom_components.voltronic_solar_inverter.const import (
    CONF_ENABLE_CONTROLS,
    CONF_FAST_INTERVAL,
    CONF_SLOW_INTERVAL,
    DOMAIN,
)
from custom_components.voltronic_solar_inverter.protocol.client import InverterClient
from custom_components.voltronic_solar_inverter.protocol.framing import crc_bytes, encode_frame

FULL = answered("snapshot_B_night_output_on.json")
GRID_OFF = answered("snapshot_B_night_grid_off.json")
SERIAL = FULL["QID"]
PREFIX = "inverter_vmii_4000"


def reply(payload: str) -> bytes:
    body = b"(" + payload.encode()
    return body + crc_bytes(body) + b"\r"


class Inverter:
    """Scripted inverter behind a FakeGateway. Unknown commands are silent."""

    def __init__(self) -> None:
        self.table = dict(FULL)
        self.write_answer = "ACK"
        self.offline = False
        self.gateway = FakeGateway(self._respond)

    def _respond(self, frame: bytes):
        command = frame[:-3].decode()
        if self.offline:
            return None
        if command.startswith("Q"):
            return [reply(self.table[command])] if command in self.table else None
        return [reply(self.write_answer)]

    @property
    def writes(self) -> list[str]:
        return [f[:-3].decode() for f in self.gateway.sent if not f.startswith(b"Q")]

    def client(self, host: str, port: int, **kwargs) -> InverterClient:
        self.gateway.refuse = self.offline
        return InverterClient(
            host, port, timeout=0.1, min_gap=0, open_connection=self.gateway.open_connection
        )


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def inverter():
    inv = Inverter()
    with (
        patch("custom_components.voltronic_solar_inverter.InverterClient", inv.client),
        patch("custom_components.voltronic_solar_inverter.config_flow.InverterClient", inv.client),
    ):
        yield inv


def make_entry(controls: bool = False) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Inverter VMII-4000",
        unique_id=SERIAL,
        data={CONF_HOST: "192.0.2.10", CONF_PORT: 8899},
        options={CONF_FAST_INTERVAL: 10, CONF_SLOW_INTERVAL: 60, CONF_ENABLE_CONTROLS: controls},
    )


async def setup(hass: HomeAssistant, controls: bool = False) -> MockConfigEntry:
    entry = make_entry(controls)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


# --- config flow -------------------------------------------------------------------


async def test_user_flow_creates_entry(hass: HomeAssistant, inverter: Inverter) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.voltronic_solar_inverter.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "192.0.2.10", CONF_PORT: 8899, CONF_FAST_INTERVAL: 15, CONF_SLOW_INTERVAL: 120},
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Inverter VMII-4000"
    assert result["data"] == {CONF_HOST: "192.0.2.10", CONF_PORT: 8899}
    assert result["options"] == {
        CONF_FAST_INTERVAL: 15,
        CONF_SLOW_INTERVAL: 120,
        CONF_ENABLE_CONTROLS: False,
    }
    assert result["result"].unique_id == SERIAL
    assert inverter.gateway.sent == [encode_frame(c) for c in ("QPI", "QMN", "QID")]


async def test_user_flow_cannot_connect(hass: HomeAssistant, inverter: Inverter) -> None:
    inverter.offline = True
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.0.2.10", CONF_PORT: 8899, CONF_FAST_INTERVAL: 10, CONF_SLOW_INTERVAL: 60},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_already_configured(hass: HomeAssistant, inverter: Inverter) -> None:
    make_entry().add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "192.0.2.11", CONF_PORT: 8899, CONF_FAST_INTERVAL: 10, CONF_SLOW_INTERVAL: 60},
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


# --- read-only entities ------------------------------------------------------------


async def test_setup_creates_read_only_entities(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.LOADED

    assert hass.states.get(f"sensor.{PREFIX}_grid_voltage").state == "237.8"
    assert hass.states.get(f"sensor.{PREFIX}_battery_voltage").state == "25.6"
    assert hass.states.get(f"sensor.{PREFIX}_mode").state == "battery"
    out_prio = hass.states.get(f"sensor.{PREFIX}_output_source_priority")
    assert out_prio.state == "sbu"
    assert out_prio.attributes["code"] == 1
    assert hass.states.get(f"sensor.{PREFIX}_charger_source_priority").state == "only_solar"
    assert hass.states.get(f"sensor.{PREFIX}_battery_type").state == "user_defined"
    assert hass.states.get(f"sensor.{PREFIX}_firmware_version").state == "00040.09"
    assert hass.states.get(f"binary_sensor.{PREFIX}_ac_output").state == STATE_ON
    assert hass.states.get(f"binary_sensor.{PREFIX}_sbu_priority").state == STATE_ON
    assert hass.states.get(f"binary_sensor.{PREFIX}_charging").state == STATE_OFF
    # a0 (PV loss) alone must not raise a warning.
    assert hass.states.get(f"binary_sensor.{PREFIX}_warning").state == STATE_OFF
    assert hass.states.get(f"binary_sensor.{PREFIX}_fault").state == STATE_OFF
    assert hass.states.get(f"binary_sensor.{PREFIX}_grid_lost").state == STATE_OFF
    assert hass.states.get(f"binary_sensor.{PREFIX}_buzzer").state == STATE_ON
    # Voltage-based battery % exists but is disabled by default.
    registry = er.async_get(hass)
    estimate = registry.async_get(f"sensor.{PREFIX}_battery_level_estimate_voltage_based")
    assert estimate is not None and estimate.disabled_by is not None
    # No control entities unless enabled.
    domains = {e.domain for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert domains == {"sensor", "binary_sensor"}
    # Only queries were sent.
    assert inverter.writes == []


async def test_device_info(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = await setup(hass)
    [device] = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)
    assert device.identifiers == {(DOMAIN, SERIAL)}
    assert device.model == "VMII-4000"
    assert device.serial_number == SERIAL
    assert device.sw_version == "00040.09"


async def test_grid_lost_warning(hass: HomeAssistant, inverter: Inverter) -> None:
    inverter.table["QPIWS"] = GRID_OFF["QPIWS"]
    await setup(hass)
    warning = hass.states.get(f"binary_sensor.{PREFIX}_warning")
    assert warning.state == STATE_ON
    assert warning.attributes["warnings"] == ["line_fail"]
    assert hass.states.get(f"binary_sensor.{PREFIX}_grid_lost").state == STATE_ON


async def test_setup_retries_when_offline(hass: HomeAssistant, inverter: Inverter) -> None:
    inverter.offline = True
    entry = make_entry()
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_connection_loss_makes_entities_unavailable(
    hass: HomeAssistant, inverter: Inverter
) -> None:
    entry = await setup(hass)
    inverter.offline = True
    await entry.runtime_data.fast.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{PREFIX}_grid_voltage").state == STATE_UNAVAILABLE
    inverter.offline = False
    await entry.runtime_data.fast.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{PREFIX}_grid_voltage").state == "237.8"


async def test_unload_closes_connection(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = await setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert all(writer.closed for _, writer in inverter.gateway.connections)


# --- control entities ----------------------------------------------------------------


async def test_options_flow_enables_controls(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = await setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_FAST_INTERVAL: 20, CONF_SLOW_INTERVAL: 300, CONF_ENABLE_CONTROLS: True},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options[CONF_ENABLE_CONTROLS] is True
    assert hass.states.get(f"switch.{PREFIX}_buzzer") is not None
    select = hass.states.get(f"select.{PREFIX}_output_source_priority")
    assert select.attributes["options"] == ["sbu"]

    # Turning controls off again removes the entities from the registry.
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_FAST_INTERVAL: 20, CONF_SLOW_INTERVAL: 300, CONF_ENABLE_CONTROLS: False},
    )
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    domains = {e.domain for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert domains == {"sensor", "binary_sensor"}
    assert inverter.writes == []


async def test_switch_sends_flag_command_and_refreshes(
    hass: HomeAssistant, inverter: Inverter
) -> None:
    await setup(hass, controls=True)
    entity_id = f"switch.{PREFIX}_buzzer"
    assert hass.states.get(entity_id).state == STATE_ON
    sent_before = len(inverter.gateway.sent)
    inverter.table["QFLAG"] = "EbjvxyDakuz"  # what the inverter reports after PDa
    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    assert inverter.writes == ["PDa"]
    after = [f[:-3].decode() for f in inverter.gateway.sent[sent_before:]]
    assert after == ["PDa", "QPIRI", "QFLAG", "QPIWS"]  # slow coordinator refreshed
    assert hass.states.get(entity_id).state == STATE_OFF


async def test_switch_nak_raises(hass: HomeAssistant, inverter: Inverter) -> None:
    await setup(hass, controls=True)
    inverter.write_answer = "NAK"
    with pytest.raises(HomeAssistantError, match="rejected"):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": f"switch.{PREFIX}_auto_restart_on_overload"}, blocking=True
        )
    assert inverter.writes == ["PEu"]


async def test_select_sends_verified_code(hass: HomeAssistant, inverter: Inverter) -> None:
    await setup(hass, controls=True)
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": f"select.{PREFIX}_charger_source_priority", "option": "only_solar"},
        blocking=True,
    )
    assert inverter.writes == ["PCP02"]
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": f"select.{PREFIX}_output_source_priority", "option": "battery_first"},
            blocking=True,
        )
    assert inverter.writes == ["PCP02"]


async def test_numbers(hass: HomeAssistant, inverter: Inverter) -> None:
    await setup(hass, controls=True)
    charge = hass.states.get(f"number.{PREFIX}_max_charging_current")
    assert charge.state == "50"
    assert (charge.attributes["min"], charge.attributes["max"], charge.attributes["step"]) == (10, 80, 10)
    assert hass.states.get(f"number.{PREFIX}_back_to_utility_voltage").state == "22.0"
    assert hass.states.get(f"number.{PREFIX}_battery_float_voltage") is None  # PBFT not implemented

    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": f"number.{PREFIX}_max_charging_current", "value": 40}, blocking=True,
    )
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": f"number.{PREFIX}_max_utility_charging_current", "value": 10}, blocking=True,
    )
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": f"number.{PREFIX}_back_to_utility_voltage", "value": 23.5}, blocking=True,
    )
    assert inverter.writes == ["MCHGC040", "MUCHGC010", "PBCV23.5"]

    # Within min/max but not an allowed value / step: rejected locally, nothing sent.
    for entity, value in (("max_utility_charging_current", 4), ("back_to_utility_voltage", 22.2)):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "number", "set_value",
                {"entity_id": f"number.{PREFIX}_{entity}", "value": value}, blocking=True,
            )
    assert inverter.writes == ["MCHGC040", "MUCHGC010", "PBCV23.5"]


# --- diagnostics -----------------------------------------------------------------------


async def test_diagnostics_redacts_serial(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = await setup(hass)
    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)
    assert SERIAL not in str(result)
    assert "192.0.2.10" not in str(result)
    assert result["identity"]["model"] == "VMII-4000"
    assert result["raw_responses"]["QPIGS"] == FULL["QPIGS"]
    assert result["slow"]["data"]["rated"]["output_source_priority"] == 1
