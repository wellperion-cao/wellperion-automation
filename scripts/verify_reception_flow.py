#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""종합접수처·습득물 자체 점검 — 실무진에게 넘기기 전에 내가 한 바퀴 돌려 본다.

왜 있나 (GM 지시 2026-08-24): "이런건 자체 테스트해서 실무진들은 실무에서 바로 적용할 수
있게 해줘." 그 전까지는 화면에 코드가 실렸는지까지만 보고 "첫 건 넣어보시면 확인됩니다"로
넘겼다. 그건 확인을 실무진에게 떠넘긴 것이다. 이 스크립트가 그 자리를 대신한다.

두 가지를 본다:
  ① 습득물 한 바퀴 — 접수 폼이 보내는 것과 똑같은 요청을 실제로 보내 저장까지 확인하고,
     만든 건을 지운 뒤 다른 습득물이 함께 사라지지 않았는지 전후 대조한다.
  ② 키오스크 확대 고정 — 4개 화면을 실제 브라우저로 열어 확대 차단이 켜지는지 읽는다.
     (코드가 페이지에 실려 있는 것과 브라우저에서 도는 것은 다르다. 앞 스크립트가 죽으면
      뒤 코드는 실행되지 않는다.)

쓰기:
  python scripts/verify_reception_flow.py              # 둘 다
  python scripts/verify_reception_flow.py --kiosk-only # 읽기만(라이브에 아무것도 안 만든다)
  python scripts/verify_reception_flow.py --flow-only  # 습득물 한 바퀴만

①은 라이브에 습득물 1건을 잠깐 만들었다 지운다. 그동안 생기는 일:
  · 공개 갤러리에 흰 점 사진 1건이 몇 초 보인다
  · 업무보고방에 접수 알림이 1건 나간다(테스트 발송은 업무보고방이 맞는 자리다)
  · 사진 파일 1개가 Drive LF_Photos 에 남는다 — lf_delete 는 시트 행만 지운다.
    끝나면 남은 파일 ID 를 찍어 주니 지워 둔다.
  · 습득ID 순번(LF-n)이 하나 건너뛴다. 되돌리지 않는다(순번은 단조증가가 안전하다).
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# 정본 = 3. 웰페리온 가이드/coo/reception/wp_lost_found_register_block.html 의 두 상수.
# 값이 바뀌면 여기도 같이 바꾼다(폼이 쓰는 것과 같은 문을 두드려야 의미가 있다).
API = ("https://script.google.com/macros/s/AKfycbwk2XS1FND9V2xtXlWgsXzgA5p0FG7j"
       "Vm6YKD74JK_ME_ZvHsNUUfGE5A_8p0X8VcF3gQ/exec")
TOKEN = "wlp_voc_7b3f9a2e6c1d4085"

# 1x1 흰 점 JPEG(631바이트). 사진이 필수라 넣는 최소 이미지.
PIXEL = ("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsL"
         "DBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwh"
         "MjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAABAAEDASIA"
         "AhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQID"
         "AAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpT"
         "VFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXG"
         "x8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcI"
         "CQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYk"
         "NOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOU"
         "lZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oA"
         "DAMBAAIRAxEAPwD3+iiigD//2Q==")

KEEP_LOC = "리셉션 보관함 테스트칸"
MEMO = "시스템 점검용 테스트 — 자동 삭제 예정"

PAGES = [
    ("접수 조회", "http://wellperion.com/ko/lookup/"),
    ("종합접수처", "http://wellperion.com/ko/reception/"),
    ("습득물 보기", "http://wellperion.com/ko/lost-found/"),
    ("습득물 접수", "http://wellperion.com/ko/lost-found-register/"),
]

PROBE = """() => {
  const v = document.querySelector('meta[name=viewport]');
  return {
    lock: !!window.__wlpKioskZoomLock,
    viewport: v ? v.getAttribute('content') : '(없음)',
    touchAction: getComputedStyle(document.documentElement).touchAction
  };
}"""


def _post(payload: dict, label: str) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API, data=body,
                                 headers={"Content-Type": "text/plain;charset=utf-8"})
    d = json.loads(urllib.request.urlopen(req, timeout=90).read().decode("utf-8"))
    print(f"  [{label}] {json.dumps(d, ensure_ascii=False)[:200]}")
    return d


def _lf_list() -> list:
    url = f"{API}?action=lf_list&_={time.time()}"
    return json.loads(urllib.request.urlopen(url, timeout=90).read().decode("utf-8"))["data"]


def check_flow() -> list:
    """습득물 접수 한 바퀴. 반환 = 실패 사유 목록(비면 통과)."""
    print("── ① 습득물 한 바퀴 (라이브에 1건 만들었다 지운다) ──")
    fails: list = []
    new_id = None
    before_ids: set = set()
    try:
        before_ids = {str(r.get("foundId")) for r in _lf_list()}
        print(f"  시작 — 습득물 {len(before_ids)}건")

        res = _post({"action": "lf_submit", "t": TOKEN,
                     "foundWhen": time.strftime("%Y-%m-%d %H:%M"), "foundLoc": "리셉션",
                     "itemDesc": "[시스템 점검용 테스트] 곧 삭제됩니다",
                     "category": "consumable", "staff": "자체 점검",
                     "photo": PIXEL, "fileName": "lf_test.jpg", "mimeType": "image/jpeg",
                     "storageLoc": KEEP_LOC, "memo": MEMO}, "접수")
        if not res.get("ok"):
            return [f"접수 자체가 실패: {res.get('error')}"]
        new_id = res["id"]

        time.sleep(2)
        row = next((r for r in _lf_list() if str(r.get("foundId")) == str(new_id)), None)
        if row is None:
            fails.append("접수한 건이 직원 화면 목록에 안 나온다")
        else:
            print(f"  저장 확인 — 보관위치={row.get('keepLoc')!r} · 내부메모={row.get('memo')!r}")
            if str(row.get("keepLoc") or "") != KEEP_LOC:
                fails.append(f"보관위치가 안 저장됐다: {row.get('keepLoc')!r}")
            if str(row.get("memo") or "") != MEMO:
                fails.append(f"내부메모가 안 저장됐다: {row.get('memo')!r}")
            if str(row.get("status") or "") != "게시중":
                fails.append(f"상태가 게시중이 아니다: {row.get('status')!r}")
            if not str(row.get("photoUrl") or ""):
                fails.append("사진 URL 이 비었다")

        # 직원 전용 값이 공개 갤러리로 새지 않는지 — LF_HEADERS 분리의 목적이 이것이다.
        gal = urllib.request.urlopen(f"{API}?action=lf_gallery&_={time.time()}",
                                     timeout=90).read().decode("utf-8")
        leaked = [w for w in (KEEP_LOC, MEMO) if w in gal]
        print(f"  공개 갤러리 유출 검사 — {'샘: ' + str(leaked) if leaked else '없음(정상)'}")
        if leaked:
            fails.append(f"공개 갤러리에 직원 전용 값이 샌다: {leaked}")
        if row and row.get("photoUrl"):
            print(f"  ※ Drive 에 남는 사진 — {row['photoUrl']} (시트 행만 지워지니 손으로 정리)")
    finally:
        if new_id:
            try:
                d = _post({"action": "lf_delete", "t": TOKEN, "id": new_id}, "삭제")
                if not d.get("ok"):
                    fails.append(f"테스트 건 삭제 실패 — 손으로 지워야 함: {new_id}")
            except Exception as e:
                fails.append(f"테스트 건 삭제 중 오류 — 손으로 지워야 함: {new_id} / {e}")
            # 행 삭제는 엉뚱한 줄을 지울 수 있는 작업이라 전후 대조를 반드시 남긴다.
            try:
                time.sleep(2)
                final_ids = {str(r.get("foundId")) for r in _lf_list()}
                lost, extra = before_ids - final_ids, final_ids - before_ids
                print(f"  전후 대조 — 시작 {len(before_ids)}건 / 끝 {len(final_ids)}건 "
                      f"· 사라진 것 {sorted(lost) or '없음'} · 남은 것 {sorted(extra) or '없음'}")
                if lost:
                    fails.append(f"★원래 있던 습득물이 사라졌다: {sorted(lost)}")
                if extra:
                    fails.append(f"테스트 건이 안 지워지고 남았다: {sorted(extra)}")
            except Exception as e:
                fails.append(f"전후 대조 실패: {e}")
    return fails


async def _check_kiosk() -> list:
    from wordpress_admin_playwright import _import_playwright  # 이미 쓰는 것 재사용
    fails: list = []
    ap = _import_playwright()
    async with ap() as p:
        browser = await p.chromium.launch()
        for name, url in PAGES:
            page = await browser.new_page(viewport={"width": 800, "height": 1280},
                                          has_touch=True, is_mobile=True)
            errs: list = []
            page.on("pageerror", lambda e: errs.append(str(e)))
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
                await page.wait_for_timeout(2500)
                r = await page.evaluate(PROBE)
            except Exception as e:
                fails.append(f"{name}: 페이지 열기 실패 — {e}")
                await page.close()
                continue
            ok_lock = r["lock"] is True
            ok_vp = "maximum-scale=1" in r["viewport"] and "user-scalable=no" in r["viewport"]
            ok_ta = "pan-x" in r["touchAction"] and "pan-y" in r["touchAction"]
            print(f"  {'✅' if (ok_lock and ok_vp and ok_ta) else '❌'} {name} — "
                  f"확대고정 {r['lock']} · touch-action {r['touchAction']}")
            if errs:
                print(f"       ⚠ 스크립트 오류 {len(errs)}건: {errs[0][:120]}")
            if not ok_lock:
                fails.append(f"{name}: 확대 고정이 안 켜졌다(앞 스크립트가 죽었을 수 있음)")
            if not ok_vp:
                fails.append(f"{name}: viewport 가 100% 고정으로 안 덮였다 — {r['viewport']}")
            if not ok_ta:
                fails.append(f"{name}: 두 손가락 확대 차단이 안 걸렸다 — {r['touchAction']}")
            await page.close()
        await browser.close()
    return fails


def check_kiosk() -> list:
    print("── ② 키오스크 확대 고정 (실제 브라우저로 4개 화면 확인) ──")
    return asyncio.run(_check_kiosk())


def main() -> int:
    ap = argparse.ArgumentParser(description="종합접수처·습득물 자체 점검")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--kiosk-only", action="store_true", help="읽기만 — 라이브에 아무것도 안 만든다")
    g.add_argument("--flow-only", action="store_true", help="습득물 한 바퀴만")
    a = ap.parse_args()

    fails: list = []
    if not a.kiosk_only:
        fails += check_flow()
        print()
    if not a.flow_only:
        fails += check_kiosk()

    print()
    if fails:
        print("결과: 실패 — 실무진에게 넘기지 마라")
        for f in fails:
            print("  - " + f)
        return 1
    print("결과: 통과 — 실무진이 바로 써도 된다")
    return 0


if __name__ == "__main__":
    sys.exit(main())
