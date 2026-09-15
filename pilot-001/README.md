# FrostLine Benchmark V1 — prepared labelled pilot

This harness administers the frozen candidate through its existing authenticated
Express API and native browser UI. It does not solve scenarios or score outcomes.
The preparation checks exercise only a separate synthetic readiness sandbox.

## Frozen inputs and run profile

- Benchmark: `frostline-fit-benchmark-v1.0.0`, commit `57b6005599792913e17a390c48260c40d94430f6` (annotated tag object `883ee0d7caef8a3be46a4c8729ca2759a830492b`).
- Candidate: `run-001-claude-opus-5-high-001`, commit `72a924b0de17643a3cfe6d53ea85a47ba79c04c0` (annotated tag object `89cc50d0b22623019876ff18092d86b8b5451bb8`).
- Both tags resolve to their repositories' current HEAD commits. Only tagged files were extracted; mutable/untracked data was not copied.
- Benchmark baseline: `e61e7c4199aeafb0d232f8fb1f31c1eb61ec10a2`.
- Profile: operational application used by an authorised operator; optional Anthropic AI disabled.
- Label: pilot, pending recorded release approval and independent calibration.
- Scope: 27 isolated scenarios, 30 total stages; B002/B012/B019 have two stages.
- No real communications, purchases, suppliers or physical engineering. Exact sandbox instructions and observed downstream state must be recorded separately.
- Node 22+, Python 3, local copied dependencies, macOS `sandbox-exec`, Chrome and the installed Python `websocket-client` package are available. No external credential is required for this profile.

Detailed provenance, benchmark validation, source/build/dependency hashes and
runtime versions are in `admin/` and `readiness/`. Do not share either directory
with the operator/model acting as candidate. A separate operator context should
receive only the current source portal and ordinary application guidance.

## Prepared layout

```text
pilot-001/
  admin/benchmark/             pinned benchmark/docs; includes private evaluator files
  admin/                      provenance, hashes, route catalogue, private control socket
  candidate/app/              tagged app source, copied dependencies, built SPA
  scenarios/B###/
    input/stage-1/            exact exporter allowlist: docs + contract + case/task/fixtures
    baseline/                clean SQLite pre-state, adaptation log, input hashes
    attempts/<attempt>/      created only when that scenario is started
      input/                 current scenario only; later stage created on delivery
      data/                  mutable DB/uploads; never reuse for another scenario
      observations/          trace, raw HTTP, snapshots, uploads, browser/artifact evidence
      bundle-manifest.json   created only when every stage is captured and sealed
  readiness/                  preparation checks and clearly labelled synthetic smoke evidence
  assessments/independent/   reserved; no assessments created
  assessments/final/         reserved; no assessments created
  adjudication/             reserved; no rulings created
  reports/                  administration status; no candidate verdict
```

## Fixture fidelity and authority

Every initial fact and unknown is preserved verbatim in the allowlisted input
packet and in a source-labelled native inbox entry. Initial data uses the frozen
schema directly; no demo customers, jobs, stock, approvals or qualifications are
seeded. Conservative native rows are created where explicit source names and
relationships permit a partial faithful projection. The exact mapping, source
references, defaults and required placeholders are recorded per scenario.

The full packet remains authoritative. For example, the adapter does not choose
a disputed payer, reconcile ambiguous asset lineage, load reserved/customer-owned
stock as free stock, invent ticket expiry dates or infer component prices from
an inclusive quotation. Source-only delivery is an administration adaptation;
it is not a declaration that the application lacks a capability. The operator
may use normal supported representations with exact available source facts.
Document further adaptations before claiming an outcome.

Schema defaults are visible and documented but do not establish FrostLine facts.
The source inbox entry's receipt timestamp is harness delivery metadata, never a
contractual response-clock start. Relative appointments are not silently assigned
a date. The server uses the actual host clock with Europe/London timezone; event
dates, contractual periods and later business events remain exactly as supplied.
Record any mismatch affecting observation as an administration limitation.

Sandbox logins use password `frostline` and addresses `coordinator@pilot.invalid`,
`manager@pilot.invalid`, `sales@pilot.invalid`, `stores@pilot.invalid`, and
`engineer@pilot.invalid`; explicitly named engineers have their own linked test
logins. These are software duty-role translations, not extra business authority.
Only use a role for an action authorised by episode evidence. Generic accounts do
not allocate engineers to jobs or grant new competence. There is no administrator
task account. Account choice and role changes are captured in the API trace.

## Start one scenario

From the workspace parent of this repository:

```sh
python3 -B hvac-evaluation-runs/harness/pilot.py serve B001 --attempt operational-001
```

This starts a fresh runtime copied from the immutable baseline. Only one scenario
can be active. Use `http://127.0.0.1:43100/` for the app and
`http://127.0.0.1:43100/pilot/` for exact current-stage inputs. The proxy captures
native API/UI traffic; do not operate the unrecorded backend port 43101 directly.

In a separate terminal, record fidelity and context before any task mutation:

```sh
python3 -B hvac-evaluation-runs/harness/pilot.py control acknowledge --text 'Record operator identity/role, source fidelity review, training/context, tools, integration scope and assistance policy here.'
```

The harness blocks task mutations before this acknowledgement and at stage
boundaries. These are administration pauses, not evidence of candidate control.
The gate does not enforce business policy or a hidden desired outcome.

Give the exact public task and operate ordinarily. Do not coach toward rubric
checks. Answer genuine missing business questions only from established current
episode/canonical evidence; otherwise record unknown. Log setup clarification,
assistance, deviation and elapsed effort with `control note --text ...`.
Use a soft initial budget of 30 minutes per stage after fixture review, extend
with a recorded reason where needed, and apply no invented per-minute penalty.

## Supported API automation and browser use

For deterministic operator-selected actions, use the existing supported API:

```sh
python3 -B hvac-evaluation-runs/harness/operator_api.py request --email coordinator@pilot.invalid --path /api/jobs
python3 -B hvac-evaluation-runs/harness/operator_api.py replay path/to/operator-selected-actions.json
```

An action plan has an `actions` list with `email`, `method`, `path`, optional
`body`, `source_refs`, `rationale` and `save_as`. Only supported routes are allowed.
Use `{"$response":"saved-name","pointer":"/id"}` to reference a real previous
response value. `path_responses` can substitute those values into `{name}` path
tokens. No automatic policy choices, golden plans or task-specific expected
outcomes are provided. HTTP errors are retained, without silently repairing them.

Browser interaction is available on the same recorded proxy. Capture native
screens when rendering, permissions, downloads or UI workflows matter:

```sh
python3 -B hvac-evaluation-runs/harness/pilot.py browser --email coordinator@pilot.invalid --path /jobs --path /inbox
```

Browser capture creates a fresh Chrome profile, normal login, screenshots, DOM,
visible text, network events and capture policy. External resources/file URLs are
blocked and disclosed as administrator boundaries. Screenshots are read-only;
choose the account and relevant record paths matching actual operator activity.
Boundary captures default to dashboard/jobs/inbox; add exact record/report paths
and other role captures as appropriate. Read-only observation login events are
separate from business operations. Retain downloaded/native documents with:

```sh
python3 -B hvac-evaluation-runs/harness/pilot.py control capture --file path/to/document --text 'Describe the actual app output and supporting record.'
python3 -B hvac-evaluation-runs/harness/pilot.py control sandbox-event --actor 'Source-authorised actor' --source-ref B001-F5 --text 'Exact submitted external instruction and observed scope; do not invent successful downstream action.'
```

## Stage boundaries and sealing

When the operator completes or explicitly blocks, capture the exact handoff:

```sh
python3 -B hvac-evaluation-runs/harness/pilot.py control boundary --text 'Exact candidate completion/handoff or blocking explanation.' --path /jobs --path /inbox
```

The proxy pauses further task mutations, captures selected native UI and a
consistent SQLite/upload snapshot, and appends the boundary. Actual issued
instructions, commitments, costs, adverse events, reversals and continuing owners
remain in history. A justified owned wait can be a valid final state.

For B002, B012 and B019 only:

```sh
python3 -B hvac-evaluation-runs/harness/pilot.py control deliver-next
```

This invokes the frozen exporter only at the declared boundary. Stage 2 contains
only `submission-contract.md`, `event.json` and `event.md`. Delivery is logged as
a supplied source event and leaves the existing DB/history unchanged. Apply it
through candidate operation; never fabricate a completion bridge after failure.
Capture the second stage with another `boundary` command.

After every declared stage:

```sh
python3 -B hvac-evaluation-runs/harness/pilot.py control seal
python3 -B hvac-evaluation-runs/harness/pilot.py control stop
python3 -B hvac-evaluation-runs/harness/pilot.py verify-bundle path/to/attempt
```

Sealing stops the backend, retains exact source inputs/provenance, final snapshots,
raw outputs and observations, and creates a file-hash manifest and bundle hash.
Evidence files are made read-only. Missing stages cannot be sealed as complete;
harness faults mark observation invalidity and require repair/repetition. Originals
are never overwritten. Stop and start a **new attempt identifier** to reset a
scenario; start the next B### from its own baseline. Do not use the demo seeder.

## Readiness verification and future assessment

```sh
python3 -B hvac-evaluation-runs/harness/bootstrap.py
python3 -B hvac-evaluation-runs/harness/pilot.py prepare
python3 -B hvac-evaluation-runs/harness/test_administration.py
python3 -B hvac-evaluation-runs/harness/pilot.py serve SMOKE --attempt readiness-new
python3 -B hvac-evaluation-runs/harness/readiness_check.py --live
```

Bootstrap verifies/reuses pinned extractions and builds only the runtime copy.
Preparation validates the locked benchmark, exact initial allowlists, and baseline
hashes. Live readiness tests only SMOKE transport/isolation/capture/sealing and
stop that instance. Unit stage-delivery checks use synthetic administrator state,
no application/task execution. Neither is candidate evaluation or calibration.

The sealed bundle is the future shared evidence for two independent evaluators.
Do not place suggested scores or another evaluator's reasoning in it. Scoring,
comparison, adjudication and aggregation require a later assessment step and remain
unstarted. The primary benchmark contract and thresholds are unchanged. Approved
comparisons additionally require external approval/calibration records, which must
remain outside the frozen benchmark.
