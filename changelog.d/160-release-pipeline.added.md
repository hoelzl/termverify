- **Release pipeline.** CI-gated merge-driven release workflow: a `Bump
  version` commit on `main` (or an explicit matching `vX.Y.Z` tag push) waits
  for CI green on the commit, creates the annotated tag only after the gate,
  builds and contract-checks sdist and wheel, attests build provenance,
  publishes to PyPI via OIDC trusted publishing (`pypi` environment, no stored
  tokens), and creates the GitHub release with the extracted changelog
  section. Version management uses bump-my-version with `pyproject.toml` as
  the single source of truth. (PRs #160, #161; first exercised for 0.1.0.)
