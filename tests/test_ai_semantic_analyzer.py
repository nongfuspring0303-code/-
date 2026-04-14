import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import ai_semantic_analyzer as semmod
from ai_semantic_analyzer import SemanticAnalyzer


def test_semantic_analyzer_disabled_returns_abstain(tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("modules: {}\nruntime:\n  semantic:\n    enabled: false\n", encoding="utf-8")
    out = SemanticAnalyzer(config_path=str(cfg)).analyze("headline", "")
    assert out["verdict"] == "abstain"
    assert out["fallback_reason"] == "semantic_disabled"


def test_semantic_analyzer_emergency_disable_returns_abstain(tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    emergency_disable: true\n",
        encoding="utf-8",
    )
    out = SemanticAnalyzer(config_path=str(cfg)).analyze("headline", "")
    assert out["verdict"] == "abstain"
    assert out["fallback_reason"] == "emergency_disabled"


def test_semantic_analyzer_full_enable_false_returns_abstain(tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    full_enable: false\n",
        encoding="utf-8",
    )
    out = SemanticAnalyzer(config_path=str(cfg)).analyze("headline", "")
    assert out["verdict"] == "abstain"
    assert out["fallback_reason"] == "full_enable_disabled"


def test_semantic_analyzer_timeout_returns_abstain(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("modules: {}\nruntime:\n  semantic:\n    enabled: true\n", encoding="utf-8")
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    def _raise_timeout(*_args, **_kwargs):
        raise TimeoutError("provider timed out")

    monkeypatch.setattr(analyzer, "_call_provider", _raise_timeout)
    out = analyzer.analyze("headline", "")
    assert out["verdict"] == "abstain"
    assert out["fallback_reason"] == "timeout"


def test_semantic_analyzer_provider_error_returns_abstain(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text("modules: {}\nruntime:\n  semantic:\n    enabled: true\n", encoding="utf-8")
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    def _raise_provider_error(*_args, **_kwargs):
        raise RuntimeError("provider crashed")

    monkeypatch.setattr(analyzer, "_call_provider", _raise_provider_error)
    out = analyzer.analyze("headline", "")
    assert out["verdict"] == "abstain"
    assert out["fallback_reason"] == "provider_error"


def test_semantic_analyzer_low_confidence_triggers_fallback(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    min_confidence: 80\n",
        encoding="utf-8",
    )
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    def _low_confidence(*_args, **_kwargs):
        return {
            "event_type": "tariff",
            "sentiment": "negative",
            "confidence": 60,
            "recommended_chain": "tariff_chain",
            "provider": "mock_provider",
            "latency_ms": 12,
        }

    monkeypatch.setattr(analyzer, "_call_provider", _low_confidence)
    out = analyzer.analyze("headline", "")
    assert out["verdict"] == "abstain"
    assert out["fallback_reason"] == "confidence_below_threshold"


def test_semantic_analyzer_high_confidence_without_chain_has_specific_fallback(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    min_confidence: 70\n",
        encoding="utf-8",
    )
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    def _high_conf_no_chain(*_args, **_kwargs):
        return {
            "event_type": "trade_talks",
            "sentiment": "neutral",
            "confidence": 90,
            "recommended_chain": "",
            "provider": "mock_provider",
            "latency_ms": 8,
        }

    monkeypatch.setattr(analyzer, "_call_provider", _high_conf_no_chain)
    out = analyzer.analyze("headline", "")
    assert out["verdict"] == "abstain"
    assert out["fallback_reason"] == "chain_missing"


def test_semantic_analyzer_normal_hit_contains_provider(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    min_confidence: 70\n    provider: mock_vendor\n",
        encoding="utf-8",
    )
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    def _high_confidence(*_args, **_kwargs):
        return {
            "event_type": "trade_talks",
            "sentiment": "neutral",
            "confidence": 90,
            "recommended_chain": "trade_talks_chain",
            "provider": "mock_vendor",
            "latency_ms": 10,
        }

    monkeypatch.setattr(analyzer, "_call_provider", _high_confidence)
    out = analyzer.analyze("Trump-Xi trade meeting", "capital flows")
    assert out["verdict"] == "hit"
    assert out["provider"] == "mock_vendor"


def test_semantic_analyzer_preserves_recommended_stocks(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    min_confidence: 10\n",
        encoding="utf-8",
    )
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    def _with_recommendations(*_args, **_kwargs):
        return {
            "event_type": "monetary",
            "sentiment": "positive",
            "confidence": 90,
            "recommended_chain": "rate_cut_chain",
            "recommended_stocks": ["nvda", "aapl"],
            "provider": "mock_vendor",
            "latency_ms": 10,
        }

    monkeypatch.setattr(analyzer, "_call_provider", _with_recommendations)
    out = analyzer.analyze("Fed signals rate cuts ahead", "policy easing expected")

    assert out["verdict"] == "hit"
    assert out["recommended_stocks"] == ["nvda", "aapl"]


def test_semantic_analyzer_missing_api_key_falls_back(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    provider: glm-4.7-flash\n    model: glm-4.7-flash\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("GLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENCLAW_GLM_API_KEY", raising=False)

    out = SemanticAnalyzer(config_path=str(cfg)).analyze("headline", "raw")

    assert out["verdict"] == "abstain"
    assert out["fallback_reason"] == "api_key_missing"
    assert out["reason"] == "api_key_missing"
    assert out["semantic_status"] == "fallback"


def test_semantic_analyzer_uses_model_from_config(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    provider: glm-4.7-flash\n    model: glm-4.7-flash-custom\n    min_confidence: 10\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZAI_API_KEY", "test_key")
    captured = {}

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"event_type":"trade_talks","sentiment":"neutral","confidence":90,"recommended_chain":"trade_talks_chain","reason":"ok"}'
                        }
                    }
                ]
            }

    def _fake_post(_url, headers=None, json=None, timeout=None):
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(semmod.requests, "post", _fake_post)
    out = SemanticAnalyzer(config_path=str(cfg)).analyze("headline", "raw")

    assert out["verdict"] == "hit"
    assert captured["json"]["model"] == "glm-4.7-flash-custom"
