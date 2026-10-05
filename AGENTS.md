# Hound agent guide

Hound is a small agent-facing workflow runner. Prefer an editable adapter over core changes when a
behavior is specific to one application.

## Fast path

1. Run `hound setup --json`, then `hound check --json`.
2. Inspect `hound adapter-schema --json`.
3. Search a configured registry with `hound adapters search --json`.
4. Install only the adapter needed for the current OS and task.
5. Edit the installed adapter under `~/.hound/adapters` when workflow-specific knowledge is needed.
6. Run with `--tutorial` when the requested output is a narrated/captioned demonstration.

## Invariants

- Do not use physical mouse or keyboard injection or steal the foreground window.
- Keep drivers (`jev`, `clef`) interchangeable; adapters describe workflows, not provider APIs.
- Keep registry URLs configurable. Do not silently contact a registry when none is configured.
- Preserve run evidence, criteria results, captions, timing, and cost metadata.
- Do not commit credentials, personal information, absolute workstation paths, or generated runs.

## Verify changes

Run `python -m pytest -q`. For backend changes, also execute a real adapter while using another
foreground application and confirm cursor, keyboard focus, foreground, and z-order are preserved.
