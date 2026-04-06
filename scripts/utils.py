#!/usr/bin/env python3
"""
工具函数 - 备份、恢复、验证等辅助功能
"""

import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, Any, Optional
import yaml


def backup_file(file_path: Path) -> Optional[Path]:
    """备份文件"""
    if not file_path.exists():
        return None
    
    backup_path = file_path.with_suffix(file_path.suffix + ".guard_backup")
    try:
        shutil.copy2(file_path, backup_path)
        return backup_path
    except Exception:
        return None


def restore_backup(file_path: Path) -> bool:
    """从备份恢复文件"""
    backup_path = file_path.with_suffix(file_path.suffix + ".guard_backup")
    if not backup_path.exists():
        return False
    
    try:
        shutil.copy2(backup_path, file_path)
        return True
    except Exception:
        return False


def cleanup_backups(root_dir: Path) -> int:
    """清理备份文件"""
    backups = list(root_dir.rglob("*.guard_backup"))
    count = 0
    
    for backup in backups:
        try:
            backup.unlink()
            count += 1
        except Exception:
            pass
    
    return count


def safe_yaml_load(file_path: Path) -> Optional[Dict[str, Any]]:
    """安全加载YAML文件"""
    if not file_path.exists():
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def safe_json_load(file_path: Path) -> Optional[Dict[str, Any]]:
    """安全加载JSON文件"""
    if not file_path.exists():
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def check_file_exists(file_path: Path) -> Dict[str, Any]:
    """检查文件是否存在"""
    exists = file_path.exists()
    result = {
        "exists": exists,
        "path": str(file_path)
    }
    
    if exists:
        result["size"] = file_path.stat().st_size
        result["is_file"] = file_path.is_file()
    
    return result


def validate_schema_file(schema_path: Path) -> Dict[str, Any]:
    """验证Schema文件"""
    result = {
        "path": str(schema_path),
        "exists": False,
        "valid": False,
        "error": None
    }
    
    if not schema_path.exists():
        result["error"] = "文件不存在"
        return result
    
    result["exists"] = True
    
    try:
        if schema_path.suffix in ['.yaml', '.yml']:
            with open(schema_path, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
        elif schema_path.suffix == '.json':
            with open(schema_path, 'r') as f:
                json.load(f)
        else:
            # 其他文件类型，只检查存在性
            pass
        
        result["valid"] = True
    except Exception as e:
        result["valid"] = False
        result["error"] = str(e)[:100]
    
    return result


def check_config_keys(config: Dict[str, Any], required_keys: Dict[str, Any]) -> Dict[str, Any]:
    """检查配置键完整性"""
    missing_keys = []
    present_keys = []
    
    def _check_nested(base_path: str, config_part: Any, required_part: Any):
        if isinstance(required_part, dict):
            for key, sub_required in required_part.items():
                new_path = f"{base_path}.{key}" if base_path else key
                if key in config_part:
                    _check_nested(new_path, config_part[key], sub_required)
                else:
                    missing_keys.append({
                        "path": new_path,
                        "expected_type": type(sub_required).__name__
                    })
        else:
            # 叶节点，检查存在性
            if base_path:
                # 这里简化处理，实际需要更复杂的路径解析
                pass
    
    _check_nested("", config, required_keys)
    
    return {
        "missing_keys": missing_keys,
        "present_keys": present_keys,
        "all_present": len(missing_keys) == 0
    }


def check_sensitive_patterns(content: str, patterns: Dict[str, str]) -> Dict[str, Any]:
    """检查敏感模式"""
    found = []
    
    for pattern, description in patterns.items():
        if pattern in content:
            found.append({
                "pattern": pattern,
                "description": description
            })
    
    return {
        "found_patterns": found,
        "is_clean": len(found) == 0
    }


def format_report(report: Dict[str, Any], format_type: str = "human") -> str:
    """格式化报告"""
    if format_type == "json":
        return json.dumps(report, indent=2, ensure_ascii=False)
    
    # 人类可读格式
    lines = []
    
    # ==================== 最上层一眼决策区 ====================
    lines.append("🚨 最上层一眼决策区")
    lines.append("=" * 60)
    
    # 最终状态
    status = report.get("overall_status", "UNKNOWN")
    stats = report.get("statistics", {})
    red_count = stats.get("red", 0)
    yellow_count = stats.get("yellow", 0)
    fixed_count = stats.get("fixed", 0)
    
    # 是否允许继续推进
    if status == "PASS":
        allow_continue = "允许"
    elif status == "WARN":
        allow_continue = "允许但需复核"
    else:  # FAIL
        allow_continue = "不允许"
    
    # 一句话结论
    conclusion = report.get("conclusion", "")
    
    lines.append(f"最终状态: {status}")
    lines.append(f"是否允许继续推进: {allow_continue}")
    lines.append(f"红灯数量: {red_count}")
    lines.append(f"黄灯数量: {yellow_count}")
    lines.append(f"已自动修复数量: {fixed_count}")
    lines.append(f"一句话结论: {conclusion}")
    
    lines.append("=" * 60)
    lines.append("\n📋 详细报告")
    lines.append("-" * 60)
    
    # 详细统计
    lines.append(f"📊 总体状态: {status}")
    lines.append(f"   红灯: {red_count} | 黄灯: {yellow_count} | 绿灯: {stats.get('green', 0)}")
    lines.append(f"   已修复: {fixed_count}")
    
    # 验证结果
    validation = report.get("validation", {})
    lines.append(f"\n✅ 最小验证:")
    for key, value in validation.items():
        status = "通过" if value else "失败"
        lines.append(f"   {key}: {status}")
    
    # 高风险未修复项
    unfixed = report.get("unfixed_high_risk", [])
    if unfixed:
        lines.append(f"\n🚨 高风险未修复项 ({len(unfixed)} 个):")
        for issue in unfixed[:3]:  # 只显示前3个
            lines.append(f"   • {issue.get('description', '未知问题')}")
        if len(unfixed) > 3:
            lines.append(f"   ... 还有 {len(unfixed) - 3} 个")
    
    # 结论
    conclusion = report.get("conclusion", "")
    lines.append(f"\n💡 结论: {conclusion}")
    
    lines.append("\n" + "=" * 60)
    
    return "\n".join(lines)


def save_report(report: Dict[str, Any], output_path: Path) -> bool:
    """保存报告到文件"""
    try:
        # 保存JSON格式
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # 保存人类可读格式
        human_path = output_path.with_suffix(".txt")
        with open(human_path, 'w', encoding='utf-8') as f:
            f.write(format_report(report, "human"))
        
        return True
    except Exception:
        return False