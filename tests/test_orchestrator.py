import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from edt_module_base import EDTModule, ModuleInput, ModuleOutput, ModuleStatus
from orchestrator import OrchestratorNode


class _SuccessModule(EDTModule):
    def __init__(self):
        super().__init__("Success", "1.0.0")

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        return ModuleOutput(status=ModuleStatus.SUCCESS, data={"ok": True})


class _AlwaysFailModule(EDTModule):
    def __init__(self):
        super().__init__("Fail", "1.0.0")

    def execute(self, input_data: ModuleInput) -> ModuleOutput:
        return ModuleOutput(
            status=ModuleStatus.FAILED,
            data={},
            errors=[{"code": "TIMEOUT", "message": "simulated timeout"}],
        )


def test_orchestrator_success(monkeypatch):
    node = OrchestratorNode()
    monkeypatch.setattr(node, "_get_module", lambda node_type: _SuccessModule())

    out = node.run({"trace_id": "TRC-OK", "node_type": "ai_event_intel", "payload": {"k": "v"}})

    assert out.status == ModuleStatus.SUCCESS
    assert out.data["status"] == "SUCCESS"
    assert out.data["fallback_used"] is False
    assert out.data["attempts"] == 1


def test_orchestrator_timeout_fallback(monkeypatch):
    node = OrchestratorNode()
    monkeypatch.setattr(node, "_get_module", lambda node_type: _AlwaysFailModule())

    out = node.run(
        {
            "trace_id": "TRC-TIMEOUT",
            "node_type": "ai_event_intel",
            "payload": {},
            "retry": {"max_attempts": 2, "backoff_factor": 0, "retry_on": ["TIMEOUT"]},
            "fallback": {"enabled": True, "default_action": "WATCH"},
        }
    )

    assert out.status == ModuleStatus.SUCCESS
    assert out.data["status"] == "FALLBACK"
    assert out.data["fallback_used"] is True
    assert out.data["attempts"] == 2


def test_orchestrator_circuit_opens(monkeypatch):
    node = OrchestratorNode()
    monkeypatch.setattr(node, "_get_module", lambda node_type: _AlwaysFailModule())

    base_input = {
        "trace_id": "TRC-CB",
        "node_type": "ai_event_intel",
        "payload": {},
        "retry": {"max_attempts": 1, "backoff_factor": 0, "retry_on": ["TIMEOUT"]},
        "circuit_breaker": {"failure_threshold": 2, "recovery_timeout_ms": 100000},
    }

    first = node.run(dict(base_input))
    second = node.run(dict(base_input))
    third = node.run(dict(base_input))

    assert first.data["status"] == "FALLBACK"
    assert second.data["status"] == "FALLBACK"
    assert third.data["status"] == "CIRCUIT_OPEN"
