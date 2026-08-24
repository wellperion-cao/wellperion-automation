# -*- coding: utf-8 -*-
"""[스트림 #2] 시설&지원&주차 점검 및 이슈 현황 — 프로덕션 (CTO 2026-07-22).

통일 포맷 [하루 일과 정리]:
  ① 점검 핵심요약 3섹션 (support_check_summary — 텔레그램 점검현황방과 단일 진실)

종합접수 현황은 이 메시지에서 분리됨 — GM 2026-07-22 지시로 배9424(2026-07-21)의
'점검현황방 병합'을 되돌리고 별도 종합접수방으로 복원. 종합접수 현황 발송은
scripts/report_stream_2b_reception.py 참조.

텔레그램: 점검현황방(TELEGRAM_CHECK_CHAT_ID, -5136037543) 단일 발송.
카카오톡: ★운영+시설+지원+주차. 이 파일의 run(kakao_go=True)/--kakao-go는 독립 CLI
실행·수동 검증 전용 경로다. 프로덕션 자동 발송은 daily_scheduler.py run_daily_digest()가
이 모듈의 build_digest() 결과를 그대로 재사용해 별도로 처리한다(종합접수현황과 분리된
메시지 2통 중 하나 — GM 2026-07-22 go, KAKAO_GO_STREAM2 게이트). 두 경로를 동시에 켜면
중복 발송되므로 daily_scheduler.py 경유 시엔 이 CLI를 --kakao-go로 무인 실행하지 말 것.
발사 시각: 매일 22:30 (daily_scheduler.py run_daily_digest 경유) / 독립 실행 가능.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import requests

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from publish_digest import _load_env_val  # noqa: E402
try:  # 발신 관문(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import send as _tg_send
except Exception:
    def _tg_send(*a, **k):
        return False

TELEGRAM_CHAT_ID = int(os.environ.get("TELEGRAM_CHECK_CHAT_ID") or -5136037543)  # 점검현황방
KAKAO_ROOM = "★운영+시설+지원+주차"
_SENDER = REPO_ROOT / "scripts" / "kakao_report_sender.py"
_WEEKDAY_KOR = ["월", "화", "수", "목", "금", "토", "일"]


# 2026-08-01 GM 지시 — 북극성 대비 블록 제외(하루 일과 정리는 그대로 진행)


def _check_section_and_filled(today: str) -> tuple[str, dict]:
    """support_check_summary 공용 모듈로 3섹션 핵심요약 렌더 + 판정용 filled(제출여부) 반환."""
    try:
        import support_check_summary as _scs
        lines, filled = _scs.build_summary_lines(date=today)
        text = "\n".join(lines) if lines else "점검 데이터 없음."
        return text, filled
    except Exception as e:
        return f"점검 조회 실패: {e}", {}


def _check_section(today: str) -> str:
    """support_check_summary 공용 모듈로 3섹션 핵심요약 렌더."""
    return _check_section_and_filled(today)[0]


def build_digest(today: str | None = None) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    weekday = _WEEKDAY_KOR[datetime.strptime(today, "%Y-%m-%d").weekday()]
    header = (
        f"📊 [하루 일과 정리] {today}({weekday})\n"
        "🏗️ 시설&지원&주차 점검 및 이슈 현황\n"
        f"{_SENDER_LINE}"
    )
    section, filled = _check_section_and_filled(today)
    praise = _praise_block(section, filled)
    top = f"{header}\n\n{praise}\n" if praise else f"{header}\n\n"
    # 2026-08-01 GM 지시 — 법정·정기점검 공백 안내는 본문에서 빼고 run()에서 별도 메시지로 발송
    return f"{top}{section}"


# ── 실시일이 비어 있는 법정·정기점검 (2026-07-31 GM 결정) ──
# 배경: 전사 일정 SSOT 34건의 '최근 실시일'이 전부 공란인데, 그걸 채워 달라고 자동으로 묻는
#   알림이 어디에도 없었다(시설팀 알람방은 방만 등록돼 있고 정기 발신 0건). 회신이 0인 게
#   아니라 질문이 0이었다. GM: "★운영+시설+지원+주차 방을 고정하고, 알림해줘."
# ▸새 발송·새 예약을 만들지 않는다(약속 L21) — 이미 매일 밤 그 4방으로 나가는 이 점검 현황
#   메시지 끝에 얹는다. 알림이 하나 더 늘면 그만큼 안 읽힌다.
# ▸부서 라벨을 달아 한 통에 담는다 — 각자 자기 부서 줄만 보면 된다.
_SCHEDULE_SSOT = REPO_ROOT / "status" / "schedule_ssot.json"


# 살아있는 원천 = 전사 일정 GAS. 저장소 파일(status/schedule_ssot.json)은 GAS 가 죽었을 때만 쓰는
# 씨앗이다 — 실무진이 화면에서 실시일을 넣으면 **GAS 에만 저장**되고 저장소 파일은 안 바뀐다.
# ★2026-07-31 웰리 실측: GAS 에는 이미 10건이 채워져 있는데 저장소 파일은 0건이었다. 저장소를 읽으면
#   답을 이미 준 항목까지 매일 밤 다시 물어보게 된다 — 그러면 실무진은 "말해도 안 듣는다"고 느끼고
#   그 순간 이 알림은 죽는다. 물어보는 쪽과 답을 받는 쪽이 같은 한 곳을 봐야 고리가 닫힌다(약속 L01).
_SCHEDULE_GAS = ("https://script.google.com/macros/s/"
                 "AKfycbyHY37y5Cu2OGkqoODbygg5-Q-5ouCOqSOVu_HMFPlKXgudJMtiLXEtstTs3Ow4xvUn/exec")


def _load_schedule_items():
    """살아있는 일정(GAS) 우선 · 실패 시 저장소 씨앗. (items, 출처라벨) 반환."""
    try:
        r = requests.get(_SCHEDULE_GAS, params={"action": "load_schedule"},
                         timeout=20, allow_redirects=True)
        data = r.json()
        items = (data.get("data") or {}).get("items")
        if isinstance(items, list) and items:
            return items, "live"
    except Exception:
        pass
    try:
        import json
        data = json.loads(_SCHEDULE_SSOT.read_text(encoding="utf-8"))
        return (data.get("items") if isinstance(data, dict) else data), "seed"
    except Exception:
        return None, "none"


def _legal_check_blank_block() -> str:
    items, src = _load_schedule_items()
    if items is None:
        return ""   # 원천을 못 읽으면 조용히 뺀다(있는 보고를 깨뜨리지 않는다)
    if not isinstance(items, list):
        return ""
    blank: dict[str, list[str]] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        if str(it.get("last_done") or "").strip():
            continue                      # 이미 채워진 것은 묻지 않는다
        cycle = str(it.get("cycle") or "").strip()
        if not cycle:
            continue                      # 주기가 없는 것(회의·행사)은 법정·정기점검이 아니다
        name = str(it.get("name") or "").strip()
        dept = str(it.get("dept") or it.get("owner") or "미지정").strip()
        if name:
            blank.setdefault(dept, []).append(f"{name} ({cycle})")
    if not blank:
        return ""
    total = sum(len(v) for v in blank.values())
    # ★상세를 그대로 담는다(2026-07-31 GM 확정). 한 번 줄여 봤다가 되돌린 이유:
    #   "나만 보는 게 아니고, 상세 내용이 있어야 이해를 하기 때문에." 건수만 적으면 실무진은
    #   무엇을 답해야 하는지 모른다. 대신 부서를 또렷이 갈라 자기 줄만 찾게 한다.
    lines = ["━" * 10,
             f"🏛 법정·정기점검 — 최근 실시일이 비어 있는 {total}건",
             "아래 항목을 마지막으로 하신 날짜만 알려주시면 저희가 채워 넣겠습니다.", ""]
    for dept in sorted(blank, key=lambda d: -len(blank[d])):
        lines.append(f"【{dept}】 {len(blank[dept])}건")
        for nm in blank[dept]:
            lines.append(f"   · {nm}")
        lines.append("")
    lines.append("👉 여기서 날짜를 넣으시면 다음 날부터 이 목록에서 빠집니다")
    lines.append("   https://wellperion-cao.github.io/wellperion-automation/coo/check/전사_일정.html")
    # 부서 체계 페이지 — 주 1회(월요일)만 같이 안내한다(2026-07-31 GM 지시
    # "각 체계 페이지 공유해서 작성하라고 하는 구조도 있어야 할 듯").
    # ▸매일 붙이면 소음이 되어 안 읽힌다. 주 1회면 집요하되 견딜 만하다.
    # ▸무엇이 비었는지까지 세는 것은 각 체계 보드(GAS)를 읽어야 해서 시우 배(4부서 체계) 몫이다 —
    #   지금은 '자리와 방법'만 정확히 알린다. 세는 것이 붙으면 이 줄에 건수를 넣는다.
    if datetime.now().weekday() == 0:
        lines.append("")
        lines.append("📄 부서 체계 페이지 — 이번 주에 바뀐 것·빠진 것이 있으면 직접 적어 주세요")
        for _d, _f in (("시설부", "시설부 체계"), ("운영부", "운영부 체계"),
                       ("지원부", "지원부 체계"), ("주차관리부", "주차관리부 체계")):
            lines.append(f"   · {_d} {_page_url(_f)}")
        # 브로제이 실무 가이드 — 가이드 카드에 '⬜ 확인 필요 N줄 남음' 이 떠 있어도 화면을 안
        # 열면 모른다. 여기서 같이 알린다.
        # ★2026-08-07 시토(배429 · 약속 L24) — 받는 사람을 **이경연 실장**으로 바꿨다.
        #   종전엔 윤병현AM 개인 앞으로 바로 내려갔다(2026-07-31 지시). GM 확정 2026-08-06 으로
        #   운영부 지시는 실장 한 곳을 거친다 — 누가 채울지는 실장이 정한다. 아는 사람을 잃지
        #   않도록 이름은 지우지 않고 '참고' 로 남긴다.
        lines.append("")
        lines.append("🅱 브로제이 실무 가이드 — 아직 비어 있는 항목이 있습니다 (이경연 실장 · 참고: 윤병현AM)")
        lines.append("   회원앱·강사앱·부모님-유소년 얼굴연동 — 아시는 것부터 채워 주시면 됩니다")
        lines.append("   https://wellperion-cao.github.io/wellperion-automation/coo/brojay/브로제이_업무분장.html")
    if src == "seed":
        # 조용한 폴백을 숨기지 않는다 — 씨앗을 읽었다면 이미 답한 항목이 다시 떴을 수 있다.
        lines.append("(※ 일정 서버 응답이 없어 예비 자료로 만들었습니다 — 이미 알려주신 건이 다시 보이면 알려주세요)")
    return "\n".join(lines)


# ── 상단 인사 — 누가 보냈는지 + 오늘 수고하신 것 (2026-07-31 GM 지시) ──
# GM: "랭킹이나 고생했다 등의 격려 포인트도 상단에 있으면 좋을 것 같아, 웰리가 보냈다는 것도
#      인지시켜야 하고."
# ▸격려는 실제 숫자에서만 뽑는다(약속 L05 — 안 한 건 지어내지 않는다). 오늘 잘된 것이 없으면
#   격려 줄을 아예 빼고 인사만 남긴다. 없는 칭찬을 지어내면 그 순간 아무도 안 믿는다.
# ▸독려·미체크는 아래 본문이 이미 하고 있다 — 위에서 또 하지 않는다(같은 말 두 번 금지).
_SENDER_LINE = "— 웰페리온 AI 운영지원 '웰리'가 정리해 보내드립니다."



def _page_url(name: str) -> str:
    """점검 페이지 주소 — 파일 이름의 띄어쓰기를 %20 으로 바꾼다.

    ★2026-08-08 GM 지적 "링크가 짤려서 보내지네 · 들어가보니 404".
      '지원부 체계.html' 처럼 띄어쓰기가 든 이름을 그대로 붙이면 카카오톡·텔레그램이
      **띄어쓰기에서 주소를 끊는다.** 앞쪽 반쪽만 링크가 되어 404 가 뜬다.
      한글은 messenger 가 알아서 처리하므로 띄어쓰기만 바꾸면 된다(전체 인코딩하면
      사람이 주소를 읽고 어느 페이지인지 알 수 없게 된다 — 실무진이 보는 링크다).

    ★2026-08-20 수정(배670 후속) — quote(safe="가-힣ㄱ-ㅎㅏ-ㅣ")는 저 문자열을 '범위'가
      아니라 7개 낱글자(가·-·힣·ㄱ·ㅎ·ㅏ·ㅣ)로만 읽어 한글을 전부 %인코딩해왔다(실측:
      URL 이 84자→132자). 의도(위 docstring)대로 한글은 그대로 두고 띄어쓰기만 바꾼다.
    """
    return ("https://wellperion-cao.github.io/wellperion-automation/coo/check/"
            + f"{name}.html".replace(" ", "%20"))

def _praise_block(section_text: str, filled: dict | None = None) -> str:
    praise: list[str] = []
    m = re.search(r"🏗 시설부 현황\s*(\d+)회차\s*·\s*이상 없음", section_text)
    if m:
        praise.append(f"▪ 시설부 — 오늘 {m.group(1)}회차 점검까지 이상 없음. 고생하셨습니다.")
    # ── 지원부 (GM 지적 2026-08-08: "지원부는 왜 없어?") ──
    # 그 전엔 부서 전체 90% 이상일 때만 올랐다. 그런데 시설부는 '이상 없음', 주차부는
    # '이슈 없음'이면 오르는 조건이라 사실상 매일 오르고, 지원부만 90% 문턱이라 사실상
    # 못 오른다(실측 2026-08-07 47% · 08-08 42%). 같은 방에서 매일 두 부서만 이름이 뜨고
    # 한 부서만 빠지면 그건 격려가 아니라 낙인이다.
    # ▸그렇다고 없는 칭찬을 지어내지 않는다(약속 L05). 부서 전체 대신 **조 단위로 다 채운 곳**을
    #   사실에서 뽑는다 — 어제도 '여성구역 오후조 15/15'가 실제로 있었는데 안 보였다.
    m2 = re.search(r"🛠 지원부 현황\s*\d+/\d+\((\d+)%\)", section_text)
    if m2 and int(m2.group(1)) >= 90:
        praise.append(f"▪ 지원부 — 오늘 {m2.group(1)}% 완료. 고생하셨습니다.")
    else:
        done_groups = []
        for zone, _d, _t, _p, groups in re.findall(
                r"(남성구역|여성구역) (\d+)/(\d+)\((\d+)%\) — (.+)", section_text):
            for gname, gd, gt in re.findall(r"(\S+조)\s*(\d+)/(\d+)", groups):
                if int(gt) > 0 and int(gd) == int(gt):
                    done_groups.append((f"{zone} {gname}", int(gt)))
        for name, cnt in done_groups[:2]:      # 두 개까지만 — 칭찬도 길면 안 읽힌다
            praise.append(f"▪ 지원부 {name} — {cnt}건 전부 완료. 고생하셨습니다.")
    # ★2026-08-24 실측 오탐 — "이슈사항: 없음"은 실제 무이슈 제출과 미제출 폴백("자체점검
    # 준비 중")이 문구가 같아 정규식만으로는 못 가른다. filled["parking"](실제 제출 있음)을
    # 받으면 그걸로 판정하고, 없을 때만 옛 문구 매칭으로 되돌아간다(구버전 호출부 호환).
    parking_submitted = (filled.get("parking") if filled is not None
                          else bool(re.search(r"🅿 주차부 이슈사항:\s*없음", section_text)))
    if parking_submitted:
        praise.append("▪ 주차부 — 오늘 이슈 없이 마감. 고생하셨습니다.")
    if not praise:
        return ""
    return "\n".join(["🏆 오늘 수고하신 곳"] + praise) + "\n"


# ── 카카오 ★운영+시설+지원+주차 압축본 (2026-08-18 GM 결정 · 배670) ────────────────
# 텔레그램(build_digest)은 전문 그대로 유지, 카카오만 800자 상한으로 줄인다. 회차별
# 일지·측정값 20줄 등 기록성 데이터는 뺀다 — 점검 화면(체계 페이지)이 원본을 갖고 있으니
# 카톡엔 이상치·완료율·반복미완료만. 데이터는 support_check_summary 절 함수를 그대로
# 불러써서 재조회하지 않는다(약속 L01) — _check_section이 이미 하는 조회를 두 번 안 한다.
def build_kakao_digest(today: str | None = None) -> str:
    """🏗 시설·🛠 지원·🔁 반복미완료·🅿 주차 압축 4줄. 회차별 일지·측정값은 링크로 뺀다."""
    import support_check_summary as _scs
    today = today or datetime.now().strftime("%Y-%m-%d")

    fac_lines, fac_f = _scs.build_facility_section(today)
    sup_data = _scs.fetch_gas({"action": "today_live", "dept": "support", "date": today})
    sup_lines, sup_f = _scs.build_support_section(today, data=sup_data)
    par_lines, par_f = _scs.build_parking_section(today)

    def _pick(lines: list[str], *prefixes: str) -> str:
        return next((ln.strip() for ln in lines if ln.strip().startswith(prefixes)), "")

    out: list[str] = []

    # 🏆 수고 인정 — 3부서 규칙은 _praise_block 그대로 재사용, 한 줄로 합친다.
    filled = {**fac_f, **sup_f, **par_f}
    praise = _praise_block("\n".join(fac_lines + sup_lines + par_lines), filled)
    if praise:
        bits = []
        for ln in praise.split("\n")[1:]:
            if not ln.strip():
                continue
            t = re.sub(r"\s*고생하셨습니다\.?$", "", ln.lstrip("▪").strip())
            t = re.sub(r"^(\S+)\s*—\s*", r"\1 ", t)
            bits.append(t)
        if bits:
            out.append("🏆 " + " · ".join(bits) + " — 고생하셨습니다")

    # 🛠 지원부 — 종일 완료율 + 구역 요약 + 오늘 짚을 점(있으면)만. sup_lines[0]에 이미
    # "🛠 지원부 현황 …" 이모지가 있어 그대로 쓴다(중복 접두 방지).
    if sup_lines:
        line = sup_lines[0]
        zone = " · ".join(
            ln.strip().split(" — ")[0] for ln in sup_lines[1:3]
            if ln.strip().startswith(("남성구역", "여성구역")))
        if zone:
            line += f" — {zone}"
        issue = _pick(sup_lines, "❗ 짚을 점:")
        if issue:
            line += f" / {issue}"
        out.append(line)
        # ★2026-08-20(배670 후속) — 짚을 점이 있을 때만 링크를 붙인다. 이상 없는 날 매번
        #   붙이면 클릭할 것도 없는 링크가 800자 예산만 깎아먹는다. 미체크 화면(점검 남/여)은
        #   PIN 게이트라 해시 딥링크 대상에서 제외돼 있어(약속 — PIN 우회 방지) 탭 이름만 안내한다.
        if issue:
            out.append(f"👉 지원부 상세: {_page_url('지원부 체계')} → 「점검(남)/(여)」 탭(PIN)")

    # 🔁 반복 미완료 — 원장 기반, 최근 7일 반복만(1회성 특이점 제외)
    rec = _scs.recurring_issue_lines(today, max_items=3)
    if rec:
        items = " · ".join(ln.strip().lstrip("· ") for ln in rec[1:])
        out.append(f"🔁 자주 빠지는 항목 — {items}")

    # 🏗 시설부 — 회차·이상 유무 head 1줄(이미 "🏗 시설부 현황 …" 이모지 포함) + 특이사항만.
    # 회차별 일지·측정값은 뺀다.
    if fac_lines:
        out.append(fac_lines[0])
    fac_note = _pick(fac_lines, "📝 특이사항:", "❗ 기준이탈")
    if fac_note:
        out.append("📝 시설 특이 — " + fac_note.split(":", 1)[-1].strip())
        # 시설점검 탭은 PIN 없음 — 해시 딥링크가 바로 먹힌다(위 지원부와 차이).
        out.append(f"👉 시설부 상세: {_page_url('시설부 체계')}#fcheck")

    if par_lines:
        out.append(par_lines[0])
        if not re.search(r"이슈사항:\s*없음", par_lines[0]):
            out.append(f"👉 주차부 상세: {_page_url('주차관리부 체계')}#manual")

    return "\n".join(out)


def _send_telegram(text: str) -> bool:
    token = _load_env_val("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[stream2] TELEGRAM_BOT_TOKEN 미설정", flush=True)
        return False
    # parse_mode 미지정 = 평문 전송(점검요약 내 특수문자 MarkdownV2 이스케이프 불필요)
    return _tg_send(token, TELEGRAM_CHAT_ID, text, source="report_stream_2_check._send_telegram", timeout=20)


def _send_kakao(text: str) -> None:
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        subprocess.run(
            [sys.executable, str(_SENDER), "--message", text, "--only-room", KAKAO_ROOM],
            cwd=str(REPO_ROOT), capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=180,
        )
    except Exception as e:
        print(f"[stream2] 카카오 예외: {e}", flush=True)


def run(today: str | None = None, dry_run: bool = True, kakao_go: bool = False) -> str:
    today = today or datetime.now().strftime("%Y-%m-%d")
    text = build_digest(today)
    # 2026-08-01 GM 지시 — 법정·정기점검 공백 안내는 하루 일과 정리와 별도 메시지로 발송
    # (같은 목적지·같은 발신 함수 재사용, 새 발신 헬퍼 없음 — 약속 L21). 공백이 없으면 미발송.
    legal_alert = _legal_check_blank_block()
    if dry_run:
        print(f"[stream2] DRY-RUN — chat_id={TELEGRAM_CHAT_ID} 발송 안 함", flush=True)
        if legal_alert:
            print("\n=== 법정·정기점검 안내(별도 발송분) ===\n" + legal_alert, flush=True)
        return text
    ok = _send_telegram(text)
    print(f"[stream2] 텔레그램 {'완료' if ok else '실패'} → {TELEGRAM_CHAT_ID}", flush=True)
    if kakao_go:
        _send_kakao(text)
        print(f"[stream2] 카카오 → {KAKAO_ROOM}", flush=True)
    else:
        print(f"[stream2] 카카오 SKIP (kakao_go=False — GM go 게이트)", flush=True)
    if legal_alert:
        ok2 = _send_telegram(legal_alert)
        print(f"[stream2] 법정·정기점검 안내 텔레그램 {'완료' if ok2 else '실패'} → {TELEGRAM_CHAT_ID}", flush=True)
        if kakao_go:
            _send_kakao(legal_alert)
            print(f"[stream2] 법정·정기점검 안내 카카오 → {KAKAO_ROOM}", flush=True)
    return text


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(description="스트림 #2 점검+이슈 현황 보고")
    p.add_argument("--live", action="store_true", help="실발송")
    p.add_argument("--kakao-go", action="store_true", help="카카오 실발송 (GM go 게이트)")
    p.add_argument("--today", default=None, help="날짜 YYYY-MM-DD (기본=오늘)")
    a = p.parse_args()
    result = run(today=a.today, dry_run=not a.live, kakao_go=a.kakao_go)
    print("\n=== 렌더 ===")
    print(result)
