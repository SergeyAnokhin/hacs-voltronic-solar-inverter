# Code Map

Where to find things. `custom_components/` contains only this integration (the Home Assistant example integrations were removed on 2026-10-02 so HACS installs the right folder).

## Project files

| Path | Role |
|---|---|
| [`AGENTS.md`](../AGENTS.md) | Rules for AI agents (read-only inverter rule, docs workflow, testing, language) |
| [`CLAUDE.md`](../CLAUDE.md) | One-line import of `AGENTS.md` for Claude Code |
| [`README.md`](../README.md) | Public GitHub page (HACS install, config, entities) |
| [`.claude/skills/update-docs/SKILL.md`](../.claude/skills/update-docs/SKILL.md) | Skill: sync docs after changes |
| [`.claude/skills/session-retro/SKILL.md`](../.claude/skills/session-retro/SKILL.md) | Skill: end-of-session retrospective |
| [`python_scripts/get_inverter_info.py`](../python_scripts/get_inverter_info.py) | Working prototype: queries the inverter over TCP and prints JSON; source of the protocol knowledge in [inverter-protocol.md](inverter-protocol.md) |
| [`tools/probe_inverter.py`](../tools/probe_inverter.py) | Read-only diagnostic: verbose timed queries, legacy vs stream strategy, CRC check, `--save` raw responses, `--extra` to probe more `Q` commands, `--no-crc` for the Solar Plug dialect. Refuses everything except `Q…` and an exact allow-list of 14 owner-approved read-only `H…` queries |
| [`tools/quick_check.py`](../tools/quick_check.py) | Read-only health check in ~1 s: `QMOD` + `QPIGS` on one connection, prints mode and key live values, exit code 0/1 |
| [`tests/fixtures/`](../tests/fixtures/) | Raw responses recorded from the real inverter; contain the device serial number. `probe_run1.json` (first full set), `probe_extra*.json` / `probe_candidates.json` (discovery of extra `Q` commands, incl. silent ones), `probe_nocrc.json` / `probe_qprtl.json` (CRC vs no-CRC), `probe_h_commands_S.json` / `probe_h_variants.json` / `probe_heep2_schedule_23-00.json`, `snapshot_p46-47_01-02_p43_LBU_*.json` (Solar Plug H-protocol, setting deltas), `snapshot_*.json` (state-change snapshots: schedule, load, grid off/on, modes B/L/S) |
| [`esphome/`](../esphome/) | ESPHome configs for an ESP32 + MAX3232 on the RS232 port: `vevor-inverter.yaml` (native, core `pipsolar`, read-only), `packages/vevor-controls.yaml` (opt-in writes), `vevor-bridge.yaml` (RS232↔TCP bridge on 8899 for this integration), `secrets.yaml.example`. See [esphome.md](esphome.md) (firmware) and [esphome-hardware.md](esphome-hardware.md) (build guide) |
| [`docs/images/`](images/) | SVG diagrams: `esphome-wiring.svg` (ESP32–MAX3232–inverter wiring), `rj45-pinout.svg` (RJ45 pin numbers, colours, known pinouts) |
| [`hacs.json`](../hacs.json) | HACS metadata (name, minimum HA 2025.8) |
| [`custom_components/voltronic_solar_inverter/`](../custom_components/voltronic_solar_inverter/) | The integration (domain `voltronic_solar_inverter`); per-file roles in [integration.md](integration.md#files) |
| [`…/manifest.json`](../custom_components/voltronic_solar_inverter/manifest.json) | Version, `config_flow`, `iot_class: local_polling`, `integration_type: device`, no requirements |
| [`…/protocol/framing.py`](../custom_components/voltronic_solar_inverter/protocol/framing.py) | CRC-16/XMODEM with 0x28/0x0D/0x0A escaping, frame encode/decode |
| [`…/protocol/client.py`](../custom_components/voltronic_solar_inverter/protocol/client.py) | `InverterClient`: async TCP, lock, timeout/retry/reconnect, `query()` (Q only) / `write()` (ACK/NAK), typed `read_*` helpers |
| [`…/protocol/h_parsers.py`](../custom_components/voltronic_solar_inverter/protocol/h_parsers.py) | Parsers for the CRC-less H dialect: `HGEN` (clock, PV energy), `HEEP1`/`HEEP2` (P43, schedules, thresholds), `HTEMP`, `HGRID`, `HIMSG1` |
| [`…/protocol/parsers.py`](../custom_components/voltronic_solar_inverter/protocol/parsers.py) | Response dataclasses and parsers; enum code tables incl. the `*_VERIFIED` priority codes; QPIWS bit table |
| [`…/protocol/commands.py`](../custom_components/voltronic_solar_inverter/protocol/commands.py) | **All** setting commands (validated builders), 24 V voltage ranges, `QUERY_RE` |
| [`…/protocol/errors.py`](../custom_components/voltronic_solar_inverter/protocol/errors.py) | Exception hierarchy (`InverterError` …) |
| [`…/smoothing.py`](../custom_components/voltronic_solar_inverter/smoothing.py) | `SmoothedValue` (mean or median over a window, publishes only significant changes) and `DailyMax`; no HA imports |
| [`…/coordinator.py`](../custom_components/voltronic_solar_inverter/coordinator.py), [`entity.py`](../custom_components/voltronic_solar_inverter/entity.py) | Fast/slow coordinators, runtime data; base entity and the single write path |
| `…/sensor.py`, `binary_sensor.py`, `switch.py`, `select.py`, `number.py` | Entity platforms (descriptions with `value_fn`) |
| `…/config_flow.py`, `diagnostics.py`, `strings.json`, `translations/en.json`, `icons.json` | Config/options flow, redacted diagnostics, UI text (en only), icons |
| [`tests/conftest.py`](../tests/conftest.py) | Fixture loaders and `FakeGateway` (fake transport; no socket) |
| `tests/test_framing.py`, `test_parsers.py`, `test_h_parsers.py`, `test_commands.py`, `test_client.py`, `test_smoothing.py` | Tests without HA (plain pytest); `test_h_parsers.py` covers H dialect, `Q1`, `QBEQI`; `test_smoothing.py` the publish rules |
| [`tests/test_ha_integration.py`](../tests/test_ha_integration.py) | HA tests (config flow, entities, controls, diagnostics); skipped without `pytest-homeassistant-custom-component` |
| [`pytest.ini`](../pytest.ini), [`requirements_test.txt`](../requirements_test.txt) | Test configuration and dependencies |
| [`docs/`](README.md) | Living documentation index |

## Unrelated files

| Path | What it is |
|---|---|
| [`python_scripts/counter.py`](../python_scripts/counter.py), [`count_people_home.py`](../python_scripts/count_people_home.py) | Unrelated HA `python_script` examples |
