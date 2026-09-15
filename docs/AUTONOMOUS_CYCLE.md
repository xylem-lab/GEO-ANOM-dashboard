# GEO-ANOM Task 1 — Autonomous Cycle Runbook

Added 2026-09-15. This is the entry point for running the three-agent
research/experiment/teach cycle, whether triggered on a schedule or on demand.
Read this before running a cycle; read `docs/NEXT_SESSION.md` for current
project state.

## Why three agents, not one

One session doing research, implementation, and reporting back to back tends
to blur the lines between "I found a paper that says this should work" and "I
verified this actually works on our data" — exactly the failure mode this
project has hit before (see the working-style notes on self-reported numbers
vs. real ground truth). Splitting into three roles with different tool access
and different hard rules forces the verification step to actually happen
instead of being skipped under time pressure:

- **`geo-anom-researcher`** — investigates one gap, proposes experiments with
  testable, ground-truth-based success criteria. No code, no git.
- **`geo-anom-experimenter`** — implements exactly one proposed experiment on
  a feature branch, validates it against real external ground truth, opens a
  PR. Never merges, never touches `main` directly.
- **`geo-anom-teacher`** — turns the cycle into a plain-language explanation
  for the user, updates `docs/NEXT_SESSION.md`, checks for contradictions
  with prior claims, and ends with open questions the user needs to decide.

Definitions live in `.claude/agents/`.

## Scope guardrail (applies to every cycle)

Task 1's goal, as of 2026-09-15: **every poultry, dairy, swine, beef, and
lagoon AFO mapped** in Maryland. Poultry-house detection and lagoon detection
already have working (if imperfect — see `docs/NEXT_SESSION.md`) pipelines;
dairy/swine/beef detection does not exist yet and is genuinely new research,
not a known transfer of the poultry U-Net.

Do not start on the unpermitted-farm search (`temporal-cluster-matching`) or
any other Task Tracker item as part of an autonomous cycle — that requires a
direct, in-session instruction from the user, per this project's history of
that item being explicitly deferred.

## Compute/funding guardrail (applies to every cycle)

Default: this laptop (CPU/MPS, no CUDA). If a cycle's experimenter step
identifies a genuine need for more (a larger training run, GPU hours, a paid
dataset, a UMD Zaratan allocation), it stops and reports the specific need
instead of provisioning anything. Acquiring compute or spending funding is
always a decision the user makes explicitly, in chat — never assume a prior
approval covers it.

## Git guardrail (applies to every cycle)

Every code change happens on an `experiment/<slug>-<date>` branch with a PR
opened against `main` for the user to review and merge. No direct commits to
`main` from an autonomous cycle, no force-push, no auto-merge. This replaces
the previous pattern of committing straight to `main`.

## One cycle, step by step

1. **Orient**: read the top (most recent dated section) of
   `docs/NEXT_SESSION.md`, the last few entries of `docs/research_log.md`,
   and relevant project memory. Confirm nothing contradicts what you're about
   to do before starting.
2. **Research** (`geo-anom-researcher`): pick the single highest-value open
   gap (coordinate gap, lagoon full-scale precision, or — now in scope — a
   dairy/swine/beef detection approach that doesn't exist yet). Append
   findings and a ranked experiment proposal to `docs/research_log.md`.
3. **Experiment** (`geo-anom-experimenter`): implement the top-ranked
   proposal on a feature branch, validate against real ground truth, open a
   PR. If it turns out to need more compute/data than the laptop has, stop
   and report that instead of forcing it through.
4. **Teach** (`geo-anom-teacher`): explain what happened in plain language,
   prepend a dated section to `docs/NEXT_SESSION.md`, flag any contradiction
   with prior "closed" claims, and end with concrete questions for the user
   (including any compute/dataset ask from step 3).
5. **Stop.** A cycle ends with an open PR awaiting review and a report to the
   user — never with a merge, a deployment, or a second cycle chained on
   automatically.

## Self-correction between cycles

Before believing anything in `docs/NEXT_SESSION.md`, memory, or the research
log is still true, check it against the current code/data rather than citing
it as fact — this project's own history (the lagoon registration bug, the
filter recalibration) shows results that looked "closed" needed revisiting
more than once. When a cycle finds a prior claim was wrong, the teacher step
must say so explicitly in the next `NEXT_SESSION.md` section, not silently
build around it.
