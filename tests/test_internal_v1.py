from __future__ import annotations

import hashlib

import pytest

from termverify._json import JsonValue as InternalJsonValue
from termverify._key_v1 import KEY_NAMES, is_key_chord
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


def test_v1_key_registry_complete_contents_match_reviewed_digest() -> None:
    canonical_names = ("\n".join(KEY_NAMES) + "\n").encode()

    assert len(KEY_NAMES) == 99
    assert hashlib.sha256(canonical_names).hexdigest() == (
        "51955be77ab11b23240c642edd0e4f08dbd56389b82f99bbe2ee87871ce9d0a0"
    )


@pytest.mark.parametrize(
    "keys",
    [
        ["Enter"],
        ["F1"],
        ("Escape",),
        ["Shift", "Tab"],
        ["Control", "c"],
        ["Control", "Alt", "Shift", "Meta", "F12"],
        ["Alt", "1"],
        ["Control", "0"],
        ["Meta", "z"],
        ["Control", "Space"],
        ["Control", "/"],
        ["Control", "_"],
        ["Alt", "<"],
        ["Alt", ">"],
        ["Meta", "?"],
        ["Control", "Alt", "["],
    ],
)
def test_v1_key_chord_accepts_canonical_semantic_components(
    keys: list[str] | tuple[str, ...],
) -> None:
    assert is_key_chord(keys)


@pytest.mark.parametrize(
    "keys",
    [
        [],
        ["enter"],
        ["  "],
        ["NotAKey"],
        ["é"],
        ["Ctrl", "c"],
        ["Control", "C"],
        ["Control", "é"],
        ["Control+c"],
        ["Control", "Control", "c"],
        ["Shift", "Control", "c"],
        ["Control"],
        ["Enter", "Tab"],
        ["c"],
        ["Shift", "a"],
        ["1"],
        ["Space"],
        ["/"],
        ["<"],
        ["Shift", "/"],
        ["Shift", "<"],
        ["\x1b[A"],
        [1],
        "Enter",
    ],
)
def test_v1_key_chord_rejects_aliases_malformed_order_and_nonsemantic_values(
    keys: object,
) -> None:
    assert not is_key_chord(keys)


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
