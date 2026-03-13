"""pytest conftest for archetypal integration tests."""

import os

import pytest

from helpers import load_case

FIXTURE_DIR = os.path.dirname(__file__)


@pytest.fixture
def case():
    """Load the integration test case (10 hosts x 15 sections)."""
    return load_case(FIXTURE_DIR)
