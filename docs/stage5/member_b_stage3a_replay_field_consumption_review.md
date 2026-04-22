# Member B Stage3A Replay Field Consumption Review
**Version**: v1.0  
**Date**: 2026-04-23  
**Role**: Member B review / sign-off for Stage3A replay field impact on mapping consumption  
**Scope**: B side only reviews whether replay field changes affect mapping consumption. This file does not re-define C-owned replay/join implementation.

---

## 1) Replay fields in scope

The current PR touches these replay-related fields:

- `event_trace_id`
- `request_id`
- `batch_id`
- `event_hash`

---

## 2) B-side mapping consumption review

| Field | Directly affects B mapping main consumption | Indirect effect | Need B joint review | Need new B-side consumption field |
| --- | --- | --- | --- | --- |
| `event_trace_id` | No | Yes, as a join key for replay / execution evidence correlation | No, unless the field stops being persisted or changes meaning | No |
| `request_id` | No | Yes, as a dedupe and traceability key | No, unless request-scoped correlation becomes ambiguous | No |
| `batch_id` | No | Yes, as a batch-scoped trace key for evidence review | No, unless batch correlation is removed or renamed | No |
| `event_hash` | No | Yes, as the stable content hash used for replay / execution joins | Yes, if hash semantics or persistence change in a way that affects B reviewability | No |

---

## 3) B-side conclusion

- These replay fields do **not** enter B's current mapping main consumption surface.
- They are still important for traceability, replay review, and evidence joining.
- B does **not** need new consumption fields for Stage3A.
- B only needs joint review if these fields stop being stable join keys or if their semantics change in a way that affects mapping reviewability.

---

## 4) Sign-off condition for B

B may sign off Stage3A replay field changes when:

- replay fields remain stable join keys,
- B-side mapping summary consumption is unchanged,
- no new B-side business field is introduced for replay mechanics,
- the change stays within C-owned replay/join implementation boundaries.

