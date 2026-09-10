# -*- coding: utf-8 -*-
"""
gocheok_blog_daily.py — 고척골프 조재오부장님 블로그 매일 07시 임시저장 자동화.
GM 지시 2026-09-10: 「데이터값들 정확하면 블로그 내용 학습해서 그 방식대로
블로그 7시마다 작업해서 임시저장해놔줘. 오늘은 지금 한번, 내일부터는 오전 7시마다」

정본(이 파일이 지어내지 않고 그대로 읽는 곳):
  - 글쓰기 규칙 = "2. 브랜드_자료/11_고척골프_조재오부장님/blog_style.json"
  - 확인된 사실 = "2. 브랜드_자료/11_고척골프_조재오부장님/client.json" facts_confirmed
  - 사진        = "2. 브랜드_자료/11_고척골프_조재오부장님/00_부장님_원자료/사진_선정/"

흐름: 주제 선택(상태 파일로 중복 방지) → run_claude 로 본문(인사~오늘의TIP)만 생성
→ 푸터·해시태그는 footer_canon·tags.core_25 그대로 코드로 붙임(정확성 보장) →
검사 4종 통과해야 → naver_blog_upload_playwright.py --mode draft (WP_TENANT=jo) 로 임시저장.

상태 = status/gocheok_blog_daily.json (쓴 주제 · 실행 기록).
로그 = logs/gocheok_blog_daily.log.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STYLE_FILE = ROOT / "2. 브랜드_자료" / "11_고척골프_조재오부장님" / "blog_style.json"
CLIENT_FILE = ROOT / "2. 브랜드_자료" / "11_고척골프_조재오부장님" / "client.json"
PHOTO_DIR = ROOT / "2. 브랜드_자료" / "11_고척골프_조재오부장님" / "00_부장님_원자료" / "사진_선정"
STATE_FILE = ROOT / "status" / "gocheok_blog_daily.json"
LOG_FILE = ROOT / "logs" / "gocheok_blog_daily.log"
UPLOADER = ROOT / "scripts" / "naver_blog_upload_playwright.py"

TENANT = "jo"
MIN_LEN = 2000
ALLOWED_AMOUNT = 99000

sys.path.insert(0, str(ROOT / "scripts"))


def log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def notify(msg: str) -> None:
    """GM 업무보고방 1줄 — alert_router 단일 관문(약속 L01) + notify.telegram_send 재사용."""
    try:
        import alert_router
        from notify.telegram_send import send as tg_send
        chat_id = alert_router.route(alert_router.GM_ACTION)
        tg_send(chat_id, msg)
    except Exception as e:
        log(f"[WARN] 텔레그램 알림 실패(무시): {e}")


def load_style() -> dict:
    return json.loads(STYLE_FILE.read_text(encoding="utf-8"))


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"used_topics": [], "runs": []}


def save_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def pick_topic(style: dict, state: dict) -> str | None:
    used = set(state.get("used_topics", []))
    for t in style["topic_bank"]:
        if t not in used:
            return t
    return None


def build_prompt(topic: str, style: dict) -> str:
    axis = random.choice(style["philosophy"]["axes"])
    return f"""너는 고척 gdr QA 골프존(고척동 gdr QA 골프아카데미) 조재오 부장님 명의로 네이버 블로그
글을 쓴다. 아래 규칙을 그대로 지켜 오늘 주제로 본문을 써라.

# 오늘 주제
{topic}

# 절대 규칙
{json.dumps(style["hard_rules"], ensure_ascii=False, indent=2)}

# 구성 (아래 순서로만 쓴다 — 시설 정보·푸터·해시태그는 절대 쓰지 마라. 코드가 따로 붙인다)
1. 인사 — 「안녕하세요 😊」 + 「고척동 gdr QA 골프아카데미입니다.」 두 줄
2. 공감 장면 — 연습장에서 누구나 본 장면을 그림처럼 묘사
3. 질문 — 그 장면 끝에 의문 한 줄 + 🤔
4. 본론 3~5덩어리 — 덩어리마다 구분선 "{style['markers']['divider']}" + 이모지({', '.join(style['markers']['section_emoji'])}) 소제목. 원리 → 방법 → 예시
5. 체크리스트 — {style['markers']['checklist']} 로 오늘 바로 할 수 있는 순서
6. GDR 데이터 — 볼 스피드·헤드 스피드·발사각·방향·구질을 눈으로 확인한다는 강점을 정보로. 숫자 자랑이 아니라 "왜 이 결과가 나왔는지" 로 잇는다
7. 업의 본질 한 덩어리 — 🌱 소제목 + 3~5문단. 아래 철학 축 하나를 오늘 본론과 이어 붙인다. 설교하지 않는다.
   철학 축: {axis['name']} — {axis['body']}
   쓰는 법: {json.dumps(style['philosophy']['how_to_write'], ensure_ascii=False)}
   금지: {json.dumps(style['philosophy']['forbidden'], ensure_ascii=False)}
8. 오늘의 골프 TIP — "{style['markers']['tip_header']}" + 한 문장 인용으로 글 전체를 한 줄로 남긴다

# 참고 사실(이 값만 쓴다 — 요금은 99,000원 외에 어떤 금액도 쓰지 마라)
{json.dumps(style["facility_facts"], ensure_ascii=False, indent=2)}

# 하지 말 것
- 푸터(주소·주차·운영시간·전화) 쓰지 마라 — 코드가 따로 붙인다
- 해시태그 쓰지 마라 — 코드가 따로 붙인다
- "웰페리온" 이름·문구를 쓰지 마라 — 이 글은 고척골프(조재오부장님) 계정 글이다
- 99,000원 외의 금액을 쓰지 마라
- 등록·결제를 재촉하지 마라

# 분량
1번~8번 본문 전체가 1,800자 이상이 되게 충분히 써라. 다른 말 없이 본문만 출력해라(설명·머리말 금지).
"""


def build_footer_and_tags(style: dict) -> str:
    fc = style["footer_canon"]
    divider = style["markers"]["divider"]
    footer = "\n".join([fc["name"], fc["address"], fc["parking"], fc["hours"], fc["phone"], fc["closing"]])
    tags = " ".join(style["tags"]["core_25"])
    return f"\n\n{divider}\n\n{footer}\n\n{tags}\n"


def assemble_body(llm_body: str, style: dict) -> str:
    return llm_body.strip() + build_footer_and_tags(style)


# ── 검사 4종 (보내기 전 코드로 막는다) ──────────────────────────────────
def run_checks(body: str, style: dict) -> list[str]:
    errs: list[str] = []
    fc = style["footer_canon"]
    for key in ("name", "address", "parking", "hours", "phone", "closing"):
        if fc[key] not in body:
            errs.append(f"푸터가 정본과 다름({key})")
    amounts = re.findall(r"[0-9][0-9,]*\s*원", body)
    for a in amounts:
        num = int(re.sub(r"[^0-9]", "", a))
        if num != ALLOWED_AMOUNT:
            errs.append(f"허용 안 된 금액 발견: {a.strip()}")
    if "#고척골프" not in body:
        errs.append("#고척골프 태그 없음")
    if re.search(r"웰페리온|wellperion|정원제\s*스포츠클럽", body, re.IGNORECASE):
        errs.append("웰페리온 문구/브랜드 혼입")
    if len(body) < MIN_LEN:
        errs.append(f"본문 {len(body)}자 — {MIN_LEN}자 미만")
    return errs


def run_upload(title: str, body: str, style: dict, mode: str) -> tuple[int, str]:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False)
    try:
        tmp.write(body)
        tmp.close()
        env = dict(os.environ)
        env["WP_TENANT"] = TENANT
        argv = [
            sys.executable, str(UPLOADER),
            "--mode", mode,
            "--title", title,
            "--body-file", tmp.name,
            "--image-dir", str(PHOTO_DIR),
            "--image-glob", "*.jpg",
            # --blog-id 는 넘기지 않는다 — 업로더가 로그인 세션(WP_TENANT=jo)에서
            # 실제 블로그 아이디를 자동 확인한다(_resolve_blog_id). "QAGOLFSTUDIO"는
            # 화면 프로필 표시명이지 실제 blogId 슬러그가 아니어서(blog.naver.com/QAGOLFSTUDIO
            # 는 404) 고정 지정하면 "유효하지 않은 요청" 에러로 draft가 막힌다(2026-09-10 실측).
            "--tags", *style["tags"]["core_25"],
        ]
        ret = subprocess.run(argv, cwd=str(ROOT), env=env, capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = (ret.stdout or "") + (ret.stderr or "")
        return ret.returncode, out[-4000:]
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="본문만 만들고 브라우저를 열지 않는다")
    ap.add_argument("--self-test", action="store_true", help="검사 함수 자가점검")
    args = ap.parse_args()

    if args.self_test:
        _self_test()
        print("gocheok_blog_daily 자가점검 통과")
        return 0

    style = load_style()
    state = load_state()
    topic = pick_topic(style, state)
    if topic is None:
        msg = "고척골프 블로그 — topic_bank 9개 전부 사용함. 주제 추가 필요."
        log(msg)
        notify(msg)
        return 0

    from model_router import run_claude
    prompt = build_prompt(topic, style)
    llm_body, used_model = run_claude(prompt, label="gocheok-blog-daily")
    if not llm_body:
        msg = f"고척골프 블로그 실패 — 모델 호출 실패(주제: {topic})"
        log(msg)
        notify(msg)
        _record_run(state, topic, "fail", "모델 호출 실패", 0, None)
        return 1

    body = assemble_body(llm_body, style)
    errs = run_checks(body, style)
    if errs:
        reason = "; ".join(errs)
        msg = f"고척골프 블로그 실패 — 검사 불통과({reason}) 주제: {topic}"
        log(msg)
        notify(msg)
        _record_run(state, topic, "fail", reason, len(body), used_model)
        return 1

    title = topic
    if args.dry_run:
        rc, out = run_upload(title, body, style, mode="dryrun")
        log(f"[dry-run] rc={rc}\n{out}")
        print(f"[dry-run] 본문 {len(body)}자 · 검사 통과 · 업로더 dryrun rc={rc}")
        return 0 if rc == 0 else 1

    rc, out = run_upload(title, body, style, mode="draft")
    if rc == 0:
        msg = f"고척골프 블로그 임시저장 성공 — 「{topic}」 {len(body)}자 (모델 {used_model})"
        log(msg + "\n" + out)
        notify(msg)
        state.setdefault("used_topics", []).append(topic)
        _record_run(state, topic, "ok", "", len(body), used_model)
        save_state(state)
        return 0

    # 실패 사유는 지어내지 않는다 — 업로더가 찍은 [ERROR] 줄을 그대로 실어 보낸다.
    # 2026-09-10: 「임시저장 큐 누적 여부 확인 필요」라고 미리 적어 두었더니 실제 원인(파트너 계정 자리에
    # 웰페리온 세션이 들어 있던 것)과 다른 곳을 가리켰다.
    err = next((ln.strip() for ln in reversed(out.splitlines()) if "[ERROR]" in ln), "")
    reason = f"업로더 rc={rc}" + (f" · {err[:160]}" if err else "")
    msg = f"고척골프 블로그 임시저장 실패 — 「{topic}」 {reason}"
    log(msg + "\n" + out)
    notify(msg)
    _record_run(state, topic, "fail", reason, len(body), used_model)
    save_state(state)
    return 1


def _record_run(state: dict, topic: str, result: str, reason: str, chars: int, model: str | None) -> None:
    state.setdefault("runs", []).append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "topic": topic,
        "result": result,
        "reason": reason,
        "chars": chars,
        "model": model,
    })
    save_state(state)


def _self_test() -> None:
    style = load_style()
    fc = style["footer_canon"]
    good_footer_tags = build_footer_and_tags(style)
    filler = ("연습장에서 흔히 보는 장면을 오늘도 하나 떠올려 봅니다. " * 80)
    good = filler + good_footer_tags
    assert len(good) >= MIN_LEN, "자가점검 표본이 최소길이보다 짧음 — 표본 보강 필요"
    assert run_checks(good, style) == [], run_checks(good, style)

    bad_footer = good.replace(fc["phone"], "010-0000-0000")
    assert any("푸터" in e for e in run_checks(bad_footer, style))

    bad_amount = good + " 체험비는 150,000원 입니다."
    assert any("금액" in e for e in run_checks(bad_amount, style))

    bad_tag = good.replace("#고척골프", "")
    assert any("태그" in e for e in run_checks(bad_tag, style))

    bad_brand = good + " 웰페리온 정원제 스포츠클럽 문의는 여기로."
    assert any("웰페리온" in e for e in run_checks(bad_brand, style))

    bad_len = "짧은 글"
    assert any("미만" in e for e in run_checks(bad_len, style))


if __name__ == "__main__":
    sys.exit(main())
