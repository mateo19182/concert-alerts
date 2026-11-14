import json
from pathlib import Path

import pytest

from concert_alerts.region import Region

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def spain():
    return Region.from_config({"preferred_areas": json.loads((EXAMPLES / "preferred-areas.spain.json").read_text())})
