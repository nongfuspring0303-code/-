#!/usr/bin/env python3
"""
项目体检工具 - 快速检查EDT Phase 3项目状态

使用方式：
python3 scripts/project_check.py           # 快速检查
python3 scripts/project_check.py --fix     # 自动修复
python3 scripts/project_check.py --report  # 生成报告
"""

import os
import sys
import json
import tempfile
import yaml
from pathlib import Path
from datetime import datetime

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CURRENT_DIR.parent
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from phase3_evidence_ledger import Phase3EvidenceLedger
from data_adapter import DataAdapter
from canary_source_health import CanarySourceHealth


def check_project():
    """检查项目状态"""
    root = Path(".").resolve()
    issues = []
    results = []
    
    print("🔍 EDT Phase 3 项目体检")
    print("=" * 60)
    
    # 1. 检查目录结构
    print("\n📁 目录结构检查:")
    required_dirs = ["configs", "scripts", "schemas", "tests", "canvas", "logs"]
    for dir_name in required_dirs:
        dir_path = root / dir_name
        if dir_path.exists():
            print(f"  ✅ {dir_name}")
        else:
            print(f"  ❌ {dir_name} (缺失)")
            issues.append(f"目录缺失: {dir_name}")
    
    # 2. 检查A模块
    print("\n📰 A模块检查 (新闻→板块):")
    a_files = [
        ("configs/sector_impact_mapping.yaml", "板块影响映射"),
        ("configs/conduction_chain.yaml", "传导链配置"),
    ]
    
    for file_path, desc in a_files:
        full_path = root / file_path
        if full_path.exists():
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)
                if 'schema_version' in data:
                    print(f"  ✅ {desc} (版本: {data['schema_version']})")
                else:
                    print(f"  ⚠️  {desc} (缺少版本)")
                    issues.append(f"A模块配置缺少版本: {desc}")
            except Exception as e:
                print(f"  ❌ {desc} (格式错误: {str(e)[:30]})")
                issues.append(f"A模块配置格式错误: {desc}")
        else:
            print(f"  ❌ {desc} (文件缺失)")
            issues.append(f"A模块文件缺失: {desc}")
    
    # 3. 检查B模块
    print("\n🎯 B模块检查 (策略层):")
    b_files = [
        ("configs/premium_stock_pool.yaml", "优质股票池"),
        ("scripts/opportunity_score.py", "机会评分"),
        ("scripts/verify_direction_consistency.py", "方向验证"),
    ]
    
    for file_path, desc in b_files:
        full_path = root / file_path
        if full_path.exists():
            if file_path.endswith('.yaml'):
                try:
                    with open(full_path, 'r', encoding='utf-8') as f:
                        data = yaml.safe_load(f)
                    stock_count = len(data.get('stocks', []))
                    print(f"  ✅ {desc} ({stock_count}只股票)")
                except Exception as e:
                    print(f"  ❌ {desc} (格式错误)")
                    issues.append(f"B模块配置格式错误: {desc}")
            else:
                print(f"  ✅ {desc}")
        else:
            print(f"  ❌ {desc} (文件缺失)")
            issues.append(f"B模块文件缺失: {desc}")
    
    # 4. 检查C模块
    print("\n🎨 C模块检查 (前端+总线):")
    c_files = [
        ("schemas/event_update.yaml", "事件Schema"),
        ("schemas/sector_update.yaml", "板块Schema"),
        ("schemas/opportunity_update.yaml", "机会Schema"),
        ("canvas/index.html", "前端主页面"),
        ("canvas/styles.css", "样式文件"),
        ("canvas/app.js", "前端逻辑"),
    ]
    
    for file_path, desc in c_files:
        full_path = root / file_path
        if full_path.exists():
            size = full_path.stat().st_size
            print(f"  ✅ {desc} ({size} bytes)")
        else:
            print(f"  ❌ {desc} (文件缺失)")
            issues.append(f"C模块文件缺失: {desc}")

    # 4.5 检查真实压力门禁
    print("\n⚙️  真实压力门禁检查:")
    pressure_gate = root / "scripts" / "run_phase3_pressure_gate.py"
    if pressure_gate.exists():
        sample = [
            {
                "headline": "Fed signals policy shift",
                "source_url": "https://example.com/news-1",
                "raw_text": "policy shift",
                "source_type": "rss",
                "timestamp": "2026-04-09T01:02:03Z",
            },
            {
                "headline": "AI spending remains strong",
                "source_url": "https://example.com/news-2",
                "raw_text": "ai spending",
                "source_type": "official",
                "timestamp": "2026-04-09T01:02:03Z",
            },
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump(sample, handle, ensure_ascii=False)
            sample_path = Path(handle.name)
        try:
            import subprocess

            cmd = [
                sys.executable,
                str(pressure_gate),
                "--input-json",
                str(sample_path),
                "--min-board-coverage",
                "0.5",
                "--max-p99-ms",
                "5000",
                "--min-throughput",
                "0.1",
            ]
            proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, encoding="utf-8", errors="replace")
            if proc.returncode == 0:
                print("  ✅ 真实压力门禁")
            else:
                print("  ❌ 真实压力门禁 (失败)")
                issues.append("真实压力门禁失败")
                tail = (proc.stdout or proc.stderr or "").strip().splitlines()
                if tail:
                    print(f"    {tail[-1][:120]}")
        finally:
            try:
                sample_path.unlink(missing_ok=True)
            except Exception:
                pass
    else:
        print("  ❌ 真实压力门禁 (脚本缺失)")
        issues.append("真实压力门禁脚本缺失")

    print("\n📚 证据台账检查:")
    ledger = Phase3EvidenceLedger(str(root / "logs"))
    summary = ledger.read_summary()
    total_runs = int(summary.get("total_runs", 0) or 0)
    live_run_count = int(summary.get("live_run_count", 0) or 0)
    if total_runs > 0:
        print(f"  ✅ 证据台账 ({total_runs} 条，live={live_run_count})")
    else:
        print("  ⚠️  证据台账为空")
        issues.append("证据台账为空")

    print("\n🛰️  外部数据健康检查:")
    adapter = DataAdapter(audit_dir=str(root / "logs"))
    _ = adapter.fetch()
    data_health = adapter.health_report()
    total_fetches = int(data_health.get("total_fetches", 0) or 0)
    live_news_count = int(data_health.get("live_news_count", 0) or 0)
    fallback_news_count = int(data_health.get("fallback_news_count", 0) or 0)
    market_test_count = int(data_health.get("market_test_count", 0) or 0)
    if total_fetches > 0:
        print(
            f"  ✅ 外部数据健康 ({total_fetches} 次，live={live_news_count}, fallback={fallback_news_count}, market_test={market_test_count})"
        )
    else:
        print("  ⚠️  外部数据健康暂无记录")
        issues.append("外部数据健康暂无记录")

    print("\n🛰️  Canary 源健康检查:")
    canary = CanarySourceHealth()
    canary_summary = canary.read_summary()
    canary_assessment = canary.assess(summary=canary_summary, mode="dev")
    canary_window_1h = canary_assessment.windows.get("60", {}) or canary_assessment.windows.get("1h", {})
    canary_window_30m = canary_assessment.windows.get("30", {}) or canary_assessment.windows.get("30m", {})
    symbol = "✅" if canary_assessment.status == "GREEN" else "⚠️" if canary_assessment.status == "YELLOW" else "❌"
    print(f"  {symbol} Canary 源健康: {canary_assessment.summary}")
    print(
        "    "
        f"1h success_rate={canary_window_1h.get('success_rate', 0)} "
        f"p95_latency_ms={canary_window_1h.get('p95_latency_ms', 0)} "
        f"freshness_lag_sec={canary_window_1h.get('freshness_lag_sec', 0)} "
        f"new_item_count_30m={canary_window_30m.get('new_item_count', 0)}"
    )
    for warn in canary_assessment.warnings:
        print(f"    ⚠️  {warn}")
    for err in canary_assessment.errors:
        print(f"    ❌ {err}")
    if canary_assessment.status == "RED":
        issues.append("Canary 源健康未通过")

    # 5. 检查测试
    print("\n🧪 测试检查:")
    test_dir = root / "tests"
    if test_dir.exists():
        test_files = list(test_dir.rglob("test_*.py"))
        if test_files:
            print(f"  ✅ 测试文件 ({len(test_files)}个)")
        else:
            print(f"  ⚠️  测试目录为空")
            issues.append("测试目录为空")
    else:
        print(f"  ❌ tests目录不存在")
        issues.append("测试目录缺失")
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 检查结果:")
    
    if issues:
        print(f"发现 {len(issues)} 个问题:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. {issue}")
        
        print(f"\n💡 建议:")
        print("  1. 运行修复命令: python3 scripts/project_check.py --fix")
        print("  2. 查看详细报告: python3 scripts/project_check.py --report")
    else:
        print("✅ 项目状态良好！所有检查通过。")
        print("\n🎉 项目可以正常使用。")
    
    print("=" * 60)
    
    return issues


def fix_issues():
    """自动修复问题"""
    print("🔧 开始自动修复...")
    print("=" * 60)
    
    root = Path(".").resolve()
    fixes_applied = []
    
    # 创建缺失目录
    required_dirs = ["configs", "scripts", "schemas", "tests", "canvas", "logs"]
    for dir_name in required_dirs:
        dir_path = root / dir_name
        if not dir_path.exists():
            os.makedirs(dir_path, exist_ok=True)
            print(f"✅ 创建目录: {dir_name}")
            fixes_applied.append(f"创建目录: {dir_name}")
    
    # 创建缺失的配置文件模板
    config_files = {
        "configs/conduction_chain.yaml": """# conduction_chain.yaml
schema_version: v1.0
description: "传导链层级配置 - 宏观→板块→主题映射关系"
chain_templates: []
event_to_chain_mapping: []
""",
        "requirements.txt": """PyYAML>=6.0
pytest>=8.0
""",
    }
    
    for file_path, content in config_files.items():
        full_path = root / file_path
        if not full_path.exists():
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"✅ 创建配置文件: {file_path}")
            fixes_applied.append(f"创建配置文件: {file_path}")
    
    print("\n" + "=" * 60)
    print(f"🔧 修复完成:")
    print(f"   应用了 {len(fixes_applied)} 个修复")
    print("=" * 60)
    
    return fixes_applied


def generate_report():
    """生成详细报告"""
    print("📄 生成项目体检报告...")
    print("=" * 60)
    
    root = Path(".").resolve()
    report = {
        "project": str(root),
        "timestamp": datetime.now().isoformat(),
        "modules": {},
        "issues": [],
        "recommendations": []
    }
    
    # 检查各个模块
    modules = {
        "A模块": ["configs/sector_impact_mapping.yaml", "configs/conduction_chain.yaml"],
        "B模块": ["configs/premium_stock_pool.yaml", "scripts/opportunity_score.py", 
                 "scripts/verify_direction_consistency.py"],
        "C模块": ["schemas/event_update.yaml", "schemas/sector_update.yaml", 
                 "schemas/opportunity_update.yaml", "canvas/index.html",
                 "canvas/styles.css", "canvas/app.js"]
    }
    
    for module_name, files in modules.items():
        module_status = {"files": [], "status": "✅"}
        
        for file_path in files:
            full_path = root / file_path
            file_info = {
                "path": file_path,
                "exists": full_path.exists()
            }
            
            if full_path.exists():
                if file_path.endswith(('.yaml', '.yml')):
                    try:
                        with open(full_path, 'r', encoding='utf-8') as f:
                            data = yaml.safe_load(f)
                        file_info["valid_yaml"] = True
                        file_info["schema_version"] = data.get('schema_version', '未知')
                    except Exception as e:
                        file_info["valid_yaml"] = False
                        file_info["error"] = str(e)
                        module_status["status"] = "⚠️"
                        report["issues"].append(f"{module_name}: {file_path} YAML格式错误")
                else:
                    size = full_path.stat().st_size
                    file_info["size"] = size
            else:
                module_status["status"] = "❌"
                report["issues"].append(f"{module_name}: {file_path} 文件缺失")
            
            module_status["files"].append(file_info)
        
        report["modules"][module_name] = module_status
    
    # 生成建议
    if report["issues"]:
        report["recommendations"].append("运行修复命令: python3 scripts/project_check.py --fix")
        report["recommendations"].append("检查缺失的文件并补充")
    else:
        report["recommendations"].append("项目状态良好，可以继续开发")
    
    # 保存报告
    report_file = root / "project_health_report.json"
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 报告已生成: {report_file}")
    print("=" * 60)
    
    return report


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="EDT Phase 3 项目体检工具")
    parser.add_argument("--fix", action="store_true", help="自动修复问题")
    parser.add_argument("--report", action="store_true", help="生成详细报告")
    
    args = parser.parse_args()
    
    if args.fix:
        fix_issues()
        print("\n🔄 修复后重新检查...")
        check_project()
    elif args.report:
        generate_report()
    else:
        check_project()


if __name__ == "__main__":
    main()
