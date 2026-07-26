- **Marker-protocol corrections from the #233 adversarial review.** The
  review probed the tokenised printable readiness marker against a fresh
  oracle and the real console and found the scanner sound but the
  specification wrong in places. Measured corrections: a marker wider than
  the terminal is delivered contiguous and *honoured* — wrapping is
  screen-buffer layout, not stream content — so the token charset's
  fail-closed skip defends against cursor-addressed mid-emission corruption,
  not line wraps; the module docstring, design doc, and developer guide all
  claimed the opposite, and a new Windows integration test pins the measured
  behaviour. `_validate_marker_prefix` now rejects non-printable prefixes,
  closing a configuration path that recreated the #232 OSC-overtaking defect
  (e.g. `"\x1b]7791;"` as prefix). The subject cooperation contract now
  discloses the three measured marker-forgery channels — stray prefix
  emission in ordinary output, console input echo (`ENABLE_ECHO_INPUT`),
  and marker text inside escape-sequence payloads such as OSC titles — and
  that repeat-run transcript comparison requires run-stable token values.
  (Closes #233.)
