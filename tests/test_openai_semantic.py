#!/usr/bin/env python3
"""Manual verifier for OpenAI semantic path (gateway + OAuth profile)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from ai_semantic_analyzer import SemanticAnalyzer


def main() -> int:
    analyzer = SemanticAnalyzer()

    print("== OpenAI Semantic Connectivity Check ==")
    print(f"base_url={analyzer._openai_base_url()}")
    print(f"endpoint_candidates={json.dumps(analyzer._openai_endpoint_candidates(), ensure_ascii=False)}")
    print(f"profile_path={analyzer._openclaw_auth_profiles_path()}")
    print(f"profile_token_present={bool(analyzer._openclaw_oauth_access())}")
    print(f"gateway_token_present={bool(analyzer._gateway_token())}")

    out = analyzer._call_openai_api(
        "U.S. CPI surprise and FOMC forward guidance update.",
        timeout_ms=12000,
        model="gpt-5.3-codex",
    )

    print("\n== Semantic Output ==")
    print(json.dumps(out, ensure_ascii=False, indent=2))

    fallback_reason = str(out.get("fallback_reason", "") or "")
    verdict = str(out.get("verdict", "") or "")
    has_contract_fields = bool(
        out.get("event_type")
        and out.get("sentiment")
        and out.get("confidence") is not None
    )

    # Expected success criteria for this task:
    # - route should not fail with 404 endpoint issues
    # - if failing, should expose real business cause (e.g., quota/permission) instead.
    if "endpoint_not_found" in fallback_reason or "openai_http_404" in fallback_reason:
        print("\n[FAIL] OpenAI endpoint still unresolved (404).")
        return 2
    if "openai_http_429" in fallback_reason:
        print("\n[WARN] Route is correct, but account/quota is limited (429).")
        return 3
    if verdict == "hit":
        print("\n[PASS] Semantic call succeeded.")
        return 0
    if has_contract_fields and not fallback_reason:
        print("\n[PASS] OpenAI semantic JSON contract returned.")
        return 0

    print("\n[INFO] Call reached provider but returned fallback. Check fallback_reason above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
