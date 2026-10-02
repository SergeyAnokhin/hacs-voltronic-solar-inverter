---
name: update-docs
description: Update project documentation after changes. Updates markdown docs in the docs/ directory and README.md to reflect recent work. Also patches any gaps that slowed down code search earlier in the session.
---

# Update Documentation

This skill updates project docs after a chat session that added or changed code.

## What to do

### 1. Identify what changed this session

Look at the conversation and git diff to find:
- New files created or renamed
- New or changed entities (sensors, binary sensors), inverter commands/fields parsed, modules, data models
- Architecture changes (data flow, new integrations, changed interfaces)
- New configuration keys (config flow options, `manifest.json`, `hacs.json`)
- New user wishes, decisions, or findings about the inverter (go to `docs/project-overview.md` / `docs/inverter-protocol.md`)

### 2. Bootstrap missing docs (if they don't exist yet)

**`README.md`** - the public GitHub page of the HACS integration. If missing, create it with:
- One-paragraph project description and supported hardware
- HACS install steps, configuration (config flow), list of entities
- Limitations (e.g. read-only)
- Documentation table (links to `docs/*.md`)

**`docs/code-map.md`** - if missing, create it: a table of every non-trivial file with a one-line description and its role. Purpose: let a reader find the right file to edit without grepping.

### 3. Update affected docs

**`docs/code-map.md`** - for any new, renamed, or repurposed file: add or update its row.

**Other docs in `docs/`** - update the doc that covers the area you changed:
- New/changed entity or parsed field -> `docs/inverter-protocol.md` (field map) and the entity list in `README.md`
- New config key -> `README.md` configuration section
- Inverter capability/setting facts -> `docs/inverter-vevor-gd5548jmh.md`
- User wishes, decisions, roadmap -> `docs/project-overview.md`
- New subsystem -> relevant architecture doc

**Create a new `docs/<topic>.md`** if a changed area has no doc yet and warrants one: 3+ files involved, non-obvious data flow, or an area where future edits require upfront context. Do not create a doc for a single-function fix or UI tweak.

**`README.md`** and **`docs/README.md`** - add any newly created doc to the Documentation tables.

### 4. Fix search gaps (always do this)

Look back at the beginning of this session: what was hard to find?
- Had to grep for something that should be in a doc
- A file wasn't in code-map at all
- Had to read source to learn what a function returns or what a config key does

For each gap: add the missing fact to the relevant doc - 1-3 sentences or a table row. Do not rewrite accurate sections.

### 5. Documentation quality rules

**Compression:** docs must be far smaller than the code they describe - aim for a 5-10x ratio. A doc is a navigation aid, not a transcript of the code.

**What to include:** file paths with links, data flow at a high level, non-obvious decisions, schema tables, key config values.

**What to omit:** implementation details readable from the source, parameter-by-parameter descriptions, anything that would need updating every commit.

**Format:** tables for schemas/config/file maps, short ASCII flows for request paths, relative file links (`../custom_components/...`). Match existing style.

**Language:** all docs are written in English.

**After editing:** verify every file path in the doc actually exists. Do not update `AGENTS.md` or `CLAUDE.md` with code facts. Never document or edit the reference example integrations in `custom_components/` (official HA examples) other than listing them in the code map.
