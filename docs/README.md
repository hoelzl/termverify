# Documentation Map

This is the entry point to everything under `docs/` and the canonical home of
the documentation placement rules. `AGENTS.md` points here instead of
repeating them.

## Where things live

| Document kind | Location | Published on termverify.dev |
| --- | --- | --- |
| Human-facing introduction and quick start | `README.md` | yes (landing page) |
| Durable architecture, protocol, terminology, and verification knowledge | [`docs/knowledge/`](knowledge/index.md) (OKF bundle) | yes |
| Developer guides and operating workflows | [`docs/developer-guide/`](developer-guide/) | yes |
| Architecture decision records (ADRs) and reuse assessments | [`docs/agent/design/`](agent/design/) | no |
| Handovers for initiatives that cross an ownership or phase boundary | [`docs/agent/handovers/`](agent/handovers/index.md) | no |
| Implementation plans for accepted initiatives | [`docs/agent/plans/`](agent/plans/README.md) | no |
| Adversarial and independent review reports | [`docs/agent/reviews/`](agent/reviews/README.md) | no |
| Starting prompts for worktree agents | [`docs/agent/prompts/`](agent/prompts/README.md) | no |
| Pending changelog entries | [`changelog.d/`](../changelog.d/README.md) | no |
| Reusable agent procedures (skills) | `.agents/skills/` — only once a workflow is proven and stable; none yet | no |

Choose the location by the *kind* of information, never by the task that
produced it. One fact has one home; other documents link to it rather than
copying it.

## Placement rules

- **Durable, not volatile.** Documents state contracts, decisions, and
  procedures. Volatile state — which phase is active, which issue is open,
  what was merged last — belongs to GitHub issues and pull requests, Git, and
  the changelog. A document that needs a volatile fact names the command or
  page that reports it.
- **Records are historical.** ADRs, reviews, and archived handovers record
  what was decided or found at the time. Correct them only to repair dead
  links or paths, or to mark supersession; record a changed decision in a new
  or amended record.
- **Knowledge pages are timeless.** `docs/knowledge/` follows OKF:
  `index.md` files are navigation-only, and every other page has YAML
  frontmatter with at least a non-empty `type`
  (`scripts/validate_knowledge_frontmatter.py` enforces it).
- **Repository, not harness.** Decisions, plans, handovers, and workflow rules
  are written here, never only to a harness's private memory, state
  directory, or session context. See
  [agent harnesses](developer-guide/agent-harnesses.md).
- **Agent records carry metadata.** Every record under `docs/agent/` opens
  with the frontmatter below (`scripts/validate_agent_docs.py` enforces it).
- **Not published:** `docs/agent/` never reaches the site; the build rewrites
  links into it to GitHub URLs (`scripts/build_site.py`).

## Agent-record metadata

Every Markdown file under `docs/agent/` except `README.md` and `index.md`
opens with YAML frontmatter:

```yaml
---
type: decision          # decision | assessment | review | plan | prompt | handover
status: accepted        # closed vocabulary per type, below
date: 2026-07-19        # when the record was made or decided
summary: One line that says what the record decides or finds.
issue: 146              # optional
supersedes: [docs/agent/design/old.md]       # optional, repository-relative
superseded_by: docs/agent/design/new.md      # required when status is superseded
---
```

| Type | Folder | Statuses |
| --- | --- | --- |
| `decision` | `design/` | proposed, accepted, superseded, rejected |
| `assessment` | `design/` | current, superseded |
| `review` | `reviews/` (older reports also in `design/`) | findings, resolved |
| `plan` | `plans/` | active, completed, abandoned |
| `prompt` | `prompts/` | current, retired |
| `handover` | `handovers/` | draft, active, blocked, complete, superseded |

Unknown keys are rejected; older review reports may also keep their
`scope`, `rounds`, `verdicts`, and `subject` keys. Quote any value that
contains `#` or `:` — YAML otherwise truncates it at ` #` without warning,
and the validator rejects that form.

The frontmatter status is the living status. Records keep their historical
text: a superseded decision's body still says what was accepted at the time,
and a review's body is never rewritten. Finished handovers move to
`handovers/archive/`; a decision amended in place stays where it is and
says so in its summary. Paths cited by source code stay stable, so decisions are never moved.
