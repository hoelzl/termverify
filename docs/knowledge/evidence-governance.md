---
type: Evidence Governance
title: Evidence safety and baseline governance
description: Accepted safe-capture, redaction, and baseline-approval contract for TermVerify.
tags: [evidence, redaction, baselines, snapshots, security]
---

# Evidence safety and baseline governance

> **Status: accepted.** Independently human-reviewed on 2026-07-15. The
> required redactor, governance validator, and tests must pass before TermVerify
> enables persistent evidence capture, committed baselines, or CI artifact
> upload.

Terminal evidence can contain credentials, personal data, host paths, and
proprietary application output. The safe default is to capture only sanitized,
non-persistent evidence. This policy applies to direct adapters, terminal
adapters, fixtures, reports, and future CI artifact publication.

## Classification and handling

| Evidence type | Default classification | Persistent handling |
| --- | --- | --- |
| Transcript records, including `state`, event `data`, diagnostic `details`, and `x-` extensions | restricted | Recursively classify and redact before any persistence; unknown fields remain restricted. |
| Synthetic transcript fixtures | public | May be committed only after recursive transcript redaction validation. |
| User input and text paste | restricted | Redact by default; persist only synthetic or explicitly approved values. |
| Clipboard value | secret | Do not capture or persist the value by default; record only a redaction marker when event evidence is needed. |
| Rendered frame or raw ANSI bytes | restricted | Redact before persistence; raw bytes are diagnostic evidence, not a baseline oracle. |
| Process error, command line, environment, or exit diagnostic | restricted | Redact secrets and normalize sandbox paths before persistence. |
| Filesystem path | restricted | Store only a sandbox-relative path; otherwise redact it. |
| CI artifact | restricted | Disabled until this policy's implementation and review are complete. |

`public` evidence is safe for a public repository after validation. `restricted`
evidence may contain project or user information and must be sanitized before
it becomes public. `secret` evidence can authenticate, identify, or otherwise
harm its owner; it is never committed, uploaded, or exposed in a readable diff.

## Secure capture defaults

Future evidence capture has these modes:

- **safe (default):** sensitive fields are redacted; clipboard values are never
  retained; paths are sandbox-relative or redacted; persistence is allowed only
  for validated public evidence.
- **non-persistent:** evidence stays in process memory for the current verdict
  and is not serialized, written to a fixture, reported, or uploaded.
- **sensitive (explicit opt-in):** may retain restricted evidence locally for a
  debugging session, but never enables repository persistence or CI upload. It
  requires an explicit caller setting.

No mode permits secret evidence to enter committed files or CI artifacts. CI
must use safe mode and no artifact-upload step until a separately reviewed
policy change enables it.

Sensitive-mode retention is bounded: evidence may be written only beneath a
caller-supplied directory outside the repository, readable only by the
initiating OS account and the current debugging process. The implementation must
refuse persistent sensitive mode when it cannot establish those boundaries. It
must delete the directory when the run completes and must never retain it for
more than 24 hours after creation; a caller may request earlier deletion. Child
processes, CI workers, other OS accounts, and repository tools have no access
boundary exception.

## Redaction contract

Redaction happens before any serializer, fixture writer, report renderer, or
artifact publisher receives evidence. It is deterministic and replaces a value
with the exact marker `<redacted:reason>`; it must not retain the original
value, its length, hash, or a reversible encoding.

The initial implementation must recursively redact structured transcript
values, including `state`, event `data`, diagnostic `details`, and `x-`
extensions, as well as values identified by evidence type and keys such as
`authorization`, `cookie`, `credential`, `password`, `secret`, `token`, and
`clipboard`. It must also redact recognized credential-shaped strings in free
text. A missed or unknown value is classified as restricted rather than
silently treated as public.

Fixture and artifact writers must invoke the same redactor; no path-specific
writer may serialize raw evidence directly. Tests must construct nested fixture
and artifact destinations to prove that changing a normal output path does not
bypass redaction.

## Baseline proposal and approval

No baseline files are committed until this design is accepted and its validator
is implemented. The designated baseline root is `tests/fixtures/baselines/`.
Once enabled, every baseline under that root must have a nearby
`<baseline-name>.approval.json` sidecar and `<baseline-name>.review.md`
readable-diff record. V1 baselines are UTF-8 text without a byte-order mark,
use LF line endings, and end with exactly one LF. Their canonical bytes are the
exact resulting UTF-8 file bytes; `baseline_sha256` is SHA-256 of those bytes.
Any future binary or differently canonicalized baseline type requires a new
approval format version. The sidecar has exactly these required members:

| Member | Rule |
| --- | --- |
| `format` | Exactly `termverify.baseline-approval/v1`. |
| `baseline_sha256` | SHA-256 of the canonical baseline bytes. |
| `rationale` | Non-empty human-readable reason for the expected behavior. |
| `proposed_by` | Non-empty author identity. |
| `reviewed_by` | Non-empty human reviewer identity that differs from `proposed_by`. |
| `reviewed_at` | UTC RFC 3339 timestamp. |
| `review_url` | HTTPS URL to the PR, issue, or review record. |
| `review_diff_sha256` | SHA-256 of the adjacent readable-diff record. |

The readable-diff record starts with `before_sha256` (or `null` for a new
baseline) and `after_sha256`, where `after_sha256` exactly equals the sidecar's
`baseline_sha256`; it then contains a non-empty human-readable explanation of
the change. It is UTF-8 text without a byte-order mark, uses LF line endings,
and ends with exactly one LF; `review_diff_sha256` is SHA-256 of its exact file
bytes. The baseline path, sidecar path, readable-diff record, canonical digest,
and approval record are a single validation unit. The validator rejects a
missing, malformed, stale, or orphan sidecar or readable-diff record; it
rejects a baseline outside the designated baseline root; it verifies both
digests and the `after_sha256` binding; and it rejects equal proposer/reviewer
identities. A PR still requires the repository's normal branch-protection
review; metadata does not substitute for a human review.

## Enforcement and ownership

The project maintainer owns policy exceptions and redaction-pattern updates.
False positives are resolved by improving the deterministic redactor or marking
the evidence restricted/non-persistent; they are never resolved by disabling
validation for a path. Suspected leakage means revoke affected credentials,
remove public exposure, rotate secrets, and add a regression test before
resuming capture.

Before enabling baselines or artifacts, CI and local pre-commit must run the
same evidence-governance validator. The validator's tests must cover valid
redaction of nested transcript fields/extensions, nested fixture and artifact
paths, sensitive-retention boundary failure, missing/stale approval metadata or
readable-diff records, proposer self-approval, and rejection of a changed
baseline without matching approval and readable-diff digests.