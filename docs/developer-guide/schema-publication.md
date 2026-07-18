# Canonical Schema Publication (termverify.dev)

This guide records how the canonical schema publication at
`https://termverify.dev` operates and how to troubleshoot it. The governing
decisions live in the accepted design
[`canonical-schema-publication.md`](../agent/design/canonical-schema-publication.md):
the schema `$id` stays on the owner-controlled domain, the published bytes
must be identical to the committed resource, and nothing in the library or
required validation gate may depend on the site being reachable.

## How publication works

Every push to `main` runs the `Pages` workflow
(`.github/workflows/pages.yml`):

1. **Build** — `scripts/build_site.py` assembles the static site from the
   checkout: each committed resource under `src/termverify/schemas/` is
   copied byte-for-byte to `/schemas/<protocol>/<version>.schema.json`, plus
   a generated landing page at `/`. The build fails closed on any file that
   does not match the publishable layout and refuses a non-empty output
   directory.
2. **Deploy** — the artifact is deployed with the GitHub Actions Pages flow
   (`actions/upload-pages-artifact` + `actions/deploy-pages`). There is no
   `gh-pages` branch; the site is always a pure function of one `main`
   commit.
3. **Verify** — `scripts/check_published_schema.py` fetches every published
   schema URL over HTTPS and fails the workflow on any byte difference with
   the committed resource, so a drifted publication cannot exist silently.
   A failure here means the live site is wrong or stale — fix and push;
   library correctness and CI are unaffected by design.

The site build never joins the required build/test path. `pytest` covers the
build and comparison logic (`tests/test_site_publication.py`) without any
network access.

## DNS and domain state (configured 2026-07-19)

Registrar and DNS: IONOS (`termverify.dev`). The configured records:

| Record | Host | Value |
| --- | --- | --- |
| A ×4 | `@` | `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153` |
| AAAA ×4 | `@` | `2606:50c0:8000::153`, `2606:50c0:8001::153`, `2606:50c0:8002::153`, `2606:50c0:8003::153` |
| CNAME | `www` | `hoelzl.github.io` |
| TXT | `_github-pages-challenge-hoelzl` | GitHub domain-verification challenge — keep permanently |

GitHub-side state: the domain is a **verified domain** on the owner account
(this closes the Pages domain-takeover window and must stay verified), and
the repository's Pages settings use build source **GitHub Actions** with
custom domain `termverify.dev`. "Enforce HTTPS" is enabled once GitHub's
certificate exists; the `.dev` TLD is HSTS-preloaded, so the site is
HTTPS-only regardless.

## Troubleshooting

- **Verify job fails with a byte mismatch** right after a deploy: usually
  CDN propagation lag. Re-run the failed job; if it still fails, compare
  `curl -s https://termverify.dev/schemas/termverify.transcript/v1.schema.json | sha256sum`
  against the committed file.
- **Certificate or connection errors** on `termverify.dev`: check the apex
  A/AAAA records against the table above (`Resolve-DnsName termverify.dev
  -Type A`), then the repository Pages settings for certificate-provisioning
  state. Plain HTTP never works on `.dev`; that is expected.
- **`www.termverify.dev` not redirecting**: confirm the `www` CNAME targets
  `hoelzl.github.io` (not an IONOS redirect service, which would break the
  certificate).
- **Adding a new schema**: commit it as
  `src/termverify/schemas/<protocol>/<version>.schema.json` with an `$id` of
  `https://termverify.dev/schemas/<protocol>/<version>.schema.json`; the
  build publishes it automatically and the verify job starts covering it.
  New schema versions are protocol changes and follow the protocol's
  versioning and review rules first.
- **Changing published bytes**: never edit the site or a published file
  directly — change the committed resource under the protocol's amendment
  rules and let the workflow republish it.
