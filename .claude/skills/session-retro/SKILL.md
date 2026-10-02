---
name: session-retro
description: End-of-session retrospective for AI-assisted (vibe-coding) work. Reviews the just-finished chat for friction - slow searches, ambiguity, rework, wasted tokens - and fixes the systemic causes (doc gaps, oversized/tangled files, missing tests around non-trivial or paid-external-API code) so future sessions on this repo are faster and cheaper. Run manually after a chat that made substantial changes.
---

# Session Retrospective

This skill does not fix the task you just finished - that's done. It looks back at
*how* the session went and improves the repository so the **next** AI-assisted session
on a similar area is faster and cheaper (less search, less back-and-forth, less rework).

Never scope the fix to "the one thing that went wrong in this chat." Ask: what
underlying gap made that possible, and would it bite the next session too?

## Step 1 - Sync documentation

Invoke the `update-docs` skill (Skill tool, skill: `update-docs`) to bring
`README.md`, `docs/code-map.md`, and other docs up to date with what changed this
session. That skill already handles "what's new" and "what was hard to find" -
don't duplicate its logic here.

## Step 2 - Mine this session for friction

Reread the conversation (not just the final diff) and list concrete friction points,
each with a root cause. Look for:

- **Rediscovery cost**: had to grep/read multiple files to learn something that
  should have been one doc lookup or one obvious file name.
- **Ambiguity that caused guessing or backtracking**: unclear conventions, unstated
  assumptions, a requirement that got reinterpreted mid-task.
- **Repeated trial-and-error**: failed commands, wrong assumptions about APIs/tools,
  config that wasn't discoverable.
- **Large, tangled files**: any file you had to read in full or partially just to
  find the few lines relevant to the task, because responsibilities were mixed.
- **Risky code with no safety net**: non-trivial logic - especially calls to
  external paid services (request building, response parsing, format conversion) -
  that has no tests, so correctness relied on manual inspection or lucky guessing.

For each item, write one line: *what happened -> why it happened -> what class of
future session it would also slow down.* Discard anything that's a one-off,
task-specific detail with no recurrence risk.

## Step 3 - Fix what's clear-cut

Apply directly, without asking, when the fix is small, safe, and unambiguous:

- Add a missing fact, table row, or file-map entry to the relevant `docs/*.md`.
- Add a short note documenting a convention that had to be inferred (e.g. "config
  keys live in X", "external API responses are normalized in Y before storage").
- Add tests for non-trivial logic that was touched this session and has no
  coverage, in particular anything that builds requests to, or parses responses
  from, external paid services - mock the external call, never hit the real
  service in tests.

Match existing test framework/conventions already used in the repo; don't
introduce a new one.

## Step 4 - Propose what's not clear-cut

For anything with real blast radius or a judgment call - splitting a large file
into smaller ones, restructuring a module's responsibilities, changing a public
interface, picking a testing approach where none exists yet - do not do it
silently. Either:

- Ask the user directly (AskUserQuestion) with the concrete tradeoff, or
- Summarize the proposal in your final report as a recommendation, and wait for
  confirmation before touching the code.

A file being "large" is only worth flagging if it mixes distinct responsibilities
that could be split along a natural seam and doing so would have made *this*
session's search/edit faster. Don't propose a split just because a file is long.

When you do split a file, keep behavior identical - it's a move/reorganize, not a
rewrite - and run the relevant tests before and after to prove nothing broke.

## Step 5 - Report

End with a short summary (not a new doc, not a persisted log):

- Friction points found this session (from Step 2), one line each.
- What was fixed automatically (Step 3) - docs touched, tests added.
- What's proposed and pending confirmation (Step 4).

Keep it tight enough to read in 30 seconds. This is a retrospective, not an audit
report.

Write this final report in Russian, regardless of what language the rest of the
session was conducted in. This applies only to the Step 5 report text itself -
code, comments, docs, and everything else this skill touches stay in whatever
language the project already uses.
