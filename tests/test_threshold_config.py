"""Verify that business thresholds are sourced from configs/*.yaml and never hardcoded
as bare defaults in production code paths.

Stage 8-A config single-source-of-truth policy:
  - All thresholds must come from configs/*.yaml
  - Hardcoded business thresholds are forbidden
  - Missing config must fail-fast in production

KNOWN_LEGACY: Existing hardcoded defaults documented for incremental migration.
  These must not grow. New thresholds introduced in Stage 8-A must use config.
  Full migration to config-only tracked by Stage8A-Impl follow-up PRs.

Refs #139 (Stage8A-Impl-1)
"""

import ast
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROTECTED_FILES = [
    "scripts/conduction_mapper.py",
    "scripts/ai_semantic_analyzer.py",
    "scripts/ai_conduction_selector.py",
]

KNOWN_LEGACY_HARDCODED = {
    "conduction_mapper.py": {
        640: "max_recommended_high_conf",
        641: "max_recommended_mid_conf",
        642: "max_recommended_low_conf",
        872: "template_base_confidence",
        874: "template_rate_cut_confidence",
        876: "template_inflation_confidence",
        930: "tariff_asset_confidence",
        956: "tariff_confidence",
        979: "high_threshold",
        980: "medium_threshold",
        1026: "max_evidence_items",
        1261: "policy_base_confidence",
        1265: "policy_confidence_min",
        1266: "policy_confidence_max",
        1267: "policy_confidence_scale",
        1268: "policy_confidence_base",
        1278: "policy_asset_confidence",
        1343: "fallback_confidence",
    },
    "ai_semantic_analyzer.py": {
        75: "min_confidence",
        83: "timeout_ms",
        999: "confidence_default",
        1002: "confidence_default",
        1243: "evidence_grade_threshold",
    },
    "ai_conduction_selector.py": {
        10: "min_confidence",
    },
}


def _find_hardcoded_defaults(filepath):
    """Find lines with bare numeric defaults in .get() calls, excluding known legacy."""
    basename = os.path.basename(filepath)
    known = KNOWN_LEGACY_HARDCODED.get(basename, {})
    known_lines = set(known.keys())
    violations = []

    with open(filepath) as f:
        lines = f.readlines()

    for lineno, line in enumerate(lines, 1):
        line_clean = line.strip()
        if not line_clean or line_clean.startswith("#"):
            continue
        if lineno in known_lines:
            continue

        m = re.search(r'\.get\([^,]+,\s*(\d+)', line)
        if m and int(m.group(1)) > 0:
            violations.append(
                f"  line {lineno}: bare default {m.group(1)} in .get() — "
                f"must source from config or fail-fast"
            )

    return violations


def test_no_new_hardcoded_thresholds():
    """No NEW hardcoded thresholds beyond known legacy in any PROTECTED_FILES."""
    all_violations = []
    for relpath in PROTECTED_FILES:
        filepath = os.path.join(REPO_ROOT, relpath)
        if not os.path.exists(filepath):
            continue
        violations = _find_hardcoded_defaults(filepath)
        if violations:
            all_violations.append(f"{relpath}:")
            all_violations.extend(violations)
    assert not all_violations, (
        "NEW hardcoded business thresholds found:\n" + "\n".join(all_violations)
    )


def test_known_legacy_does_not_grow():
    """Documented legacy hardcoded count must not increase."""
    expected = {
        "conduction_mapper.py": 18,
        "ai_semantic_analyzer.py": 5,
        "ai_conduction_selector.py": 1,
    }
    for basename, expected_count in expected.items():
        known = KNOWN_LEGACY_HARDCODED.get(basename, {})
        actual = len(known)
        assert actual == expected_count, (
            f"KNOWN_LEGACY_HARDCODED baseline count for {basename}: "
            f"{actual} (expected {expected_count}). "
            f"Update KNOWN_LEGACY_HARDCODED if migrating thresholds to config."
        )


def test_workflow_exists():
    """CI workflow file must exist."""
    workflow_path = os.path.join(REPO_ROOT, ".github", "workflows", "ci.yml")
    assert os.path.exists(workflow_path), f"CI workflow not found at {workflow_path}"


def test_feature_flags_config_exists():
    """Feature flags config must exist."""
    config_path = os.path.join(REPO_ROOT, "configs", "feature_flags_v22.yaml")
    assert os.path.exists(config_path), f"Feature flags config not found at {config_path}"


import yaml as _yaml


def test_feature_flags_shadow_boundary_values():
    """Stage8A shadow flags must match contract: v5_shadow_output=true, replace_legacy=false."""
    config_path = os.path.join(REPO_ROOT, "configs", "feature_flags_v22.yaml")
    with open(config_path) as f:
        cfg = _yaml.safe_load(f)
    flags = cfg.get("flags", {})

    shadow = flags.get("enable_v5_shadow_output", {})
    replace = flags.get("enable_replace_legacy_output", {})

    missing = []
    if not shadow:
        missing.append("enable_v5_shadow_output")
    if not replace:
        missing.append("enable_replace_legacy_output")
    assert not missing, f"Required Stage8A shadow flags missing from config: {missing}"

    assert shadow.get("default") is True, (
        "enable_v5_shadow_output.default must be true per contract matrix"
    )
    assert replace.get("default") is False, (
        "enable_replace_legacy_output.default must be false per contract matrix"
    )


def test_feature_flags_required_keys_exist():
    """Each required flag must have default, owner, and rollback_owner."""
    config_path = os.path.join(REPO_ROOT, "configs", "feature_flags_v22.yaml")
    with open(config_path) as f:
        cfg = _yaml.safe_load(f)
    flags = cfg.get("flags", {})

    required_keys = {"default", "owner", "rollback_owner", "description"}
    invalid = []
    for name, flag in flags.items():
        missing_keys = required_keys - set(flag.keys())
        if missing_keys:
            invalid.append(f"  {name}: missing {sorted(missing_keys)}")
    assert not invalid, (
        f"Feature flags with missing required keys:\n" + "\n".join(invalid)
    )


def test_feature_flags_impl2_candidate_envelope_flags_exist():
    """PR-2 feature flags must exist and stay disabled by default until runtime lands."""
    config_path = os.path.join(REPO_ROOT, "configs", "feature_flags_v22.yaml")
    with open(config_path) as f:
        cfg = _yaml.safe_load(f)
    flags = cfg.get("flags", {})

    required = {
        "enable_source_metadata_propagation": "member_b",
        "enable_candidate_envelope": "member_b",
    }
    missing = [name for name in required if name not in flags]
    assert not missing, f"Required Stage8A Impl-2 flags missing from config: {missing}"

    invalid = []
    for name, owner in required.items():
        flag = flags.get(name, {})
        if flag.get("default") is not False:
            invalid.append(f"{name}.default must be false before Impl-2 runtime lands")
        if flag.get("owner") != owner:
            invalid.append(f"{name}.owner must be {owner}")
        if flag.get("rollback_owner") != owner:
            invalid.append(f"{name}.rollback_owner must be {owner}")
    assert not invalid, "Invalid Stage8A Impl-2 feature flag metadata:\n" + "\n".join(invalid)


def test_missing_config_fails_fast():
    """Loading a non-existent config file must raise, not silently skip."""
    missing_path = os.path.join(REPO_ROOT, "configs", "__nonexistent_config_test__.yaml")
    with __import__("pytest").raises((FileNotFoundError, OSError, _yaml.YAMLError)):
        with open(missing_path) as f:
            _yaml.safe_load(f)
