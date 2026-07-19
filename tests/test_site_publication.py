"""Site-assembly and published-byte-identity checks for termverify.dev.

The site build and the post-deploy verification are deploy-workflow tooling,
not library behavior: nothing here touches the network, and no library or
required gate depends on the published site being reachable.
"""

from __future__ import annotations

import importlib.util
import runpy
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

MKDOCS_AVAILABLE = importlib.util.find_spec("mkdocs") is not None

_BUILDER = runpy.run_path(
    str(Path("scripts/build_site.py")),
    run_name="site_builder",
)
discover_schema_resources = cast(
    Callable[[Path], tuple[Path, ...]], _BUILDER["discover_schema_resources"]
)
build_site = cast(Callable[..., tuple[str, ...]], _BUILDER["build_site"])
stage_docs = cast(Callable[[Path, Path], None], _BUILDER["stage_docs"])
ensure_reserved_prefix_free = cast(
    Callable[[Path], None], _BUILDER["ensure_reserved_prefix_free"]
)

_CHECKER = runpy.run_path(
    str(Path("scripts/check_published_schema.py")),
    run_name="published_schema_checker",
)
verify_published_bytes = cast(
    Callable[[str, bytes, bytes], None], _CHECKER["verify_published_bytes"]
)
verify_with_retry = cast(
    Callable[..., None],
    _CHECKER["verify_with_retry"],
)
published_url = cast(Callable[[str, Path], str], _CHECKER["published_url"])
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

    def test_missing_root_fails_closed_with_clear_message(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not a directory"):
            discover_schema_resources(tmp_path / "absent")


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

    def test_refuses_output_path_that_is_a_file(self, tmp_path: Path) -> None:
        output = tmp_path / "site"
        output.write_bytes(b"a file, not a directory")
        with pytest.raises(ValueError, match="not a directory"):
            build_site(COMMITTED_SCHEMAS_ROOT, output)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "docs" / "knowledge").mkdir(parents=True)
    (repo / "docs" / "developer-guide").mkdir(parents=True)
    (repo / "docs" / "agent" / "design").mkdir(parents=True)
    (repo / "README.md").write_bytes(b"# Landing\n")
    (repo / "docs" / "knowledge" / "index.md").write_bytes(b"# Knowledge\n")
    (repo / "docs" / "knowledge" / "protocol.md").write_bytes(b"# Protocol\n")
    (repo / "docs" / "developer-guide" / "guide.md").write_bytes(b"# Guide\n")
    (repo / "docs" / "agent" / "design" / "secret.md").write_bytes(b"# Internal\n")
    return repo


class TestStageDocs:
    def test_stages_readme_as_index_and_curated_trees_only(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path)
        staging = tmp_path / "staging"
        stage_docs(repo, staging)
        files = sorted(
            path.relative_to(staging).as_posix()
            for path in staging.rglob("*")
            if path.is_file()
        )
        assert files == [
            "developer-guide/guide.md",
            "index.md",
            "knowledge/index.md",
            "knowledge/protocol.md",
        ]
        assert (staging / "index.md").read_bytes() == (repo / "README.md").read_bytes()

    def test_agent_tree_is_never_staged(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        staging = tmp_path / "staging"
        stage_docs(repo, staging)
        assert not (staging / "agent").exists()
        staged = [path.relative_to(staging).as_posix() for path in staging.rglob("*")]
        assert not any("agent" in path for path in staged)

    def test_missing_source_tree_fails_closed(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        shutil.rmtree(repo / "docs" / "knowledge")
        with pytest.raises(ValueError, match="knowledge"):
            stage_docs(repo, tmp_path / "staging")

    def test_refuses_nonempty_staging_directory(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        staging = tmp_path / "staging"
        staging.mkdir()
        (staging / "stale.md").write_bytes(b"stale")
        with pytest.raises(ValueError, match="not empty"):
            stage_docs(repo, staging)


class TestStagedLinkRewriting:
    def test_readme_links_into_curated_trees_are_remapped(self, tmp_path: Path) -> None:
        repo = _make_repo(tmp_path)
        (repo / "README.md").write_text(
            "See [knowledge](docs/knowledge/index.md) and"
            " [guide](docs/developer-guide/guide.md).\n",
            encoding="utf-8",
        )
        staging = tmp_path / "staging"
        stage_docs(repo, staging)
        index = (staging / "index.md").read_text(encoding="utf-8")
        assert "(knowledge/index.md)" in index
        assert "(developer-guide/guide.md)" in index
        assert "docs/" not in index

    def test_links_to_unpublished_repo_files_become_github_urls(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path)
        (repo / "README.md").write_text(
            "Read [contributing](CONTRIBUTING.md) first.\n", encoding="utf-8"
        )
        (repo / "docs" / "knowledge" / "protocol.md").write_text(
            "See the [design](../agent/design/secret.md#section) record.\n",
            encoding="utf-8",
        )
        staging = tmp_path / "staging"
        stage_docs(repo, staging)
        index = (staging / "index.md").read_text(encoding="utf-8")
        assert (
            "(https://github.com/hoelzl/termverify/blob/main/CONTRIBUTING.md)" in index
        )
        protocol = (staging / "knowledge" / "protocol.md").read_text(encoding="utf-8")
        assert (
            "(https://github.com/hoelzl/termverify/blob/main/"
            "docs/agent/design/secret.md#section)" in protocol
        )

    def test_intra_tree_absolute_and_anchor_links_are_untouched(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path)
        (repo / "docs" / "knowledge" / "protocol.md").write_text(
            "See [index](index.md), [site](https://example.org/x),"
            " [anchor](#limits), and [mail](mailto:tc@xantira.com).\n",
            encoding="utf-8",
        )
        staging = tmp_path / "staging"
        stage_docs(repo, staging)
        protocol = (staging / "knowledge" / "protocol.md").read_text(encoding="utf-8")
        assert "(index.md)" in protocol
        assert "(https://example.org/x)" in protocol
        assert "(#limits)" in protocol
        assert "(mailto:tc@xantira.com)" in protocol

    def test_cross_tree_links_are_remapped_relative_to_staged_file(
        self, tmp_path: Path
    ) -> None:
        repo = _make_repo(tmp_path)
        (repo / "docs" / "developer-guide" / "guide.md").write_text(
            "See the [protocol](../knowledge/protocol.md).\n", encoding="utf-8"
        )
        staging = tmp_path / "staging"
        stage_docs(repo, staging)
        guide = (staging / "developer-guide" / "guide.md").read_text(encoding="utf-8")
        assert "(../knowledge/protocol.md)" in guide


class TestReservedPrefixGuard:
    def test_docs_output_without_schemas_passes(self, tmp_path: Path) -> None:
        (tmp_path / "index.html").write_bytes(b"<html></html>")
        ensure_reserved_prefix_free(tmp_path)

    def test_docs_output_with_schemas_fails_closed(self, tmp_path: Path) -> None:
        (tmp_path / "schemas").mkdir()
        (tmp_path / "schemas" / "index.html").write_bytes(b"<html></html>")
        with pytest.raises(ValueError, match="reserved"):
            ensure_reserved_prefix_free(tmp_path)


@pytest.mark.skipif(
    not MKDOCS_AVAILABLE,
    reason="docs dependency group not installed; the required gate must not"
    " depend on the docs build tooling",
)
class TestBuildSiteWithDocs:
    def test_combined_site_renders_docs_and_mirrors_schemas(
        self, tmp_path: Path
    ) -> None:
        output = tmp_path / "site"
        published = build_site(COMMITTED_SCHEMAS_ROOT, output, include_docs=True)
        assert published == ("schemas/termverify.transcript/v1.schema.json",)
        landing = (output / "index.html").read_text(encoding="utf-8")
        assert "TermVerify" in landing
        assert (output / "knowledge" / "protocol" / "index.html").is_file()
        assert (
            output / "developer-guide" / "schema-publication" / "index.html"
        ).is_file()
        assert not (output / "agent").exists()
        mirrored = output / "schemas" / TRANSCRIPT_V1_RELATIVE
        committed = COMMITTED_SCHEMAS_ROOT / TRANSCRIPT_V1_RELATIVE
        assert mirrored.read_bytes() == committed.read_bytes()

    def test_okf_frontmatter_does_not_leak_into_rendered_pages(
        self, tmp_path: Path
    ) -> None:
        output = tmp_path / "site"
        build_site(COMMITTED_SCHEMAS_ROOT, output, include_docs=True)
        rendered = (output / "knowledge" / "protocol" / "index.html").read_text(
            encoding="utf-8"
        )
        assert "type: Protocol Design" not in rendered


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


class TestPublishedUrl:
    def test_joins_base_and_schema_path(self) -> None:
        url = published_url("https://termverify.dev", Path("example/v1.schema.json"))
        assert url == "https://termverify.dev/schemas/example/v1.schema.json"

    def test_trailing_slash_on_base_is_normalized(self) -> None:
        url = published_url("https://termverify.dev/", Path("example/v1.schema.json"))
        assert url == "https://termverify.dev/schemas/example/v1.schema.json"


class TestVerifyWithRetry:
    URL = "https://termverify.dev/schemas/example/v1.schema.json"

    def test_transient_fetch_errors_are_retried_until_success(self) -> None:
        outcomes: list[object] = [OSError("no route"), OSError("reset"), b"ok\n"]
        delays: list[float] = []

        def fetcher(url: str) -> bytes:
            outcome = outcomes.pop(0)
            if isinstance(outcome, bytes):
                return outcome
            raise cast(OSError, outcome)

        verify_with_retry(
            self.URL,
            b"ok\n",
            fetcher=fetcher,
            attempts=5,
            delay_seconds=7.0,
            sleep=delays.append,
        )
        assert not outcomes
        assert delays == [7.0, 7.0]

    def test_stale_bytes_are_retried_then_fail_after_all_attempts(self) -> None:
        calls: list[str] = []
        delays: list[float] = []

        def fetcher(url: str) -> bytes:
            calls.append(url)
            return b"stale\n"

        with pytest.raises(AssertionError, match="does not match"):
            verify_with_retry(
                self.URL,
                b"fresh\n",
                fetcher=fetcher,
                attempts=3,
                delay_seconds=1.0,
                sleep=delays.append,
            )
        assert calls == [self.URL] * 3
        assert delays == [1.0, 1.0]

    def test_immediate_match_neither_retries_nor_sleeps(self) -> None:
        delays: list[float] = []
        verify_with_retry(
            self.URL,
            b"ok\n",
            fetcher=lambda url: b"ok\n",
            attempts=5,
            delay_seconds=9.0,
            sleep=delays.append,
        )
        assert delays == []
