- Made pre-push failures fast and diagnosable (issue #168): the pre-push
  stage now runs the cheap checks first (mypy, distribution build) and the
  multi-minute test suite last, so a trivially fixable type or packaging
  error aborts the push in seconds instead of after the full suite. The
  developer guide now documents that git's generic `error: failed to push
  some refs` means a local pre-push hook failed (not a remote race), to
  rerun `pre-commit run --hook-stage pre-push --all-files` in the
  foreground to see the failing hook's banner, and never to retry with
  `--no-verify` (which pushes commits CI will reject).
