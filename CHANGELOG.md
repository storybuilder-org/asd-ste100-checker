# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project aims to follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- **Part-of-speech senses are no longer collapsed.** The dictionary indexed one
  record per surface form, but 189 headwords carry more than one part of
  speech. `DictionaryEngine` now keeps every sense and resolves lookups against
  the part of speech spaCy assigns the token. This fixes four defects:
  - False negatives: an approved sense hid an unapproved one, so the unapproved
    verb in `Check the valve.` was not reported (`check` n. is approved).
  - False positives: a form listed under one part of speech was reported
    against uses in another (`cover`, `power` as nouns).
  - `STE-POS-MISMATCH` compared the observed part of speech against whichever
    sense indexed last, so `Set the switch to ON.` was flagged even though
    `set` is approved as both noun and verb.
  - Text corruption in `apply_safe_fixes`, which replaced by surface form:
    `power supply` → `supply supply`, and `in the event that` → `in the if
    that` (the `event` → `if` alternative comes from the whole phrase).
- `apply_safe_fixes` now drives replacement from spaCy tokens rather than a
  context-free regex, and only substitutes an alternative that is approved in
  the same part of speech as the word it replaces.
- Seed technical nouns reached `_index` but not the per-POS index, so a
  POS-aware lookup saw only the unapproved sense they were meant to override.
- `ste_apply_safe_fixes` returned a blanked `diff`; the diff is now returned
  and capped, and `original` (the caller's own input) is no longer echoed.
- `ste_lookup_word` / `ste100 lookup` described only one sense of a multi-sense
  headword, reporting `check` as plainly "approved" while the checker flagged
  its unapproved verb sense. Payloads for such headwords now carry a `senses`
  list; single-sense entries are unchanged.

### Changed

- Edge cases E13 and E34 were reworded. Both asserted compliance for text that
  contains a genuinely unapproved sense (`switch` as a verb → *set*; `use` as a
  noun → *operation*), which only passed because the POS-blind lookup resolved
  each form to its other, approved sense. Each case still tests its stated
  intent; `tests/test_pos_sense.py` asserts the newly-detected findings.
- Added `cover` and `power` to `seed_technical_nouns.json` (Rule 1.5).

## [1.0.0] — 2026-07-23

### Added

- Branch-vs-base mode for `ste_check_changed_files` / `ste100 check-changed`
  via `base=` / `--base` (`git merge-base HEAD <base>`).
- Packaging readiness: classifiers, typed marker, documented install path.
- Continuous edge-case gate report refresh for acceptance.

### Changed

- Declared **agent-complete, not ASD-certified**.
- Architecture / MCP / LSP documentation polish in README.
- Development status classifier → Beta.

## [0.6.0] — 2026-07-23

### Added

- HTTP/SSE (streamable) MCP transport: `ste100 serve --transport http|sse|streamable-http`
  with required `STE100_MCP_TOKEN` Bearer auth (stdio unchanged).
- Thin diagnostics LSP: `ste100 lsp` (pygls); Finding → severity/range; filetypes
  md/txt/rst/adoc; no code actions.
- Edge-case corpus `tests/edge_cases/cases.json` (E01–E20, W01–W10).
- Pytest engine harness `tests/test_edge_cases.py`.
- Skill-subagent gate prompt + `scripts/run_skill_gate.py` →
  `tests/edge_cases/gate_report.md`.

## [0.5.0] — 2026-07-23

### Added

- Tier-1–3 rules, stdio MCP (check/lookup/fixes/rewrite/semantic/changed-files/explain),
  skill, CLI, CI.

[1.0.0]: https://github.com/search?q=asd-ste100-checker
[0.6.0]: https://github.com/search?q=asd-ste100-checker
[0.5.0]: https://github.com/search?q=asd-ste100-checker
