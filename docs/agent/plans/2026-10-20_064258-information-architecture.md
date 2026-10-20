---
type: plan
status: active
date: 2026-10-20
summary: 'Information-architecture overhaul: lean always-on context, indexed agent records, generated indexes, and mechanical documentation gates.'
issue: 322
---

# Information Architecture Overhaul Implementation Plan

> **For the implementing agent:** Execute one phase per pull request, each
> referencing [issue #322](https://github.com/hoelzl/termverify/issues/322).
> Phases are ordered by dependency; do not start a phase before its
> predecessor has merged. Each PR gets a fresh-context adversarial review
> before merge. GitHub is the source of truth for which phases have merged —
> this plan does not track progress.

**Goal:** Make the repository cheaper and safer for coding agents to navigate.
Always-loaded context becomes a small, stable map. On-demand knowledge becomes
indexed, uniformly described, and free of volatile project state. Derived
navigation is generated rather than hand-maintained. Documentation conventions
are enforced by gates instead of prose.

**Scope:** documentation, documentation tooling under `scripts/`, its tests,
pre-commit, and the CI `docs-contract` job. No change to `src/termverify/`
behavior, the public API, or any wire protocol.

---

## 1. Sources and principles

The plan applies four external sources:

- OpenAI, [*Harness engineering*](https://openai.com/index/harness-engineering/).
  `AGENTS.md` is a ~100-line table of contents, not an encyclopedia. Design
  docs are catalogued and indexed with their verification status. Plans are
  split into active and completed. Generated material is kept apart from the
  docs it is derived from. Linters and CI keep the knowledge base current and
  cross-linked. A recurring doc-gardening pass opens fix-up PRs. Lint
  messages carry remediation instructions.
- OpenAI, [*Unrolling the Codex agent loop*](https://openai.com/index/unrolling-the-codex-agent-loop/).
  `AGENTS.md` files are concatenated from the project root down to the
  working directory, subject to a 32 KiB default limit. Prompt caching needs
  an identical prefix, so always-on instructions must be stable.
- Anthropic, [*Effective context engineering for AI agents*](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents).
  The instruction set should be the smallest one that works, at the right
  altitude. Retrieve just in time via lightweight identifiers (paths,
  links). File names and folder structure are signals.
- Anthropic, [*Equipping agents for the real world with Agent Skills*](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills).
  Disclosure happens in three levels: metadata, body, linked files. Keep
  mutually exclusive contexts in separate files. State whether a bundled
  script is meant to be run or read.

From these, the repository adopts four tiers. Tier 1 is always-on. Tier 2 is
retrieved on demand. Tier 3 is self-reporting: commands, gates, and tools.
Tier 4 is derived and regenerable. Each fact lives in the cheapest tier that
works.

## 2. Baseline findings (audit of `e58ef2c`)

Strengths to preserve:

- `AGENTS.md` is already map-like (82 lines, about 1.7k tokens).
- `AGENTS.md` has a source-of-truth table, the executable-over-prose rule,
  and an explicit repair direction.
- `CLAUDE.md` is a thin harness adapter.
- `docs/knowledge/` is a navigation-only OKF index with enforced frontmatter.
- `scripts/validate_prose_status.py` checks prose claims against shipped
  registry sizes.
- `tests/test_readme_capability_truth.py` keeps README capability claims
  honest.
- Changelog fragments; a site publication boundary that excludes
  `docs/agent/`; every relative Markdown link resolves.

Defects to repair:

1. **Tier 1 is heavier than it needs to be.**
   - "Start Here" makes the agent read `README.md` (9 KB) and the knowledge
     index on every task.
   - Several sections are only needed for specific tasks: GitHub Copilot
     Surfaces (a copy of a vendor support matrix), Agent-Harness
     Compatibility, and the two long protocol-authority rows.
   - The validation block is eight commands of prose rather than one entry
     point.
   - The placement table lists `skills/`, which does not exist.
2. **Durable knowledge pages carry volatile status.**
   - Phase and handover state: `protocol.md` opening and `architecture.md`.
   - Slice progress and issue numbers: `product-vision.md` and
     `architecture.md`.
   - Dated review or configuration claims: `evidence-governance.md` and
     `schema-publication.md`.
   - The knowledge index calls the implemented protocol "planned".
3. **No indexes outside handovers and prompts.**
   - `docs/agent/design/` (20 ADRs) has none.
   - `reviews/` and `plans/` READMEs describe conventions but do not list
     their files.
   - There is no `docs/` root map and no developer-guide index.
4. **Metadata is not machine-readable.**
   - ADR status lives in a bold bullet, and four ADRs have none.
   - Nothing records supersession.
   - Review frontmatter has three shapes; prompts and plans have none.
   - One handover status ("implementation candidate") is outside its
     vocabulary.
5. **Superseded records still read as current.**
   - `terminal-adapter-dependency-decision.md`: core decision reversed.
   - `phase-1-protocol-and-windows-boundary.md`: still pins `pywinpty`.
   - `jsonl-control-transport.md`: its enumeration was superseded by
     `control-protocol.md`.
   - The 2026-07-16 remediation plan still says "Resume with Slice 6".
   - An active ADR cites the removed `src/termverify/conpty.py`.
6. **Copy-pasted content.**
   - Identical rename banners (#218, #268) in six records.
   - The validation block in four files.
   - The Python-version claim, the OKF rule, and the context-budget reading
     path in two files each.
7. **Large pages without internal navigation.**
   - `protocol.md` is 36 KB, with the key-encoding registry embedded in it.
   - The active pre-release handover is 58 KB.
8. **Misfiled records.**
   - The two model-named 2026-07-16 reviews live under `design/`.
   - Phase-1 prompts are presented as current.
   - The repository layout in `development.md` is stale.
9. **Gates cover only knowledge frontmatter and ADR status words.**
   - Nothing checks index completeness, backticked repo paths, the Tier-1
     size, or freshness.
   - The link check (`mkdocs --strict`) runs only at Pages deploy and skips
     `docs/agent/`.
10. **No skills, although several procedures are proven.** These include the
    handover lifecycle, adversarial review, changelog fragments, release
    cutting, and worktree setup.

## 3. Decisions taken for this initiative

These resolve open questions in favour of stability and the smallest
reversible change.

- **Design-record paths stay stable.** Source docstrings and tests cite
  `docs/agent/design/*.md`. Superseded ADRs are therefore marked in
  frontmatter and in the generated index, not moved into an archive folder.
  Older reviews filed under `design/` stay there too, as `reviews/README.md`
  already directs.
- **Only handovers have an archive folder.** Plans and prompts record their
  lifecycle in frontmatter status, which the generated index displays.
- **Generated indexes are committed Tier-4 files.** Each carries a
  "GENERATED — do not edit" header that names the regeneration command.
  `--check` mode runs in pre-commit and in the CI `docs-contract` job.
- **`protocol.md` is split into `docs/knowledge/protocol/`.** The new
  `index.md` publishes at the same site URL under mkdocs' directory URLs.
  Anchors move to the new topic pages. All in-repo references are updated
  in the same PR.
- **No nested `AGENTS.md` files.** Claude Code does not read nested
  `AGENTS.md`, and the repository is harness-neutral by policy. Directory-
  specific guidance lives in indexes and skills instead.
- **Skills live in `.agents/skills/<name>/SKILL.md`.** This is the
  harness-neutral location read by Codex and Copilot. Each skill links to its
  developer-guide page rather than duplicating it.
- **Records keep their text.** Historical records (ADRs, reviews, archived
  handovers) receive frontmatter and supersession pointers. Their body is
  edited only to repair dead paths or links, never to re-argue history.

## 4. Phases

Every phase ends with the full gate passing (`scripts/check.py --full` once
Phase 1 lands) and a changelog fragment `changelog.d/322-<slug>.changed.md`.

### Phase 1 — Lean Tier 1

- Rewrite `AGENTS.md` as a map within a gated 4 KB budget.
  - Make reading conditional on the task.
  - Keep the source-of-truth table with short rows.
  - Keep the non-negotiable rules.
  - Point to one check command.
  - Shrink the placement table to a pointer to `docs/README.md`.
- Move Copilot surfaces and harness compatibility into
  `docs/developer-guide/agent-harnesses.md`.
- Add `scripts/check.py` as the single gate entry point: pre-commit hooks by
  default, plus the pre-push stage with coverage under `--full`. Its
  docstring says it is meant to be run.
- Add a Tier-1 size budget to `scripts/validate_prose_status.py`, applied to
  `AGENTS.md` and `CLAUDE.md`. Its failure message says what to move out and
  where.
- Add `docs/README.md`: the documentation map and placement rules (hand
  written, short).

### Phase 2 — Uniform metadata for `docs/agent/`

- Define the frontmatter schema in `docs/README.md`:
  - required: `type`, `status`, `date`, `summary`;
  - optional: `issue`, `supersedes`, `superseded_by`, `review_by`.
- Define one status vocabulary per record *type*, and the types each folder
  may hold:
  - `decision` (`design/`): proposed, accepted, superseded, rejected;
  - `assessment` (`design/`): current, superseded;
  - `review` (`reviews/`, older reports also `design/`): findings, resolved;
  - `plan` (`plans/`): active, completed, abandoned;
  - `prompt` (`prompts/`): current, retired;
  - `handover` (`handovers/`): draft, active, blocked, complete, superseded.
- Add `scripts/validate_agent_docs.py` with tests. It fails when:
  - frontmatter is missing or invalid;
  - the status is outside the type vocabulary, or the type is outside the
    folder;
  - `superseded` lacks `superseded_by`, or a supersession target is missing;
  - a finished handover sits outside `handovers/archive/`, or an unfinished
    record inside an `archive/` folder;
  - a body `- **Status:**` bullet disagrees with the frontmatter (except in
    reviews and superseded records, whose bullets are history).
- Retire the bold-bullet status check in `validate_prose_status.py` in favour
  of the new validator.
- Convert every record. Mark the completed plan and the retired prompts, and
  archive the delivered issue-278 handover.
- *Revised during implementation:* move nothing else. `reviews/README.md`
  keeps older reports under `design/` where other documents link to them,
  and the generated index (Phase 3) shows each record's status, so archive
  folders for plans and prompts would only churn links. No ADR turned out to
  be fully superseded; the amended ones say so in their summary.

### Phase 3 — Generated indexes (Tier 4)

- Add `scripts/build_doc_indexes.py` (`--check`), which generates:
  - `docs/agent/design/index.md`: title, status, date, summary, successor;
  - `docs/agent/reviews/index.md`;
  - `docs/agent/plans/index.md`;
  - `docs/agent/prompts/index.md`;
  - `docs/agent/handovers/index.md`;
  - `docs/developer-guide/index.md`.
- Each file states that it is generated and names its command. Folder
  conventions stay in each folder's hand-written `README.md`.
- Gate it: pre-commit hook plus CI `docs-contract`. The index must list
  every record.

### Phase 4 — Knowledge-page hygiene

- Remove phase, handover, slice, issue-number, and dated-review status from
  the six knowledge pages. State contracts timelessly; status routes to
  GitHub, handovers, and the changelog.
- Fix the stale "planned" wording in the knowledge index.
- Add `docs/knowledge/glossary.md` with the historical-name table (#218,
  #268) and the core vocabulary. Replace the six rename banners with a
  one-line pointer.
- Split `protocol.md` into `docs/knowledge/protocol/` with topic pages and a
  navigation-only `index.md`. Move the key-encoding registry to its own page.
  Update `validate_prose_status.py` claim sites, source docstrings, tests,
  and the site build.
- Add a short "At a glance" section to `control-protocol.md` and
  `evidence-governance.md`.

### Phase 5 — De-duplicate human-facing docs

- `docs/developer-guide/development.md` becomes the only home for commands,
  supported Python versions, and repository layout. `README.md` and
  `CONTRIBUTING.md` link to it.
- Keep the OKF rule only in `docs/knowledge/index.md` and the reading order
  only in `AGENTS.md`. Update `agent-workflow.md` "Context budget".
- Merge README "Design principles" with the AGENTS engineering rules: one
  home, one pointer. Keep `tests/test_readme_capability_truth.py` passing,
  updating it if its anchors move.

### Phase 6 — Mechanical gates and doc gardening

- Add `scripts/check_doc_references.py` with tests. It checks:
  - relative Markdown links and anchors;
  - backticked repo-relative paths in all Markdown, including `docs/agent/`.
- Archived records may opt out per path via an allowlist that states the
  reason.
- Enforce `review_by` on knowledge pages and active handovers, and fail once
  it has passed. Add a size budget for active handovers that points to
  archiving completed phases.
- Add the gates to pre-commit and CI `docs-contract`.
- Document the doc-gardening procedure, packaged as a skill in Phase 7.

### Phase 7 — Skills

Add `.agents/skills/` with:

- `doc-gardening`;
- `changelog-fragment`;
- `handover-lifecycle`;
- `adversarial-review`;
- `cut-release`;
- `parallel-worktree`.

Each skill has a precise `description` and links to its developer-guide page
instead of copying it. Update the placement row and `development.md`.
Shorten the AGENTS worktree paragraph to a pointer.

## 5. Risks and constraints

- `tests/test_readme_capability_truth.py` pins README and product-vision
  structure. Phases 4 and 5 must keep it green or update it deliberately.
- `tests/test_site_publication.py` and `scripts/build_site.py` define the
  publication boundary. New `docs/README.md` and generated indexes must not
  leak `docs/agent/` content to the site.
- Published URLs for knowledge pages change only for protocol anchors.
- Branch protection requires all CI contexts and strict up-to-date branches.
  Rebase before merge.

## 6. Completion criteria

- `AGENTS.md` fits its gated budget.
- Every `docs/agent/` record validates and appears in a generated index.
- No knowledge page contains phase or handover status.
- The reference checker passes over all Markdown.
- The skills exist and are linked.
- Mark this plan `completed` and move it to `plans/archive/`.
