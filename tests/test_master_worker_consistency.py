import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from realtime_news_monitor import RealtimeNewsMonitor


def _build_monitor(monkeypatch, role: str):
    def _fake_load(self):
        self.event_capture = None
        self.data_adapter = None
        self.workflow = None

    monkeypatch.setattr(RealtimeNewsMonitor, "_load_news_module", _fake_load)
    monkeypatch.setenv("EDT_NODE_ROLE", role)
    return RealtimeNewsMonitor(api_url="http://127.0.0.1:18787")


def test_worker_does_not_publish_main_chain_events(monkeypatch):
    monitor = _build_monitor(monkeypatch, "worker")
    assert monitor._can_publish_main_chain() is False


def test_master_can_publish_main_chain_events(monkeypatch):
    monitor = _build_monitor(monkeypatch, "master")
    assert monitor._can_publish_main_chain() is True


def test_worker_push_is_skipped_without_network_call(monkeypatch):
    monitor = _build_monitor(monkeypatch, "worker")

    def _fail_urlopen(*_args, **_kwargs):
        raise AssertionError("worker should not call network")

    import urllib.request

    monkeypatch.setattr(urllib.request, "urlopen", _fail_urlopen)
    monitor._push_to_c_module({"x": 1}, "http://127.0.0.1:18787")
