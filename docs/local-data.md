# Local Data: Analysing the Owner's Home Assistant History

To check a sensor or a hypothesis against real history (not the live inverter), the owner copies Home Assistant's recorder database and a dashboard into `local_data/` at the repository root. The folder is git-ignored (`/local_data/*` in [`.gitignore`](../.gitignore)) and never leaves the machine. [`tools/ha_history.py`](../tools/ha_history.py) opens the database **read-only** and exports entity history as CSV. This is the safe way to analyse days of data without querying the inverter (see AGENTS.md section 0).

## What to copy into `local_data/`

| File | Where it comes from | Why |
|---|---|---|
| `home-assistant_v2.db` | HA config folder (`/config/home-assistant_v2.db`), via Samba / SSH / File editor, or from a full backup (`homeassistant.tar.gz` → `data/home-assistant_v2.db`) | The history itself (SQLite, recorder schema 53 at the time of writing) |
| `home-assistant_v2.db-wal` (if present) | Same folder, copied **together** with the `.db` | Holds the last minutes not yet merged into the `.db`. Without it the copy simply ends a little earlier |
| `ui-*.yaml` (optional) | Dashboard → ⋮ → Edit → ⋮ → Raw configuration editor → copy | Tells the agent which entity IDs the owner looks at (e.g. `sensor.vevor_elfin_pv_power`) |

A copy taken while HA runs is usually readable; if SQLite reports `database disk image is malformed`, copy again from a backup or stop HA for the copy. Example: on 2026-10-06 the file was 1.3 GB.

## What the database holds

```text
states            every state change, ~10 days (recorder purge_keep_days)   -> "states" command
statistics        hourly mean/min/max (or state/sum for energy), kept forever -> "stats" command
statistics_short_term   5-minute version of the same, ~10 days               -> "stats --short"
```

- Raw states: tables `states` + `states_meta` (entity ID) + `state_attributes`. Time column `last_updated_ts` (Unix seconds, UTC).
- Statistics only exist for sensors with a `state_class`: `mean`/`min`/`max` for measurements (W, V, A, °C), `state`/`sum` for energy counters (`sum` = growing total since HA first saw the sensor, survives daily resets).
- Integration entities: `sensor.vevor_elfin_*`, `binary_sensor.vevor_elfin_*`, … (prefix = device name the owner gave). Older names with prefix `0_obogrevatel_vevor_elfin_` are entities that got renamed later; their history stops at the rename. `sensor.vevor_4k_*` belong to the previous integration (Solar Assistant style), `sensor.glceenergy25v100a_*` to the battery BMS, `sensor.zha_din_solar_inverter_ac_input_*` to the external meter on the inverter's AC input.

## Using `tools/ha_history.py`

Times are local time of the machine that runs the script (same zone as HA here). `--to` is exclusive.

```bash
# which entities have history, how much, and since when
python tools/ha_history.py list "%vevor_elfin%"

# raw state changes of one or more entities
python tools/ha_history.py states sensor.vevor_elfin_pv_power sensor.vevor_elfin_mode --from 2026-10-06T08:00 --to 2026-10-06T20:00 --csv local_data/pv.csv

# hourly mean/min/max (or state/sum for energy); --short for 5-minute rows
python tools/ha_history.py stats sensor.vevor_elfin_pv_power --from 2026-10-01
python tools/ha_history.py stats sensor.vevor_elfin_pv_daily_energy --short --from 2026-10-06
```

Other database: `--db path/to/file.db`. Write outputs into `local_data/` too, so they stay out of git. States are text (`unavailable`, `unknown`, `on`/`off` appear as-is); convert to numbers in the analysis step.

## Rules

- Read-only: the script opens the file with `mode=ro`; never modify, vacuum or commit the database.
- The history is the owner's private data: no copying outside `local_data/` or the session scratchpad, no publishing.
- Values from the database are not test fixtures: tests still use recorded raw inverter responses in `tests/fixtures/`.
