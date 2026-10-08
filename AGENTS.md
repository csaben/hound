# Hound agent guide

Hound is a small agent-facing workflow runner. Prefer an editable adapter over core changes when a
behavior is specific to one application.

## Fast path

1. Run `hound setup --json`, then `hound check --json`.
   Read `check.drivers`; if a potentially needed driver is not ready, show its setup commands and
   ask the user to configure the secret locally. Never ask for an API key in chat. For CLEF, start
   `hound clef serve` in the background; the user signs in to Cloudflare in the browser.
2. Inspect `hound adapter-schema --json`.
3. Search a configured registry with `hound adapters search --json`.
4. Install only the adapter needed for the current OS and task.
5. Edit the installed adapter under `~/.hound/adapters` when workflow-specific knowledge is needed.
6. Run with `--tutorial` when the requested output is a narrated/captioned demonstration.

Use a `hound.chain/v1` manifest and `hound chain` when a workflow crosses application boundaries.
Keep application order explicit and keep each application's behavior in its own adapter.

## Adapter authoring budget

- Use one adapter directory per application. Create it once, then edit it in place.
- Do not create a new adapter for a tutorial step, dialog, retry, hypothesis, or diagnostic run.
- Put ordered actions, recovery choices, criteria, and captions in that one adapter.
- Use a chain only when the task crosses application boundaries, with one stage per application.
- Keep experiments in the run directory. Do not scatter generated YAML, screenshots, or scripts
  through the application repository.
- Start with the smallest end-to-end workflow. After two failed exploratory runs, inspect the
  captured frames, trace, `/windows` data, and adapter assumptions before running again.
- Do not modify Hound, Foxhound, or the application under test unless the task asks for source
  changes or the evidence proves a reusable infrastructure defect.

Foxhound treats a target application and its owned dialogs as one window group. Coordinates are
relative to the composite stage, clicks route to the window under that point, and keys route to the
topmost enabled input window. Keep modal handling in the same adapter unless the dialog belongs to
a different process that Foxhound cannot resolve as part of the group.

Hound is the harness even when no model is called. If exactly one action is valid, Hound executes it
deterministically. JEV or CLEF is used only when two or more actions are genuinely available. Zero
driver calls is the preferred fast and cheap result, not a reason to manufacture model decisions.

For a tutorial, produce one continuous Hound run or chain and one final video. Temporary diagnostic
runs are evidence, not deliverables.

## Invariants

- Do not use physical mouse or keyboard injection or steal the foreground window.
- Keep drivers (`jev`, `clef`) interchangeable; adapters describe workflows, not provider APIs.
- Keep registry URLs configurable. Do not silently contact a registry when none is configured.
- Preserve run evidence, criteria results, captions, timing, and cost metadata.
- Do not commit credentials, personal information, absolute workstation paths, or generated runs.

## Verify changes

Run `python -m pytest -q`. For backend changes, also execute a real adapter while using another
foreground application and confirm cursor, keyboard focus, foreground, and z-order are preserved.
