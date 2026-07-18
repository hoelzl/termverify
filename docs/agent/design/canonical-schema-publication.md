# Canonical Schema Publication and Documentation Site at termverify.dev

- **Status:** accepted — decided 2026-07-19 by explicit owner direction in
  session. The document records those decisions, defines the publication
  contract, and authorizes the implementation slices listed at the end. It
  does not itself add code, workflows, or DNS state, and it makes no claim
  that the `$id` currently resolves.
- **Issue:** [#131](https://github.com/hoelzl/termverify/issues/131)
- **Date:** 2026-07-19
- **Inputs:** the packaged-schema distribution slice (issue #95) and its
  byte-identity installed-artifact checks; the documented
  `termverify.TRANSCRIPT_SCHEMA_V1_ID`; the schema-authority and
  inception-period rules in
  [`docs/knowledge/protocol.md`](../../knowledge/protocol.md); the
  release-governance slice (issue #99) and
  [`docs/developer-guide/release.md`](../../developer-guide/release.md); the
  transferred "resolvable canonical schema publication" criterion in the
  [pre-release boundary hardening handover](../handovers/pre-release-boundary-hardening-handover.md);
  the owner-registered domain `termverify.dev` (registrar and DNS: IONOS,
  unconfigured at decision time).

## Decision summary

The documented schema `$id`,
`https://termverify.dev/schemas/termverify.transcript/v1.schema.json`, keeps
its exact current value and becomes resolvable. Publication is a GitHub Pages
site for the `hoelzl/termverify` repository with `termverify.dev` as its
custom domain, deployed by a GitHub Actions workflow from `main`. The
published schema bytes are copied in-workflow from the single committed
source, `src/termverify/schemas/termverify.transcript/v1.schema.json`, and a
post-deploy check fetches the live URL and fails the workflow on any byte
difference, so hand-edited or drifted publications cannot exist silently.

By owner direction the same origin also serves the project's human-facing
documentation at the site root; schemas live under the reserved `/schemas/`
path prefix. Resolvability is a distribution convenience only: it changes
neither the schema's non-exhaustive role nor runtime authority, and nothing
in the library, tests, or required build path may depend on the site being
reachable.

## Owner decisions recorded (2026-07-19)

1. **The `$id` stays on the owner-controlled domain and is not repointed at
   a GitHub URL.** A `raw.githubusercontent.com` or Pages default-domain URL
   bakes the org name, repository name, branch, and internal file layout
   into the protocol's permanent identifier; none of those are
   protocol-stable, and `raw.githubusercontent.com` additionally serves
   `text/plain`, is rate-limited, and is not a supported publication
   endpoint. The committed schema and the packaged resource already carry
   the `termverify.dev` `$id`, and the installed-artifact byte-identity
   checks pin those bytes, so keeping the identifier and making reality
   match it is also the only option that changes nothing about the schema
   itself.
2. **Hosting is GitHub Pages with `termverify.dev` as the custom domain.**
   The apex domain is the canonical host, with HTTPS enforced once GitHub
   issues the certificate. `www.termverify.dev` is configured as a CNAME so
   GitHub redirects it to the apex. Deployment uses the GitHub Actions Pages
   flow (`actions/upload-pages-artifact` plus `actions/deploy-pages`) from
   pushes to `main`; no `gh-pages` branch exists, so the deployed site is
   always a pure function of a single `main` commit.
3. **Documentation is served from the same origin.** The site root hosts the
   curated human-facing documentation: a landing page derived from
   `README.md` plus the `docs/knowledge/` and `docs/developer-guide/` trees.
   `docs/agent/` (designs, handovers, plans, prompts) is agent-facing
   working material and is not part of the published site, although it
   remains public in the repository.
4. **Publication is generated, never hand-copied.** The deploy workflow
   assembles the site from the committed repository content of the deployed
   commit. The committed resource under `src/termverify/schemas/` remains
   the single authoritative copy; the site build copies it verbatim, and the
   post-deploy verification described below makes byte identity a
   machine-enforced invariant rather than a convention.

## Publication contract

### URL layout

| Path | Content |
| --- | --- |
| `/schemas/<protocol>/<version>.schema.json` | Exact bytes of the committed schema resource for that protocol version. |
| `/schemas/termverify.transcript/v1.schema.json` | The transcript v1 schema; this URL is byte-for-byte `termverify.TRANSCRIPT_SCHEMA_V1_ID`'s target and must always equal the committed resource. |
| `/` and documentation paths | Human-facing documentation site. |

The `/schemas/` prefix is reserved: the documentation build must never emit
content under it, and every future published schema uses the same
`<protocol>/<version>.schema.json` pattern with an `$id` equal to its
published URL. Publishing a new schema version is a protocol change and
follows the protocol's existing versioning and review rules; the site is
only a mirror of committed content.

### Invariants

- **Byte identity.** For every published schema path, the served bytes equal
  the committed resource bytes at the deployed `main` commit. The deploy
  workflow enforces this twice: structurally, because the artifact is copied
  from the committed file in the same checkout, and observationally, by a
  post-deploy step that fetches each published schema URL over HTTPS and
  fails the workflow on any mismatch.
- **Runtime authority unchanged.** The schema remains a non-exhaustive
  structural aid; the Python validator remains authoritative for protocol
  acceptance. Resolvability adds no conformance meaning, and schema
  acceptance is still not a conformance verdict.
- **No ambient network dependency.** The library never fetches the `$id` at
  runtime, tests validate against the packaged resource only, and no
  required build/test/release gate depends on `termverify.dev` being
  reachable. The post-deploy fetch check lives exclusively in the deploy
  workflow, which is not part of the required validation gate. A site or
  DNS outage therefore has no effect on library correctness or CI.
- **Inception-period semantics.** During the declared pre-release inception
  period the committed v1 schema may still be amended with the protocol
  version staying 1, under the protocol's existing amendment rule. The
  publication mirrors `main`, so published bytes may change during
  inception. From the protocol's freeze trigger onward — the first declared
  real client or supported external artifact, per the protocol's amendment
  rule — a published schema version becomes immutable under the
  release-governance rules; any later change requires a new version at a
  new URL.
- **Identifier-first.** The `$id` remains primarily an identifier.
  Consumers must treat resolution as a convenience; documentation must not
  instruct anyone to fetch schemas at validation time.

## Operational prerequisites (owner-manual)

These steps require registrar and repository-settings access and are the
only manual steps; everything else is workflow-driven.

1. **IONOS DNS records for the apex** (`termverify.dev`): four `A` records
   to GitHub Pages' addresses `185.199.108.153`, `185.199.109.153`,
   `185.199.110.153`, `185.199.111.153`, and four `AAAA` records to
   `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`,
   `2606:50c0:8003::153`. Any registrar-supplied default `A`/`AAAA` records
   or domain parking for the apex must be removed first.
2. **`www` subdomain:** one `CNAME` record from `www` to
   `hoelzl.github.io.` so GitHub can redirect it to the apex.
3. **Verify the domain with GitHub** (account settings → Pages → verified
   domains) via the `TXT` challenge record GitHub displays, *before* the
   custom domain is attached to the Pages site. Verification prevents a
   domain-takeover window in which another GitHub user could claim the
   domain for their own Pages site if ours is ever disabled.
4. **Pages site configuration:** enable Pages for `hoelzl/termverify` with
   build source "GitHub Actions", set the custom domain to
   `termverify.dev`, and enable "Enforce HTTPS" once GitHub finishes
   certificate issuance (this option stays greyed out until DNS has
   propagated and the certificate exists; `.dev` is HSTS-preloaded, so
   HTTPS is effectively mandatory anyway).

The `dev` TLD sits on the browser HSTS preload list: plain-HTTP access never
works, so DNS mistakes surface as certificate or connection errors rather
than silent downgrades. This is a feature, not a problem to work around.

## Documentation-site tooling decision

The documentation site is built with **MkDocs and the Material for MkDocs
theme**, pinned in a new `docs` dependency group in `pyproject.toml` and
managed by `uv` like every other group. Rationale, as required by the
dependency rule in `AGENTS.md`:

- The published documentation's source of truth stays the existing Markdown
  under `docs/` and `README.md`; MkDocs consumes it in place, so no content
  is forked into a second format.
- Output is fully static, matching Pages hosting with no server-side or
  client-side runtime dependency.
- MkDocs and Material are mature, widely reviewed, pure-Python packages
  installable from the existing index with hashes locked in `uv.lock`.
- The docs *build* runs only in the deploy workflow and on demand locally;
  it is an optional integration and never joins the required build/test
  path, keeping the harness-compatibility rule intact. (The locked `docs`
  group is still installed by the standard `uv --no-config sync
  --all-groups --locked` gate like every other group; what stays out of the
  required path is running MkDocs, not installing it.)

The OKF YAML frontmatter on `docs/knowledge/` pages must not leak into
rendered pages (MkDocs treats leading YAML as page metadata by default,
which satisfies this). Navigation, theming, and page-inclusion details are
implementation-slice concerns; the design constrains only the source-of-truth
rule, the `/schemas/` reservation, and the exclusion of `docs/agent/`.

## Explicit non-goals

- No package release, index publication, or change to release governance.
- No change to schema bytes, the `$id` value, the schema's non-exhaustive
  role, or runtime authority.
- No JSON Schema `$ref` resolution service, schema registry API, or
  content-negotiation guarantees beyond static file serving.
- No versioned documentation hosting (per-release doc snapshots), search
  service, or analytics decision; any of these needs a new owner decision.
- No publication of `docs/agent/` content on the site.

## Authorized implementation slices

1. **Slice 1 — schema publication.** After the owner completes the DNS and
   Pages prerequisites: add the Pages deploy workflow that publishes
   `/schemas/termverify.transcript/v1.schema.json` (copied from the
   committed resource) plus a minimal landing page; include the post-deploy
   byte-identity fetch check; add a `docs/developer-guide/` page recording
   the DNS records, verification state, and troubleshooting; and update the
   `protocol.md` "no resolvable canonical publication exists yet" caveat to
   describe the publication and its mirror-of-`main` inception semantics.
   Acceptance evidence: the live HTTPS URL serves bytes identical to the
   committed schema, shown by the deploy workflow's check on the merged
   commit. The `protocol.md` update lands only with that evidence.
2. **Slice 2 — documentation site.** Add the `docs` dependency group
   (MkDocs + Material, locked), the MkDocs configuration serving the
   curated trees at the root, and extend the deploy workflow to build docs
   and schemas into one artifact. Acceptance evidence: the published site
   renders the landing page and knowledge/developer-guide content, the
   schema URL still serves identical bytes, and no content is emitted under
   `/schemas/` by the docs build.

Each slice follows the standard loop: focused issue, sibling worktree,
test-first for everything locally testable (site-assembly and
byte-identity check scripts), the full validation gate, PR, independent
adversarial review, merge. Slice ordering is fixed — the schema contract
must not wait on documentation tooling.
