import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from data_adapter import DataAdapter


def test_data_adapter_fetch():
    data = DataAdapter().fetch()
    assert "news" in data
    assert "market_data" in data
    assert "headline" in data["news"]
    assert "vix_level" in data["market_data"]
    assert "sector_data" in data
    assert isinstance(data["sector_data"], list)

