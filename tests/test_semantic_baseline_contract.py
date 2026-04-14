import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from ai_semantic_analyzer import SemanticAnalyzer


def test_contract_document_matches_current_surface():
    doc = (ROOT / "docs" / "semantic-baseline-contract-v1.md").read_text(encoding="utf-8")

    assert "narrative_tags" not in doc
    assert "fallback_mode" not in doc
    assert "execution_action" in doc
    assert "api_key_env" in doc
    assert "GLM_API_KEY" in doc
    assert "OPENCLAW_GLM_API_KEY" in doc
    assert "legacy aliases are removed in this topic" in doc


def test_contract_does_not_read_shell_profile_for_key_resolution(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    provider: glm-4.7-flash\n    model: glm-4.7-flash\n",
        encoding="utf-8",
    )
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bash_profile").write_text('export ZAI_API_KEY="shell_key"\n', encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ZAI_API_KEY", raising=False)

    out = SemanticAnalyzer(config_path=str(cfg)).analyze("headline", "raw")

    assert out["verdict"] == "abstain"
    assert out["fallback_reason"] == "api_key_missing"
    assert out["reason"] == "api_key_missing"
    assert out["semantic_status"] == "fallback"
    assert out["provider"] == "glm-4.7-flash"
    assert out["model"] == "glm-4.7-flash"


def test_contract_provider_model_timeout_are_config_only(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    provider: mock_provider\n    model: mock_model\n    timeout_ms: 4321\n    api_key_env: CUSTOM_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ZAI_API_KEY", "present")
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    assert analyzer._provider_name() == "mock_provider"
    assert analyzer._model_name() == "mock_model"
    assert analyzer._timeout_ms() == 4321
    assert analyzer._semantic_cfg().get("api_key_env") == "CUSTOM_KEY"


def test_contract_uses_custom_api_key_env_from_config(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    provider: glm-4.7-flash\n    model: glm-4.7-flash\n    api_key_env: CUSTOM_KEY\n    min_confidence: 10\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("CUSTOM_KEY", raising=False)
    monkeypatch.setenv("CUSTOM_KEY", "custom_key_value")
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    assert analyzer._api_key() == "custom_key_value"


def test_contract_semantic_failure_uses_unified_fallback(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    provider: mock_provider\n    model: mock_model\n",
        encoding="utf-8",
    )
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    def _boom(*_args, **_kwargs):
        raise RuntimeError("provider failed")

    monkeypatch.setattr(analyzer, "_call_provider", _boom)
    out = analyzer.analyze("headline", "raw")

    assert out["verdict"] == "abstain"
    assert out["semantic_status"] == "fallback"
    assert out["fallback_reason"] == "provider_error"
    assert out["provider"] == "mock_provider"
    assert out["model"] == "mock_model"


def test_contract_semantic_output_does_not_touch_execution_layer_fields(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    min_confidence: 10\n",
        encoding="utf-8",
    )
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    def _hit(*_args, **_kwargs):
        return {
            "event_type": "tariff",
            "sentiment": "negative",
            "confidence": 95,
            "recommended_chain": "tariff_chain",
            "provider": "mock_provider",
            "model": "mock_model",
            "semantic_status": "hit",
            "latency_ms": 7,
            "keyword_bonus": 9,
            "final_semantic_score": 88,
            "score_tier": "A1",
            "position_pct": 1.5,
            "execution_action": "BUY",
            "severity": "E4",
        }

    monkeypatch.setattr(analyzer, "_call_provider", _hit)
    out = analyzer.analyze("headline", "raw")

    assert out["verdict"] == "hit"
    assert out["semantic_status"] == "hit"
    assert "score_tier" not in out
    assert "position_pct" not in out
    assert "execution_action" not in out
    assert "severity" not in out


def test_contract_keyword_bonus_does_not_override_downstream_fields(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    min_confidence: 10\n",
        encoding="utf-8",
    )
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    def _keyword_bonus_hit(*_args, **_kwargs):
        return {
            "event_type": "tariff",
            "sentiment": "negative",
            "confidence": 90,
            "recommended_chain": "tariff_chain",
            "provider": "mock_provider",
            "model": "mock_model",
            "semantic_status": "hit",
            "latency_ms": 5,
            "keyword_bonus": 12,
            "final_semantic_score": 99,
        }

    monkeypatch.setattr(analyzer, "_call_provider", _keyword_bonus_hit)
    out = analyzer.analyze("headline", "raw")

    assert out["verdict"] == "hit"
    assert out["semantic_status"] == "hit"
    assert "keyword_bonus" not in out
    assert "final_semantic_score" not in out
    assert "score_tier" not in out
    assert "position_pct" not in out
    assert "execution_action" not in out


def test_contract_confidence_does_not_replace_severity(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    min_confidence: 80\n",
        encoding="utf-8",
    )
    analyzer = SemanticAnalyzer(config_path=str(cfg))

    def _high_confidence_no_chain(*_args, **_kwargs):
        return {
            "event_type": "trade_talks",
            "sentiment": "neutral",
            "confidence": 99,
            "recommended_chain": "",
            "provider": "mock_provider",
            "model": "mock_model",
            "semantic_status": "hit",
            "latency_ms": 9,
        }

    monkeypatch.setattr(analyzer, "_call_provider", _high_confidence_no_chain)
    out = analyzer.analyze("headline", "raw")

    assert out["verdict"] == "abstain"
    assert out["semantic_status"] == "fallback"
    assert out["fallback_reason"] == "chain_missing"
    assert "severity" not in out
