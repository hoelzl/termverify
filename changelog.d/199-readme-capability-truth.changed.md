- **The README now lists only capabilities that exist, and the rest is stated
  once in the product vision.** Four of its six promised capabilities —
  property/state-machine testing, reviewed golden snapshots, differential
  testing, and failure minimization / CI artifacts — were written in the
  present tense with nothing in `src/` behind them (finding P5 of the
  2026-07-24 adversarial review). "What TermVerify does today" now names the
  implementing module for every claim, and `docs/knowledge/product-vision.md`
  is the single source for planned scope, each entry saying plainly what does
  not exist and what it waits on. The README's "Planned architecture" diagram
  moved there rather than being duplicated; `docs/knowledge/architecture.md`
  marks its own rows `[built]` / `[planned]`. `tests/test_readme_capability_truth.py`
  gives the split a ratchet: every module the README names must import, the
  vision document must be linked exactly once, and no deferred capability may
  reappear in the current-capability section.
