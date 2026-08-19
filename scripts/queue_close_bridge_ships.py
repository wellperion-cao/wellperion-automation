# -*- coding: utf-8 -*-
"""배 정리 1회용 — '이어서 억지로 만든 배'와 오래 세워 둔 배를 종결한다 (GM 지시 2026-08-19).

GM 원문: "배를 처리하고, 다음에 이어서 뭔가를 계속 하려고 하다보니 어쩔수없이 이어서 배가
늘어난 것 같은데, 이것도 없었으면 좋겠어. 억지로 안만들어도되, 그냥 종결처리해도되."

무엇을 닫나 — 아래 세 부류만. 사람이 답을 기다리는 배·GM 지시 배·실무진 신고 배는 건드리지 않는다.
  ① 조건 대기: "다음에 ~하면 확인" 처럼 사건이 와야 시작되는 배. 사건이 오면 그때 다시 뜬다.
  ② 앞 배가 남긴 '다음': 완료를 닫으며 의무적으로 만든 후속 배.
  ③ 오래 세워 둔 AI 자체 기획: 아무도 기다리지 않고 몇 주째 기록이 없는 것. 필요하면 GM 이 다시 준다.

되돌리기: 각 배는 지워지지 않고 status/_queue_archive.json 으로 옮겨지며 closed_reason 이 붙는다.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from queue_lock import mutate_queue  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "status" / "_queue_archive.json"
TODAY = "2026-08-19"

# (배번호 또는 task_id, 닫는 이유)
CLOSE = [
    (261, "조건 대기 — 다음 문의가 들어오면 그때 확인하면 되는 일이라 배로 세워 둘 필요가 없다"),
    (377, "조건 대기 — GM 버튼 반응 1회 실측은 카드가 나갈 때 보면 된다"),
    (412, "조건 대기 — 정기 감사는 예약으로 저절로 돈다"),
    (495, "조건 대기 — 월 1회 갱신은 알림이 안 오면 그때 본다"),
    (501, "배가 아니라 안내문 — 실무진 요청이 오면 그때 실행하면 된다"),
    (509, "조건 대기 — 다음 습득물 접수 때 보면 된다"),
    (512, "조건 대기 — 한 달 뒤 정리는 그때 다시 판단한다"),
    (519, "조건 대기 — 다음 LOSS 처리 때 보면 된다"),
    (525, "조건 대기 — 다음 대청소 사진이 접수되면 그때 만든다"),
    (546, "앞 배가 남긴 다음 — 앞 배가 끝나면 그 자리에서 하면 된다"),
    (569, "조건 대기 — 첫 데이터가 쌓이면 그때 본다"),
    (679, "watcher 가 다음 회차에 자동으로 처리한다 — 사람이 볼 배가 아니다"),
    (681, "앞 배가 남긴 다음 — 라이브 확인은 그 배 안에서 끝난다"),
    (695, "앞 배가 남긴 다음 — 다음 발신 때 결과를 보면 된다"),
    (162, "배699(배가 늘기만 하는 구조)와 같은 일 — 그쪽으로 합친다"),
    (233, "상설 수집처 — 아침 자가점검이 더 이상 배를 만들지 않으므로 받을 것이 없다"),
    ("CTO-2026-07-13-KAKAO-OPS-AI-DIGEST", "37일째 기록 없음 — 아무도 기다리지 않는다. 필요하면 GM 이 다시 준다"),
    ("CTO-2026-07-14-RUNNER-ALL-CLEVEL-AUTODRIVE", "36일째 기록 없음 — 아무도 기다리지 않는다. 필요하면 GM 이 다시 준다"),
    ("CMO-2026-07-09-AUTONOMY-BRAIN-CMO-REFERENCE", "41일째 세워 둔 AI 자체 기획 — 필요하면 GM 이 다시 준다"),
    ("CPO-2026-07-09-AUTONOMY-BRAIN", "41일째 세워 둔 AI 자체 기획 — 필요하면 GM 이 다시 준다"),
    ("CMO-2026-07-09-NORTHSTAR-PRODUCTION-LOOP", "41일째 세워 둔 AI 자체 기획 — 필요하면 GM 이 다시 준다"),
    ("CTO-2026-06-18-PII-PROTECTION-REDESIGN", "62일째 세워 둔 AI 자체 기획 — 실제로 굴리려면 GM 이 다시 띄운다"),
    ("CTO-2026-06-23-SELF-HOSTED-SERVER-SETUP", "57일째 세워 둔 AI 자체 기획 — 실제로 굴리려면 GM 이 다시 띄운다"),
]


def _match(task, key):
    return task.get("short_no") == key if isinstance(key, int) else task.get("task_id") == key


def main() -> int:
    moved: list[dict] = []
    missed: list = []

    def apply(queue):
        moved.clear()   # mutate_queue 가 재시도하면 이 함수가 다시 불린다 — 중복 누적 방지
        missed.clear()
        items = queue if isinstance(queue, list) else (queue.get("items") or queue.get("tasks"))
        for key, reason in CLOSE:
            hit = [t for t in items if _match(t, key)]
            if not hit:
                missed.append(key)
                continue
            for t in hit:
                if t.get("status") in ("DONE", "ARCHIVED"):
                    continue
                t["status"] = "DONE"
                t["closed_reason"] = reason
                t["closed_by"] = "cto"
                t["closed_at"] = TODAY
                t["next"] = ""          # 후속 배를 만들지 않는다 (GM 지시 2026-08-19)
                t["terminal"] = True
                t["updated_at"] = TODAY
                moved.append(t)
        # 큐에서 빼서 보관함으로 (같은 객체인지로 가른다 — 값 비교는 비슷한 배를 잘못 집는다)
        moved_ids = {id(t) for t in moved}
        keep = [t for t in items if id(t) not in moved_ids]
        if isinstance(queue, list):
            return keep
        for k in ("items", "tasks"):
            if k in queue:
                queue[k] = keep
        return queue

    mutate_queue(apply, allow_shrink=True)   # 의도된 축소 — 보관함으로 옮긴다

    if moved:
        arch = json.loads(ARCHIVE.read_text(encoding="utf-8"))
        bucket = arch if isinstance(arch, list) else (arch.get("items") or arch.get("tasks"))
        bucket.extend(moved)
        ARCHIVE.write_text(json.dumps(arch, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"종결·보관 {len(moved)}척")
    for t in moved:
        print(f"  {t.get('short_no') or t.get('task_id')} | {(t.get('title') or '')[:64]}")
    if missed:
        print(f"[경고] 큐에서 못 찾은 것 {len(missed)}건: {missed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
