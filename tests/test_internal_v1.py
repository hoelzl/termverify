from __future__ import annotations

import pytest

from termverify._json import JsonValue as InternalJsonValue
from termverify._language_tag import is_well_formed_language_tag
from termverify._protocol_v1 import (
    CONSTRAINT_NAMES,
    REQUIRED_CONFIG_MEMBERS,
)
from termverify._protocol_v1 import (
    ConstraintName as InternalConstraintName,
)
from termverify.adapter import ConstraintName
from termverify.evidence import _PAYLOAD_MEMBERS
from termverify.evidence import JsonValue as EvidenceJsonValue
from termverify.transcript import (
    _RECORD_KINDS,
)
from termverify.transcript import JsonValue as TranscriptJsonValue


@pytest.mark.parametrize(
    "value",
    ["C", "en-US", "i-KLINGON", "x-private", "sl-rozaj-biske-1994"],
)
def test_neutral_language_tag_grammar_accepts_v1_values(value: str) -> None:
    assert is_well_formed_language_tag(value)


@pytest.mark.parametrize("value", ["c", "en_US", "a-DE", "en-x", "en--US", "én-US"])
def test_neutral_language_tag_grammar_rejects_malformed_values(value: str) -> None:
    assert not is_well_formed_language_tag(value)


def test_v1_constraint_order_defines_required_configuration_membership() -> None:
    assert CONSTRAINT_NAMES == (
        "seed",
        "clock",
        "locale",
        "timezone",
        "terminal",
        "filesystem",
        "network",
    )
    assert frozenset(CONSTRAINT_NAMES) == REQUIRED_CONFIG_MEMBERS
    assert ConstraintName is InternalConstraintName


def test_json_value_compatibility_imports_share_one_alias() -> None:
    assert TranscriptJsonValue is InternalJsonValue
    assert EvidenceJsonValue is InternalJsonValue


def test_every_defined_v1_record_kind_has_independent_evidence_classification() -> None:
    expected_kinds = frozenset(
        {
            "run.started",
            "capability.result",
            "input.key",
            "input.text",
            "input.resize",
            "input.mouse",
            "input.clock_advanced",
            "input.clipboard_set",
            "input.stop",
            "diagnostic",
            "observation",
            "run.finished",
            "run.failed",
            "run.unsupported",
        }
    )

    assert expected_kinds == _RECORD_KINDS
    assert frozenset(_PAYLOAD_MEMBERS) == expected_kinds
