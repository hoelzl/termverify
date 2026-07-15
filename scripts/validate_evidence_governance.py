"""Validate TermVerify evidence-governance controls for approved baselines."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit

import yaml

from termverify.evidence import JsonValue, redact_evidence

BASELINE_ROOT = Path("tests/fixtures/baselines")
TRANSCRIPT_FIXTURE_ROOT = Path("tests/fixtures/transcripts")
DISABLED_PERSISTENT_ROOTS = (Path("artifacts"), Path("reports"))
WORKFLOW_ROOT = Path(".github/workflows")
FIXTURE_CLASSIFICATION_SCHEMA = "termverify.fixture-evidence/v1"
FIXTURE_CLASSIFICATION_SUFFIX = ".jsonl.evidence.json"
APPROVAL_FORMAT = "termverify.baseline-approval/v1"
APPROVAL_FIELDS = frozenset(
    {
        "format",
        "baseline_sha256",
        "rationale",
        "review_mode",
        "proposed_by",
        "reviewed_by",
        "reviewed_at",
        "review_url",
        "review_diff_sha256",
    }
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_HTTPS_HOST_PATTERN = re.compile(
    r"(?=.{1,253}\Z)"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*"
)
_GITHUB_REVIEW_PATH_PATTERN = re.compile(
    r"/[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
    r"/(?!(?:\.{1,2})/)[A-Za-z0-9._-]{1,100}"
    r"/(?:pull|issues)/[1-9][0-9]*"
)


class _RestrictedEvidence(ValueError):
    pass


def validate_evidence_governance(repository_root: Path) -> list[str]:
    """Return evidence-governance violations below *repository_root*."""
    errors = _validate_transcript_fixtures(repository_root / TRANSCRIPT_FIXTURE_ROOT)
    errors.extend(_validate_disabled_persistent_roots(repository_root))
    errors.extend(_validate_workflows(repository_root / WORKFLOW_ROOT))
    root = repository_root / BASELINE_ROOT
    if not root.exists():
        return errors

    baselines = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not path.name.endswith(".approval.json")
        and not path.name.endswith(".review.md")
    )
    expected_sidecars: set[Path] = set()

    for baseline in baselines:
        approval = baseline.with_suffix(".approval.json")
        review = baseline.with_suffix(".review.md")
        expected_sidecars.update((approval, review))
        errors.extend(_validate_baseline(baseline, approval, review))

    for sidecar in sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and (path.name.endswith(".approval.json") or path.name.endswith(".review.md"))
    ):
        if sidecar not in expected_sidecars:
            errors.append(f"{sidecar}: orphan approval or readable-diff record")

    return errors


def _validate_transcript_fixtures(root: Path) -> list[str]:
    errors: list[str] = []
    if not root.exists():
        return errors
    for fixture in sorted(path for path in root.rglob("*") if path.is_file()):
        if fixture.name.endswith(FIXTURE_CLASSIFICATION_SUFFIX):
            target = fixture.with_name(fixture.name[: -len(".evidence.json")])
            if not target.is_file():
                errors.append(f"{fixture}: orphan transcript fixture classification")
            continue
        if fixture.suffix != ".jsonl":
            errors.append(f"{fixture}: unsupported transcript fixture extension")
            continue
        errors.extend(_validate_fixture_classification(fixture))
        try:
            text = fixture.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            errors.append(f"{fixture}: transcript fixture must be UTF-8 text")
            continue
        if redact_evidence(text) != text:
            errors.append(f"{fixture}: transcript fixture contains restricted evidence")
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            try:
                value = cast(
                    JsonValue,
                    json.loads(
                        line,
                        parse_constant=_reject_constant,
                        object_pairs_hook=_safety_object,
                    ),
                )
            except _RestrictedEvidence:
                errors.append(
                    f"{fixture}:{line_number}: transcript fixture contains "
                    "restricted evidence"
                )
                continue
            except (ValueError, json.JSONDecodeError):
                errors.append(
                    f"{fixture}:{line_number}: transcript fixture is not finite JSON"
                )
                continue
            if redact_evidence(value) != value:
                errors.append(
                    f"{fixture}:{line_number}: transcript fixture contains "
                    "restricted evidence"
                )
    return errors


def _validate_fixture_classification(fixture: Path) -> list[str]:
    classification_path = fixture.with_name(f"{fixture.name}.evidence.json")
    if not classification_path.is_file():
        return [f"{fixture}: missing public-synthetic classification"]
    try:
        classification = json.loads(
            classification_path.read_text(encoding="utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_safety_object,
        )
    except (OSError, UnicodeDecodeError, ValueError) as error:
        return [f"{classification_path}: invalid fixture classification: {error}"]
    expected = {
        "schema": FIXTURE_CLASSIFICATION_SCHEMA,
        "classification": "public-synthetic",
        "fixture": fixture.name,
    }
    if classification != expected:
        return [
            f"{classification_path}: fixture classification must equal {expected!r}"
        ]
    return []


def _validate_disabled_persistent_roots(repository_root: Path) -> list[str]:
    errors: list[str] = []
    for relative_root in DISABLED_PERSISTENT_ROOTS:
        root = repository_root / relative_root
        for evidence in sorted(path for path in root.rglob("*") if path.is_file()):
            errors.append(f"{evidence}: persistent evidence root is disabled")
    return errors


def _validate_workflows(root: Path) -> list[str]:
    errors: list[str] = []
    for pattern in ("*.yml", "*.yaml"):
        for workflow in sorted(path for path in root.rglob(pattern) if path.is_file()):
            try:
                text = workflow.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                errors.append(f"{workflow}: workflow must be readable UTF-8 text")
                continue
            try:
                document = yaml.safe_load(text)
            except yaml.YAMLError as error:
                errors.append(f"{workflow}: cannot parse workflow YAML: {error}")
                continue
            if _contains_artifact_upload(document):
                errors.append(f"{workflow}: CI artifact upload is disabled")
    return errors


def _contains_artifact_upload(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                isinstance(key, str)
                and key.casefold() == "uses"
                and isinstance(item, str)
                and item.strip().casefold().startswith("actions/upload-artifact@")
            ):
                return True
            if _contains_artifact_upload(item):
                return True
    elif isinstance(value, list):
        return any(_contains_artifact_upload(item) for item in value)
    return False


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def _safety_object(pairs: list[tuple[str, JsonValue]]) -> dict[str, JsonValue]:
    result: dict[str, JsonValue] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate object member: {key}")
        candidate: dict[str, JsonValue] = {key: value}
        if redact_evidence(candidate) != candidate:
            raise _RestrictedEvidence
        result[key] = value
    return result


def _validate_baseline(baseline: Path, approval: Path, review: Path) -> list[str]:
    errors = _validate_canonical_text(baseline)
    if not approval.exists():
        errors.append(f"{baseline}: missing approval sidecar")
    if not review.exists():
        errors.append(f"{baseline}: missing readable-diff record")
    if errors:
        return errors

    baseline_digest = hashlib.sha256(baseline.read_bytes()).hexdigest()
    approval_data, approval_errors = _load_approval(approval)
    errors.extend(approval_errors)
    review_text, review_errors = _load_canonical_text(review)
    errors.extend(review_errors)
    if approval_data is None or review_text is None:
        return errors

    errors.extend(_validate_approval(approval, approval_data, baseline_digest, review))
    errors.extend(_validate_review(review, review_text, baseline_digest, approval_data))
    return errors


def _validate_canonical_text(path: Path) -> list[str]:
    _, errors = _load_canonical_text(path)
    return errors


def _load_canonical_text(path: Path) -> tuple[str | None, list[str]]:
    data = path.read_bytes()
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None, [f"{path}: must be UTF-8 text"]
    if text.startswith("\ufeff"):
        return None, [f"{path}: must not contain a UTF-8 byte-order mark"]
    if "\r" in text:
        return None, [f"{path}: must use LF line endings"]
    if not text.endswith("\n") or text.endswith("\n\n"):
        return None, [f"{path}: must end with exactly one LF"]
    return text, []


def _load_approval(path: Path) -> tuple[dict[str, object] | None, list[str]]:
    try:
        raw_data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None, [f"{path}: invalid approval JSON"]
    if not isinstance(raw_data, dict):
        return None, [f"{path}: approval record must be an object"]
    return cast(dict[str, object], raw_data), []


def _validate_approval(
    path: Path,
    approval: dict[str, object],
    baseline_digest: str,
    review: Path,
) -> list[str]:
    errors: list[str] = []
    if set(approval) != APPROVAL_FIELDS:
        errors.append(f"{path}: approval fields do not match v1")
        return errors
    if approval["format"] != APPROVAL_FORMAT:
        errors.append(f"{path}: unsupported approval format")
    if approval["baseline_sha256"] != baseline_digest:
        errors.append(f"{path}: baseline digest does not match")
    if not _is_non_empty_string(approval["rationale"]):
        errors.append(f"{path}: rationale must be non-empty")
    if not _is_non_empty_string(approval["proposed_by"]):
        errors.append(f"{path}: proposed_by must be non-empty")
    if not _is_non_empty_string(approval["reviewed_by"]):
        errors.append(f"{path}: reviewed_by must be non-empty")
    review_mode = approval["review_mode"]
    identities_match = approval["proposed_by"] == approval["reviewed_by"]
    if review_mode not in {"independent", "maintainer-self-review"}:
        errors.append(f"{path}: review_mode is invalid")
    elif review_mode == "independent" and identities_match:
        errors.append(
            f"{path}: proposer and reviewer must differ for independent review"
        )
    elif review_mode == "maintainer-self-review" and not identities_match:
        errors.append(
            f"{path}: proposer and reviewer must match for maintainer self-review"
        )
    if not _is_rfc3339_utc(approval["reviewed_at"]):
        errors.append(f"{path}: reviewed_at must be a UTC RFC 3339 timestamp")
    if not _is_review_url(approval["review_url"]):
        errors.append(
            f"{path}: review_url must identify a GitHub pull request or issue"
        )
    if not _is_sha256(approval["review_diff_sha256"]):
        errors.append(f"{path}: review_diff_sha256 must be a SHA-256 digest")
    if (
        review.exists()
        and _is_sha256(approval["review_diff_sha256"])
        and approval["review_diff_sha256"]
        != hashlib.sha256(review.read_bytes()).hexdigest()
    ):
        errors.append(f"{path}: readable-diff digest does not match")
    return errors


def _validate_review(
    path: Path,
    text: str,
    baseline_digest: str,
    approval: dict[str, object],
) -> list[str]:
    lines = text.splitlines()
    if len(lines) < 4 or lines[2] != "":
        return [f"{path}: readable diff must contain digest header and explanation"]
    before_prefix = "before_sha256: "
    after_prefix = "after_sha256: "
    if not lines[0].startswith(before_prefix) or not lines[1].startswith(after_prefix):
        return [f"{path}: readable diff must start with digest header"]
    before = lines[0].removeprefix(before_prefix)
    after = lines[1].removeprefix(after_prefix)
    errors: list[str] = []
    if before != "null" and not _is_sha256(before):
        errors.append(f"{path}: before_sha256 must be null or a SHA-256 digest")
    if after != baseline_digest or after != approval["baseline_sha256"]:
        errors.append(f"{path}: after_sha256 does not match baseline digest")
    if not "\n".join(lines[3:]).strip():
        errors.append(f"{path}: readable diff explanation must be non-empty")
    return errors


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and _SHA256_PATTERN.fullmatch(value) is not None


def _is_review_url(value: object) -> bool:
    if not isinstance(value, str) or any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        return False
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
        return (
            parsed.scheme == "https"
            and hostname is not None
            and _HTTPS_HOST_PATTERN.fullmatch(hostname) is not None
            and hostname.casefold() == "github.com"
            and parsed.username is None
            and parsed.password is None
            and port in {None, 443}
            and parsed.netloc.casefold() in {"github.com", "github.com:443"}
            and _GITHUB_REVIEW_PATH_PATTERN.fullmatch(parsed.path) is not None
        )
    except ValueError:
        return False


def _is_rfc3339_utc(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return True


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    errors = validate_evidence_governance(Path("."))
    if errors:
        print("\n".join(errors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
