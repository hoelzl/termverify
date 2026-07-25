- **Removed the `termverify.timezone/v1` registry.** A 374-line closed registry
  pinned to IANA TZDB 2026c by tarball SHA-256, with a generator and
  digest-bound tests, existed to validate timezone requests that v1 must then
  refuse anyway: only literal `UTC` can ever be applied, because applying a
  named zone needs zone data the protocol deliberately never consults. Its one
  concrete effect was to paint v1 into a corner — a record carries no
  registry-version selector, so any future TZDB zone would have required a whole
  new protocol version (adversarial review 2026-07-24, finding P4; owner
  decision 2026-07-24). `timezone` is now a plain non-empty string.
  **This widens acceptance**: `Mars/Olympus` is a structurally valid *request*,
  exactly as `Europe/Berlin` always was, and the refusal — a `capability.result`
  with `status: "unsupported"` and a matching `run.unsupported` — is what keeps
  the evidence truthful. What has not changed is the rule that actually protects
  it: only literal `UTC` may appear as an applied effective value, enforced by
  the runtime and beyond what schema validation can express. Deleted:
  `src/termverify/_timezone_v1.py`, `scripts/generate_timezone_registry.py`, and
  the registry's tests; Git history preserves them, and any reintroduction, when
  a vertical actually demands non-UTC zones, is a fresh design with a
  registry-version selector rather than a revival of this one. (Resolves #192.)
