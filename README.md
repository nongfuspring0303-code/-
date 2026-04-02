# 浜嬩欢椹卞姩浜ゆ槗妯″潡 - 寮€鍙戞寚鍗?
## 椤圭洰瀹氫綅

灏嗏€滈噸澶т簨浠堕┍鍔ㄤ氦鏄撶郴缁熲€濆崌绾т负鍙璁°€佸彲鍥炴斁銆佸彲骞惰鍗忎綔鐨勬ā鍧楀寲宸ヤ綔娴併€?
## 蹇呰鍏ュ彛

- `AI杈呭姪宸ヤ綔娴佸崌绾т换鍔℃竻鍗?md`
- `EDT-AI鍗忓悓寮€鍙戜笌闆嗘垚鍗忚(Git鐗?.md`

## 鐩綍缁撴瀯

```text
浜嬩欢椹卞姩浜ゆ槗妯″潡闃舵浜?
鈹溾攢鈹€ configs/                 # 鍙傛暟閰嶇疆涓績
鈹溾攢鈹€ schemas/                 # 杈撳叆杈撳嚭濂戠害
鈹溾攢鈹€ scripts/                 # 妯″潡瀹炵幇涓庤繍琛屽叆鍙?鈹溾攢鈹€ tests/                   # 鍥炲綊涓庨泦鎴愭祴璇?鈹溾攢鈹€ docs/                    # 鍗忚銆佹槧灏勩€佸仴搴锋墜鍐?鈹溾攢鈹€ module-registry.yaml     # 妯″潡娉ㄥ唽涓績
鈹斺攢鈹€ logs/                    # 瀹¤涓庡仴搴锋鏌ユ姤鍛?```

## 鏍稿績閾捐矾

```text
EventCapture -> SourceRanker -> SeverityEstimator -> EventObjectifier
EventObjectifier -> LifecycleManager -> FatigueCalculator
EventObjectifier -> ConductionMapper -> MarketValidator
AIEventIntelOutput -> NarrativeStateRecognizer -> AISignalAdapter
SignalScorer + AISignalAdapter -> LiquidityChecker -> RiskGatekeeper -> PositionSizer -> ExitManager
```

## B灞傦紙绛栫暐涓庨鎺э級鏂板妯″潡

- `NarrativeStateRecognizer`锛圔4锛?  - 杈撳嚭锛歚initial/continuation/decay/invalid`
  - 涓嶇洿鎺ヤ慨鏀规墽琛屽眰鐘舵€佹満
- `AISignalAdapter`锛圔1锛?  - 灏?AI 杈撳嚭鏄犲皠涓?`A0/A-1/A1/A1.5/A0.5`
  - 鏄犲皠琛ㄤ粠閰嶇疆璇诲彇锛屾敮鎸佺増鏈洖婊?- `RiskGatekeeper` 澧炲己锛圔2/B3锛?  - 鏂板 G7锛圓I澶嶆牳/闄嶇骇闂搁棬锛?  - 鍐崇瓥杈撳嚭鏂板 `decision_summary` 涓?`reasoning`

## 蹇€熼獙璇?
### 2. 统一验收入口（推荐）
```bash
python3 -m pytest -q
PYTHONPYCACHEPREFIX=/tmp/pycache python3 scripts/system_healthcheck.py
bash scripts/verify_phase12.sh
bash scripts/verify_fullchain.sh
```

褰撶幆澧冧腑 `pytest` 涓?Python 鐗堟湰涓嶅吋瀹规椂锛岃嚦灏戦渶淇濈暀锛?
```bash
python scripts/system_healthcheck.py
python scripts/verify_execution_no_pytest.py
```

## 鍗忎綔纭鍒?
1. 鍏堣 schema锛屽啀鏀逛唬鐮併€?2. 瀛楁鍙樻洿閬靛惊鍥涜仈鍔細`schemas` + `tests` + `module-registry.yaml` + 鏂囨。銆?3. PR 鍓嶅繀椤婚檮闂ㄧ缁撴灉涓庡仴搴锋姤鍛娿€?
