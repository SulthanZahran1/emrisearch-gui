# emrisearch-gui

A proper GUI for [verasha/emrisearch](https://github.com/verasha/emrisearch): inspect EMRI search runs without writing Python.

## What this is

Companion app, not a fork. Upstream (verasha/emrisearch) is an actively developed WIP library for EMRI (extreme mass ratio inspiral) search with LISA. This repo builds a GUI around its run outputs (`manifest.json` + `sampler_state.pkl` + plots), so researchers can browse, compare, and understand runs without `load_run` + matplotlib.

## Delivery rule

- Work on a branch in its own worktree, commit atomically, push, open a PR, merge.
- Commit + push without asking.
- Subagents implement; the parent orchestrates and verifies.

## Wayfinding

The wayfinder map lives on GitHub issues (label `wayfinder:map`). See `docs/agents/issue-tracker.md` for conventions and `docs/agents/domain.md` for the domain glossary and verified facts.
