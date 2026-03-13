"""conftest.py for integration tests."""
import os
import sys
import pytest

# Import helpers from parent (archetypal/) directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from helpers import load_case

FIXTURE_DIR = os.path.dirname(__file__)


@pytest.fixture(scope="session")
def case():
    """Load the integration fixture."""
    return load_case(FIXTURE_DIR)
