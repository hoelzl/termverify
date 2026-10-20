# Contributing to TermVerify

Thank you for contributing. TermVerify is designed to be trustworthy infrastructure, so a small, verified change is better than a broad speculative one.

## Development loop

1. Read `AGENTS.md` and the relevant knowledge page.
2. Open or reference an issue with a precise behavioral outcome.
3. Write one focused failing test or executable transcript.
4. Run it and confirm the failure is for the intended missing behavior.
5. Implement the smallest change that makes it pass.
6. Run the focused check, then the wider validation gate.
7. Update documentation whenever behavior, architecture, protocol, or workflow changes.
8. Request independent review for nontrivial code or baseline changes.

## Local checks

```bash
uv --no-config sync --all-groups --locked
uv --no-config run python scripts/check.py          # before a commit
uv --no-config run python scripts/check.py --full   # before a push
```

The individual commands and tooling notes are in
[`docs/developer-guide/development.md`](docs/developer-guide/development.md).

## Pull requests

- Keep one coherent purpose per pull request.
- Explain the behavior being changed and the evidence that verifies it.
- Include a replay transcript or property regression for interaction failures when applicable.
- Never fold unrelated formatting, refactoring, or generated documentation into a feature change.
- Baseline/snapshot updates must include an explanation of why the new behavior is intended.

## Documentation

Follow the placement and metadata rules in [`docs/README.md`](docs/README.md);
the documentation gates in `scripts/check.py` enforce them.
