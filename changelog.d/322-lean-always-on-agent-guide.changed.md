- **Leaner always-on agent guide (#322).** `AGENTS.md` is now a task-indexed
  map within a gated byte budget: reading is conditional on the task instead
  of always starting with `README.md`; harness portability rules and the
  GitHub Copilot surface decision moved to
  `docs/developer-guide/agent-harnesses.md`; documentation placement rules
  moved to the new `docs/README.md` map; and the eight-command validation
  block is replaced by `scripts/check.py`, the single gate entry point
  (`--full` before a push, `--list` to print the commands).
  `scripts/validate_prose_status.py` now fails when `AGENTS.md` or
  `CLAUDE.md` outgrows its always-on budget.
