- **Machine-readable agent records (#322).** Every record under
  `docs/agent/` — decisions, assessments, reviews, plans, prompts, and
  handovers — now opens with uniform YAML frontmatter (`type`, `status`,
  `date`, `summary`, optional `issue` and supersession links), documented in
  `docs/README.md`. The new `scripts/validate_agent_docs.py` (pre-commit and
  CI) enforces the schema, a closed status vocabulary per record type,
  existing supersession targets, archive placement for finished handovers,
  and agreement between a body status bullet and the frontmatter; it replaces
  the bold-bullet ADR check in `scripts/validate_prose_status.py`. The
  delivered issue-278 handover moved to the archive, the completed 2026-07-16
  remediation plan no longer says to resume it, and every prompt is marked
  retired.
