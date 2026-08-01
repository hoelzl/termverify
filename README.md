# TermVerify

Protocol-driven verification for autonomous terminal applications.

TermVerify is a Python library and reference toolkit for testing terminal and TUI applications through reproducible interaction. It combines direct semantic adapters with real pseudoconsole-driven runs, then compares structured observations rather than relying only on brittle raw-terminal snapshots.

## Why

An autonomous coding agent is most reliable when it can make a change, exercise the actual program, observe meaningful results, and leave behind replayable evidence. Terminal applications need this especially badly: unit tests alone do not prove that key bindings, focus, rendering, prompts, and real interaction work.

## What TermVerify does today

Every item below is implemented and covered by the test suite; the named
module is where it lives.

- **A strict transcript codec and semantic validator** — `termverify.transcript`
  parses, validates, and canonically serializes `termverify.transcript/v1`
  JSONL, and is authoritative for what the protocol accepts. A packaged
  Draft 2020-12 schema (`termverify.schema`) is a non-exhaustive structural
  aid alongside it.
- **An immutable producer-side adapter contract** — `termverify.adapter`
  defines the run configuration, semantic inputs, observations, and the
  constraint receipts an adapter must produce to make a run replayable.
- **A deterministic in-process runtime** — `termverify.direct` drives a
  subject through input and clock epochs with no terminal, clock, or
  filesystem ambient state.
- **A terminal adapter with a VT normalizer** — `termverify.terminal` drives a
  subject through a pseudoterminal binding port (spawn, drain, resize,
  process-tree teardown, cancellation) and `termverify.vt` turns its byte
  stream into comparable screen state. The adapter names no platform; the
  binding with end-to-end evidence behind it is `ConptyBinding`, which owns a
  real Windows pseudoconsole.
- **Opt-in cooperation-tier constraint ports** — `termverify.cooperation`
  delivers the six non-terminal constraints to the subject's environment,
  within documented per-constraint limits (only `UTC` for timezone, only
  `deny` for network, mapped roots for filesystem — anything else is
  refused), and reports them at the truthful `delivered` tier, never
  claiming enforcement it does not perform.
- **A JSONL subprocess transport** — `termverify.jsonl` and
  `termverify.control` run an out-of-process subject over the
  `termverify.control/v1` wire protocol.
- **Recording, comparison, and replay** — `termverify.recorder` turns a run
  into a transcript, `termverify.comparator` compares two transcripts by
  exact closed equivalence with a deterministic report, and
  `termverify.replay` re-drives a recorded run against a caller-supplied
  adapter — the recorded subject selector is disclosed, never resolved or
  launched. `termverify.evidence` is the safe-persistence boundary every
  verified run is expected to write through.

## Where TermVerify is going

The capabilities above are the foundation, not the destination — property and
state-machine testing, reviewed golden snapshots, differential testing,
failure minimization, CI artifacts, and a verified POSIX terminal path are all
intended and none of them exist yet as capabilities you can rely on. They are described once, with their sequencing, in
[the product vision](docs/knowledge/product-vision.md); this README
deliberately does not restate them.

## Project status

The repository is in its foundation phase; the capabilities above are what
that phase has produced. This section covers release and support status only.

**termverify 0.1.0 was published to PyPI on 2026-07-19**, and 0.1.1 followed,
both through a CI-gated, merge-driven attested release workflow — landing a
version-bump commit on `main` is what publishes; the workflow creates the tag
after the gate passes, and an explicit tag is the fallback path. Those
publications were a distribution-pipeline exercise, not a stability promise:
TermVerify is in its **prototyping stage**, no backward compatibility is
guaranteed for any published artifact, and protocols and APIs may change
incompatibly without notice until the owner declares readiness for external
clients (recorded governance decision:
[prototyping-stage protocol governance](docs/agent/design/prototyping-stage-protocol-governance.md)).

Release governance is defined — changelog policy, private security
disclosure, reviewed release checklist — and a strict no-regression coverage
floor gates the full suite in CI. The canonical transcript schema ships inside
the package with a public access API, and isolated installation checks verify
the wheel and sdist resource contract. The schema's `$id` is an **identifier,
not a resolvable publication contract**: it happens to resolve at
[termverify.dev](https://termverify.dev/schemas/termverify.transcript/v1.schema.json)
as a byte-identical mirror, verified after every deployment, but consumers
must not fetch it at validation time, no gate depends on the site being
reachable, and runtime validation stays authoritative regardless.

The curated public surface is the top-level `termverify` package: the adapter
contract, the direct runtime, the authoritative codec, the schema accessors,
and the key registries' entry points are all importable from it directly. The
module paths named above remain public and equivalent — see the
[adapter-author surface](docs/developer-guide/adapter-authors.md).

Two boundaries are worth stating before you rely on a run. The terminal
adapter is platform-neutral, but its two bindings are not equally proven: the
ConPTY binding has end-to-end evidence on the Windows CI matrix, while the
POSIX binding's evidence today is at the binding itself — spawning a real
pseudoterminal, geometry, teardown — and **not yet** the adapter driving a
real subject through it end to end (issue #269). Treat the POSIX path as
unproven until that lands.

The second boundary is that constraint enforcement is tiered and honestly
reported: the shipped
cooperation ports deliver the six non-terminal constraints to the subject's
environment at the `delivered` tier, honored by subject cooperation rather
than OS enforcement. **OS-level containment is an explicit non-goal** by
recorded owner decision — TermVerify verifies applications whose authors
control the subject and is not an execution sandbox for adversarial code.
Configuration values or receipt construction alone do not prove constraint
enforcement.

## Design principles

These are commitments that govern what gets built, not a description of what
is built. Where a principle names a mechanism that does not exist yet, it is
binding on that mechanism when it arrives.

1. **Semantic evidence first.** Verify state, events, and explicit UI semantics before comparing raw ANSI output.
2. **Production interaction still matters.** PTY/terminal tests validate the application a person or agent actually drives.
3. **Determinism is a contract.** Seeds, clock, locale, terminal size, filesystem sandbox, and network policy are explicit.
4. **Human review will own baselines.** The accepted rule for the baseline mechanism is that a human approves every change against a human-readable diff, and agents never silently bless one. No baseline store exists yet; the rule is recorded in [evidence governance](docs/knowledge/evidence-governance.md) so it cannot be quietly relaxed when one is built.
5. **Harness-neutral by default.** The project works with Hermes, Claude Code, Codex, OpenCode, and ordinary CI without a required proprietary integration.

## Architecture

A subject is driven either in-process through a direct semantic adapter or
out-of-process through a pseudoconsole or JSONL transport; either way the run
produces one `termverify.transcript/v1` transcript, which is the single
artifact replay and comparison consume.

See [the knowledge bundle](docs/knowledge/index.md) for the durable
architecture and verification model, and the product-vision link above for the
layers that do not exist yet.

## Development

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer. The
minimum installer version is 3.12; the continuously supported and tested
versions are currently 3.12 through 3.14. Support for later Python releases is
not implied until they join the CI matrix.

```bash
uv --no-config sync --all-groups --locked
uv --no-config run pytest --cov --cov-report=term-missing
uv --no-config run ruff check .
uv --no-config run ruff format --check .
uv --no-config run mypy src tests scripts
uv --no-config run pre-commit run --all-files
uv --no-config run pre-commit run --hook-stage pre-push --all-files
uv --no-config build
uv --no-config run pre-commit install --hook-type pre-commit --hook-type pre-push
```

See [developer workflow](docs/developer-guide/agent-workflow.md) and [contributing guide](CONTRIBUTING.md).
External subjects implementing the producer contract start with the
[adapter-author surface](docs/developer-guide/adapter-authors.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
