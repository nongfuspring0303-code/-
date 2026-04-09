#!/usr/bin/env python3
"""
Config center loader (T1.3).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml


class ConfigCenter:
    """Load and provide typed access to module configs."""

    def __init__(self, config_path: Optional[str] = None):
        base = Path(__file__).resolve().parent.parent
        self.config_path = Path(config_path) if config_path else base / "configs" / "edt-modules-config.yaml"
        self._registered_paths: Dict[str, Path] = {}
        self._registered_data: Dict[str, Dict[str, Any]] = {}
        self._registered_mtime: Dict[str, float] = {}
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        with open(self.config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        if "modules" not in cfg:
            raise ValueError("Invalid config: missing top-level 'modules'")
        return cfg

    def module_config(self, module_name: str) -> Dict[str, Any]:
        return self.data.get("modules", {}).get(module_name, {})

    def get(self, dotted_path: str, default: Any = None) -> Any:
        current: Any = self.data
        for part in dotted_path.split("."):
            if not isinstance(current, dict) or part not in current:
                return default
            current = current[part]
        return current

    def reload(self) -> Dict[str, Any]:
        self.data = self._load()
        for name, path in self._registered_paths.items():
            self._registered_data[name] = self._load_yaml_file(path)
        return self.data

    def register(self, name: str, path: str | Path) -> None:
        real_path = Path(path)
        self._registered_paths[name] = real_path
        self._registered_data[name] = self._load_yaml_file(real_path)
        self._registered_mtime[name] = self._safe_mtime(real_path)

    def refresh_registered(self, name: str) -> None:
        path = self._registered_paths.get(name)
        if path is None:
            return
        current_mtime = self._safe_mtime(path)
        last_mtime = self._registered_mtime.get(name)
        if last_mtime is None or current_mtime != last_mtime:
            self._registered_data[name] = self._load_yaml_file(path)
            self._registered_mtime[name] = current_mtime

    def get_registered(self, name: str, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.refresh_registered(name)
        return self._registered_data.get(name, default or {})

    @staticmethod
    def _load_yaml_file(path: Path) -> Dict[str, Any]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = yaml.safe_load(f) or {}
            return payload if isinstance(payload, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _safe_mtime(path: Path) -> float:
        try:
            return path.stat().st_mtime
        except Exception:
            return -1.0

    def module_enabled(self, module_name: str) -> bool:
        return bool(self.module_config(module_name).get("enabled", False))

    def module_timeout(self, module_name: str, default: int = 60) -> int:
        return int(self.module_config(module_name).get("timeout", default))

    def module_params(self, module_name: str) -> Dict[str, Any]:
        return self.module_config(module_name).get("params", {})

    def validate_required_modules(self, required_modules: list[str]) -> tuple[bool, list[str]]:
        missing = []
        modules = self.data.get("modules", {})
        for name in required_modules:
            if name not in modules:
                missing.append(name)
        return len(missing) == 0, missing


if __name__ == "__main__":
    center = ConfigCenter()
    ok, missing = center.validate_required_modules(
        ["SignalScorer", "LiquidityChecker", "RiskGatekeeper", "PositionSizer", "ExitManager"]
    )
    print("config_path:", center.config_path)
    print("required_modules_ok:", ok)
    if not ok:
        print("missing:", missing)
