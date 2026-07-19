"""Assemble the static termverify.dev site for GitHub Pages deployment.

The published site is a pure function of committed repository content: every
schema resource under ``src/termverify/schemas`` is copied byte-for-byte to
``/schemas/<protocol>/<version>.schema.json``, and the site root carries the
curated human-facing documentation (``README.md`` as the landing page plus
``docs/knowledge/`` and ``docs/developer-guide/``, rendered with MkDocs) or,
without ``--docs``, a minimal generated landing page. ``docs/agent/`` is
never staged, and the ``/schemas/`` prefix is reserved: a docs build that
emits anything under it fails closed. The build also fails closed on any
unexpected file in the schema tree and refuses a non-empty output directory
so stale content can never leak into a deployment.

This is deploy-workflow tooling only. It never joins the required build/test
path, and nothing in the library depends on it.
"""

from __future__ import annotations

import argparse
import posixpath
import re
import shutil
import subprocess
import sys
from pathlib import Path

CANONICAL_BASE_URL = "https://termverify.dev"
SITE_SCHEMA_PREFIX = "schemas"
DEFAULT_SCHEMAS_ROOT = Path("src/termverify/schemas")
DEFAULT_REPO_ROOT = Path()
STAGED_DOCS_DIRECTORY = ".site-docs"
CURATED_DOC_TREES = ("knowledge", "developer-guide")
REPOSITORY_BLOB_BASE = "https://github.com/hoelzl/termverify/blob/main"

_MARKDOWN_LINK = re.compile(r"(\]\()([^)\s]+)(\))")
_EXTERNAL_TARGET = re.compile(r"^(?:[a-z][a-z0-9+.-]*:|#)")

_PROTOCOL_DIRECTORY = re.compile(r"^[a-z0-9._-]+$")
_SCHEMA_FILE = re.compile(r"^v[1-9][0-9]*\.schema\.json$")


def discover_schema_resources(schemas_root: Path) -> tuple[Path, ...]:
    """Return committed schema resources relative to ``schemas_root``.

    Every file must sit exactly one directory deep as
    ``<protocol>/<version>.schema.json``; anything else fails closed.
    """
    if not schemas_root.is_dir():
        raise ValueError(f"schema root {schemas_root} is not a directory")
    resources: list[Path] = []
    for path in sorted(schemas_root.rglob("*")):
        if path.is_symlink():
            relative = path.relative_to(schemas_root)
            raise ValueError(
                f"symlink in schema tree: {relative.as_posix()!r};"
                " only regular files are publishable"
            )
        if path.is_dir():
            continue
        relative = path.relative_to(schemas_root)
        if not (
            len(relative.parts) == 2
            and _PROTOCOL_DIRECTORY.match(relative.parts[0]) is not None
            and _SCHEMA_FILE.match(relative.parts[1]) is not None
        ):
            raise ValueError(
                f"unexpected file in schema tree: {relative.as_posix()!r};"
                " only <protocol>/<version>.schema.json is publishable"
            )
        resources.append(relative)
    if not resources:
        raise ValueError(f"no schema resources found under {schemas_root}")
    return tuple(resources)


def _landing_page(published: tuple[str, ...]) -> str:
    links = "\n".join(
        f'      <li><a href="/{path}">{CANONICAL_BASE_URL}/{path}</a></li>'
        for path in published
    )
    return f"""<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>TermVerify</title>
  </head>
  <body>
    <h1>TermVerify</h1>
    <p>
      A Python library and reference tooling for verifying autonomous
      terminal applications: deterministic behavior, replayable evidence,
      and human review as product features.
    </p>
    <p>
      Source, documentation, and issues:
      <a href="https://github.com/hoelzl/termverify">github.com/hoelzl/termverify</a>
    </p>
    <h2>Canonical schemas</h2>
    <ul>
{links}
    </ul>
    <p>
      Schemas published here mirror the committed repository resources
      byte-for-byte. They are non-exhaustive structural aids; runtime
      validation remains authoritative for protocol acceptance.
    </p>
  </body>
</html>
"""


def _staged_location(repo_relative: str) -> str | None:
    """Map a repo-relative posix path to its staged path, if it is staged."""
    if repo_relative == "README.md":
        return "index.md"
    for tree in CURATED_DOC_TREES:
        if repo_relative.startswith(f"docs/{tree}/"):
            return repo_relative[len("docs/") :]
    return None


def _rewrite_links(text: str, source_repo_dir: str, staged_dir: str) -> str:
    """Rewrite relative Markdown links for the staged location of one file.

    Targets that resolve to staged content are remapped relative to the
    file's staged directory; targets that resolve to unpublished repository
    files become GitHub URLs so the rendered site never links into content
    it does not carry. External, anchor-only, and repository-escaping
    targets are left untouched.
    """

    def replace(match: re.Match[str]) -> str:
        target = match.group(2)
        if _EXTERNAL_TARGET.match(target):
            return match.group(0)
        path_part, _, fragment = target.partition("#")
        suffix = f"#{fragment}" if fragment else ""
        repo_relative = posixpath.normpath(
            posixpath.join(source_repo_dir, path_part) if source_repo_dir else path_part
        )
        if repo_relative.startswith(".."):
            return match.group(0)
        staged_target = _staged_location(repo_relative)
        if staged_target is not None:
            rewritten = posixpath.relpath(staged_target, staged_dir or ".")
        else:
            rewritten = f"{REPOSITORY_BLOB_BASE}/{repo_relative}"
        return f"{match.group(1)}{rewritten}{suffix}{match.group(3)}"

    return _MARKDOWN_LINK.sub(replace, text)


def _stage_file(
    source: Path, target: Path, source_repo_dir: str, staged_dir: str
) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if source.suffix.lower() != ".md":
        shutil.copyfile(source, target)
        return
    rewritten = _rewrite_links(
        source.read_text(encoding="utf-8"), source_repo_dir, staged_dir
    )
    target.write_text(rewritten, encoding="utf-8", newline="\n")


def stage_docs(repo_root: Path, staging_dir: Path) -> None:
    """Assemble the curated MkDocs source tree from committed content only.

    ``README.md`` becomes ``index.md`` and the curated ``docs/`` trees are
    copied verbatim. ``docs/agent/`` is deliberately never staged. Missing
    sources and a non-empty staging directory fail closed.
    """
    if staging_dir.exists():
        if not staging_dir.is_dir():
            raise ValueError(f"staging path {staging_dir} is not a directory")
        if any(staging_dir.iterdir()):
            raise ValueError(f"staging directory {staging_dir} is not empty")
    readme = repo_root / "README.md"
    if not readme.is_file():
        raise ValueError(f"missing landing-page source {readme}")
    sources = {tree: repo_root / "docs" / tree for tree in CURATED_DOC_TREES}
    for tree, source in sources.items():
        if not source.is_dir():
            raise ValueError(f"missing curated docs tree {tree!r} at {source}")
    staging_dir.mkdir(parents=True, exist_ok=True)
    _stage_file(readme, staging_dir / "index.md", source_repo_dir="", staged_dir="")
    for tree, source in sources.items():
        for file in sorted(path for path in source.rglob("*") if path.is_file()):
            relative = file.relative_to(source)
            staged_parent = (
                f"{tree}/{relative.parent.as_posix()}"
                if relative.parent != Path()
                else tree
            )
            _stage_file(
                file,
                staging_dir / tree / relative,
                source_repo_dir=f"docs/{staged_parent}",
                staged_dir=staged_parent,
            )


def ensure_reserved_prefix_free(site_dir: Path) -> None:
    """Fail closed if a docs build emitted content under ``/schemas/``."""
    reserved = site_dir / SITE_SCHEMA_PREFIX
    if reserved.exists():
        raise ValueError(
            f"docs build emitted content under the reserved"
            f" /{SITE_SCHEMA_PREFIX}/ prefix: {reserved}"
        )


def _build_docs(repo_root: Path, output_dir: Path) -> None:
    staging_dir = repo_root / STAGED_DOCS_DIRECTORY
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    stage_docs(repo_root, staging_dir)
    try:
        subprocess.run(  # noqa: S603 - fixed argv, no shell
            [
                sys.executable,
                "-m",
                "mkdocs",
                "build",
                "--strict",
                "--config-file",
                str(repo_root / "mkdocs.yml"),
                "--site-dir",
                str(output_dir.resolve()),
            ],
            check=True,
        )
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)
    ensure_reserved_prefix_free(output_dir)


def build_site(
    schemas_root: Path,
    output_dir: Path,
    *,
    include_docs: bool = False,
    repo_root: Path = DEFAULT_REPO_ROOT,
) -> tuple[str, ...]:
    """Build the site into ``output_dir`` and return published schema paths."""
    if output_dir.exists():
        if not output_dir.is_dir():
            raise ValueError(f"output path {output_dir} is not a directory")
        if any(output_dir.iterdir()):
            raise ValueError(f"output directory {output_dir} is not empty")
    resources = discover_schema_resources(schemas_root)
    published = tuple(
        f"{SITE_SCHEMA_PREFIX}/{resource.as_posix()}" for resource in resources
    )
    if include_docs:
        _build_docs(repo_root, output_dir)
    for resource in resources:
        target = output_dir / SITE_SCHEMA_PREFIX / resource
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(schemas_root / resource, target)
    if not include_docs:
        (output_dir / "index.html").write_text(
            _landing_page(published), encoding="utf-8", newline="\n"
        )
    return published


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "output_dir",
        type=Path,
        help="directory to assemble the site into (must be absent or empty)",
    )
    parser.add_argument(
        "--schemas-root",
        type=Path,
        default=DEFAULT_SCHEMAS_ROOT,
        help="committed schema resource tree (default: %(default)s)",
    )
    parser.add_argument(
        "--docs",
        action="store_true",
        help="render the curated documentation site (requires the locked"
        " docs dependency group) instead of the minimal landing page",
    )
    arguments = parser.parse_args()
    published = build_site(
        arguments.schemas_root,
        arguments.output_dir,
        include_docs=arguments.docs,
    )
    for path in published:
        print(f"published {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
