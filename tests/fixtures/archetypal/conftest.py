"""
pytest conftest for archetypal fixture tests.

Discovers all set_* directories and parametrises tests by set.
"""

import os
from glob import glob

import pytest

from helpers import load_case

FIXTURE_DIR = os.path.dirname(__file__)

# Discover all set directories
SET_DIRS = sorted(glob(os.path.join(FIXTURE_DIR, "set_*")))
SET_NAMES = [os.path.basename(d) for d in SET_DIRS]


@pytest.fixture(params=SET_DIRS, ids=SET_NAMES)
def case(request):
    """Load one test case (one set directory)."""
    return load_case(request.param)
