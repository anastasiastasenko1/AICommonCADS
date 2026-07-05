# apprentice

**A tacit-knowledge elicitation harness.** Wraps the assistant you already use,
learns how you actually work — from the context you volunteer, the corrections
you make, and a few well-chosen questions — and consolidates it into a knowledge
model *you own*, which later compiles into synthetic environments for training
specialised agents.

Built on forty years of knowledge-acquisition research (CommonKADS, Critical
Decision Method, repertory grids), one principle above all: **people are poor
rule-authors but excellent critics.**

## Install

```bash
pip install -e .            # CLI core
pip install -e ".[mcp]"     # + MCP adapter for Claude Code / Cowork / claude.ai
```

## Five-minute start

```bash
export ANTHROPIC_API_KEY=...        # or point config at any OpenAI-compatible endpoint

apprentice init --owner marie@example.com
apprentice new nda_triage --type assessment --description "Triage incoming NDAs"
apprentice interview nda_triage            # 10-min LLM-led bootstrap interview
apprentice consolidate                     # fold the interview into the model

# daily life — the correction loop:
apprentice observe nda_triage --draft claude_draft.md --final what_i_sent.md
apprentice ask nda_triage                  # ≤3 questions/day, only if worth asking
apprentice answer nda_triage q-a1b2c3d4 "we always escalate competitors"

apprentice consolidate                     # nightly (cron it)
apprentice status                          # yield %, convergence, coverage
apprentice review nda_triage               # audit every assertion + provenance
apprentice compile nda_triage              # → environment_spec.yaml
```

## Wire into Claude

`apprentice serve` starts an MCP server (stdio). Add to Claude Code:

```bash
claude mcp add apprentice -- apprentice serve
```

Then install the skill in `skills/apprentice/` so the assistant recalls your
knowledge model at task start, logs corrections, and asks its one budgeted
question at task end — never mid-flow.

## Design in one paragraph

Everything lives in plain files under `~/.apprentice` (or `./.apprentice`):
`model.yaml` is the CommonKADS-lite knowledge model with confidence and
provenance on every assertion; `episodes.jsonl` is the append-only raw
evidence; `questions.yaml` is the budgeted queue with yield tracking. Episodes
only become knowledge through the offline `consolidate` pass (LLM-backed,
model-agnostic — a frontier model bootstraps, a small specialised model can
take over). When question yield drops, the workflow is marked converged and
the apprentice goes quiet. `compile` turns a converged model into an
environment spec: scenario generator weighted by the elicited exception
distribution, checkers from quality criteria, real episodes held out for
sim-to-real validation only.

## Privacy contract

Local files, employee-owned, human-readable. Nothing leaves the machine except
the LLM calls you configure. No log mining, no telemetry. Deletion is honoured
at the next consolidate and compile. Team aggregation is an explicit,
provenance-credited push — never automatic.

See `SPEC.md` for the full specification.
