import sys
import os
import json
from pathlib import Path
from typing import Dict, Any

# Setup Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from workflow_runner import WorkflowRunner

def print_separator(char="=", length=60):
    print(f"\n{char * length}")

def format_card(card: Dict[str, Any]):
    print_separator("━")
    print(f" 🎴  COMMAND ACTION CARD: {card['event_name']}")
    print_separator("─")
    
    # Layer 1: Event
    print(f" [EVENT]  Type: {card['event_type']} | State: {card['catalyst_state']} | Time: {card['event_time']}")
    print(f"          Window: {card['time_window']}")
    
    # Layer 2: Path & Target
    print(f" [PATH]   Primary: {card['primary_path']} | Target: {card['best_target']} ({card['target_bucket']})")
    
    # Layer 3: Market Evidence
    print(f" [MARKET] A1: {card['a1_market_validation']} | Macro: {card['macro_state']}")
    print(f"          Sector: {card['sector_confirmation']} | Leader: {card['leader_confirmation']}")
    
    # Layer 4: Action & Decision
    grade_color = {"A": "\033[92m", "B": "\033[94m", "C": "\033[93m", "D": "\033[91m"}.get(card['trade_grade'], "")
    reset = "\033[0m"
    print(f" [ACTION] Decision: {card['trade_decision'].upper()} | Tier: {card['position_tier'].upper()}")
    print(f"          Grade: {grade_color}{card['trade_grade']}{reset} | State: {card['trading_state']}")
    
    # Layer 5: Execution
    print(f" [EXEC]   Setup: {card['best_setup']} | Window: {card['execution_window']}")
    
    # Layer 6: Risk & Conclusion
    if card['blockers']:
        print(f" [BLOCK]  {', '.join(card['blockers'])}")
    print(f" [VERDICT] {card['one_line_verdict']}")
    print_separator("━")

def run_simulation(name: str, payload: Dict[str, Any]):
    print(f"\n🚀 SIMULATING USAGE SCENARIO: {name}")
    runner = WorkflowRunner()
    try:
        result = runner.run(payload)
        card = result.get("action_card")
        if card:
            format_card(card)
        else:
            print(f"Error: No action card generated for {name}")
            print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"Simulation failed: {str(e)}")

# Define Usage Scenarios
SCENARIOS = {
    "Triple Resonance (High Conviction)": {
        "event_name": "AI Cluster Scaling Breakthrough",
        "event_type": "tech",
        "event_time": "2026-04-18T10:00:00Z",
        "event_state": "Developing",
        "evidence_grade": "A",
        "A0": 85, "A-1": 80, "A1": 92, "A1.5": 80, "A0.5": 10,
        "score": 88.5,
        "macro_confirmation": "supportive",
        "sector_confirmation": "strong",
        "leader_confirmation": "confirmed",
        "target_leader": ["NVDA"],
        "primary_path": "AI Hardware Supercycle",
        "symbol": "NVDA",
        "a1_market_validation": "pass"
    },
    "Evidence-C Noise Filter": {
        "event_name": "Rumor: Tech Merger Talk",
        "event_type": "tech",
        "event_time": "2026-04-18T11:30:00Z",
        "event_state": "Developing",
        "evidence_grade": "C", # SHIFT GATE
        "A0": 40, "A-1": 50, "A1": 70, "A1.5": 30, "A0.5": 0,
        "score": 45.0,
        "macro_confirmation": "neutral",
        "sector_confirmation": "medium",
        "leader_confirmation": "unconfirmed",
        "target_leader": [],
        "target_etf": ["QQQ"],
        "primary_path": "Sector Consolidation",
        "symbol": "QQQ",
        "a1_market_validation": "pass"
    },
    "A1 Hard Gate Block": {
        "event_name": "Interest Rate Hike Scare",
        "event_type": "macro",
        "event_time": "2026-04-18T14:00:00Z",
        "event_state": "Developing",
        "evidence_grade": "A",
        "A0": 20, "A-1": 20, "A1": 15, "A1.5": 10, "A0.5": 0,
        "score": 18.0,
        "macro_confirmation": "hostile",
        "sector_confirmation": "weak",
        "leader_confirmation": "failed",
        "a1_market_validation": "fail", # SHIFT GATE
        "symbol": "SPY"
    }
}

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", choices=list(SCENARIOS.keys()) + ["all"], default="all")
    args = parser.parse_args()
    
    if args.scenario == "all":
        for name, payload in SCENARIOS.items():
            run_simulation(name, payload)
    else:
        run_simulation(args.scenario, SCENARIOS[args.scenario])
