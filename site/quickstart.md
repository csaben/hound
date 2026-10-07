# Hound quickstart

Requirements: Windows x86_64 and Python 3.11 or newer.

```powershell
uv tool install "hound-agent @ git+https://github.com/csaben/hound.git"
hound codex install
hound setup --json
$env:HOUND_REGISTRY_URL = "https://hound.clarksaben.com/index.json"
hound check --json
hound adapters search --json
hound adapters add notepad
hound run notepad "Write a short note" --var text="hello" --tutorial --json
```

Read the `drivers` object returned by `hound check`. It reports whether JEV and CLEF are ready and
provides exact setup instructions. Do not ask a user to paste an API key into chat; have them set it
in their local environment. Drivers are optional for deterministic steps with one valid action.

To make the preference repository-local as well, run `hound codex install --agents` from the
repository root. Remove both managed integrations later with `hound codex remove --agents`, then
remove the executable with `uv tool uninstall hound-agent`. Hound refuses to overwrite or remove
an unowned skill directory and touches only its marked block in `AGENTS.md`.

For a multi-application tutorial:

```powershell
hound chain .\examples\terminal-notepad-chain.yaml --tutorial --json
```

Use one adapter per application and edit it in place. Do not create separate adapters for steps,
dialogs, retries, or diagnostics. Foxhound already treats owned dialogs as part of the application's
window group. Use a chain only for different applications and produce one final tutorial video.

When only one workflow action is valid, Hound executes it deterministically and does not call JEV
or CLEF. `driver_calls: 0` is the intended fastest and cheapest path, not a failure to use Hound.
After two failed exploratory runs, inspect the existing run evidence and revise the same adapter.

`hound setup` downloads a pinned Foxhound release and verifies its SHA-256 digest. Hound does not
move the physical pointer, inject global keyboard input, activate the target, or allow its windows
to cover the user's foreground application.

Set `JEV_API_KEY` or `TYPESAFE_API_KEY` after adding the JEV optional dependency with
`uv tool install --force --with "typesafe-sdk>=0.7.2" "hound-agent @ git+https://github.com/csaben/hound.git"`.
Set `CLEF_URL` to use a compatible CLEF endpoint.
