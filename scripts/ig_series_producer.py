"""AI 시리즈 다음 편 자동 제작 → M5 검수큐 등록 (제작만 · 발행 절대 자동 아님)

GM 정정 지시(2026-06-04, AI CTO 위임). 매일 07:30 예약작업으로 가동되어
로드맵상 '다음 예정 편'을 시모(헤드리스 claude)가 GM 1인칭 보이스로 초안 제작 → 빌드 →
register_publish 로 M5 검수큐(status='검수대기') 적재 → 로드맵 행 '제작완료(자동생성)' 자동 표시 →
send_review_card 로 GM 텔레그램에 [✅승인]/[❌반려] 버튼 카드 발송까지 자동. 그 뒤 GM 이 M5 에서
슬라이드 검토 → 텔레그램 카드 [✅승인] 탭 → 봇 pub: 콜백이 그 순간 즉시 발행(무폴링). 발행 게이트는
GM 텔레그램 탭(수동 승인) 불변 — 스케줄 발행 없음.

★ 안전 원칙 (절대 위반 금지):
  - 자동 발행 없음. 이 스크립트는 status='검수대기' 적재 + [승인] 버튼 카드 발송까지만 한다.
  - 발행 트리거는 오직 GM 텔레그램 [✅승인] 탭(봇 pub: 콜백). review_queue 폴링 감시기 부활 금지.
  - 로드맵 '기획예정' 소진 시 생성 금지 + 텔레그램 1줄 경고 후 종료(쓰레기/중복 생성 금지).
  - 생성 실패(로드맵 파싱·헤드리스 호출·빌드 등) 시 텔레그램 경고 + 중단. 불량 항목 M5 미등록.

설계: 결정적(deterministic) 작업 = 이 스크립트(로드맵 파싱·다음편 선정·폴더 스캐폴드·소진 가드·
      텔레그램). 창의적(copy) 작업 = 시모(헤드리스 claude)에게 build_slides.py 1개만 작성 위임.
      그 build_slides.py 가 기존 편 표준(6장·logo_style='symbol'·마지막 장 시그니처 슬로건 고정·
      DM CTA·litt.ly 금지)을 그대로 따르고, 끝에서 register_publish(M5 등록)를 호출한다.

실행:
  제작:                 python scripts\\ig_series_producer.py
  로직만(테스트):        python scripts\\ig_series_producer.py --dry-run   (헤드리스 호출·빌드 안 함)
  다음편 선정만 출력:     python scripts\\ig_series_producer.py --plan-only

종료코드: 0=성공(또는 소진으로 정상 종료) / 1=오류(텔레그램 경고 발송됨).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 콘솔 인코딩 하드닝 (cp949 콘솔에서 대시·이모지 print 시 죽지 않게)
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    _reconf = getattr(_stream, "reconfigure", None) if _stream is not None else None
    if _reconf is not None:
        try:
            _reconf(encoding="utf-8", errors="replace")
        except Exception:
            pass

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
ROADMAP = ROOT / "instagram" / "_AI시리즈_로드맵.md"
INSTAGRAM_DIR = ROOT / "instagram"
PY = ROOT / ".venv" / "Scripts" / "python.exe"
ENV_PATH = ROOT / "telegram_bot" / ".env"

TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID = "8254867551"  # @namuki_report_bot (CLAUDE.md §3)

PLANNED_STATUS = "기획예정"  # 로드맵 편별 표에서 '아직 제작 안 한 다음 예정 편' 상태값

# 마지막 장 시그니처 슬로건 고정 (2026-06-04 GM 지시 — 전 편 공통 SOP, 로드맵 ★섹션)
SIGNATURE_SLOGAN = "AI를 다루는 대표가\n살아남는다"


# ─────────────────────────────────────────────────────────────────────────────
# 텔레그램 (토큰 stdout 노출 금지 — 메모리 feedback_telegram_token_env_key)
# ─────────────────────────────────────────────────────────────────────────────
def _load_telegram_token() -> str:
    token = os.environ.get(TELEGRAM_TOKEN_ENV_KEY, "").strip()
    if token:
        return token
    try:
        if ENV_PATH.exists():
            for raw in ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                if key.strip() == TELEGRAM_TOKEN_ENV_KEY:
                    return val.strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


def telegram(message: str) -> None:
    """1줄 텔레그램 보고. 실패해도 죽지 않음(토큰 trace 미출력)."""
    token = _load_telegram_token()
    if not token:
        print("[WARN] 텔레그램 토큰 미설정 — 보고 생략")
        return
    try:
        import urllib.parse
        import urllib.request

        data = urllib.parse.urlencode(
            {"chat_id": TELEGRAM_CHAT_ID, "text": message, "disable_web_page_preview": "true"}
        ).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[INFO] 텔레그램 보고 {'성공' if resp.status == 200 else '실패'}")
    except Exception:
        print("[WARN] 텔레그램 보고 실패 (토큰 trace 노출 방지)")


# ─────────────────────────────────────────────────────────────────────────────
# 로드맵 파싱 + 다음 편 선정
# ─────────────────────────────────────────────────────────────────────────────
class RoadmapError(Exception):
    """로드맵 파싱·구조 이상 (상위에서 텔레그램 경고 + 중단)."""


def parse_roadmap_episodes(text: str) -> list[dict]:
    """편별 로드맵 표 행을 파싱해 dict 리스트 반환.

    표 헤더: | # | 일자 | 폴더(코드명) | 제목 | 핵심메시지(1줄) | 상태 |
    구분선(|---|...) 과 헤더 행은 제외. 숫자(또는 '8(피날레)' 같은 형태)로 시작하는 행만 채택.
    반환 항목: {"num": int, "num_raw": str, "date": str, "folder": str,
               "title": str, "message": str, "status": str}
    """
    episodes: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        # 구분선 제외
        if set(line.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6:
            continue
        num_raw = cells[0]
        # 헤더 행('#') 제외 / 첫 셀이 숫자로 시작하는 행만 채택
        m = re.match(r"^\s*(\d+)", num_raw)
        if not m:
            continue
        episodes.append(
            {
                "num": int(m.group(1)),
                "num_raw": num_raw,
                "date": cells[1],
                "folder": cells[2],
                "title": cells[3],
                "message": cells[4],
                "status": cells[5],
            }
        )
    if not episodes:
        raise RoadmapError("편별 로드맵 표에서 유효한 편 행을 1건도 못 찾음 (표 구조 변경 의심)")
    return episodes


def pick_next_episode(episodes: list[dict]) -> dict | None:
    """상태='기획예정' 중 번호가 가장 빠른 편 1건 반환. 없으면 None (소진)."""
    planned = [e for e in episodes if e["status"] == PLANNED_STATUS]
    if not planned:
        return None
    planned.sort(key=lambda e: e["num"])
    return planned[0]


def prev_published_episode(episodes: list[dict], next_num: int) -> dict | None:
    """다음 편 직전(번호 기준 바로 앞) 편 — 중복 점검 컨텍스트용. 없으면 None."""
    befores = [e for e in episodes if e["num"] < next_num]
    if not befores:
        return None
    befores.sort(key=lambda e: e["num"])
    return befores[-1]


# ─────────────────────────────────────────────────────────────────────────────
# 폴더 코드명 / slug 생성
# ─────────────────────────────────────────────────────────────────────────────
def make_folder_slug(ep: dict) -> str:
    """제작용 폴더명(코드명) 생성. 예: 260605_AI6_작은가게AI팀

    로드맵 폴더 셀이 '(예정)' 등 placeholder 이므로, 제작일(오늘) + AI{num} + 제목 압축으로 생성.
    한글/영문/숫자만 남기고 공백 제거(파일시스템 안전).
    """
    today = datetime.now().strftime("%y%m%d")
    title = ep["title"]
    # 제목에서 콜론 앞부분(한글 헤드) 우선 사용
    head = title.split(":")[0].split("—")[0].strip()
    # 파일시스템 안전: 한글·영숫자만
    safe = re.sub(r"[^0-9A-Za-z가-힣]", "", head)[:14] or f"AI{ep['num']}편"
    return f"{today}_AI{ep['num']}_{safe}"


def make_queue_id(ep: dict) -> str:
    """이 편의 review_queue id 를 결정적으로 재구성.

    ★ build_producer_prompt 의 QUEUE_ID 공식과 반드시 동일해야 한다(시모가 쓴 build_slides.py
    의 queue_id 와 일치해야 카드를 정확히 그 엔트리로 발송·발행 가능). 공식 변경 시 양쪽 동시 수정.
    예: #6 「작은 가게도 AI 팀을 가질 수 있다」 → CMO-2026-06-04-AI6-작은가게도AI팀을가
    """
    head = re.sub(r"[^0-9A-Za-z가-힣]", "", ep["title"].split(":")[0])[:10]
    return f"CMO-{datetime.now().strftime('%Y-%m-%d')}-AI{ep['num']}-{head}"


# ─────────────────────────────────────────────────────────────────────────────
# 시모(헤드리스 claude) 호출 — build_slides.py 작성 위임
# ─────────────────────────────────────────────────────────────────────────────
def _find_claude() -> str:
    """claude CLI 경로 탐색 (telegram_bot/bot.py _find_claude 동일 전략)."""
    import shutil as _shutil

    for name in ("claude.cmd", "claude.exe", "claude"):
        p = _shutil.which(name)
        if p:
            return p
    for cand in (
        Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd",
        Path.home() / "AppData" / "Roaming" / "npm" / "claude",
    ):
        if cand.exists():
            return str(cand)
    return "claude"


def build_producer_prompt(ep: dict, prev: dict | None, folder_slug: str) -> str:
    """시모에게 보낼 제작 지시 프롬프트. build_slides.py 1개 파일만 작성하도록 강제."""
    folder_path = INSTAGRAM_DIR / folder_slug
    ref_build = INSTAGRAM_DIR / "260604_AI5_깨진환상들" / "build_slides.py"
    prev_block = (
        f"- 직전 편(#{prev['num']}): 제목「{prev['title']}」 / 핵심메시지「{prev['message']}」\n"
        f"  → 이 직전 편과 메시지·표현이 겹치지 않게 차별화하라(중복 점검 의무)."
        if prev
        else "- 직전 편 없음(이 편이 첫 편)."
    )
    return f"""너는 웰페리온 AI CMO(시모)다. GM 개인계정 namuk.wellperion 의 'AI A~Z' 연재 다음 편을 제작한다.
GM 1인칭 진솔 보이스(생각 리더십)로, 초등학생도 이해할 일상어로 쓴다. 광고·멤버십 모집 톤 금지.

## 이번 편
- 번호: #{ep['num']}
- 제목(로드맵 초안): {ep['title']}
- 핵심메시지(1줄): {ep['message']}
{prev_block}

## 산출물 (단 하나의 파일만 작성)
파일 경로: {folder_path / "build_slides.py"}
참고 표준(똑같은 구조·함수·register_publish 호출을 그대로 따른다): {ref_build}

## 절대 준수 (위반 시 불량 — M5 등록 안 됨)
1. 정확히 6장. SLIDES 리스트에 본문 5장(1장 표지 + 4장 본문) + main()에서 마지막 6장(시그니처)을 별도 생성.
2. 모든 슬라이드 logo_style="symbol" (개인계정 W 심볼만).
3. 마지막 6장 kor_title 은 반드시 "{SIGNATURE_SLOGAN}" 로 고정(다른 슬로건 생성 금지).
4. CTA = "함께 성장합시다" + "운동시설 대표님 DM 주세요" 톤. litt.ly 링크·URL 절대 삽입 금지(개인계정).
5. CAPTION 마무리도 시그니처 슬로건과 모순 없게. 해시태그 포함.
6. compose_text_slide(main 프리셋) 외 디자인 코드 재발명 금지. build_montage 함수도 참고 파일 그대로 복사.
7. QUEUE_ID="CMO-{datetime.now().strftime('%Y-%m-%d')}-AI{ep['num']}-{re.sub(r'[^0-9A-Za-z가-힣]', '', ep['title'].split(':')[0])[:10]}",
   slug="{folder_slug}", title="AI #{ep['num']}편 — (이번 편 한글 요약)(개인계정)",
   channel="인스타그램 (namuk.wellperion)", account="namuk.wellperion".
8. FOLDER = ROOT / "instagram" / "{folder_slug}" 로 설정.

## 작업 방법
- Write 도구로 위 build_slides.py 파일 하나만 생성하라. 다른 파일은 만들지 마라. 발행/커밋/push 하지 마라.
- 코드만 작성한다. build_slides.py 실행은 이 호출 밖(상위 스케줄러)에서 한다.
- 완료하면 "BUILD_SLIDES_WRITTEN: {folder_path / 'build_slides.py'}" 한 줄을 마지막에 출력하라.
"""


def invoke_simo_producer(ep: dict, prev: dict | None, folder_slug: str, timeout: int = 600) -> str:
    """헤드리스 claude(시모) 호출 → build_slides.py 작성. 반환: 응답 텍스트.

    실패(비정상 종료·예외) 시 RuntimeError 로 상위에 전파 → 텔레그램 경고 + 중단.
    """
    claude_bin = _find_claude()
    prompt = build_producer_prompt(ep, prev, folder_slug)
    args = [
        claude_bin,
        "-p",
        "--output-format",
        "json",
        "--permission-mode",
        "bypassPermissions",
    ]
    try:
        # Windows .cmd 는 exec 불가 → shell 모드 (bot.py run_claude 와 동일 전략)
        if claude_bin.lower().endswith(".cmd") or os.name == "nt":
            shell_cmd = subprocess.list2cmdline(args)
            proc = subprocess.run(
                shell_cmd,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT),
                timeout=timeout,
                shell=True,
            )
        else:
            proc = subprocess.run(
                args,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=str(ROOT),
                timeout=timeout,
            )
    except FileNotFoundError:
        raise RuntimeError(f"claude CLI 를 찾을 수 없음 ({claude_bin})")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"시모 헤드리스 호출 타임아웃({timeout}s)")
    except Exception as exc:
        raise RuntimeError(f"시모 호출 subprocess 예외: {type(exc).__name__}: {exc}")

    if proc.returncode != 0:
        err = (proc.stderr or "")[:600]
        raise RuntimeError(f"시모 비정상 종료 exit={proc.returncode} stderr={err}")

    raw = proc.stdout or ""
    # output-format=json → result 추출 (실패해도 원문 반환)
    try:
        import json

        data = json.loads(raw)
        return data.get("result") or data.get("response") or raw
    except Exception:
        return raw


# ─────────────────────────────────────────────────────────────────────────────
# 로드맵 자동 갱신 (생산·등록 성공 시 해당 편 행 상태 → 제작완료, 다음날 다음 편 선정)
# ─────────────────────────────────────────────────────────────────────────────
PRODUCED_STATUS = "제작완료·GM검수대기(자동생성)"  # 생산 성공 후 로드맵 행 상태값


def mark_episode_produced(ep: dict, folder_slug: str) -> bool:
    """로드맵 편별 표에서 ep['num'] 행의 일자·폴더·상태를 '제작완료(자동생성)'로 갱신.

    현재 상태가 PLANNED_STATUS('기획예정') 인 행만 손댄다(이미 발행완료 등은 강등 금지).
    그래야 다음날 가동 시 pick_next_episode 가 그 다음 '기획예정' 편을 고른다(중복 재생성 차단).
    반환: 갱신 성공 여부. 실패해도 빌드/등록은 이미 끝났으므로 죽지 않음(상위에서 경고만).
    """
    try:
        text = ROADMAP.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"[WARN] 로드맵 읽기 실패 — 자동표시 건너뜀: {exc}")
        return False

    today_iso = datetime.now().strftime("%Y-%m-%d")
    out_lines: list[str] = []
    updated = False
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        stripped = line.strip()
        # 표 데이터 행만 검사 (| 로 시작, 구분선·헤더 제외)
        if updated or not stripped.startswith("|"):
            out_lines.append(line)
            continue
        if set(stripped.replace("|", "").replace("-", "").replace(":", "").strip()) == set():
            out_lines.append(line)
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 6:
            out_lines.append(line)
            continue
        m = re.match(r"^\s*(\d+)", cells[0])
        if not m or int(m.group(1)) != ep["num"]:
            out_lines.append(line)
            continue
        # 매칭 — 단 '기획예정' 행만 갱신(회귀 가드)
        if cells[5] != PLANNED_STATUS:
            print(f"[INFO] 로드맵 #{ep['num']} 행 상태='{cells[5]}' (기획예정 아님) — 자동표시 생략(강등 금지).")
            out_lines.append(line)
            updated = True  # 더 갱신 안 함(첫 매칭 행만)
            continue
        cells[1] = today_iso
        cells[2] = folder_slug
        cells[5] = PRODUCED_STATUS
        out_lines.append("| " + " | ".join(cells) + " |")
        updated = True
        print(f"[INFO] 로드맵 #{ep['num']} 행 자동 갱신 → 일자={today_iso} 폴더={folder_slug} 상태={PRODUCED_STATUS}")

    if not updated:
        print(f"[WARN] 로드맵에서 #{ep['num']} 행을 찾지 못함 — 자동표시 실패(다음날 중복 재생성 위험).")
        return False
    try:
        # 끝 개행 보존
        new_text = "\n".join(out_lines)
        if text.endswith("\n") and not new_text.endswith("\n"):
            new_text += "\n"
        ROADMAP.write_text(new_text, encoding="utf-8")
        return True
    except Exception as exc:
        print(f"[WARN] 로드맵 쓰기 실패 — 자동표시 미반영: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 검수 카드 발송 (제작완료 시 [✅승인]/[❌반려] 버튼 카드 → 텔레그램, 무폴링 발행 트리거)
# ─────────────────────────────────────────────────────────────────────────────
def send_review_card(queue_id: str) -> bool:
    """scripts/send_review_card.py --id <queue_id> 호출 → GM 텔레그램에 [✅승인] 버튼 카드 발송.

    register_publish 의 montage 사진(버튼 없음) 와 별개로, 이 버튼 카드 탭이 유일한 무폴링 발행
    트리거다(bot.py pub: 콜백). 실패해도 제작·등록은 이미 끝났으므로 죽지 않음(경고만).
    """
    script = ROOT / "scripts" / "send_review_card.py"
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        proc = subprocess.run(
            [str(PY), str(script), "--id", queue_id],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=30,
        )
        print((proc.stdout or "") + (proc.stderr or ""))
        ok = proc.returncode == 0
        print(f"[{'OK' if ok else 'WARN'}] 검수 카드 발송 {'성공' if ok else '실패'} — id={queue_id}")
        return ok
    except Exception as exc:
        print(f"[WARN] 검수 카드 발송 예외 (제작·등록은 완료): {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# 빌드 실행 (생성된 build_slides.py → register_publish → M5 검수대기)
# ─────────────────────────────────────────────────────────────────────────────
def run_build_slides(build_path: Path, timeout: int = 300) -> None:
    """생성된 build_slides.py 실행. register_publish 가 M5 검수대기 등록까지 수행.

    실패(exit≠0) 시 RuntimeError 전파 → 텔레그램 경고 + 중단(불량 미등록).
    """
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    proc = subprocess.run(
        [str(PY), str(build_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out)
    if proc.returncode != 0:
        raise RuntimeError(f"build_slides.py 실행 실패 exit={proc.returncode}")


# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────
def run(dry_run: bool, plan_only: bool) -> int:
    print(
        f"[INFO] === AI 시리즈 제작기 시작 === "
        f"{datetime.now().isoformat(timespec='seconds')} (dry_run={dry_run}, plan_only={plan_only})"
    )

    # 1) 로드맵 파싱 (실패 시 경고 + 중단)
    try:
        if not ROADMAP.exists():
            raise RoadmapError(f"로드맵 파일 부재: {ROADMAP}")
        episodes = parse_roadmap_episodes(ROADMAP.read_text(encoding="utf-8"))
    except RoadmapError as exc:
        msg = f"⚠️ AI 시리즈 제작 중단 — 로드맵 파싱 실패: {exc}"
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    # 2) 다음 편 선정 (소진 시 생성 금지 + 경고 후 정상 종료)
    nxt = pick_next_episode(episodes)
    if nxt is None:
        planned_nums = [e["num_raw"] for e in episodes if e["status"] == PLANNED_STATUS]
        print(f"[INFO] 기획예정 편 소진 — 생성 금지(쓰레기/중복 방지). (남은 기획예정: {planned_nums})")
        telegram("📭 AI 시리즈 #6~#8 소진 — 신규 기획 필요 (다음 편 자동 제작 중단)")
        return 0

    prev = prev_published_episode(episodes, nxt["num"])
    folder_slug = make_folder_slug(nxt)
    print(
        f"[INFO] 다음 편 선정 → #{nxt['num']} 「{nxt['title']}」 / 핵심메시지: {nxt['message']}\n"
        f"       제작 폴더(코드명): {folder_slug}"
        + (f" / 직전 편 #{prev['num']} 「{prev['title']}」(중복 점검 대상)" if prev else "")
    )

    if plan_only:
        print("[PLAN-ONLY] 선정만 출력하고 종료(제작 안 함).")
        return 0

    if dry_run:
        print(
            "[DRY-RUN] 헤드리스 시모 호출·빌드·M5 등록 안 함. 아래 프롬프트만 검증:\n"
            "----- 프롬프트 미리보기 (앞 800자) -----"
        )
        print(build_producer_prompt(nxt, prev, folder_slug)[:800])
        print("----- (생략) -----")
        return 0

    # 3) 폴더 스캐폴드
    folder_path = INSTAGRAM_DIR / folder_slug
    folder_path.mkdir(parents=True, exist_ok=True)
    build_path = folder_path / "build_slides.py"

    # 4) 시모 헤드리스 호출 → build_slides.py 작성 (실패 시 경고 + 중단)
    try:
        result_text = invoke_simo_producer(nxt, prev, folder_slug)
        print(f"[INFO] 시모 응답 수신 (len={len(result_text)})")
    except RuntimeError as exc:
        msg = f"⚠️ AI 시리즈 #{nxt['num']} 제작 중단 — 시모 헤드리스 호출 실패: {exc}"
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    # 4-1) build_slides.py 실제 생성 검증 (시모가 안 썼으면 불량 — M5 미등록)
    if not build_path.exists():
        msg = (
            f"⚠️ AI 시리즈 #{nxt['num']} 제작 중단 — 시모가 build_slides.py 미생성 "
            f"({build_path}). M5 미등록."
        )
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    # 5) 빌드 실행 → register_publish 가 M5 검수대기 등록까지 (실패 시 경고 + 중단)
    try:
        run_build_slides(build_path)
    except Exception as exc:
        msg = f"⚠️ AI 시리즈 #{nxt['num']} 빌드 실패 — M5 미등록: {exc}"
        print(f"[ERROR] {msg}")
        telegram(msg)
        return 1

    # 6) 로드맵 자동 갱신 — 이 편 행을 '제작완료(자동생성)'로 표시(다음날 다음 편 선정·중복 차단).
    #    실패해도 제작·등록은 끝났으므로 경고만.
    if not mark_episode_produced(nxt, folder_slug):
        telegram(
            f"⚠️ AI 시리즈 #{nxt['num']} 로드맵 자동표시 실패 — 다음날 같은 편 재생성 위험. "
            f"로드맵 #{nxt['num']} 행 상태 수동 확인 요망."
        )

    # 7) 검수 카드 발송 — [✅승인]/[❌반려] 버튼 카드(무폴링 발행 트리거). register_publish montage 와 별개.
    queue_id = make_queue_id(nxt)
    if not send_review_card(queue_id):
        telegram(
            f"⚠️ AI 시리즈 #{nxt['num']} 검수 카드(버튼) 발송 실패 — id={queue_id}. "
            f"M5 등록은 됨. 수동 카드 발송: send_review_card.py --id {queue_id}"
        )

    # 8) 성공 — register_publish montage + 위 [승인] 버튼 카드까지 발송됨.
    #    발행은 GM 텔레그램 [✅승인] 탭 시 봇 pub: 콜백이 즉시 수행(무폴링). 이 스크립트는 발행 안 함.
    print(
        f"[OK] AI 시리즈 #{nxt['num']} 「{nxt['title']}」 제작 완료 → M5 검수대기 등록 + 검수 카드 발송. "
        f"발행은 GM 텔레그램 [✅승인] 탭 → 봇 pub: 즉시 발행(무폴링). (이 스크립트는 발행 안 함)"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="AI 시리즈 다음 편 자동 제작 → M5 검수큐 등록 (발행 절대 자동 아님)"
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="헤드리스 호출·빌드·등록 없이 선정·프롬프트만 검증"
    )
    ap.add_argument(
        "--plan-only", action="store_true", help="다음 편 선정 결과만 출력하고 즉시 종료"
    )
    args = ap.parse_args()
    return run(dry_run=args.dry_run, plan_only=args.plan_only)


if __name__ == "__main__":
    sys.exit(main())
