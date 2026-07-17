# Changelog

All notable changes to the termverify package are documented in this file. The
format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and
the package adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html)
with the pre-1.0 policy below.

## Versioning and compatibility policy

- **Package versions are not protocol versions.** The transcript wire contract
  (`termverify.transcript/v1`) and its closed registries
  (`termverify.timezone/v1`, `termverify.key/v1`) are versioned independently
  and are immutable after freeze; changing their membership or meaning requires
  a new protocol or registry version, never a package release note alone.
- **Before 1.0.0** every `0.x` release may contain breaking changes to the
  Python API. Breaking changes are listed under a **Changed** or **Removed**
  heading with a migration note; they are never silent.
- **Pre-alpha status.** No published release exists yet and no stable/public
  support claim is made. The first supported external artifact requires the
  release checklist in `docs/developer-guide/release.md`.
- Golden masters, baselines, and fixtures never update automatically as part
  of a release; human-reviewed diffs remain mandatory.

## [Unreleased]

### Added

- Deterministic transcript v1 codec, semantic lifecycle validator, and
  fail-closed resource limits with parser/serializer symmetry.
- Closed protocol-owned v1 registries for requested timezone names and
  semantic key chords, with an immutable direct-dispatch key representation.
- Immutable producer-side adapter contract and deterministic in-process direct
  runtime with structured failure classification.
- Safe transcript-persistence boundary with fail-closed evidence
  classification, redaction, and atomic same-directory replacement.
- Packaged canonical transcript schema with installed access API
  (`TRANSCRIPT_SCHEMA_V1_ID`, `transcript_schema_v1_bytes`,
  `transcript_schema_v1_json`) and isolated installed-artifact contract checks.
- No-regression coverage ratchet with a strict committed floor.
- Release governance: this changelog and policy, security-disclosure process,
  release checklist, and tag-triggered build-provenance workflow producing
  attested draft artifacts only.
