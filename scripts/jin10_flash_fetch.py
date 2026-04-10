#!/usr/bin/env python3
"""Fetch Jin10 flash list via MCP and output structured JSON."""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from typing import Any, Dict, List, Optional


DEFAULT_URL = "https://mcp.jin10.com/mcp"
DEFAULT_PROTOCOL = "2025-11-25"


def _read_env(name: str, default: str = "") -> str:
    value = os.getenv(name, "").strip()
    return value or default


def _parse_sse_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if "\ndata:" in text:
        data_line = text.split("\ndata:", 1)[1].strip()
        return json.loads(data_line)
    return json.loads(text)


def _rpc_call(url: str, headers: Dict[str, str], method: str, params: Optional[Dict[str, Any]] = None, request_id: Optional[int] = 1, notify: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if not notify:
        payload["id"] = request_id
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        parsed = _parse_sse_json(raw)
        return parsed, resp.headers


def _extract_structured(result: Dict[str, Any]) -> Dict[str, Any]:
    return result.get("structuredContent") or {}


def fetch_flash(cursor: Optional[str] = None) -> Dict[str, Any]:
    url = _read_env("JIN10_MCP_URL", DEFAULT_URL)
    token = _read_env("JIN10_MCP_TOKEN")
    if not token:
        raise RuntimeError("JIN10_MCP_TOKEN not set")

    headers = {
        "Content-Type": "application/json",
        "Authorization": token,
    }

    init_params = {
        "protocolVersion": DEFAULT_PROTOCOL,
        "capabilities": {"tools": {}, "resources": {}},
        "clientInfo": {"name": "jin10-flash-fetch", "version": "0.1.0"},
    }
    init_resp, init_headers = _rpc_call(url, headers, "initialize", init_params, request_id=1)
    session_id = None
    for k, v in init_headers.items():
        if k.lower() in ("mcp-session-id", "session-id", "x-session-id"):
            session_id = v
            break
    if session_id:
        headers["mcp-session-id"] = session_id

    _rpc_call(url, headers, "notifications/initialized", {}, notify=True)

    arguments: Dict[str, Any] = {}
    if cursor:
        arguments["cursor"] = cursor
    call_params = {"name": "list_flash", "arguments": arguments}
    call_resp, _ = _rpc_call(url, headers, "tools/call", call_params, request_id=2)

    result = call_resp.get("result", {})
    structured = _extract_structured(result)
    return structured


def _extract_items(structured: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = structured.get("data", {}) if isinstance(structured, dict) else {}
    items = data.get("items", []) if isinstance(data, dict) else []
    return items if isinstance(items, list) else []


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Jin10 flash via MCP")
    parser.add_argument("--cursor", type=str, default=None, help="pagination cursor")
    parser.add_argument("--out", type=str, default=None, help="output file path")
    parser.add_argument("--limit", type=int, default=10, help="max items to keep in output")
    args = parser.parse_args()

    structured = fetch_flash(cursor=args.cursor)
    items = _extract_items(structured)[: max(1, args.limit)]
    output = {
        "items": items,
        "next_cursor": structured.get("data", {}).get("next_cursor", "") if isinstance(structured, dict) else "",
        "has_more": structured.get("data", {}).get("has_more", False) if isinstance(structured, dict) else False,
    }

    payload = json.dumps(output, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(payload)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
