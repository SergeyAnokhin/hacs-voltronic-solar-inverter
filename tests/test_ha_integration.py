"""Home Assistant level tests: config flow, entities, control entities, diagnostics.

Needs pytest-homeassistant-custom-component; skipped otherwise. The inverter is
replaced by a fake gateway answering from recorded fixtures (no real socket).
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from conftest import FakeGateway, answered, plain_answered
from custom_components.voltronic_solar_inverter import diagnostics
from custom_components.voltronic_solar_inverter.const import (
    CONF_FAST_INTERVAL,
    CONF_SLOW_INTERVAL,
    DOMAIN,
    MAX_MISSED_UPDATES,
)
from custom_components.voltronic_solar_inverter.protocol.client import InverterClient
from custom_components.voltronic_solar_inverter.protocol.framing import crc_bytes, encode_frame

FULL = answered("snapshot_B_night_output_on.json")
GRID_OFF = answered("snapshot_B_night_grid_off.json")
Q_EXTRA = {
    "Q1": answered("snapshot_S_night_output_off.json")["Q1"],  # charge stage 10 = idle
    "QBEQI": answered("snapshot_p46-47_01-02_p43_LBU_q.json")["QBEQI"],
}
H_S = plain_answered("probe_h_commands_S.json")
H_LBU = plain_answered("snapshot_p46-47_01-02_p43_LBU_h.json")
PLAIN = {
    "QPRTL": "HPVINV02",
    "HIMSG1": H_S["HIMSG1"],
    "HGEN": H_S["HGEN"],
    "HTEMP": H_S["HTEMP"],
    "HGRID": H_S["HGRID"],
    "HEEP1": H_LBU["HEEP1"],  # P43 = LBU
    "HEEP2": H_LBU["HEEP2"],  # P46/P47 01-02, P48/P49 23-00
}
SERIAL = FULL["QID"]
PREFIX = "inverter_vmii_4000"


def reply(payload: str) -> bytes:
    body = b"(" + payload.encode()
    return body + crc_bytes(body) + b"\r"


def frame_name(frame: bytes) -> str:
    """Command name of a sent frame (CRC frames lose 2 CRC bytes + CR, plain ones CR)."""
    plain = frame[:-1].decode("ascii", "replace")
    if plain in PLAIN or frame[:1] == b"H":
        return plain
    return frame[:-3].decode("ascii", "replace")


class Inverter:
    """Scripted inverter behind a FakeGateway. Unknown commands are silent.

    Like the real unit, Q commands answer only with a valid CRC and the H
    dialect (incl. QPRTL) only without CRC.
    """

    def __init__(self) -> None:
        self.table = {**FULL, **Q_EXTRA}
        self.plain = dict(PLAIN)
        self.write_answer = "ACK"
        self.offline = False
        self.gateway = FakeGateway(self._respond)

    def _respond(self, frame: bytes):
        if self.offline:
            return None
        plain = frame[:-1].decode("ascii", "replace")
        if plain in self.plain:
            return [b"(" + self.plain[plain].encode() + b"\r"]
        command = frame[:-3].decode("ascii", "replace")
        if encode_frame(command) != frame:
            return None
        if command.startswith("Q"):
            return [reply(self.table[command])] if command in self.table else None
        return [reply(self.write_answer)]

    @property
    def writes(self) -> list[str]:
        return [
            frame_name(f) for f in self.gateway.sent if f[:1] not in (b"Q", b"H")
        ]

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


def make_entry(minor_version: int = 2) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=minor_version,
        title="Inverter VMII-4000",
        unique_id=SERIAL,
        data={CONF_HOST: "192.0.2.10", CONF_PORT: 8899},
        options={CONF_FAST_INTERVAL: 10, CONF_SLOW_INTERVAL: 60},
    )


async def setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = make_entry()
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

    assert hass.states.get(f"sensor.{PREFIX}_grid_voltage").state == "238"  # mains voltage: whole volts
    assert hass.states.get(f"sensor.{PREFIX}_battery_voltage").state == "25.6"
    assert hass.states.get(f"sensor.{PREFIX}_mode").state == "battery"
    # Settings that have a select/number/switch are not duplicated as read-only sensors.
    for entity_id in (
        f"sensor.{PREFIX}_output_source_priority",
        f"sensor.{PREFIX}_charger_source_priority",
        f"sensor.{PREFIX}_max_charging_current",
        f"binary_sensor.{PREFIX}_buzzer",
    ):
        assert hass.states.get(entity_id) is None, entity_id
    assert hass.states.get(f"select.{PREFIX}_output_source_priority").state == "sbu"
    assert hass.states.get(f"switch.{PREFIX}_buzzer").state == STATE_ON
    assert hass.states.get(f"sensor.{PREFIX}_battery_type").state == "user_defined"
    assert hass.states.get(f"sensor.{PREFIX}_battery_type").attributes["update_group"] == "slow"
    assert "update_group" not in hass.states.get(f"sensor.{PREFIX}_battery_voltage").attributes
    assert hass.states.get(f"sensor.{PREFIX}_firmware_version").state == "00040.09"
    assert hass.states.get(f"binary_sensor.{PREFIX}_ac_output").state == STATE_ON
    assert hass.states.get(f"binary_sensor.{PREFIX}_sbu_priority").state == STATE_ON
    assert hass.states.get(f"binary_sensor.{PREFIX}_charging").state == STATE_OFF
    # a0 (PV loss) alone must not raise a warning.
    assert hass.states.get(f"binary_sensor.{PREFIX}_warning").state == STATE_OFF
    assert hass.states.get(f"binary_sensor.{PREFIX}_fault").state == STATE_OFF
    assert hass.states.get(f"binary_sensor.{PREFIX}_grid_lost").state == STATE_OFF
    # Voltage-based battery % exists but is disabled by default.
    registry = er.async_get(hass)
    estimate = registry.async_get(f"sensor.{PREFIX}_battery_level_estimate_voltage_based")
    assert estimate is not None and estimate.disabled_by is not None
    # Control entities always exist (changes are at the user's risk).
    domains = {e.domain for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert domains == {"sensor", "binary_sensor", "number", "select", "switch"}
    # Setting up sends only queries.
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
    # Short outages are ridden out: the last value stays for MAX_MISSED_UPDATES failures.
    for _ in range(MAX_MISSED_UPDATES):
        await entry.runtime_data.fast.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(f"sensor.{PREFIX}_grid_voltage").state == "238"
    await entry.runtime_data.fast.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{PREFIX}_grid_voltage").state == STATE_UNAVAILABLE
    inverter.offline = False
    await entry.runtime_data.fast.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{PREFIX}_grid_voltage").state == "238"


async def test_unknown_mode_does_not_fail_setup(hass: HomeAssistant, inverter: Inverter) -> None:
    inverter.table["QMOD"] = "X"
    entry = await setup(hass)
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get(f"sensor.{PREFIX}_mode").state == "unknown"
    assert hass.states.get(f"binary_sensor.{PREFIX}_ac_output").state == "unknown"
    assert hass.states.get(f"sensor.{PREFIX}_battery_voltage").state == "25.6"
    inverter.table["QMOD"] = "C"
    await entry.runtime_data.fast.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{PREFIX}_mode").state == "charging"
    assert hass.states.get(f"binary_sensor.{PREFIX}_ac_output").state == STATE_OFF


async def test_unload_closes_connection(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = await setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert all(writer.closed for _, writer in inverter.gateway.connections)


# --- control entities ----------------------------------------------------------------


async def test_options_flow_changes_intervals(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = await setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_FAST_INTERVAL: 2, CONF_SLOW_INTERVAL: 300}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options == {CONF_FAST_INTERVAL: 2, CONF_SLOW_INTERVAL: 300}
    assert entry.runtime_data.fast.update_interval.total_seconds() == 2
    assert hass.states.get(f"switch.{PREFIX}_buzzer") is not None
    select = hass.states.get(f"select.{PREFIX}_output_source_priority")
    assert select.attributes["options"] == ["sbu"]
    assert inverter.writes == []


async def test_switch_sends_flag_command_and_refreshes(
    hass: HomeAssistant, inverter: Inverter
) -> None:
    await setup(hass)
    entity_id = f"switch.{PREFIX}_buzzer"
    assert hass.states.get(entity_id).state == STATE_ON
    sent_before = len(inverter.gateway.sent)
    inverter.table["QFLAG"] = "EbjvxyDakuz"  # what the inverter reports after PDa
    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    assert inverter.writes == ["PDa"]
    after = [frame_name(f) for f in inverter.gateway.sent[sent_before:]]
    assert after == [  # the write, then the whole slow coordinator refresh
        "PDa", "QPIRI", "QFLAG", "QPIWS", "QBEQI", "Q1", "HEEP1", "HEEP2", "HGEN", "HTEMP",
    ]
    assert hass.states.get(entity_id).state == STATE_OFF


async def test_switch_nak_raises(hass: HomeAssistant, inverter: Inverter) -> None:
    await setup(hass)
    inverter.write_answer = "NAK"
    with pytest.raises(HomeAssistantError, match="rejected"):
        await hass.services.async_call(
            "switch", "turn_on", {"entity_id": f"switch.{PREFIX}_auto_restart_on_overload"}, blocking=True
        )
    assert inverter.writes == ["PEu"]


async def test_select_sends_verified_code(hass: HomeAssistant, inverter: Inverter) -> None:
    await setup(hass)
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
    await setup(hass)
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
    assert inverter.writes == ["MNCHGC040", "MUCHGC010", "PBCV23.5"]

    # Within min/max but not an allowed value / step: rejected locally, nothing sent.
    for entity, value in (("max_utility_charging_current", 4), ("back_to_utility_voltage", 22.2)):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                "number", "set_value",
                {"entity_id": f"number.{PREFIX}_{entity}", "value": value}, blocking=True,
            )
    assert inverter.writes == ["MNCHGC040", "MUCHGC010", "PBCV23.5"]


# --- H dialect and optional queries ----------------------------------------------


async def test_h_dialect_entities(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = await setup(hass)
    state = hass.states.get
    assert state(f"sensor.{PREFIX}_pv_energy_today").state == "1.765"
    assert state(f"sensor.{PREFIX}_pv_energy_total").state == "8.5"
    assert state(f"sensor.{PREFIX}_pv_energy_total").attributes["state_class"] == "total_increasing"
    assert state(f"sensor.{PREFIX}_ac_output_on_time").state == "23:00"
    assert state(f"sensor.{PREFIX}_ac_output_off_time").state == "00:00"
    assert state(f"sensor.{PREFIX}_ac_charger_start_time").state == "01:00"
    assert state(f"sensor.{PREFIX}_ac_charger_stop_time").state == "02:00"
    assert state(f"sensor.{PREFIX}_solar_supply_priority") is None  # the select shows it
    assert state(f"select.{PREFIX}_solar_supply_priority").state == "load_first"
    assert state(f"sensor.{PREFIX}_charge_stage").state == "idle"
    assert state(f"sensor.{PREFIX}_inverter_temperature").state == "28"
    assert state(f"sensor.{PREFIX}_transformer_temperature").state == "32"
    assert state(f"sensor.{PREFIX}_grid_power").state == "0"
    assert state(f"sensor.{PREFIX}_grid_power_raw").state == "0"
    assert state(f"sensor.{PREFIX}_battery_low_alarm_voltage").state == "22.0"
    # Equalization is read but its entities are disabled by default.
    registry = er.async_get(hass)
    for entity_id in (
        f"sensor.{PREFIX}_equalization_voltage",
        f"binary_sensor.{PREFIX}_equalization",
    ):
        assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert state(entity_id) is None
    # 21:01 inverter local time; the test time zone is US/Pacific, states are UTC
    assert state(f"sensor.{PREFIX}_inverter_clock").state == "2026-10-03T04:01:00+00:00"
    assert state(f"sensor.{PREFIX}_inverter_clock_offset").state not in (None, STATE_UNAVAILABLE)
    assert entry.runtime_data.identity.h_protocol == "HPVINV02"
    # H queries go out without CRC.
    assert b"HGEN\r" in inverter.gateway.sent
    assert inverter.writes == []


async def test_failed_h_query_only_affects_its_entities(
    hass: HomeAssistant, inverter: Inverter
) -> None:
    entry = await setup(hass)
    today = hass.states.get(f"sensor.{PREFIX}_pv_energy_today").state
    del inverter.plain["HGEN"]  # e.g. the answer got lost
    # The last value is kept for MAX_MISSED_UPDATES missed reads, then unavailable.
    for _ in range(MAX_MISSED_UPDATES):
        await entry.runtime_data.slow.async_refresh()
        await hass.async_block_till_done()
        assert hass.states.get(f"sensor.{PREFIX}_pv_energy_today").state == today
    await entry.runtime_data.slow.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{PREFIX}_pv_energy_today").state == STATE_UNAVAILABLE
    assert hass.states.get(f"sensor.{PREFIX}_ac_output_on_time").state == "23:00"
    assert hass.states.get(f"sensor.{PREFIX}_battery_type").state == "user_defined"


async def test_inverter_without_h_dialect(hass: HomeAssistant, inverter: Inverter) -> None:
    inverter.plain.clear()
    await setup(hass)
    assert hass.states.get(f"sensor.{PREFIX}_pv_energy_today") is None
    assert hass.states.get(f"sensor.{PREFIX}_grid_power") is None
    assert hass.states.get(f"sensor.{PREFIX}_grid_power_raw") is None
    assert hass.states.get(f"sensor.{PREFIX}_charge_stage").state == "idle"  # Q1 still works
    sent = [frame_name(f) for f in inverter.gateway.sent]
    assert "HGEN" not in sent and "HEEP2" not in sent  # not polled at all


async def test_select_solar_supply_priority(hass: HomeAssistant, inverter: Inverter) -> None:
    await setup(hass)
    entity_id = f"select.{PREFIX}_solar_supply_priority"
    select = hass.states.get(entity_id)
    assert select.state == "load_first"
    assert select.attributes["options"] == ["battery_first", "load_first"]
    await hass.services.async_call(
        "select", "select_option", {"entity_id": entity_id, "option": "battery_first"}, blocking=True
    )
    assert inverter.writes == ["PVENGUSE00"]


# --- live / smoothed sensors, defaults, migration ----------------------------------


def qpigs_with_pv_power(watts: int) -> str:
    fields = FULL["QPIGS"].split()
    fields[19] = f"{watts:05d}"
    return " ".join(fields)


async def test_pv_power_raw_and_smoothed(hass: HomeAssistant, inverter: Inverter) -> None:
    inverter.table["QPIGS"] = qpigs_with_pv_power(1000)
    entry = await setup(hass)
    live_id = f"sensor.{PREFIX}_pv_power_raw"
    smooth_id = f"sensor.{PREFIX}_pv_power"
    assert hass.states.get(live_id).state == "1000"
    assert hass.states.get(smooth_id).state == "1000"
    first_write = hass.states.get(smooth_id).last_reported

    async def poll(watts: int) -> None:
        inverter.table["QPIGS"] = qpigs_with_pv_power(watts)
        await entry.runtime_data.fast.async_refresh()
        await hass.async_block_till_done()

    # +4 %: the live value follows, the smoothed state is not even re-written.
    await poll(1040)
    assert hass.states.get(live_id).state == "1040"
    assert hass.states.get(smooth_id).state == "1000"
    assert hass.states.get(smooth_id).last_reported == first_write

    # Clouds: mean of 1000, 1040, 300 = 780 (-22 %) -> published.
    await poll(300)
    assert hass.states.get(live_id).state == "300"
    assert hass.states.get(smooth_id).state == "780"

    # Unavailable together with the coordinator (after the grace period), back afterwards.
    inverter.offline = True
    for _ in range(MAX_MISSED_UPDATES + 1):
        await entry.runtime_data.fast.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(smooth_id).state == STATE_UNAVAILABLE
    inverter.offline = False
    await poll(300)
    assert hass.states.get(smooth_id).state != STATE_UNAVAILABLE


async def test_pv_voltage_raw_and_smoothed(hass: HomeAssistant, inverter: Inverter) -> None:
    fields = FULL["QPIGS"].split()
    entry = await setup(hass)
    live_id = f"sensor.{PREFIX}_pv_voltage_raw"
    smooth_id = f"sensor.{PREFIX}_pv_voltage"
    start = float(hass.states.get(live_id).state)
    assert float(hass.states.get(smooth_id).state) == start

    async def poll(volts: float) -> None:
        f = list(fields)
        f[13] = f"{volts:05.1f}"
        inverter.table["QPIGS"] = " ".join(f)
        await entry.runtime_data.fast.async_refresh()
        await hass.async_block_till_done()

    # A +0.5 V wobble moves the live value only.
    await poll(start + 0.5)
    assert float(hass.states.get(live_id).state) == start + 0.5
    assert float(hass.states.get(smooth_id).state) == start

    # A real drop: the mean falls by more than the threshold and is published.
    await poll(start - 40)
    await poll(start - 40)
    assert float(hass.states.get(live_id).state) == start - 40
    assert float(hass.states.get(smooth_id).state) < start - 5


async def test_pv_power_median_and_daily_max(hass: HomeAssistant, inverter: Inverter) -> None:
    inverter.table["QPIGS"] = qpigs_with_pv_power(1000)
    entry = await setup(hass)
    median_id = f"sensor.{PREFIX}_pv_power_median_10_min"
    max_id = f"sensor.{PREFIX}_pv_power_max_today"
    assert hass.states.get(median_id).state == "1000"
    assert hass.states.get(max_id).state == "1000"
    assert hass.states.get(f"sensor.{PREFIX}_pv_power_max_10_min").state == "1000"

    for watts in (1500, 100, 900):
        inverter.table["QPIGS"] = qpigs_with_pv_power(watts)
        await entry.runtime_data.fast.async_refresh()
        await hass.async_block_till_done()
    # medians: 1250 and 1000 are published, 950 is not (< 10 % away from 1000)
    assert hass.states.get(max_id).state == "1500"
    assert hass.states.get(median_id).state == "1000"
    assert hass.states.get(f"sensor.{PREFIX}_pv_power_max_10_min").state == "1500"


async def test_daily_max_currents_and_time(hass: HomeAssistant, inverter: Inverter) -> None:
    await setup(hass)
    for key, live, unit in (
        ("pv_power_max_today", "pv_power_raw", "W"),
        ("pv_current_max_today", "pv_current", "A"),
        ("battery_charge_current_max_today", "battery_charge_current", "A"),
        ("battery_discharge_current_max_today", "battery_discharge_current", "A"),
    ):
        state = hass.states.get(f"sensor.{PREFIX}_{key}")
        assert state.state == hass.states.get(f"sensor.{PREFIX}_{live}").state, key
        assert state.attributes["unit_of_measurement"] == unit
        assert dt_util.parse_datetime(state.attributes["max_time"]) is not None, key


async def test_values_are_rounded_in_the_state(hass: HomeAssistant, inverter: Inverter) -> None:
    await setup(hass)
    # Battery side keeps one decimal, currents are whole amperes, the state itself is rounded.
    assert hass.states.get(f"sensor.{PREFIX}_battery_voltage").state == "25.6"
    for entity_id in (
        f"sensor.{PREFIX}_battery_charge_current",
        f"sensor.{PREFIX}_pv_current",
        f"sensor.{PREFIX}_ac_output_voltage",
    ):
        assert "." not in hass.states.get(entity_id).state, entity_id


async def test_static_entities_hidden_by_default(hass: HomeAssistant, inverter: Inverter) -> None:
    await setup(hass)
    registry = er.async_get(hass)
    for entity_id in (
        f"sensor.{PREFIX}_firmware_version",
        f"sensor.{PREFIX}_serial_number",
        f"sensor.{PREFIX}_rated_output_power",
        f"sensor.{PREFIX}_battery_rating_voltage",
    ):
        entity = registry.async_get(entity_id)
        assert entity.hidden_by is er.RegistryEntryHider.INTEGRATION, entity_id
        assert hass.states.get(entity_id) is not None  # still has a state
    assert registry.async_get(f"sensor.{PREFIX}_battery_type").hidden_by is None


async def test_migration_from_1_1(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = make_entry(minor_version=1)
    entry.add_to_hass(hass)
    registry = er.async_get(hass)

    def register(domain: str, key: str):
        return registry.async_get_or_create(
            domain,
            DOMAIN,
            f"{SERIAL}_{key}",
            config_entry=entry,
            suggested_object_id=f"{PREFIX}_{key}",
        )

    old_pv = register("sensor", "pv_charging_power")
    firmware = register("sensor", "firmware_version")
    eq_voltage = register("sensor", "equalization_voltage")
    serial = register("sensor", "serial_number")
    registry.async_update_entity(serial.entity_id, hidden_by=er.RegistryEntryHider.USER)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 2
    # Renamed in place (same registry entry, so the recorder keeps its history).
    assert registry.async_get(old_pv.entity_id) is None
    new_pv = registry.async_get(f"sensor.{PREFIX}_pv_power")  # the smoothed, recorded one
    assert new_pv.id == old_pv.id
    assert new_pv.unique_id == f"{SERIAL}_pv_power"
    assert registry.async_get(firmware.entity_id).hidden_by is er.RegistryEntryHider.INTEGRATION
    assert (
        registry.async_get(eq_voltage.entity_id).disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )
    # A choice the user made is kept.
    assert registry.async_get(serial.entity_id).hidden_by is er.RegistryEntryHider.USER


# --- diagnostics -----------------------------------------------------------------------


async def test_diagnostics_redacts_serial(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = await setup(hass)
    result = await diagnostics.async_get_config_entry_diagnostics(hass, entry)
    assert SERIAL not in str(result)
    assert "192.0.2.10" not in str(result)
    assert result["identity"]["model"] == "VMII-4000"
    assert result["raw_responses"]["QPIGS"] == FULL["QPIGS"]
    assert result["slow"]["data"]["rated"]["output_source_priority"] == 1
    assert result["raw_responses"]["HEEP2"] == H_LBU["HEEP2"]


async def test_own_consumption_and_balance_sensors(hass: HomeAssistant, inverter: Inverter) -> None:
    inverter.table["QPIGS"] = answered("snapshot_B_night_load_300w.json")["QPIGS"]  # 25.10 V x 15 A discharge, 317 W load
    entry = await setup(hass)
    battery_id = f"number.{PREFIX}_own_consumption_battery_mode"
    assert hass.states.get(battery_id).state == "53.0"
    assert hass.states.get(f"number.{PREFIX}_own_consumption_line_mode").state == "47.0"
    assert hass.states.get(f"number.{PREFIX}_own_consumption_output_off_standby").state == "12.0"
    assert hass.states.get(f"number.{PREFIX}_own_consumption_output_off_solar_charging").state == "34.0"
    assert hass.states.get(f"sensor.{PREFIX}_inverter_losses").state == "60"  # 59.5 W, whole watts
    # 317 W load + 53 W + 3.5 % own - 376.5 W from the battery - 3 W unseen from the grid
    assert hass.states.get(f"sensor.{PREFIX}_pv_power_calculated").state == "2"

    await hass.services.async_call(
        "number", "set_value", {"entity_id": battery_id, "value": 100}, blocking=True
    )
    assert entry.runtime_data.own_consumption["battery"] == 100
    assert inverter.writes == []  # HA-only setting, nothing sent


async def test_old_self_consumption_numbers_are_removed(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "number", DOMAIN, f"{SERIAL}_self_consumption_line_mode", config_entry=entry
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(old.entity_id) is None


async def test_pv_power_calculated_with_external_battery_sensor(
    hass: HomeAssistant, inverter: Inverter
) -> None:
    inverter.table["QPIGS"] = answered("snapshot_B_night_load_300w.json")["QPIGS"]  # 317 W load
    hass.states.async_set("sensor.bms_power", "-0.3", {"unit_of_measurement": "kW"})
    entry = await setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_FAST_INTERVAL: 10, CONF_SLOW_INTERVAL: 60, "battery_power_sensor": "sensor.bms_power"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["battery_power_sensor"] == "sensor.bms_power"
    # 317 + 50 + 3.5 % - 300 W from the BMS = 78 W of PV the inverter does not show.
    assert hass.states.get(f"sensor.{PREFIX}_pv_power_calculated").state == "78"
    # An unusable BMS state skips the sample instead of falling back to the inverter.
    hass.states.async_set("sensor.bms_power", "unavailable")
    await entry.runtime_data.fast.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{PREFIX}_pv_power_calculated").state == "78"


async def test_daily_energy_sensors(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = await setup(hass)
    for key in ("load", "grid", "battery", "balance", "pv_calculated"):
        state = hass.states.get(f"sensor.{PREFIX}_{key}_daily_energy")
        assert state.state == "0.0", key  # first sample: nothing integrated yet
        assert state.attributes["unit_of_measurement"] == "kWh"
        assert state.attributes["device_class"] == "energy"
    for key in ("battery", "balance"):  # signed
        state = hass.states.get(f"sensor.{PREFIX}_{key}_daily_energy")
        assert state.attributes["state_class"] == "total"
        assert dt_util.parse_datetime(state.attributes["last_reset"]) == dt_util.start_of_local_day()
    for key in ("load", "pv_calculated"):
        state = hass.states.get(f"sensor.{PREFIX}_{key}_daily_energy")
        assert state.attributes["state_class"] == "total_increasing", key

    # One hour later, in one step longer than the allowed gap: nothing is added.
    with patch(
        "custom_components.voltronic_solar_inverter.sensor.time",
        monotonic=lambda: time.monotonic() + 3600,
    ):
        await entry.runtime_data.fast.async_refresh()
        await hass.async_block_till_done()
    assert hass.states.get(f"sensor.{PREFIX}_load_daily_energy").state == "0.0"


async def test_daily_energy_needs_grid_power(hass: HomeAssistant, inverter: Inverter) -> None:
    inverter.plain.clear()
    await setup(hass)
    assert hass.states.get(f"sensor.{PREFIX}_load_daily_energy") is not None
    assert hass.states.get(f"sensor.{PREFIX}_battery_daily_energy") is not None
    assert hass.states.get(f"sensor.{PREFIX}_grid_daily_energy") is None
    assert hass.states.get(f"sensor.{PREFIX}_balance_daily_energy") is None


async def test_removed_sensor_is_deleted_from_registry(hass: HomeAssistant, inverter: Inverter) -> None:
    entry = make_entry()
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    old = registry.async_get_or_create(
        "sensor", DOMAIN, f"{SERIAL}_pv_power_median_today", config_entry=entry
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get(old.entity_id) is None
