---
type: Product Vision
title: TermVerify product vision
description: A reusable verification toolkit for autonomous terminal applications.
tags: [agents, terminal, testing, verification]
---

# Problem

Terminal applications are often tested only through internal unit tests or fragile raw-output snapshots. Neither alone proves that a human or autonomous agent can drive the actual product reliably.

# Product

TermVerify supplies reusable contracts and runners for deterministic terminal interaction, structured observations, replay, comparison, property testing, and CI artifacts. It is useful for games, editors, shells, dashboards, and other TUIs.

# Primary users

- maintainers of terminal/TUI applications;
- teams building coding agents that need executable feedback;
- developers who need durable regression evidence for interaction behavior.

# Non-goals

- replacing an application's domain test suite;
- prescribing a GUI framework or agent harness;
- making raw ANSI output the source of truth;
- automatically approving changed snapshots or behavioral baselines.
- adding browser bridging before a terminal vertical slice demonstrates that its
  abstraction is needed.
