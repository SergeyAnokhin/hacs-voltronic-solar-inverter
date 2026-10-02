# AGENTS.md

Behavioral guidelines for AI agents working in this repository (a Home Assistant / HACS custom integration for Voltronic-compatible solar inverters, e.g. Vevor GD5548JMH). Keep them strict, practical, and minimal. These rules apply to **every** task, every session.

## 0. Hard Safety Rule: the live inverter is READ-ONLY for the agent

- **Never send any command that changes inverter state or settings to the real device.** This includes all setter commands (`PO…`, `PF`, `PCP`, `PGR`, `PBT`, `POP`, `PSDV`, `MUCHGC`, `MCHGC`, `PE…`/`PD…`, `PBCV`, `PBDV`, `PCVV`, `PBFT`, `DAT`, `F50`/`F60`, reset, power on/off, etc.) and anything not on the allow-list below.
- Allowed on the live device: **query commands only** (names starting with `Q`, e.g. `QPIGS`, `QPIRI`, `QPIWS`, `QMOD`, `QFLAG`, `QID`, `QVFW`). Probing for *new* `Q…` commands is allowed only one at a time, and only if the user asked for protocol research. The gateway serves one client: query only as often as needed.
- **Write code exists** (owner's decision, 2026-10-02): setting commands are built and validated in [`protocol/commands.py`](custom_components/voltronic_solar_inverter/protocol/commands.py) and exposed by switch/select/number entities that are **created only when the owner turns on the "Enable control entities" option (default off)**. The agent may change this code and its tests when asked, but tests use a fake transport only (`tests/conftest.py` `FakeGateway`); a write command is never sent to the real inverter by the agent. **Only the owner tests writes on the real device.**
- Do not add new write commands, or publish setting values marked unverified, without the owner's explicit request in chat.
- Never run the live inverter code in a loop/flood; keep a pause between commands (the integration uses 0.1 s on one persistent connection; the prototype uses 0.3 s).

## 1. Before Coding

- Do not assume unclear requirements.
- State assumptions when they matter.
- If multiple interpretations are plausible, surface them instead of picking silently.
- If the simpler solution is sufficient, use it.
- If something important is unclear or risky, stop and ask.

For multi-step work, define a short verification-driven plan:

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

## 2. During Changes

- Make the smallest change that fully solves the task.
- Do not add features, abstractions, or configurability that were not requested.
- Match the local style of the file you are editing (for HA code: follow patterns of the reference integrations in `custom_components/`).
- Do not refactor adjacent code unless the task requires it.
- Remove only the unused code created by your own change.
- If you notice unrelated problems, mention them instead of fixing them opportunistically.

Every changed line should trace directly to the request.

## 3. Documentation Workflow

Before any non-trivial task:

1. Read [`README.md`](README.md).
2. Read [`docs/README.md`](docs/README.md) (index) and then only the doc(s) relevant to the area you are changing — [`docs/code-map.md`](docs/code-map.md) first to locate files.

Do not read the whole repo or the large reference integrations when a doc already answers the question.

### Reference material (do not edit)

- `custom_components/<example_*|hello_world*|expose_service_*|mqtt_basic_*|detailed_hello_world_push>` — official Home Assistant example integrations, kept only as patterns. **Never modify them**; read them only when you need a pattern (config flow, coordinator, sensor platform, manifest).
- `python_scripts/get_inverter_info.py` — the working prototype that talks to the inverter; the source of truth for the protocol details currently used. `counter.py` and `count_people_home.py` are unrelated HA examples.
- The vendor PDF manual has been distilled into [`docs/inverter-vevor-gd5548jmh.md`](docs/inverter-vevor-gd5548jmh.md); use that instead of the PDF.

### Update docs when behavior or structure changes

**This is mandatory, not optional — `docs/` must always reflect current behavior, even for small changes.** Use the `update-docs` skill at the end of any task that changed code, config, or structure.

Update the relevant doc whenever you change documented architecture or behavior, including:

- public APIs and entities (sensor names, units, attributes)
- data formats or protocol parsing
- configuration (config flow options, `manifest.json`, `hacs.json`)
- major user or developer workflows

Also record **user wishes and decisions** (what the user asked for, what was decided, open questions) in [`docs/project-overview.md`](docs/project-overview.md) so the next session does not need to ask again.

If docs and code disagree:

- trust code for current behavior
- update docs in the same change
- mention the mismatch in the final note

### Doc format

- **All documentation, code comments, commit messages, and UI strings are written in English.**
- Start with a one-paragraph overview.
- Link to concrete files with relative paths.
- Use tables for schema, config, or file maps when helpful.
- Use short ASCII flow diagrams when helpful.
- Document what exists now, not what was once planned (planned work goes in the "Open items / roadmap" section of `docs/project-overview.md`).
- `README.md` is the public GitHub page: keep it accurate for end users (what it is, supported hardware, HACS install, configuration, entities, limitations) and update it whenever user-visible behavior changes.

## 4. Testing

After every code change, run tests or the most relevant validation available.

Rules:

- Run the smallest relevant test or validation that gives confidence in the change.
- If the repository defines multiple test suites, run the ones affected by the change.
- When in doubt, run everything.
- If you intentionally change documented behavior, update the code, the docs, and the tests together when applicable.
- Add tests for non-trivial logic that is easy to regress — especially protocol parsing (CRC, response splitting, field mapping, status-bit decoding). Test parsers against **recorded sample responses**, never against the live inverter.
- Do not add tests for trivial code.
- A task is not complete while required tests are failing.
- Test suite: `pytest` (see `README.md` "Development" for how to run it). Protocol tests (`tests/test_framing.py`, `test_parsers.py`, `test_commands.py`, `test_client.py`) need only `pytest`; `tests/test_ha_integration.py` needs `pytest-homeassistant-custom-component` and is skipped without it.

### Manual / Visual Verification

- There is no emulator. The real inverter is reachable through an Elfin RS232↔TCP gateway (address in `python_scripts/get_inverter_info.py`); only **read-only `Q` queries** may be sent to it (see section 0).
- Prefer recorded raw responses saved under a fixtures directory (`tests/fixtures/`) over hitting the device repeatedly. If no fixtures exist yet for the area you are testing, say so rather than fabricating sample data.
- Never leave shared fixture data modified, renamed, or deleted after a verification pass.

## 5. Project-Specific Guidance

- Target platform: Home Assistant custom integration installable through HACS. The integration domain must be a valid Python identifier (`voltronic_solar_inverter`, underscores — not hyphens); layout `custom_components/<domain>/` + root `hacs.json`.
- Follow current Home Assistant conventions: config flow, `DataUpdateCoordinator`, `async` I/O (no blocking sockets in the event loop), `unique_id`s, device registry, proper `device_class` / `state_class` / units for sensors.
- Read entities are sensors / binary sensors. Control entities (switch/select/number) exist but are only set up when the "Enable control entities" option is on (see section 0).
- Keep protocol logic (framing, CRC, parsing) separate from Home Assistant glue so it can be unit-tested without HA.

## 6. Language

- Chat replies, progress updates, and final summaries to the user: **Russian**, unless the user asks otherwise.
- Everything written into the repository (docs, code, comments, commits, UI strings, translations): **English only**. The integration ships a single English UI; do not add other languages unless asked.
