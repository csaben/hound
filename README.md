# Hound

Tell your agent: "Use Hound from https://hound.clarksaben.com to install the CLI, find or adapt the
right workflow for this computer, run it without taking over my mouse, keyboard, or foreground
window, and return the recording, captions, criteria results, and run summary."

Hound is a small, agent-oriented CLI and Python library for driving, inspecting, and recording an
application without taking the human's mouse, keyboard, cursor, or foreground window. On Windows it
uses [Foxhound](https://github.com/csaben/foxhound) for covered-window capture and background input.
A SystemOne decision model (JEV or CLEF) chooses one adapter-defined action per step.

[![Hound terminal-to-Notepad chain demo](public/hound-terminal-notepad-demo.gif)](public/hound-terminal-notepad-demo.mp4)

The embedded demo starts with the actual `hound chain` command, cuts to Notepad, types the note in
the background, burns action captions, and produces one 1280x720 H.264 tutorial. Click the GIF for
the full-resolution MP4. The validated run used no model calls because every stage had one
unambiguous next action.

Hound deliberately does not contain a general UI agent, publishing service, fixture laboratory, or
video-production suite. Its contract is: editable adapters, at most one model call per decision,
executable criteria, and a reviewable run folder.

## Install and check

```powershell
pipx install --python 3.11 "git+https://github.com/csaben/hound.git"
hound setup --json
hound check --json
```

Hound requires Python 3.11 or newer. Add the optional JEV driver with
`pipx inject hound-agent "typesafe-sdk>=0.7.2"`; CLEF uses the core installation.

`hound setup` downloads the pinned Windows x86_64 helper from the public Foxhound release, verifies
its SHA-256 digest, and caches it under `HOUND_HOME`. The first run also performs this bootstrap when
the helper is missing. Set `FOXHOUND_HELPER` to use a local binary, or set both
`HOUND_FOXHOUND_URL` and `HOUND_FOXHOUND_SHA256` to use another trusted build.

Set `JEV_API_KEY`/`TYPESAFE_API_KEY` for JEV, or `CLEF_URL` for a SystemOne-compatible CLEF
endpoint. `FOXHOUND_HELPER` can point at a helper binary outside the adjacent Foxhound checkout.

## Agent happy path

```powershell
hound adapters search notepad --json
hound adapters add notepad
hound adapters path notepad
hound run notepad "Write a short note" --var text="Hounds are excellent." --tutorial --json
```

An adapter can always be run directly from its directory:

```powershell
hound run .\examples\notepad "Type a greeting into a new note" --var text="hello" --no-record
```

Core discovery commands:

```text
hound check
hound setup
hound adapter-schema
hound chain CHAIN.yaml
hound adapters list
hound adapters search [QUERY]
hound adapters add NAME
hound adapters info NAME
hound adapters path NAME
hound run ADAPTER [GOAL]
```

Every command accepts `--json` before the subcommand. Installed adapters are ordinary editable files
under `~/.hound/adapters`; Hound never silently overwrites them.

## Adapter

The smallest adapter is one `adapter.yaml`:

```yaml
schema: hound.adapter/v1
name: notepad
platforms: {windows: {backend: foxhound}}

target:
  backend: foxhound
  process: notepad.exe
  launch: [notepad.exe]

driver:
  default: jev
  allowed: [jev, clef]
  image_policy: always

workflow:
  goal: Type the requested text into a new note.
  guidance:
    - Select the editor before typing.
  actions:
    - id: select_editor
      op: click
      x: 400
      y: 300
      description: Select the document editor.
      caption: Select the editor
    - id: type_text
      after: select_editor
      op: type
      text: "{{ text }}"
      description: Type the requested text.
      caption: Type the requested text
      terminal: true
  done:
    after_action: type_text
  criteria:
    - id: app_alive
      expect: Notepad remains open.
      check: builtin.target_alive
  source_refs:
    - path: src/editor.ts
      purpose: Editor behavior for an adapter-authoring agent
```

Values supplied by `--var key=value` replace `{{ key }}` in the manifest. `hooks.py` is optional and
can provide `reset(context)`, custom completion checks, criteria, or actions. Run
`hound adapter-schema --json` for the machine-readable contract.

## Evidence

Each run writes:

```text
~/.hound/runs/<adapter>/<timestamp>/
  run.json
  trace.jsonl
  recording.mp4       # when ffmpeg is installed
  captions.vtt
  captioned.mp4       # when ffmpeg has subtitle support
  shots/
```

The recorder continuously captures the Foxhound-owned window. Action events and captions share the
same run-relative clock. Hound records the physical cursor and foreground window around each action
for auditability, but does not treat human activity as a failure. The user is expected to keep using
the computer. Non-interruption is enforced structurally: Hound exposes only Foxhound's posted input
API and never calls physical mouse, keyboard, or foreground-window APIs.

## Registry

Hound is registry-agnostic and does not contact an owner-controlled service by default. Configure any
compatible static registry with `HOUND_REGISTRY_URL`, or pass `--registry PATH_OR_URL` to an adapter
command. `registry/index.json` is a local example and intentionally uses a non-resolving repository
URL so it cannot be mistaken for an endorsed service.

Search results are filtered for the current operating system and backend before installation. An
adapter is cloned selectively into the local adapter directory, stripped of its internal `.git`, and
left editable. `hound.lock` records its origin and starting revision.

```powershell
$env:HOUND_REGISTRY_URL = "https://registry.example.org/index.json"
hound adapters search
```

## Python SDK

```python
from hound import Hound, RunOptions

result = Hound("notepad", driver="jev").run(
    "Write a short note",
    RunOptions(variables={"text": "hello"}, record=True, tutorial=True),
)
print(result.success, result.run_dir)
```

The CLI calls this API; there is no separate CLI orchestration implementation.

## Multi-application chains

`hound chain` runs ordered adapter stages while keeping each app's workflow, criteria, and evidence
separate. It then normalizes the captioned stage clips to one canvas and joins them with focus cuts.
Only the current adapter's actions are considered, so adding applications does not inflate every
driver prompt.

```powershell
hound chain .\examples\terminal-notepad-chain.yaml --tutorial --json
```

```yaml
schema: hound.chain/v1
name: terminal-to-notepad
stages:
  - id: terminal
    adapter: terminal-demo
  - id: notepad
    adapter: notepad
    variables:
      text: "Hound can move between applications."
recording:
  layout: focus
```

The chain run contains `chain.json`, a `stages/` directory with each adapter's complete evidence,
and `tutorial.mp4`. A failed stage stops the chain unless it declares `continue_on_failure: true`.
Actions are executed directly when exactly one choice is valid; JEV or CLEF is called only when a
real decision is required.

## Benchmarks

### cblur Face and Object Blur

Measured 2026-10-05 on this Windows workstation after the editable cblur adapter had been created.
The workflow launches an isolated portable OBS instance, opens the talking-head fixture, adds cblur
Face and Object Blur, waits five seconds for visible inference, closes the dialog, records the owned
window, and renders a captioned H.264 MP4.

| Measurement | JEV | CLEF | CLEF Flash |
| --- | ---: | ---: | ---: |
| Result | pass, 9 actions | pass, 9 actions | pass, 9 actions |
| End-to-end, including MP4 and burned captions | 21.014 s | 24.918 s | 24.076 s |
| OBS + private Foxhound helper startup | 4.479 s | 4.859 s | 5.032 s |
| Workflow complete, before media post-processing | 18.470 s | 22.050 s | 21.290 s |
| Intentional face-inference wait | 5.000 s | 5.000 s | 5.000 s |
| Driver calls | 9 | 9 | 9 |
| Combined driver latency | 1.976 s | 6.253 s | 5.223 s |
| Median driver latency | 192.7 ms | 594.1 ms | 484.3 ms |
| Input/output tokens | 7,819 / 279 | 6,746 / 0 | 6,754 / 0 |
| Estimated direct inference cost | $0.000328 | $0.001619 | $0.000608 |
| Recording/caption post-processing | 2.544 s | 2.868 s | 2.786 s |
| Captioned artifact | 14.0 s, 1172×1080, 715 KB | 17.4 s, 1172×1080, 814 KB | 16.4 s, 1172×1080, 814 KB |

The cost calculation uses TypeSafe AI's $0.042/M JEV direct-input rate and Cloudflare's published
$0.24/M CLEF and $0.09/M CLEF Flash input rates as checked on the benchmark date
([TypeSafe pricing](https://typesafe-ai.com/), [Cloudflare pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/)).
Pricing can change. `HOUND_JEV_INPUT_USD_PER_M` and `HOUND_CLEF_INPUT_USD_PER_M` override the
assumption recorded by Hound. Each `run.json.metrics` records the selected model, usage, price,
estimated cost, and timing. CLEF's output is a probability distribution and is not billed or
reported as generated output tokens here.

During adapter development, nine recorded Hound validation runs made 76 JEV calls. Only the final
instrumented run retained exact usage; extrapolating its 869 input tokens/call gives approximately
66,000 input tokens, or **$0.0028** at the same direct rate. This is explicitly an estimate. It does
not include Codex development usage, which Hound cannot observe, or any cblur cloud-provider usage;
one rejected exploratory run briefly selected Screen Guard, so that external allowance impact is
unknown rather than claimed to be zero.

Each benchmark's machine-readable timing and cost data is retained in its `run.json` artifact.

### What the first real adapter exposed

| Observation | Infra shortcoming or unavoidable delay? | Result / next step |
| --- | --- | --- |
| The existing Foxhound release executable predated source support for `--pid`. | Packaging/version-skew shortcoming. | Built current Foxhound in Hound's isolated target. Add a helper protocol/version handshake before distributing Hound. |
| `/health` could return OK while the requested app had no resolvable window yet. | Hound readiness bug. | Fixed: startup now waits for a non-null target with an adapter-configurable timeout. |
| Modern Notepad handed off from its launcher PID. | Windows application invariant. | Fixed generically: diff process IDs across launch, target the unique new PID, and clean up only owned PIDs. |
| Qt placed a filter popup relative to the human's physical cursor even though Hound never moved it. | Toolkit invariant that defeats fixed stage coordinates. | Adapter hook now resolves the popup window dynamically. A generic window-relative action should replace this hook. |
| A list of keys meant a chord, while the workflow needed a sequence. | Hound action-schema ambiguity. | Fixed with explicit `sequence: true`; document separate chord/sequence operations in a future schema revision. |
| A startup prompt produced one 422×123 frame before the 1171×1079 main stage. | Recorder bug caused by normal startup timing. | Fixed: the recorder discards smaller startup-stage frames when the real stage appears and pads odd dimensions for H.264. |
| Static adapter actions were all offered at every step. | Token and correctness shortcoming. | Fixed with `after` prerequisites and one-shot actions; the model now sees only currently valid choices. |
| CLEF rejects a one-option `choice`, while a prerequisite-driven workflow often has exactly one valid next action. | Cross-provider contract mismatch. | Hound adds an explicit `__hound_stop__` safety alternative for CLEF. Both CLEF variants selected the workflow action in all nine measured decisions. |
| A native 1171×1079 screenshot was estimated at 280,779 multimodal tokens, exceeding CLEF's 65,536-token context. | Hound image-budget shortcoming exposed by a provider invariant. | Fixed: CLEF inputs are bounded to a 448×448 JPEG before upload. This should become an adapter-configurable image policy if fine UI text must be read. |
| Wrangler's remote AI binding logged transient internal-error references around otherwise successful CLEF requests. | Cloud-provider/dev-relay variability, not desktop delay. | The measured calls still returned 200 and needed no Hound retries. Production use should call the REST endpoint directly and add bounded retry telemetry. |
| OBS startup consumed 4.479 s. | Normal application/plugin initialization. | Do not optimize in Hound unless warm-instance reuse becomes a requirement. |
| Face inference deliberately consumed 5 s. | Product settling delay, currently encoded conservatively. | Replace the fixed wait with a visual/truth readiness predicate when adapters gain observable waits. |
| ffmpeg consumed 2.481 s after workflow completion. | Expected local media work. | It can be asynchronous if CLI latency matters more than immediate artifact availability. |
| Early runs passed `target_alive` and `dialog_closed` even when the intended filter was not added. | Important evidence-contract shortcoming. | The run was rejected by visual inspection, but Hound still needs per-action postconditions and first-class visual/truth criteria before `success` alone can support bug claims. |

The last row is the main remaining limitation: the current result is a trustworthy recorded demo
because its final output was reviewed, but Hound's minimal built-in criteria are not yet sufficient
for unattended product verdicts. Adapters can implement truth hooks today; the core should next add
action postconditions and a driver-independent visual-check interface.
