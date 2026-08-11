# -*- coding: utf-8 -*-
"""★중간관리자 방 알림성 큐 (배499 · GM 결정 2026-08-10).

여기는 알림성 건을 하루 동안 모으는 큐 하나뿐 — 새 발신기 없음(kakao_report_sender.py
가 이미 관문 · 약속 L21). 답을 요구하는 개별 요청·3-트리거(💰🔒🚫) 긴급건은 이 큐에
넣지 않는다(그건 지금처럼 즉시 개별 발송) — add()가 category로 이를 막는다.

발송 시각: 매일 17:00대(telegram_bot/daily_scheduler.run_mgmt_notice_digest, 17:05).
처음엔 하루 일과 정리(평일 22:30·휴일 20:00)에 얹었으나, GM 지시 2026-08-10 "갑자기
낮시간 카톡 자동화 중단 발송은 밤으로 이동하면 안되" 로 낮 시간으로 분리했다.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

QUEUE_PATH = Path(__file__).resolve().parent.parent / "status" / "mgmt_notice_queue.json"


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _load() -> dict:
    if QUEUE_PATH.exists():
        try:
            data = json.loads(QUEUE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "items" in data:
                return data
        except Exception:
            pass
    return {"date": "", "items": []}


def _save(data: dict) -> None:
    QUEUE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add(text: str, category: str = "notice", today: str | None = None,
        gm_task_id: str | None = None, gm_task_title: str | None = None) -> None:
    """알림성 한 줄 추가. category="notice"만 받는다 — 답요구 건·3-트리거 긴급건을
    실수로 여기 태우는 사고를 막는다(그런 건 즉시 개별 발송이 원칙).

    gm_task_id: GM업무 화면(3. 웰페리온 가이드/coo/chairman/GM업무.html) 항목을 인용할 때
    쓰는 objective id(예 "2026-08-18", status/monthly_ops_plan.json 정본). 화면에 보이는
    번호(1,2,3…)는 _gm_direct_tasks.js extract()가 렌더 시점에 배열 인덱스로 매겨 저장소엔
    없다 — 그 번호를 저장소에서 재계산하는 별도 판정 로직을 새로 만들지 않고(약속 L01:
    판정 함수 단일 출처) id를 대신 쓴다. gm_task_title을 같이 주면 본문에 제목도 실어
    id만 보고는 못 찾는 사고를 막는다(배537 팀리드 결정). 어떤 항목을 태그할지는 호출측
    (사람)이 고른다 — 여기서 자동 매칭하지 않는다."""
    if category != "notice":
        raise ValueError(f"mgmt_notice_queue.add는 category='notice'만 받는다 — 받음: {category!r} "
                          "(답요구·긴급건은 큐에 넣지 말고 즉시 개별 발송할 것)")
    text = (text or "").strip()
    if not text:
        return
    if gm_task_id:
        title_part = f"{gm_task_title.strip()} — " if gm_task_title else ""
        text = f"[GM업무 {gm_task_id}] {title_part}{text}"
    today = today or _today()
    data = _load()
    if data.get("date") != today:
        data = {"date": today, "items": []}
    data["items"].append(text)
    _save(data)


def pop_today(today: str | None = None) -> list[str]:
    """오늘치 항목을 꺼내고 큐를 비운다. 호출측(발송부)이 실패 시 재적재 책임을 진다."""
    today = today or _today()
    data = _load()
    if data.get("date") != today:
        return []
    items = list(data.get("items", []))
    _save({"date": today, "items": []})
    return items


def build_digest_text(items: list[str], today: str | None = None) -> str:
    """합본 본문 — 빈 줄 없음·한 줄에 한 가지·여러 건을 ·로 이어 붙이지 않는다
    (팀리드 지시 2026-08-10). 굵게가 안 먹으니 줄바꿈+기호로만 구분."""
    if not items:
        return ""
    today = today or _today()
    _, m, d = today.split("-")
    header = f"📌 {int(m)}/{int(d)} 공유 {len(items)}건"
    return "\n".join([header] + items)


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="★중간관리자 하루일과정리 알림성 큐")
    p.add_argument("--add", help="알림성 한 줄 추가")
    p.add_argument("--peek", action="store_true", help="오늘치 미리보기(비우지 않음)")
    a = p.parse_args()

    if a.add:
        add(a.add)
        print("추가 완료")
    elif a.peek:
        print(json.dumps(_load(), ensure_ascii=False, indent=2))
    else:
        # ── self-check (ponytail: assert 기반, 프레임워크 없음) ─────────────
        import tempfile

        _orig_path = QUEUE_PATH
        try:
            QUEUE_PATH = Path(tempfile.mkdtemp()) / "mgmt_notice_queue.json"  # noqa: F824 (모듈 전역 임시 교체)

            # ① 알림성 정상 적재 → 팝 → 큐 비워짐
            add("업무SSOT 화면에 접수·업무 점수판 2개 붙습니다 — <link>", today="2026-08-07")
            add("운영부 주간보고 초안 나왔습니다, 확인 후 고쳐 올려주세요 — <link>", today="2026-08-07")
            items = pop_today(today="2026-08-07")
            assert items == [
                "업무SSOT 화면에 접수·업무 점수판 2개 붙습니다 — <link>",
                "운영부 주간보고 초안 나왔습니다, 확인 후 고쳐 올려주세요 — <link>",
            ], f"적재 순서/내용 불일치: {items}"
            assert pop_today(today="2026-08-07") == [], "팝 후 큐가 안 비워짐"

            # ② 날짜가 다르면 어제치가 안 섞인다
            add("어제 항목", today="2026-08-06")
            assert pop_today(today="2026-08-07") == [], "날짜 경계 누수 — 어제 항목이 오늘 팝에 섞임"

            # ③ 답요구/긴급 카테고리는 거부 — 큐 오용 방지(합본 대상 분류)
            try:
                add("GM 결재 요청", category="reply_required")
                raise AssertionError("reply_required가 add()를 통과함 — 분류 가드 실패")
            except ValueError:
                pass

            # ④ 합본 본문 형식 — 헤더 1줄 + 항목별 1줄, 빈 줄·· 이음 없음
            text = build_digest_text(["A건 — <link>", "B건 — <link>"], today="2026-08-07")
            lines = text.split("\n")
            assert lines[0] == "📌 8/7 공유 2건", f"헤더 형식 불일치: {lines[0]!r}"
            assert lines[1:] == ["A건 — <link>", "B건 — <link>"], f"본문 불일치: {lines[1:]}"
            assert "" not in lines, "빈 줄 포함됨"
            assert build_digest_text([]) == "", "0건이면 빈 문자열이어야 함(발송 스킵 신호)"

            # ⑤-1 GM업무 항목 태그 — id만 있으면 "[GM업무 <id>] <text>", title도 있으면
            #    "[GM업무 <id>] <title> — <text>". 기존 호출부(태그 없음)는 그대로 동작(회귀 0).
            add("승인 상태 알려주세요", today="2026-08-07", gm_task_id="2026-08-18")
            assert pop_today(today="2026-08-07") == ["[GM업무 2026-08-18] 승인 상태 알려주세요"], "id만 태그 형식 불일치"
            add("진행 상황 알려주세요", today="2026-08-07", gm_task_id="2026-08-18", gm_task_title="리셉션 상담실 리뉴얼")
            assert pop_today(today="2026-08-07") == ["[GM업무 2026-08-18] 리셉션 상담실 리뉴얼 — 진행 상황 알려주세요"], "id+title 태그 형식 불일치"

            # ⑤ 평일/주말·공휴일 시각 판정 — daily_scheduler.run_daily_digest 가 이미 쓰는
            #    close_days.is_closed 기반 공식(_is_rest_day)을 그대로 재확인
            #    (새 판정 로직 안 만듦 — 여기서 별도 함수를 정의하지 않고 같은 한 줄 공식을
            #    직접 검증만 한다).
            import close_days as _cd
            from datetime import date as _date

            def _rest_day(d: _date) -> bool:
                return d.weekday() >= 5 or _cd.is_closed(d)

            assert _rest_day(_date(2026, 8, 11)) is False, "8/11(화) 평범한 평일인데 rest_day 오판 → 22:30 발송이어야 함"
            assert _rest_day(_date(2026, 8, 8)) is True, "8/8(토) 인데 rest_day=False → 20:00 발송이어야 하는데 놓침"
            assert _rest_day(_date(2026, 1, 1)) is True, "1/1(목·신정) 인데 rest_day=False → 평일 공휴일 20:00 케이스 놓침"
        finally:
            QUEUE_PATH = _orig_path

        print("ALL OK — mgmt_notice_queue self-check 통과 (적재/팝/분류가드/합본형식/시각판정)")
