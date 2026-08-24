# -*- coding: utf-8 -*-
"""배754 라이브 검증 — 판독 불가(응답 파싱 실패) 뒤 재확인 경로가 실제로 도는지.

실제 GAS 쓰기는 0건이다. apiPost 를 그 자리에서만 스텁으로 바꿔 '응답을 못 읽은' 상황을
강제로 만들고, 그 뒤 read-back(진짜 시트 읽기)이 어떻게 판정하는지만 본다.

시나리오 1 — 시트 값과 같은 값을 대조: 일치 → '완료'로 종결되어야 한다(유상두 회원 케이스 재현).
시나리오 2 — 시트에 없는 값을 대조: 불일치 → 큐에 남아 재시도 예약되어야 한다(유실 금지).
"""
import json
import sys
from playwright.sync_api import sync_playwright

URL = "https://wellperion-cao.github.io/wellperion-automation/cpo/member/membership.html"
ROW = 1158          # 유상두 회원(2026-08-24 원장 실측)
PHONE = "010-5253-4004"
COL = "비고(운영부 참고사항)"

SETUP = """
() => {
  window.__errs = [];
  window.__warm = [];
  window.__origApiPost = window.apiPost;
  window.apiPost = function (payload) {
    window.__lastPayload = payload;
    // 실제로 서버에 보내지 않는다 — 응답을 못 읽은 상황만 만든다.
    return Promise.resolve({ ok: false, error: '응답 파싱 실패' });
  };
  return true;
}
"""

ENQUEUE = """
(arg) => {
  WriteBuffer.enqueue(
    { action: 'member_active_update', rowIndex: arg.row, col: arg.col, value: arg.value, keyPhone: arg.phone },
    { scope: 'active', phoneKey: arg.phone, label: '배754 검증', overlay: arg.overlay }
  );
  return WriteBuffer._queue().length;
}
"""

STATE = """
() => {
  const q = WriteBuffer._queue();
  return {
    len: q.length,
    items: q.map(it => ({
      probing: !!it.probing, parked: !!it.parked, verifying: !!it.verifying,
      attempts: it.attempts || 0, nextTry: it.nextTry || 0, lastError: it.lastError || ''
    }))
  };
}
"""


def wait_settled(page, seconds=45):
    """큐가 비거나 재시도 예약으로 안정될 때까지 기다린다."""
    for _ in range(seconds * 2):
        st = page.evaluate(STATE)
        if st["len"] == 0:
            return st
        it = st["items"][0]
        if not it["probing"] and not it["verifying"] and it["attempts"] > 0:
            return st
        page.wait_for_timeout(500)
    return page.evaluate(STATE)


def main():
    out = {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context()          # 새 컨텍스트 = 시크릿과 같은 빈 상태
        page = ctx.new_page()

        errors, warm = [], []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("request", lambda r: warm.append(r.url) if "_warm=" in r.url else None)

        page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(6000)

        out["title"] = page.title()
        out["js_errors"] = errors[:5]
        out["prewarm_fired"] = len(warm) > 0
        out["writebuffer_exists"] = page.evaluate("() => typeof WriteBuffer === 'object'")

        if not out["writebuffer_exists"]:
            print(json.dumps(out, ensure_ascii=False, indent=2))
            browser.close()
            return

        page.evaluate(SETUP)

        # 시트의 현재 값을 먼저 읽어 둔다(읽기 전용).
        cur = page.evaluate(
            """(arg) => fetch(GAS_URL + '?action=member_active_list&scope=valid&rowIndexes=' + arg.row + '&_=' + Date.now())
                 .then(r => r.json())
                 .then(d => {
                   const rows = d.rows || d.data || [];
                   const r0 = rows[0] || {};
                   return { found: rows.length, value: r0[arg.col] !== undefined ? String(r0[arg.col]) : null, name: r0['회원명'] || '' };
                 }).catch(e => ({ error: String(e) }))""",
            {"row": ROW, "col": COL},
        )
        out["sheet_now"] = cur

        same = cur.get("value") if isinstance(cur, dict) else None
        if same is None:
            same = ""

        # ── 시나리오 1: 시트와 같은 값 → 일치 → 완료 종결이어야 한다
        page.evaluate(ENQUEUE, {"row": ROW, "col": COL, "value": same, "phone": PHONE,
                                "overlay": {COL: same}})
        st1 = wait_settled(page)
        out["case1_match"] = {"queue_len": st1["len"], "items": st1["items"],
                              "기대": "queue_len=0 (완료로 종결)"}

        # ── 시나리오 2: 시트에 없는 값 → 불일치 → 큐에 남아 재시도여야 한다
        page.evaluate(ENQUEUE, {"row": ROW, "col": COL, "value": "__배754검증_저장안됨__", "phone": PHONE,
                                "overlay": {COL: "__배754검증_저장안됨__"}})
        st2 = wait_settled(page)
        out["case2_mismatch"] = {"queue_len": st2["len"], "items": st2["items"],
                                 "기대": "queue_len=1 · probing=false · attempts>=1 (재시도 큐 복귀)"}

        # 검증용 큐 항목은 남기지 않는다(실제 저장은 애초에 0건).
        page.evaluate("() => { try { localStorage.removeItem('cpo_iq_writeq_v1'); } catch(e){} }")
        out["cleanup"] = "검증 큐 삭제 완료 (GAS 쓰기 0건 · 시트 무변경)"

        browser.close()

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    sys.exit(main())
