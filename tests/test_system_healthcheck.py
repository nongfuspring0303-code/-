import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import system_healthcheck


def test_phase3_evidence_replay_only_warns_in_dev(monkeypatch):
    class _FakeLedger:
        def read_summary(self):
            return {
                "total_runs": 3,
                "live_run_count": 0,
                "replay_run_count": 3,
                "real_flow_evidence": False,
                "pass_rate": 1.0,
            }

    monkeypatch.setattr(system_healthcheck, "Phase3EvidenceLedger", lambda: _FakeLedger())
    out = system_healthcheck.check_phase3_evidence_ledger(mode="dev")
    assert out.status == "GREEN"
    assert out.warnings


def test_phase3_evidence_replay_only_fails_in_prod(monkeypatch):
    class _FakeLedger:
        def read_summary(self):
            return {
                "total_runs": 3,
                "live_run_count": 0,
                "replay_run_count": 3,
                "real_flow_evidence": False,
                "pass_rate": 1.0,
            }

    monkeypatch.setattr(system_healthcheck, "Phase3EvidenceLedger", lambda: _FakeLedger())
    out = system_healthcheck.check_phase3_evidence_ledger(mode="prod")
    assert out.status == "RED"
    assert out.errors
