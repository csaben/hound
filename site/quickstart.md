# Hound quickstart

Requirements: Windows x86_64 and Python 3.11 or newer.

```powershell
pipx install --python 3.11 "git+https://github.com/csaben/hound.git"
hound setup --json
$env:HOUND_REGISTRY_URL = "https://hound.clarksaben.com/index.json"
hound check --json
hound adapters search --json
hound adapters add notepad
hound run notepad "Write a short note" --var text="hello" --tutorial --json
```

`hound setup` downloads a pinned Foxhound release and verifies its SHA-256 digest. Hound does not
move the physical pointer, inject global keyboard input, activate the target, or allow its windows
to cover the user's foreground application.

Set `JEV_API_KEY` or `TYPESAFE_API_KEY` after adding the JEV optional dependency with
`pipx inject hound-agent "typesafe-sdk>=0.7.2"`. Set `CLEF_URL` to use a compatible CLEF endpoint.
