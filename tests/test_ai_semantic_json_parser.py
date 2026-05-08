from pathlib import Path

from ai_semantic_analyzer import SemanticAnalyzer


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "semantic_parser"


def _analyzer(tmp_path):
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "modules: {}\nruntime:\n  semantic:\n    enabled: true\n    min_confidence: 10\n",
        encoding="utf-8",
    )
    return SemanticAnalyzer(config_path=str(cfg))


def test_parse_no_json_object(tmp_path):
    out = _analyzer(tmp_path)._parse_ai_content("no json here")
    assert out["parse_status"] == "parse_failed"
    assert out["parse_error_type"] == "no_json_object"


def test_parse_invalid_json_syntax(tmp_path):
    payload = (FIXTURES / "invalid_json_payload.txt").read_text(encoding="utf-8")
    out = _analyzer(tmp_path)._parse_ai_content(payload)
    assert out["parse_status"] == "parse_failed"
    assert out["parse_error_type"] == "invalid_json_syntax"


def test_parse_root_not_object(tmp_path):
    out = _analyzer(tmp_path)._parse_ai_content("[1,2,3]")
    assert out["parse_status"] == "parse_failed"
    assert out["parse_error_type"] == "root_not_object"


def test_parse_schema_failed(tmp_path):
    out = _analyzer(tmp_path)._parse_ai_content('{"sentiment":"neutral"}')
    assert out["parse_status"] == "parse_failed"
    assert out["parse_error_type"] == "schema_failed"
    assert out["fallback_reason"] == "schema_failed"


def test_parse_recommended_stocks_not_list(tmp_path):
    out = _analyzer(tmp_path)._parse_ai_content('{"event_type":"tariff","recommended_stocks":"AAPL"}')
    assert out["parse_status"] == "parse_failed"
    assert out["parse_error_type"] == "recommended_stocks_not_list"


def test_parse_truncated_response(tmp_path):
    out = _analyzer(tmp_path)._parse_ai_content('{"event_type":"tariff"')
    assert out["parse_status"] == "parse_failed"
    assert out["parse_error_type"] == "truncated_response"


def test_parse_empty_response(tmp_path):
    out = _analyzer(tmp_path)._parse_ai_content("   ")
    assert out["parse_status"] == "parse_failed"
    assert out["parse_error_type"] == "empty_response"


def test_redacted_preview_masks_secrets_without_traceback(tmp_path):
    payload = "token=RAW_TOKEN api_key=RAW_API_KEY secret=RAW_SECRET /Users/me/private /private/tmp/abc"
    out = _analyzer(tmp_path)._parse_ai_content(payload)
    preview = out["redacted_raw_response_preview"]
    assert out["parse_status"] == "parse_failed"
    assert "raw_token" not in preview.lower()
    assert "raw_api_key" not in preview.lower()
    assert "raw_secret" not in preview.lower()
    assert "/Users/" not in preview
    assert "/private/tmp/" not in preview
    assert len(preview) <= 2000


def test_redacted_preview_masks_traceback_and_secrets(tmp_path):
    payload = (FIXTURES / "sensitive_payload.txt").read_text(encoding="utf-8")
    out = _analyzer(tmp_path)._parse_ai_content(payload)
    preview = out["redacted_raw_response_preview"]
    assert out["parse_status"] == "parse_failed"
    assert "test_token_placeholder" not in preview.lower()
    assert "test_api_key_placeholder" not in preview.lower()
    assert "test_secret_placeholder" not in preview.lower()
    assert "/Users/" not in preview
    assert "/private/tmp/" not in preview
    assert "Traceback (most recent call last):" not in preview
    assert "<REDACTED_TRACEBACK>" in preview
    assert len(preview) <= 2000


def test_parse_multiple_json_candidates_prefers_schema_valid_object(tmp_path):
    payload = (
        "prefix {\"recommended_stocks\":\"AAPL\"} "
        "middle {\"event_type\":\"tariff\",\"recommended_stocks\":[\"AAPL\"],\"confidence\":80}"
    )
    out = _analyzer(tmp_path)._parse_ai_content(payload)
    assert out["parse_status"] == "parse_success"
    assert out["event_type"] == "tariff"
    assert out["recommended_stocks"] == ["AAPL"]


def test_parse_success_no_parse_error_type_required(tmp_path):
    payload = (FIXTURES / "valid_payload.json").read_text(encoding="utf-8")
    out = _analyzer(tmp_path)._parse_ai_content(payload)
    assert out["parse_status"] == "parse_success"
    assert out["parse_error_type"] == ""


def test_analyze_provider_error_is_not_called(tmp_path, monkeypatch):
    analyzer = _analyzer(tmp_path)

    def _raise(*_args, **_kwargs):
        raise RuntimeError("provider failure")

    monkeypatch.setattr(analyzer, "_call_provider", _raise)
    out = analyzer.analyze("headline", "raw")
    assert out["parse_status"] == "not_called"
    assert out["parse_error_type"] == "provider_error"


def test_analyze_timeout_is_not_called(tmp_path, monkeypatch):
    analyzer = _analyzer(tmp_path)

    def _raise(*_args, **_kwargs):
        raise TimeoutError("timed out")

    monkeypatch.setattr(analyzer, "_call_provider", _raise)
    out = analyzer.analyze("headline", "raw")
    assert out["parse_status"] == "not_called"
    assert out["parse_error_type"] == "timeout"


def test_parse_failed_always_has_non_empty_parse_error_type(tmp_path):
    analyzer = _analyzer(tmp_path)
    samples = [
        "no json",
        '{"event_type":"tariff"',
        '{"event_type":"tariff","recommended_stocks":"AAPL"}',
        '{"sentiment":"neutral"}',
    ]
    for sample in samples:
        out = analyzer._parse_ai_content(sample)
        assert out["parse_status"] == "parse_failed"
        assert str(out["parse_error_type"]).strip()
