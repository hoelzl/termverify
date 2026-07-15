from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest


def load_validator() -> ModuleType:
    path = Path("scripts/validate_evidence_governance.py")
    spec = importlib.util.spec_from_file_location("evidence_governance_validator", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("review_mode", "proposed_by", "reviewed_by"),
    [
        ("independent", "author", "reviewer"),
        ("maintainer-self-review", "maintainer", "maintainer"),
    ],
)
def test_validate_evidence_governance_accepts_approved_baseline(
    tmp_path: Path,
    review_mode: str,
    proposed_by: str,
    reviewed_by: str,
) -> None:
    repository = tmp_path / "repository"
    baseline = repository / "tests" / "fixtures" / "baselines" / "nested" / "menu.json"
    baseline.parent.mkdir(parents=True)
    baseline_bytes = b'{"selected": "file"}\n'
    baseline.write_bytes(baseline_bytes)
    baseline_digest = hashlib.sha256(baseline_bytes).hexdigest()

    review = baseline.with_suffix(".review.md")
    review_bytes = (
        f"before_sha256: null\nafter_sha256: {baseline_digest}\n\n"
        "Records the approved menu selection.\n"
    ).encode()
    review.write_bytes(review_bytes)

    approval = baseline.with_suffix(".approval.json")
    approval.write_text(
        json.dumps(
            {
                "format": "termverify.baseline-approval/v1",
                "baseline_sha256": baseline_digest,
                "rationale": "The menu opens with the file item selected.",
                "review_mode": review_mode,
                "proposed_by": proposed_by,
                "reviewed_by": reviewed_by,
                "reviewed_at": "2026-07-15T00:00:00Z",
                "review_url": "https://github.com/hoelzl/termverify/pull/5",
                "review_diff_sha256": hashlib.sha256(review_bytes).hexdigest(),
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    validator = load_validator()

    assert validator.validate_evidence_governance(repository) == []


@pytest.mark.parametrize(
    ("review_mode", "proposed_by", "reviewed_by", "message"),
    [
        ("independent", "maintainer", "maintainer", "must differ"),
        ("maintainer-self-review", "author", "reviewer", "must match"),
        ("automated", "maintainer", "maintainer", "review_mode"),
    ],
)
def test_validate_approval_enforces_review_mode_identity(
    tmp_path: Path,
    review_mode: str,
    proposed_by: str,
    reviewed_by: str,
    message: str,
) -> None:
    validator = load_validator()
    approval = {
        "format": "termverify.baseline-approval/v1",
        "baseline_sha256": "0" * 64,
        "rationale": "Reviewed expected behavior.",
        "review_mode": review_mode,
        "proposed_by": proposed_by,
        "reviewed_by": reviewed_by,
        "reviewed_at": "2026-07-15T00:00:00Z",
        "review_url": "https://github.com/hoelzl/termverify/pull/5",
        "review_diff_sha256": "1" * 64,
    }

    errors = validator._validate_approval(
        tmp_path / "baseline.approval.json",
        approval,
        "0" * 64,
        tmp_path / "baseline.review.md",
    )

    assert any(message in error for error in errors)


def test_validate_evidence_governance_rejects_unapproved_nested_baseline(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    baseline = repository / "tests" / "fixtures" / "baselines" / "nested" / "menu.json"
    baseline.parent.mkdir(parents=True)
    baseline.write_bytes(b'{"selected": "file"}\n')

    validator = load_validator()

    errors = validator.validate_evidence_governance(repository)

    assert any("missing approval sidecar" in error for error in errors)
    assert any("missing readable-diff record" in error for error in errors)


def test_review_url_requires_https_host() -> None:
    validator = load_validator()

    assert validator._is_review_url("https://github.com/hoelzl/termverify/pull/5")
    assert validator._is_review_url("https://github.com/hoelzl/termverify/issues/5")
    assert not validator._is_review_url("https://")
    assert not validator._is_review_url("https:///review/5")
    assert not validator._is_review_url("https://?review=5")
    assert not validator._is_review_url("https:// /review/5")
    assert not validator._is_review_url("https://exa mple.com/review/5")
    assert not validator._is_review_url("https://%20/review/5")
    assert not validator._is_review_url("https://exa\nmple.com/review/5")
    assert not validator._is_review_url("https://exa\tmple.com/review/5")
    assert not validator._is_review_url(" https://example.com/review/5")
    assert not validator._is_review_url("https://example.com")
    assert not validator._is_review_url("https://github.com/hoelzl/termverify")
    assert not validator._is_review_url("https://github.com/hoelzl/termverify/pull/0")
    assert not validator._is_review_url("https://github.com:999/o/r/pull/1")
    assert not validator._is_review_url("https://github.com:/o/r/pull/1")
    assert not validator._is_review_url("https://github.com/%/%/pull/1")
    assert not validator._is_review_url("https://github.com/o\\x/r/pull/1")
    assert not validator._is_review_url("https://github.com/./../pull/1")
    assert not validator._is_review_url("https://github.com/-owner/repo/pull/1")
    assert not validator._is_review_url("https://github.com/owner-/repo/issues/1")
