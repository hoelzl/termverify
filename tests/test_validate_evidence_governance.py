from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType


def load_validator() -> ModuleType:
    path = Path("scripts/validate_evidence_governance.py")
    spec = importlib.util.spec_from_file_location("evidence_governance_validator", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_validate_evidence_governance_accepts_approved_baseline(tmp_path: Path) -> None:
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
                "proposed_by": "author",
                "reviewed_by": "reviewer",
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
