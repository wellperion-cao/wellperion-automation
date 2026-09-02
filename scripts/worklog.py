# scripts/worklog.py
# 전 C-Level 공용 "작업 현황 로그" 기록 모듈 (2026-07-23, GM 승인 · CMO-2026-07-23-WORKLOG-PANEL).
#
# 계기: AI하루 EP10이 검수큐 등록 누락돼 아무도 못 봄(2026-07-23 실사고) — 로그가
# "한 일"만 남기면 "빠진 것"은 놓친다. 이 모듈은 "한 일" 쪽(기록)만 담당한다.
# "빠진 것" 자동 적발은 scripts/worklog_gaps.py.
#
# API 1개:
#   from worklog import log
#   log(role, area, event, result="ok", detail="", ref="", url="")
#   → status/worklog.jsonl 에 1줄 append.
#
# ★고정 스키마(절대 변경 금지 — 화면 담당 에이전트가 동시에 이 규격으로 렌더 중):
#   {"ts":"2026-07-23T07:39:35+09:00","role":"cmo","area":"발행",
#    "event":"AI하루 01 인스타 발행","result":"warn",
#    "detail":"성공 토스트 확인·주소 미회수","ref":"CMO-...","url":""}
#   - ts = ISO8601 KST(+09:00) / role ∈ ceo|cfo|chro|cmo|coo|cpo|cto
#   - area = 짧은 한국어 분류(예 "발행","검수","제작","점검")
#   - event = 한 줄 한국어 요약(실무진이 읽는다 — 영어·코드·약어 금지)
#   - result ∈ ok|warn|fail / detail·ref·url 선택
#
# ★ best-effort — 기록 실패가 호출부(발행 등 본업)를 절대 막지 않는다.
#   log() 는 절대 예외를 던지지 않고 성공 여부(bool)만 반환한다.
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
WORKLOG_PATH = ROOT / "status" / "worklog.jsonl"

KST = timezone(timedelta(hours=9))

VALID_RESULTS = {"ok", "warn", "fail"}
_APPEND_RETRIES = 3
_APPEND_RETRY_WAIT_SEC = 0.2

# 단일 출처 — "GM 지시"를 "GM 요청"으로 바꾼다(2026-08-15 GM 요청). 새로 쓰는 값은 GM_AREA,
# 과거 원장에 이미 쌓인 "GM지시" 까지 읽어야 하는 곳은 GM_AREAS 로 판정한다.
# 다른 파일은 이 상수를 import 해서 쓴다 — 값을 복사하지 않는다(약속 L01).
GM_AREA = "GM요청"
GM_AREAS = ("GM요청", "GM지시")

# GM요청 접수 자동화(2026-08-08, GM 지시 A안) — UserPromptSubmit 훅 진입점.
# ref 채번 = 역할별 1000단위 구간(GM-YYYYMMDD-{구간+N}) — kungjjak_board.py --all-roles 가
# ref 로만 짝을 묶으므로(role 필터 없음) 역할이 겹치는 번호를 쓰면 다른 역할 접수가 한 표에
# 섞여버린다. 구간을 나눠 물리적으로 겹칠 수 없게 한다. 미지정 역할은 9000대로 격리.
_GM_REF_BLOCK = {"ceo": 1000, "cto": 2000, "cmo": 3000, "cpo": 4000,
                  "coo": 5000, "chro": 6000, "cfo": 7000}
_GM_REMINDER = ("[형식 고정] 말투=caveman ultra(군더더기·과정 서술 금지) · "
                "GM 물음 1개 = 표 1개(8요소 📌GM요청 🔍실측 ✅반영 🔎검수 📤올림 ⏱소요 💡더나았을방법 👉GM액션) · "
                "표 밖 줄글은 표로 못 담는 것만")

# 단순 조회·질의는 접수하지 않는다(2026-08-16 · 배658 — "쿵짝표 보여줘" 같은 발화까지 지시로
# 채번돼 완료 짝이 안 붙고 쿵짝표에 거짓 미완으로 남던 것). 짧은 문장 전체가 "<대상> 보여줘/
# 알려줘" 꼴일 때만 거른다 — 길거나 다른 동사·조건이 섞인 문장(진짜 지시)은 그대로 접수한다.
_SIMPLE_QUERY_RE = re.compile(
    r'^[\w가-힣().%·/ ]{1,24}(보여\s*줘|보여\s*주세요|보여줄래\??|알려\s*줘|알려\s*주세요)[!.?~]*$')


def _next_gm_ref(role: str, day: str) -> str:
    """그날·그 역할의 기존 최대 번호 다음(역할 구간 안에서). 파일 없으면 구간 첫 번호."""
    block = _GM_REF_BLOCK.get(role, 9000)
    prefix = f"GM-{day}-"
    max_nn = block
    if WORKLOG_PATH.exists():
        with open(WORKLOG_PATH, encoding="utf-8") as f:
            for line in f:
                if prefix not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("role") != role:
                    continue
                ref = str(d.get("ref") or "")
                if not ref.startswith(prefix):
                    continue
                try:
                    nn = int(ref[len(prefix):])
                except ValueError:
                    continue
                if block <= nn < block + 1000 and nn > max_nn:
                    max_nn = nn
    return f"{prefix}{max_nn + 1}"


def record_gm_prompt_hook() -> None:
    """UserPromptSubmit 훅 진입점 — GM 프롬프트를 GM요청 접수로 best-effort 기록하고,
    항상 리마인더 JSON 을 stdout 에 낸다(예외 나도 세션은 절대 막지 않는다)."""
    try:
        data = json.loads(sys.stdin.read())
        prompt = str(data.get("prompt") or "").strip()
        role = (os.environ.get("WELLPERION_ROLE") or "").strip().lower()
        # ★역할을 못 읽으면 조용히 건너뛰지 않는다(시포 배490 · 2026-08-08 실사고).
        #   그날 시포는 GM 지시 17건을 받아 16건을 끝냈는데 쿵짝표가 "오늘 받은 지시 없음"을 냈다.
        #   훅은 돌았고 리마인더도 나갔지만 role 이 비어 접수만 건너뛴 탓이었다 — 아무 흔적이
        #   없어서 그날 하루가 통째로 사라진 것처럼 보였다. 흔적을 남겨 다음엔 바로 잡히게 한다.
        if prompt and not role:
            try:
                log("", GM_AREA, "역할 미인식 — 접수를 남기지 못했다",
                    result="fail",
                    detail="WELLPERION_ROLE 이 훅 프로세스에 안 넘어왔다. 부팅 배치의 환경변수 상속을 확인할 것(배490).")
            except Exception:
                pass
        if prompt and role:
            event = prompt.splitlines()[0].strip()
            # 사람이 친 것만 접수한다. 훅은 시스템이 주입하는 알림·명령 출력에도 똑같이 걸려서,
            # 2026-08-08 에 `<task-notification>` 한 줄이 GM 지시로 원장에 박혀 쿵짝표에
            # "진행중" 으로 떴다. 아무도 시키지 않은 일이 놓친 일로 보이면 판단이 어긋난다.
            # 'C-Level 부팅'(부팅 지시문)·'너는 …'(서브에이전트 역할 프롬프트)도 사람이 친 게 아니라
            # 붙여넣은 실행문이다. 2026-08-11 실측: 미완 91건 중 16건이 이 둘이었다 —
            # GM 이 시킨 적 없는 일이 "미완"으로 쌓여 쿵짝표 숫자를 부풀렸다.
            # '당신은 웰페리온…입니다'(7역할 부팅 프롬프트 1인칭 선언문)도 같은 부류 —
            # 2026-08-13 쿵짝표에 시우 부팅문이 GM 지시로 두 줄 잡힌 실사고로 추가.
            if event.startswith(('<', '[SYSTEM NOTIFICATION', '[형식 고정',
                                 'C-Level 부팅', '너는 ', '당신은 ')):
                event = ''
            elif _SIMPLE_QUERY_RE.match(event):
                event = ''
            if len(event) > 120:
                event = event[:120] + "…"
            if event:
                # ★새 지시를 접수하기 전에 **직전 지시들을 닫는다**(2026-08-11).
                #   GM 이 다음 말을 걸었다는 건 앞 물음에 답이 끝났다는 뜻이다.
                #   Stop 훅에도 같은 호출을 뒀지만 그쪽은 실측상 이 세션에서 한 번도 발화하지
                #   않았다 — 접수는 100% 쌓이고 있으므로(이 훅) 닫는 것도 여기서 보장한다.
                #   멱등이라 두 곳에서 불려도 같은 ref 가 두 번 닫히지 않는다.
                close_gm_refs(role)
                day = datetime.now(tz=KST).strftime("%Y%m%d")
                ref = _next_gm_ref(role, day)
                log(role, GM_AREA, event, result="warn",
                    detail="받음 · 자동 접수(UserPromptSubmit)", ref=ref)
    except Exception:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                              "additionalContext": _GM_REMINDER}},
                      ensure_ascii=False))


# 자동종결이 「한 것」 칸을 스스로 채운다 (GM 선택 2026-08-13 · 배606 후속)
#   왜: 자동종결이 "⚠️ 별도 완료 기록 없음"만 적어서, 쿵짝표 「한 것」 칸이 오늘 시토 19건 중
#   18건이 안내 문구였다. GM: "다 된 줄 알았는데 계속 빈틈이 생기네." 사람이 매번 손으로
#   적게 하는 규칙은 이미 두 번 실패했으니(2026-08-11·08-13) 기계가 적게 한다.
#   무엇을 적나: 그 지시를 받은 시각부터 다음 지시를 받기 전까지 **실제로 만들어진 커밋 제목**.
#   지어내지 않는다 — 커밋이 없으면 기존 ⚠️ 문구 그대로 둔다(없는 일을 있는 것처럼 적지 않는다).
_AUTO_NOISE = ("chore(auto)", "chore(queue): auto-log", "Merge ", "chore(sync)")


def _commits_between(since: str, until: str = "", role: str = "",
                     used: set | None = None) -> str:
    """[since, until) 사이 **그 역할이 남긴** 커밋 제목을 사람 말로 잇는다. 없으면 빈 문자열.

    ★역할 태그로 거른다(2026-08-13 실측). 이 저장소는 세션 5개가 동시에 커밋하므로 시각만으로
    자르면 시포·시우가 같은 시각에 낸 커밋이 시토 칸에 붙는다 — 빈칸보다 나쁘다(GM 이 남의 일을
    내 일로 읽는다). 그래서 `feat(cto):` 처럼 **머리 태그에 자기 역할이 박힌 것만** 가져오고,
    하나도 없으면 빈 문자열을 돌려 기존 ⚠️ 문구가 그대로 남게 한다.
    """
    import subprocess

    if not since or not role:
        return ""
    # -n 은 필터 전에 걸리므로 넉넉히 받는다 — 12 로 두면 같은 시각 남의 커밋에 밀려
    # 내 커밋이 잘려 나가고 빈칸이 된다(2026-08-13 실측).
    cmd = ["git", "log", "--no-merges", f"--since={since}", "--format=%s", "-n", "60"]
    if until:
        cmd.insert(3, f"--until={until}")
    try:
        out = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, timeout=10)
        if out.returncode != 0:
            return ""
        subs = [s.strip() for s in out.stdout.decode("utf-8", "replace").splitlines() if s.strip()]
    except Exception:  # noqa: BLE001
        return ""
    tag = f"({role.strip().lower()})"
    subs = [s for s in subs
            if not s.startswith(_AUTO_NOISE) and tag in s.split(":", 1)[0].lower()]
    # 기계가 주기적으로 내는 발행 커밋은 「한 것」이 아니다 — 같은 제목이 몇 줄씩 반복돼
    # GM 화면에서 진짜 결과를 밀어낸다(2026-08-13 실측: 시포 칸이 '문의 스냅샷 자동 발행' 로 도배).
    subs = [s for s in subs if "자동 발행" not in s]
    seen, uniq = set(), []
    for s in subs:
        if s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    subs = uniq
    # 앞선 지시가 이미 가져간 커밋은 뺀다 — 창 끝을 열어 두면(아래 close_gm_refs 참조)
    # 같은 커밋이 여러 지시의 「한 것」 칸에 중복으로 붙는다.
    if used is not None:
        subs = [s for s in subs if s not in used]
        used.update(subs)
    if not subs:
        return ""
    # 커밋 제목의 앞머리 태그(feat(cto): 등)는 GM 화면에서 읽히지 않아 떼고 보여준다.
    clean = []
    for s in subs[:3]:
        body = s.split(": ", 1)[1] if ": " in s[:24] else s
        clean.append(body[:70])
    tail = f" 외 {len(subs) - 3}건" if len(subs) > 3 else ""
    return " · ".join(clean) + tail


_GRACE_MINUTES = 60


def _window_end(ts: str, all_ts: list) -> str:
    """그 지시의 커밋을 찾을 창의 끝 = 다음 접수 시각 + 유예 60분.

    ★유예가 있어야 하는 이유(2026-08-13 수리): 접수 훅은 GM 이 말한 **순간** 찍히고,
    커밋은 내가 일을 마친 **뒤**에 나온다. 그래서 '다음 접수 시각'을 그대로 창 끝으로 쓰면
    GM 이 짧게 연달아 말씀하실 때 창이 70초짜리가 되고 그 안엔 커밋이 하나도 없다
    (실측: 창 15:57:28~15:58:38, 정작 그 지시의 커밋은 16:0x). 그 결과 「⚠️ 자동종결」이
    쌓여 하루에 두 번(7건·4건) GM 께 드리기 전에 손으로 채워야 했다.
    유예를 무한대로 두면 반대로 한 지시가 하루치 커밋을 다 먹으므로 60분으로 끊는다.
    """
    import datetime as _dt

    nxt = next((t for t in all_ts if t > ts), "")
    if not nxt:
        return ""  # 마지막 지시 — 창을 열어 둔다(그 뒤 커밋은 전부 이 지시 것)
    try:
        return (_dt.datetime.fromisoformat(nxt)
                + _dt.timedelta(minutes=_GRACE_MINUTES)).isoformat()
    except ValueError:
        return nxt


def _gm_ref_pairs(role: str) -> tuple[dict[str, str], set[str]]:
    """그 역할의 GM 접수(warn: ref→최초 ts)와 완료(ok: ref) 를 한 번에 읽는다.

    ★area 는 보지 않는다 — 짝은 ref 로만 맞춘다. 완료 기록의 area 는 그때그때 다르게
    적혀 왔다(실측 2026-09-03 ceo: GM지시 412 · GM요청 98 · 검수 1 · 판정 2 · 큐정리 1).
    area 까지 같아야 닫힌 것으로 세면 실제로 끝난 지시가 미완으로 쌓인다.
    """
    warn: dict[str, str] = {}
    ok: set[str] = set()
    role_v = (role or "").strip().lower()
    if not role_v or not WORKLOG_PATH.exists():
        return warn, ok
    with open(WORKLOG_PATH, encoding="utf-8") as f:
        for line in f:
            if "GM-" not in line:
                continue
            try:
                d = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if (d.get("role") or "").strip().lower() != role_v:
                continue
            ref = str(d.get("ref") or "")
            if not ref.startswith("GM-"):
                continue
            if d.get("result") == "warn":
                warn.setdefault(ref, str(d.get("ts") or ""))
            elif d.get("result") == "ok":
                ok.add(ref)
    return warn, ok


def open_gm_refs(role: str) -> list[tuple[str, str]]:
    """아직 완료 짝이 없는 GM 접수 [(ref, 접수시각)] — 오래된 순. 읽기전용.

    미완 건수를 세는 곳은 여기 하나다(약속 L01). 부팅·자가점검이 각자 세면 판정이
    갈린다 — 2026-09-03 아침 실측에서 손으로 센 미완 86건이 정본 기준 0건이었다.
    """
    warn, ok = _gm_ref_pairs(role)
    return [(r, t) for r, t in sorted(warn.items(), key=lambda kv: kv[1]) if r not in ok]


def close_gm_refs(role: str, detail: str = "") -> int:
    """그 역할의 열린 GM 요청 접수(warn 만 있고 ok 짝 없는 것)를 닫는다. 닫은 건수를 돌려준다.

    왜 있나(2026-08-11): 접수는 UserPromptSubmit 훅이 기계로 남기는데 완료 짝은 사람이 손으로
    남겨야 해서, 답을 다 한 물음도 "미완"으로 쌓였다. 실측 — 시토 3/30 · 웰리 26/38 · 시모
    13/16 · 시포 8/12 로 역할마다 제각각이었고 미완이 91건까지 불었다.

    ★쿵짝표는 '물음↔답' 대장이다. '지시↔완수' 추적은 배(status/_queue.json)가 한다(약속 L15).
    두 벌을 만들면 진실이 둘이 된다(L01). 그래서 세션이 응답을 끝내면 여기서 닫고,
    후속 작업이 남은 건은 배가 이어받는다.

    """
    try:
        if not WORKLOG_PATH.exists():
            return 0
        role_v = (role or "").strip().lower()
        if not role_v:
            return 0
        warn, _ok_unused = _gm_ref_pairs(role_v)
        n = 0
        pending = open_gm_refs(role_v)
        # ★창 끝을 열어 둔다(2026-08-13 수리). 전에는 '다음 접수 시각'을 창 끝으로 썼는데,
        #   GM 이 짧게 연달아 말씀하시면 창이 1분짜리가 되고 **내 작업 커밋은 그 창이 닫힌
        #   뒤에 나온다** — 접수 훅은 GM 이 말한 순간 찍히고, 커밋은 내가 일을 마친 뒤라
        #   순서가 항상 어긋난다. 실측(2026-08-13): 창 15:57:28~15:58:38(70초) 안에 내
        #   커밋이 하나도 없어 「⚠️ 자동종결」로 닫혔고, 정작 그 지시의 커밋은 16:0x 에 있었다.
        #   같은 이유로 하루에 두 번(7건·4건) GM 께 드리기 전에 손으로 채워야 했다.
        #   대신 같은 커밋이 여러 지시에 중복으로 붙지 않게 `used` 로 이미 쓴 제목을 뺀다.
        #   ★순서도 뒤집는다 — **최신 지시부터** 커밋을 집는다. 창 끝을 열어 둔 채 오래된
        #   것부터 돌리면 가장 오래된 지시가 최신 커밋까지 전부 먹고 뒤 지시는 빈칸이 된다
        #   (실측 2026-08-13: 15:37 지시가 19:0x 커밋을 가져가고 15:57 지시가 빈칸).
        #   ★순서도 뒤집는다 — **최신 지시부터** 커밋을 집는다. 창 끝을 늘린 채 오래된
        #   것부터 돌리면 가장 오래된 지시가 뒤쪽 커밋까지 전부 먹고 뒤 지시는 빈칸이 된다
        #   (실측 2026-08-13: 15:37 지시가 19:0x 커밋을 가져가고 15:57 지시가 빈칸).
        used_subjects: set = set()
        all_ts = sorted(warn.values())
        for idx, (ref, ts) in enumerate(reversed(pending)):
            nxt = _window_end(ts, all_ts)
            # 기본 detail 은 "정말 아무것도 안 적은 것"이다 — 쿵짝표가 이걸 완료로 세면서
            # GM 이 "빈틈이 생긴다"고 지적한 30건 중 다수가 이 자리였다(2026-08-13). 실제로
            # 처리한 게 없다는 사실 자체를 detail 에 정직하게 남긴다(⚠️ 로 시작 — 쿵짝표
            # evidence_state 가 상투어로 걸러낸다).
            auto = detail or _commits_between(ts, nxt, role_v, used_subjects)
            if log(role_v, GM_AREA, "답변 종결 — 세션이 응답을 마쳤다",
                   result="ok",
                   detail=auto or "⚠️ 자동종결 — 세션 응답 뒤 별도 완료 기록 없음(Stop 훅)",
                   ref=ref):
                n += 1
        return n
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] close_gm_refs 예외(best-effort): {exc}", file=sys.stderr)
        return 0


# ── GM요청 접수 번호를 한 벌로 (GM 지시 2026-08-12 "구조문제도 해결해줘") ──────────────
#   무엇이 문제였나: 같은 지시가 두 벌로 기록됐다. ①UserPromptSubmit 훅이 GM 이 말한 순간
#   자동으로 접수(GM-YYYYMMDD-1xxx) ②그 뒤 역할이 손으로 또 접수(…-2xxx). 둘은 서로를 모르니
#   짝맞춤이 한쪽을 영원히 못 닫고, 아침 미완 숫자가 실제보다 부풀었다(2026-08-12 실측 —
#   겉보기 미완 23건 중 실질 3건, 나머지 20건이 이 중복이었다).
#   어떻게 막나: 채번을 한 곳으로 모은다. 역할이 GM요청을 손으로 적을 때, 그날 아직 안 닫힌
#   자동 접수가 있으면 새 번호를 따지 않고 그 번호에 얹는다. 손으로 적은 완료도 같은 번호로 간다.
#   여기(log)에 두는 이유 = 모든 기록이 지나가는 유일한 관문이라서다(약속 L21).
_GM_MANUAL_RANGE_MIN = 2000   # 역할이 손으로 쓰던 구간 — 이 위쪽만 흡수 대상


def _open_auto_gm_ref(role: str, day: str) -> str:
    """그날 그 역할의 자동 접수 중 아직 완료 짝이 없는 가장 최근 ref. 없으면 빈 문자열.

    ★역할별 구간을 _GM_REF_BLOCK 에서 그대로 가져온다(2026-08-13 배572 수리) — 예전엔
    1000~1999 로 고정해 ceo(1000대) 말고는 절대 못 찾았다. cto(2000대)는 자기 자신의
    구간이 '수동' 판정 구간(_GM_MANUAL_RANGE_MIN=2000)과 겹쳐, 이 함수가 항상 빈
    문자열만 돌려주고 있었다 — d5919e40e 의 중복 warn 병합이 ceo 말고는 전부 무효였다."""
    block = _GM_REF_BLOCK.get(role, 9000)
    prefix = f"GM-{day}-"
    warns: list[str] = []
    closed: set[str] = set()
    try:
        with open(WORKLOG_PATH, encoding="utf-8") as f:
            for line in f:
                if prefix not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if (d.get("role") or "") != role or (d.get("area") or "") not in GM_AREAS:
                    continue
                ref = str(d.get("ref") or "")
                if not ref.startswith(prefix):
                    continue
                try:
                    nn = int(ref[len(prefix):])
                except ValueError:
                    continue
                if not (block <= nn < block + 1000):
                    continue          # 자기 역할의 자동 접수 구간만 본다
                if d.get("result") == "warn":
                    warns.append(ref)
                elif d.get("result") == "ok":
                    closed.add(ref)
    except FileNotFoundError:
        return ""
    except Exception:
        return ""
    for ref in reversed(warns):
        if ref not in closed:
            return ref
    return ""


def _ref_taken_by_other_role(ref: str, role: str) -> bool:
    """이 ref 문자열을 다른 역할이 이미 area가 GM_AREAS(GM요청·GM지시) 로 쓰고 있는가(2026-08-13 실측 —
    같은 날 GM-20260812-2001~2024 가 ceo·cto 양쪽에 동시에 존재했다. 손으로 번호를
    짓는 경로가 역할 구간을 몰라 서로 다른 두 지시가 같은 ref 를 공유했다).
    걸리면 True — 새 ref 를 다시 뽑아 충돌을 물리적으로 끊는다."""
    try:
        with open(WORKLOG_PATH, encoding="utf-8") as f:
            for line in f:
                if ref not in line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if str(d.get("ref") or "") != ref or (d.get("area") or "") not in GM_AREAS:
                    continue
                if (d.get("role") or "") and (d.get("role") or "") != role:
                    return True
    except Exception:
        return False
    return False


def _merge_gm_ref(role: str, area: str, result: str, ref: str) -> tuple[str, bool]:
    """손으로 적은 GM요청 ref 를 그날 열려 있는 자동 접수 ref 로 합친다. 그 외는 그대로 둔다.
    (합쳐진 ref, 이미 열려 있던 것에 얹었나) 를 돌려준다.

    ★warn 만 본다(2026-08-13 배506 수리) — result 를 안 가리면 손으로 남기는 **완료(ok)**
    까지 '열려 있는 딴 ref' 로 재배정돼, 의도한 것과 다른 ref 가 엉뚱하게 닫힐 뻔했다.

    ★이미 열려 있는 ref 에 얹었다는 신호를 함께 돌려준다(2026-08-13 배572 수리) — ref 만
    합치고 warn 줄을 또 쓰면, 짝맞추기가 '건수'로 세는 이상(배506 수리) 그 두 번째 warn
    이 영원히 미완 1건으로 남는다. 실제 새로 쓸 게 없다 — 이미 열린 접수를 호출부가
    한 번 더 부른 것뿐이므로, 호출부(log)가 이 신호로 두 번째 줄 자체를 건너뛴다."""
    if area not in GM_AREAS or result != "warn" or not role or not ref.startswith("GM-"):
        return ref, False
    day = datetime.now(tz=KST).strftime("%Y%m%d")
    if not ref.startswith(f"GM-{day}-"):
        return ref, False              # 지난 날 것을 소급 정리하는 중이면 손대지 않는다
    try:
        nn = int(ref.rsplit("-", 1)[-1])
    except ValueError:
        return ref, False
    if nn < _GM_MANUAL_RANGE_MIN:
        return ref, False              # 자동 접수 자신은 그대로
    merged = _open_auto_gm_ref(role, day)
    if merged:
        return merged, True            # 이미 열려 있다 — 중복, 두 번째 줄은 안 쓴다
    if _ref_taken_by_other_role(ref, role):
        return _next_gm_ref(role, day), False  # 남의 역할과 겹친 번호 — 내 구간에서 새로 뽑는다
    return ref, False


def log(
    role: str,
    area: str,
    event: str,
    result: str = "ok",
    detail: str = "",
    ref: str = "",
    url: str = "",
    ts: str = "",
) -> bool:
    """status/worklog.jsonl 에 고정 스키마로 1줄 append. best-effort(항상 bool 반환, 예외 안 던짐).

    role: ceo|cfo|chro|cmo|coo|cpo|cto (소문자 정규화만 하고 값 자체는 검증 실패해도 기록 시도
          — 스키마 계약을 지키되 호출부를 막지 않는 게 우선).
    result: ok|warn|fail (그 외 값이 오면 'ok'로 안전 폴백).
    ts: 소급 기록용 시각(ISO8601 KST). 비우면 지금. 접수를 놓쳐 나중에 남길 때,
        지금 시각으로 찍으면 쿵짝표의 소요 칸이 거짓이 된다 — 실제 시각을 넣는다.
        스키마는 그대로다(같은 ts 필드).
    """
    try:
        result_v = (result or "ok").strip().lower()
        if result_v not in VALID_RESULTS:
            result_v = "ok"
        # ref 합치기는 '있으면 좋은' 정리다 — 여기서 터져도 기록 자체는 남아야 한다(배590).
        # 2026-08-12 시포 세션에서 이 호출이 매 프롬프트마다 NameError 를 냈고, 그때 log() 전체가
        # 예외로 빠져 **GM 지시 접수(warn) 줄이 통째로 안 남았다.** 쿵짝표·아침 자가점검이 전부 이
        # 원장을 읽으므로 '오늘 GM이 시킨 것'이 사라진다. 보조 정리가 본 기록을 죽이지 못하게 가둔다.
        try:
            ref, dup = _merge_gm_ref((role or "").strip().lower(), area or "", result_v, ref or "")
            if dup:
                # 이미 열려 있는 접수에 얹혔다 — 같은 지시를 warn 줄로 또 남기면 짝맞추기가
                # (건수 기준, 배506 수리) 영원히 미완 1건을 만든다(배572). 기록할 새 게 없다.
                return True
        except Exception as exc:
            print(f"[WARN] worklog ref 합치기 건너뜀(기록은 그대로 남긴다): {exc}", file=sys.stderr)
        record = {
            "ts": (ts or "").strip() or datetime.now(tz=KST).isoformat(timespec="seconds"),
            "role": (role or "").strip().lower(),
            "area": area or "",
            "event": event or "",
            "result": result_v,
            "detail": detail or "",
            "ref": ref or "",
            "url": url or "",
        }
        line = json.dumps(record, ensure_ascii=False) + "\n"
        WORKLOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        last_exc: Exception | None = None
        for attempt in range(_APPEND_RETRIES):
            try:
                with open(WORKLOG_PATH, "a", encoding="utf-8") as f:
                    f.write(line)
                return True
            except Exception as exc:  # 동시 쓰기 등 — 짧게 재시도
                last_exc = exc
                if attempt < _APPEND_RETRIES - 1:
                    time.sleep(_APPEND_RETRY_WAIT_SEC)
        if last_exc:
            print(f"[WARN] worklog.log append 실패(best-effort): {last_exc}", file=sys.stderr)
        return False
    except Exception as exc:
        # ★stderr 로 낸다(배590). 이 함수는 UserPromptSubmit 훅에서도 불리는데, 그 훅의
        #   stdout 은 JSON 계약이다 — 경고 한 줄이 앞에 섞이면 리마인더가 통째로 깨진다.
        print(f"[WARN] worklog.log 예외(best-effort, 호출부 무영향): {exc}", file=sys.stderr)
        return False


def _selfcheck() -> None:
    """단순 조회 필터 회귀 검사(배658) — 조회 발화는 걸러지고 진짜 지시는 그대로 통과하는지."""
    queries = ['쿵짝표 보여줘', '오늘 항로 보여줘', '현황 알려줘', '진행상황 알려주세요']
    for q in queries:
        assert _SIMPLE_QUERY_RE.match(q), f'조회 발화가 안 걸림: {q!r}'
    directives = [
        '쿵짝표 칸을 5개로 고정해줘',
        '쿵짝표 보여주고 칸 하나 고쳐줘',
        '이거 왜 안 되는지 확인하고 고쳐줘',
        '배658 착수해',
    ]
    for d in directives:
        assert not _SIMPLE_QUERY_RE.match(d), f'진짜 지시가 걸러짐: {d!r}'
    print(f'[OK] worklog 단순조회 필터 자가검사 통과 — 조회 {len(queries)}건 거름·지시 {len(directives)}건 통과')


def close_gm_refs_hook() -> None:
    """Stop 훅 — 세션이 응답을 끝내면 그 역할의 열린 GM 접수를 닫는다.

    왜 필요한가(2026-08-21 시토 실측): 닫는 일을 UserPromptSubmit 훅 하나가 다 하고 있었다.
    그래서 **그날 마지막 지시는 영영 안 닫힌다** — 다음 프롬프트가 와야 닫히는데, 다음 프롬프트는
    다음 날 부팅문이고 부팅문은 걸러져서 닫기 호출까지 건너뛴다. 실측: 08-20 마지막 발화
    "나 퇴근해도되?" 가 다음 날 아침 쿵짝표에 미완으로 떴다. 코드 주석은 "Stop 훅에도 같은
    호출을 뒀다"고 적혀 있었지만 **훅 등록이 없어 한 번도 발화한 적이 없었다.**
    """
    try:
        role = (os.environ.get("WELLPERION_ROLE") or "").strip().lower()
        if role:
            close_gm_refs(role, detail="세션 응답 종료 · 자동 종결(Stop)")
    except Exception:  # noqa: BLE001 — 훅은 절대 세션을 막지 않는다
        pass


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "--hook-prompt":
        record_gm_prompt_hook()
    elif len(sys.argv) >= 2 and sys.argv[1] == "--hook-stop":
        close_gm_refs_hook()
    elif len(sys.argv) >= 2 and sys.argv[1] == "--open-gm":
        _role = sys.argv[2] if len(sys.argv) >= 3 else (os.environ.get("WELLPERION_ROLE") or "")
        _open = open_gm_refs(_role)
        print(f"미완 GM 접수({_role or '역할 미지정'}) — {len(_open)}건")
        for _r, _t in _open:
            print(f"  {_r}  {_t}")
    elif len(sys.argv) >= 2 and sys.argv[1] == "--selfcheck":
        _selfcheck()
    elif len(sys.argv) >= 4:
        ok = log(sys.argv[1], sys.argv[2], sys.argv[3])
        print(f"[{'OK' if ok else 'FAIL'}] worklog.log() 호출 — {WORKLOG_PATH}")
    else:
        print("사용: python worklog.py <role> <area> <event> | python worklog.py --hook-prompt | python worklog.py --selfcheck")
