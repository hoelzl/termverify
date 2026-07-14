# OpenWiki and OKF Policy

## OKF: adopt now, narrowly

TermVerify uses OKF v0.1 for `docs/knowledge/`, not for every document in the repository. The fit is strong: durable, cross-linked design knowledge benefits from frontmatter, stable concept paths, and progressive-disclosure indexes.

This keeps ordinary contributor documentation simple while allowing agents to retrieve architecture and protocol knowledge without loading a monolithic instruction file.

## OpenWiki: evaluate after the first vertical slice

OpenWiki is useful once the repository has enough implementation, tests, and history to synthesize navigation that humans would otherwise maintain manually. It writes a repository wiki under `openwiki/`, maintains a managed block in root agent instruction files, and can update documentation from Git diffs.

Do not add OpenWiki or a scheduled mutation workflow in the initial commit. Before adoption:

1. build one meaningful vertical slice and establish stable documentation ownership;
2. run OpenWiki locally on a branch;
3. review generated files for duplication, stale claims, and retrieval value;
4. decide which generated pages are durable enough to commit;
5. if retained, configure CI to open a reviewable documentation PR rather than auto-merge changes.

The source-of-truth policy in `AGENTS.md` remains authoritative. Generated documentation must never become a substitute for tests, protocol schemas, CI configuration, or live GitHub state.
