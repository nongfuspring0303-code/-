import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def test_stage0_goldens_exist_and_are_structured():
    fixture_dir = ROOT / "tests" / "fixtures" / "edt_goldens"
    json_files = sorted(p for p in fixture_dir.glob("*.json") if p.is_file())
    assert len(json_files) >= 5, "stage0 requires at least 5 golden json samples"

    required_categories = {
        "ai_semiconductor",
        "macro_rates_cpi",
        "commodities_oil",
        "geopolitics",
        "neutral_noise",
    }
    seen_categories = set()
    mapping_case_count = 0

    for path in json_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), f"expected single-object JSON in {path.name}"
        if "sample_id" in payload:
            assert payload.get("sample_id"), f"missing sample_id in {path.name}"
            assert payload.get("category"), f"missing category in {path.name}"
            assert isinstance(payload.get("news"), dict), f"missing news object in {path.name}"
            assert payload["news"].get("headline"), f"missing news.headline in {path.name}"
            assert isinstance(payload.get("expected"), dict), f"missing expected object in {path.name}"
            seen_categories.add(str(payload.get("category")))
        elif "case_id" in payload:
            mapping_case_count += 1
            required_keys = {
                "case_id",
                "category",
                "headline",
                "semantic_event_type",
                "expected_sector_candidates",
                "expected_ticker_candidates",
                "allowed_actions",
                "must_not_route_to",
                "notes",
            }
            assert required_keys.issubset(payload.keys()), f"missing mapping case keys in {path.name}"
            assert isinstance(payload["expected_sector_candidates"], list), f"expected sector list in {path.name}"
            assert isinstance(payload["expected_ticker_candidates"], list), f"expected ticker list in {path.name}"
            assert isinstance(payload["allowed_actions"], list), f"expected allowed_actions list in {path.name}"
            assert isinstance(payload["must_not_route_to"], list), f"expected must_not_route_to list in {path.name}"
        else:
            raise AssertionError(f"unrecognized golden schema in {path.name}")

    assert required_categories.issubset(seen_categories), "core stage0 golden categories not complete"
    assert mapping_case_count >= 1, "member B mapping cases must be present"


def test_replay_join_cases_have_required_keys():
    fixture_dir = ROOT / "tests" / "fixtures" / "replay_join_cases"
    json_files = sorted(p for p in fixture_dir.glob("*.json") if p.is_file())
    assert json_files, "replay_join_cases must include json fixtures"

    required_keys = {"event_trace_id", "request_id", "batch_id", "event_hash", "idempotency_key"}
    for path in json_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert required_keys.issubset(payload.keys()), f"missing replay join keys in {path.name}"
