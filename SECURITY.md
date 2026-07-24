# Security Policy

## Supported versions

TermVerify is in its prototyping stage (see the
[recorded governance decision](docs/agent/design/prototyping-stage-protocol-governance.md)).
termverify 0.1.0 was published to PyPI on 2026-07-19 as a
distribution-pipeline exercise; it is **not** a supported artifact — it
receives no security fixes and carries no compatibility guarantee. Security
fixes land on the `main` branch only. When supported releases exist, this
table will list which versions receive fixes.

| Version | Supported |
| --- | --- |
| `main` | ✅ latest commit only |
| 0.1.0 (PyPI) | ❌ pipeline exercise; use `main` |

## Reporting a vulnerability

Please report suspected vulnerabilities privately through
[GitHub private vulnerability reporting](https://github.com/hoelzl/termverify/security/advisories/new).
Do not open a public issue for a suspected vulnerability and do not include
secrets or sensitive evidence in a report.

What to expect:

- Acknowledgement of your report, normally within seven days.
- An assessment of impact and affected scope, coordinated with you before any
  public disclosure.
- Credit in the advisory if you wish.

This is a volunteer-maintained project; the timelines above are intentions,
not a contractual service level.

## Scope notes

- TermVerify treats terminal output as evidence and applies fail-closed
  classification and redaction before persistence. Reports that show sensitive
  data escaping the safe-evidence boundary are in scope and high priority.
- The deterministic core makes no OS-containment claim: filesystem and network
  configuration values are requested policy, not proof of enforcement.
  Reports that demonstrate termverify claiming enforcement it does not provide
  are in scope.
- Vulnerabilities in dependencies are tracked by scheduled OSV-Scanner runs;
  reports for issues already fixed upstream should reference the advisory.
