"""Site-assembly and published-byte-identity checks for termverify.dev.

The site build and the post-deploy verification are deploy-workflow tooling,
not library behavior: nothing here touches the network, and no library or
required gate depends on the published site being reachable.
"""

from __future__ import annotations

import runpy
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

_BUILDER = runpy.run_path(
    str(Path("scripts/build_site.py")),
    run_name="site_builder",
)
discover_schema_resources = cast(
    Callable[[Path], tuple[Path, ...]], _BUILDER["discover_schema_resources"]
)
build_site = cast(Callable[[Path, Path], tuple[str, ...]], _BUILDER["build_site"])

_CHECKER = runpy.run_path(
    str(Path("scripts/check_published_schema.py")),
    run_name="published_schema_checker",
)
verify_published_bytes = cast(
    Callable[[str, bytes, bytes], None], _CHECKER["verify_published_bytes"]
)
CANONICAL_BASE_URL = cast(str, _CHECKER["CANONICAL_BASE_URL"])

COMMITTED_SCHEMAS_ROOT = Path("src/termverify/schemas")
TRANSCRIPT_V1_RELATIVE = Path("termverify.transcript/v1.schema.json")


class TestDiscovery:
    def test_committed_tree_yields_exactly_the_transcript_v1_schema(self) -> None:
        assert discover_schema_resources(COMMITTED_SCHEMAS_ROOT) == (
            TRANSCRIPT_V1_RELATIVE,
        )

    def test_layout_matches_protocol_slash_version_pattern(
        self, tmp_path: Path
    ) -> None:
        root = tmp_path / "schemas"
        (root / "example.protocol").mkdir(parents=True)
        (root / "example.protocol" / "v2.schema.json").write_bytes(b"{}")
        assert discover_schema_resources(root) == (
            Path("example.protocol/v2.schema.json"),
        )

    def test_unexpected_file_fails_closed(self, tmp_path: Path) -> None:
        root = tmp_path / "schemas"
        (root / "example.protocol").mkdir(parents=True)
        (root / "example.protocol" / "v1.schema.json").write_bytes(b"{}")
        (root / "example.protocol" / "notes.txt").write_bytes(b"stray")
        with pytest.raises(ValueError, match="notes.txt"):
            discover_schema_resources(root)

    def test_file_at_root_level_fails_closed(self, tmp_path: Path) -> None:
        root = tmp_path / "schemas"
        root.mkdir()
        (root / "v1.schema.json").write_bytes(b"{}")
        with pytest.raises(ValueError, match="v1.schema.json"):
            discover_schema_resources(root)

    def test_empty_tree_fails_closed(self, tmp_path: Path) -> None:
        root = tmp_path / "schemas"
        root.mkdir()
        with pytest.raises(ValueError, match="no schema resources"):
            discover_schema_resources(root)


class TestBuildSite:
    def test_published_schema_bytes_are_identical_to_committed(
        self, tmp_path: Path
    ) -> None:
        output = tmp_path / "site"
        build_site(COMMITTED_SCHEMAS_ROOT, output)
        published = output / "schemas" / TRANSCRIPT_V1_RELATIVE
        committed = COMMITTED_SCHEMAS_ROOT / TRANSCRIPT_V1_RELATIVE
        assert published.read_bytes() == committed.read_bytes()

    def test_returns_published_site_relative_paths(self, tmp_path: Path) -> None:
        published = build_site(COMMITTED_SCHEMAS_ROOT, tmp_path / "site")
        assert published == ("schemas/termverify.transcript/v1.schema.json",)

    def test_landing_page_exists_and_names_the_canonical_schema_url(
        self, tmp_path: Path
    ) -> None:
        output = tmp_path / "site"
        build_site(COMMITTED_SCHEMAS_ROOT, output)
        landing = (output / "index.html").read_text(encoding="utf-8")
        assert (
            "https://termverify.dev/schemas/termverify.transcript/v1.schema.json"
            in landing
        )

    def test_no_content_outside_landing_page_and_schemas(self, tmp_path: Path) -> None:
        output = tmp_path / "site"
        build_site(COMMITTED_SCHEMAS_ROOT, output)
        files = sorted(
            path.relative_to(output).as_posix()
            for path in output.rglob("*")
            if path.is_file()
        )
        assert files == [
            "index.html",
            "schemas/termverify.transcript/v1.schema.json",
        ]

    def test_build_is_deterministic(self, tmp_path: Path) -> None:
        first = tmp_path / "first"
        second = tmp_path / "second"
        build_site(COMMITTED_SCHEMAS_ROOT, first)
        build_site(COMMITTED_SCHEMAS_ROOT, second)
        first_files = {
            path.relative_to(first).as_posix(): path.read_bytes()
            for path in first.rglob("*")
            if path.is_file()
        }
        second_files = {
            path.relative_to(second).as_posix(): path.read_bytes()
            for path in second.rglob("*")
            if path.is_file()
        }
        assert first_files == second_files

    def test_refuses_nonempty_output_directory(self, tmp_path: Path) -> None:
        output = tmp_path / "site"
        output.mkdir()
        (output / "leftover.txt").write_bytes(b"stale")
        with pytest.raises(ValueError, match="not empty"):
            build_site(COMMITTED_SCHEMAS_ROOT, output)


class TestVerifyPublishedBytes:
    def test_identical_bytes_pass(self) -> None:
        verify_published_bytes(
            "https://termverify.dev/schemas/example/v1.schema.json",
            b'{"a": 1}\n',
            b'{"a": 1}\n',
        )

    def test_any_byte_difference_fails_and_names_the_url(self) -> None:
        with pytest.raises(AssertionError, match="example/v1.schema.json"):
            verify_published_bytes(
                "https://termverify.dev/schemas/example/v1.schema.json",
                b'{"a": 1} \n',
                b'{"a": 1}\n',
            )

    def test_canonical_base_url_is_the_owner_domain(self) -> None:
        assert CANONICAL_BASE_URL == "https://termverify.dev"
