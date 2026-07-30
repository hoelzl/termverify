"""Shared pytest configuration for the suite.

Hypothesis profiles (owner decision 2026-07-24, review Slice 8.3): the CI
profile is derandomized so a build's property-test verdict is reproducible
from its logs alone; local runs stay exploratory (unseeded) so new
counterexamples keep surfacing during development. The profile is selected
by the ``CI`` environment variable that GitHub Actions always sets.
"""

import os

from hypothesis import settings

settings.register_profile("ci", derandomize=True)
settings.register_profile("local")
settings.load_profile("ci" if os.environ.get("CI") else "local")
