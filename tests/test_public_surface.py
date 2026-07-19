"""Curated top-level import surface for external adapter authors (issue #149).

External subjects implement ``Adapter``, ``ConstraintPorts``, and
``DirectApplication`` today by importing from module paths. These tests pin the
curated top-level re-export surface: every adapter-author contract name is
importable from ``termverify`` itself and is identical to its module-path
definition, so both import styles stay interchangeable.
"""

import termverify
import termverify.adapter
import termverify.direct

_HEADLINE_NAMES = (
    "Adapter",
    "ConstraintPorts",
    "DirectAdapter",
    "DirectApplication",
)


def test_headline_contract_names_are_importable_from_the_top_level() -> None:
    for name in _HEADLINE_NAMES:
        assert hasattr(termverify, name), name
        assert name in termverify.__all__, name


def test_every_adapter_contract_name_is_reexported_identically() -> None:
    for name in termverify.adapter.__all__:
        assert name in termverify.__all__, name
        assert getattr(termverify, name) is getattr(termverify.adapter, name), name


def test_every_direct_runtime_name_is_reexported_identically() -> None:
    for name in termverify.direct.__all__:
        assert name in termverify.__all__, name
        assert getattr(termverify, name) is getattr(termverify.direct, name), name


def test_dunder_all_is_exactly_the_curated_surface() -> None:
    curated = (
        set(termverify.adapter.__all__)
        | set(termverify.direct.__all__)
        | {
            "TRANSCRIPT_SCHEMA_V1_ID",
            "__version__",
            "persist_transcript_evidence",
            "transcript_schema_v1_bytes",
            "transcript_schema_v1_json",
        }
    )
    assert set(termverify.__all__) == curated


def test_dunder_all_is_sorted_deduplicated_and_resolvable() -> None:
    assert list(termverify.__all__) == sorted(set(termverify.__all__))
    for name in termverify.__all__:
        getattr(termverify, name)
