---
type: Protocol Design
title: Terminal interaction protocol
description: Planned event and observation contract for deterministic terminal verification.
tags: [protocol, jsonl, terminal, observations]
---

# Run configuration

Every verified run supplies explicit values for seed, terminal dimensions and capabilities, manual clock, locale, timezone, filesystem sandbox, and network policy.

# Input events

The portable protocol will use JSON Lines for events such as key chords, text paste, resize, mouse input, clock advancement, clipboard changes, and lifecycle actions. Application adapters translate those events into their native control surface.

# Observation

An observation has distinct evidence layers:

- domain state summary and ordered events;
- semantic UI regions, focus, cursor, and mode;
- optional normalized rendered frame;
- process lifecycle, exceptions, and exit status.

A rendering comparison must not conceal a domain mismatch. Applications may add domain-specific fields through documented normalizers.

# Compatibility

Protocol versioning begins before the first externally consumed schema. Additive changes are preferred; incompatible changes require a new version and migration/replay policy.
