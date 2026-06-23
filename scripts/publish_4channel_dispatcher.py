"""웰페리온 4채널 통합 발행 디스패처 v1.0

기본 dry-run — --run 플래그 없으면 외부 subprocess 호출 안 함.
발행(publish) 아닌 임시저장(draft) 전용 연결 진입점.

용도: 콘텐츠 폴더 1개를 지정하면 기존 채널별 업로드 스크립트를
      subprocess 로 한 번에 호출하는 통합 진입점.
      새 업로드 로직 없음 — 기존 스크립트 호출만.

실행 예:
  # dry-run (기본) — 어떤 명령이 넘어가는지 출력만
  python scripts/publish_4channel_dispatcher.py \\
      --content-dir "instagram/260520_발레_런칭" \\
      --include-kakao --include-danggn

  # 실제 임시저장 실행 (--run 필수)
  python scripts/publish_4channel_dispatcher.py \\
      --content-dir "instagram/260520_발레_런칭" \\
      --run
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import unicodedata
from pathlib import Path

# UTM campaign 슬러그 헬퍼 (cta_utm.slugify_campaign 직접 import)
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from cta_utm import slugify_campaign as _slugify_campaign
except Exception:
    def _slugify_campaign(s: str) -> str:  # type: ignore[misc]
        return ""

# Windows 콘솔 UTF-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:  # 발신 공용 로깅(best-effort) — 임포트 실패해도 발신 무영향
    from tg_outbound_log import log_outbound
except Exception:
    def log_outbound(*a, **k):
        pass

# ─────────────────────────────────────────────
# 경로 상수
# ─────────────────────────────────────────────
ROOT = Path(r"C:\Users\jjky0\welperion-automation")
SCRIPTS_DIR = ROOT / "scripts"

# 채널별 업로드 스크립트 경로 (수정 금지 — 기존 파일)
SCRIPT_BLOG   = SCRIPTS_DIR / "naver_blog_upload_playwright.py"
SCRIPT_CAFE   = SCRIPTS_DIR / "cafe_upload_playwright.py"
SCRIPT_KAKAO  = SCRIPTS_DIR / "kakao_channel_upload_playwright.py"
SCRIPT_DANGGN = SCRIPTS_DIR / "danggn_upload_playwright.py"

# 텔레그램 상수 (SSOT: telegram_bot/.env 단일출처)
TELEGRAM_TOKEN_ENV_KEY = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV_KEY = "TELEGRAM_CHAT_ID"


# ─────────────────────────────────────────────
# 유틸리티
# ─────────────────────────────────────────────

def _nfc(p: Path) -> Path:
    """경로 문자열 NFC 정규화 (한글 폴더명 glob 대응)."""
    return Path(unicodedata.normalize("NFC", str(p)))


def _list_images(folder: Path, glob_pat: str) -> list[Path]:
    """괄호+한글 폴더에서 os.listdir 기반 이미지 수집 (Path.glob 우회)."""
    folder = _nfc(folder)
    if not folder.exists():
        return []
    ext = glob_pat.lstrip("*").lower()  # e.g. "*.jpg" → ".jpg"
    return sorted(
        folder / f
        for f in os.listdir(str(folder))
        if f.lower().endswith(ext)
    )


def _read_first_line(path: Path) -> str:
    """파일 첫 줄(마크다운 제목 등)에서 제목 추출."""
    try:
        for line in _nfc(path).read_text(encoding="utf-8").splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                return line
    except Exception:
        pass
    return ""


def _derive_title(content_dir: Path) -> str:
    """콘텐츠 폴더명에서 제목 유도 (YYMMDD_이름 → 이름 부분)."""
    name = content_dir.name
    parts = name.split("_", 1)
    return parts[1] if len(parts) == 2 else name


def _env_val(key: str) -> str:
    """환경변수 → telegram_bot/.env 순서로 값 로드."""
    val = os.environ.get(key, "").strip()
    if val:
        return val
    env_file = ROOT / "telegram_bot" / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return ""


def _telegram_token() -> str:
    """환경변수 → telegram_bot/.env 순서로 토큰 조회."""
    return _env_val(TELEGRAM_TOKEN_ENV_KEY)


TELEGRAM_CHAT_ID: str = _env_val(TELEGRAM_CHAT_ID_ENV_KEY)  # telegram_bot/.env SSOT


def _send_telegram(text: str) -> None:
    """텔레그램 1줄 보고 (실패해도 디스패처 정상 종료)."""
    import urllib.parse
    import urllib.request

    tok = _telegram_token()
    if not tok:
        print("[텔레그램] 토큰 없음 — 보고 생략")
        return
    url = f"https://api.telegram.org/bot{tok}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TELEGRAM_CHAT_ID, "text": text}).encode()
    try:
        urllib.request.urlopen(url, data=data, timeout=10)
        log_outbound(text, chat_id=TELEGRAM_CHAT_ID, source="publish_4channel_dispatcher._send_telegram", ok=True, kind="sendMessage")
        print("[텔레그램] 보고 완료")
    except Exception as e:
        log_outbound(text, chat_id=TELEGRAM_CHAT_ID, source="publish_4channel_dispatcher._send_telegram", ok=False, kind="sendMessage")
        print(f"[텔레그램] 보고 실패(무시): {e}")


# ─────────────────────────────────────────────
# 채널별 argv 구성
# ─────────────────────────────────────────────

def _build_blog_argv(content_dir: Path, i_am_sure: bool, campaign: str = "") -> tuple[list[str], str | None]:
    """블로그 채널 argv 구성. (argv, skip_reason | None)"""
    out = _nfc(content_dir / "output(블로그)")
    body = _nfc(out / "_blog_body.txt")
    images = _list_images(out, "*.jpg")

    if not body.exists():
        return [], f"body 파일 없음: {body}"
    if not images:
        return [], f"이미지 없음: {out}/*.jpg"

    title = _read_first_line(body) or _derive_title(content_dir)
    argv = [
        sys.executable, str(SCRIPT_BLOG),
        "--mode", "draft",
        "--title", title,
        "--body-file", str(body),
        "--image-dir", str(out),
        "--image-glob", "*.jpg",
    ]
    if campaign:
        argv += ["--campaign", campaign]
    if i_am_sure:
        argv.append("--i-am-sure")
    return argv, None


def _build_cafe_argv(content_dir: Path, i_am_sure: bool, campaign: str = "") -> tuple[list[str], str | None]:
    """카페 채널 argv 구성."""
    out = _nfc(content_dir / "output(카페)")
    body = _nfc(out / "_cafe_body.txt")
    images = _list_images(out, "*.jpg")

    if not body.exists():
        return [], f"body 파일 없음: {body}"
    if not images:
        return [], f"이미지 없음: {out}/*.jpg"

    title = _read_first_line(body) or _derive_title(content_dir)
    argv = [
        sys.executable, str(SCRIPT_CAFE),
        "--mode", "draft",
        "--title", title,
        "--body-file", str(body),
        "--image-dir", str(out),
        "--image-glob", "*.jpg",
    ]
    if campaign:
        argv += ["--campaign", campaign]
    if i_am_sure:
        argv.append("--i-am-sure")
    return argv, None


def _build_kakao_argv(content_dir: Path, i_am_sure: bool, campaign: str = "") -> tuple[list[str], str | None]:
    """카카오 채널 argv 구성. content-dir 방식으로 넘김."""
    out = _nfc(content_dir / "output(카카오 채널)")
    body = _nfc(out / "kakao_copy.md")
    images = _list_images(out, "*.jpg")

    if not body.exists():
        return [], f"body 파일 없음: {body}"
    if not images:
        return [], f"이미지 없음: {out}/*.jpg"

    argv = [
        sys.executable, str(SCRIPT_KAKAO),
        "--mode", "draft",
        "--content-dir", str(content_dir),
        "--image-dir", str(out),
        "--image-glob", "*.jpg",
    ]
    if campaign:
        argv += ["--campaign", campaign]
    if i_am_sure:
        argv.append("--i-am-sure")
    return argv, None


def _build_danggn_argv(content_dir: Path, i_am_sure: bool, campaign: str = "") -> tuple[list[str], str | None]:
    """당근 채널 argv 구성. output(당근)/ 우선, 없으면 루트 폴백."""
    out = _nfc(content_dir / "output(당근)")
    body_out = _nfc(out / "danggn_copy.md")
    body_root = _nfc(content_dir / "danggn_copy.md")

    # body 폴백: output(당근)/ 우선
    if body_out.exists():
        body = body_out
        img_dir = out
    elif body_root.exists():
        body = body_root
        img_dir = out  # 이미지는 여전히 output(당근)/ 시도
    else:
        return [], f"body 파일 없음: {body_out} / {body_root}"

    images = _list_images(img_dir, "*.jpg")
    if not images:
        return [], f"이미지 없음: {img_dir}/*.jpg"

    argv = [
        sys.executable, str(SCRIPT_DANGGN),
        "--mode", "draft",
        "--content-dir", str(content_dir),
        "--image-dir", str(img_dir),
        "--image-glob", "*.jpg",
    ]
    if campaign:
        argv += ["--campaign", campaign]
    if i_am_sure:
        argv.append("--i-am-sure")
    return argv, None


# ─────────────────────────────────────────────
# 채널 디스패치 실행
# ─────────────────────────────────────────────

# 채널명 → (빌더 함수, 스크립트 파일)
CHANNEL_MAP = {
    "blog":   (_build_blog_argv,   SCRIPT_BLOG),
    "cafe":   (_build_cafe_argv,   SCRIPT_CAFE),
    "kakao":  (_build_kakao_argv,  SCRIPT_KAKAO),
    "danggn": (_build_danggn_argv, SCRIPT_DANGGN),
}


def _dispatch(
    channels: list[str],
    content_dir: Path,
    do_run: bool,
    i_am_sure: bool,
) -> list[dict]:
    """채널별 실행·dry-run 수행. 결과 리스트 반환."""
    # campaign 슬러그 1회 산출 (콘텐츠 폴더 경로 기반)
    campaign = _slugify_campaign(str(content_dir))

    results = []
    for ch in channels:
        builder, script_path = CHANNEL_MAP[ch]

        # 스크립트 존재 확인
        if not script_path.exists():
            results.append({"ch": ch, "status": "SKIP", "note": f"스크립트 없음: {script_path}"})
            continue

        argv, skip_reason = builder(content_dir, i_am_sure, campaign)
        if skip_reason:
            results.append({"ch": ch, "status": "SKIP", "note": skip_reason})
            continue

        if not do_run:
            # dry-run: 명령만 출력
            cmd_str = " ".join(f'"{a}"' if " " in a else a for a in argv)
            results.append({"ch": ch, "status": "DRY", "note": cmd_str})
        else:
            # 실제 실행
            print(f"\n[{ch}] 실행 중...")
            ret = subprocess.run(argv, cwd=str(ROOT))
            rc = ret.returncode
            results.append({
                "ch": ch,
                "status": "OK" if rc == 0 else "FAIL",
                "note": f"returncode={rc}",
            })
    return results


# ─────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "웰페리온 4채널 통합 발행 디스패처 v1.0\n"
            "기본 dry-run — --run 없으면 subprocess 미호출 (임시저장 전용)"
        )
    )
    parser.add_argument(
        "--content-dir", dest="content_dir", required=True,
        help="콘텐츠 폴더 경로 (예: instagram/260520_발레_런칭)",
    )
    parser.add_argument(
        "--channels", default="blog,cafe",
        help="실행 채널 쉼표 구분 (기본 blog,cafe). kakao·danggn은 별도 플래그 필요",
    )
    parser.add_argument(
        "--include-kakao", dest="include_kakao", action="store_true",
        help="카카오 채널 포함 (성숙도 보호 — 명시해야만 합류)",
    )
    parser.add_argument(
        "--include-danggn", dest="include_danggn", action="store_true",
        help="당근 채널 포함 (자동입력 미완 PENDING — 명시해야만 합류)",
    )
    parser.add_argument(
        "--run", dest="do_run", action="store_true",
        help="실제 subprocess 실행. 없으면 dry-run (명령어 출력만)",
    )
    parser.add_argument(
        "--i-am-sure", dest="i_am_sure", action="store_true",
        help="하위 업로드 스크립트의 발행 가드 해제 플래그 — 실 발행 시 그대로 전파",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    # 콘텐츠 폴더 해석 (절대/상대 모두 지원)
    content_dir = Path(args.content_dir)
    if not content_dir.is_absolute():
        content_dir = ROOT / content_dir
    content_dir = _nfc(content_dir)

    if not content_dir.exists():
        print(f"[오류] 콘텐츠 폴더가 없습니다: {content_dir}")
        return 1

    # 채널 목록 조합
    channels: list[str] = [c.strip() for c in args.channels.split(",") if c.strip()]
    if args.include_kakao and "kakao" not in channels:
        channels.append("kakao")
    if args.include_danggn and "danggn" not in channels:
        channels.append("danggn")

    # 지원 채널 검증
    unknown = [c for c in channels if c not in CHANNEL_MAP]
    if unknown:
        print(f"[오류] 알 수 없는 채널: {unknown}. 지원 채널: {list(CHANNEL_MAP)}")
        return 1

    mode_label = "실행" if args.do_run else "DRY-RUN"
    print(f"\n{'='*60}")
    print(f"  웰페리온 4채널 디스패처 [{mode_label}]")
    print(f"  콘텐츠 폴더: {content_dir}")
    print(f"  채널: {channels}")
    print(f"{'='*60}\n")

    results = _dispatch(channels, content_dir, args.do_run, args.i_am_sure)

    # 결과 표 출력
    print(f"\n{'─'*60}")
    print(f"{'채널':<10} {'상태':<8} 비고")
    print(f"{'─'*60}")
    ok_count = skip_count = fail_count = 0
    for r in results:
        print(f"{r['ch']:<10} {r['status']:<8} {r['note']}")
        if r["status"] in ("OK", "DRY"):
            ok_count += 1
        elif r["status"] == "SKIP":
            skip_count += 1
        else:
            fail_count += 1
    print(f"{'─'*60}")
    print(f"합계: OK/DRY={ok_count}, SKIP={skip_count}, FAIL={fail_count}\n")

    # 텔레그램 1줄 보고 (실행 모드에서만)
    if args.do_run:
        summary = (
            f"[4채널 디스패처] {content_dir.name} | "
            f"채널={','.join(channels)} | "
            f"OK={ok_count} SKIP={skip_count} FAIL={fail_count}"
        )
        try:
            _send_telegram(summary)
        except Exception as e:
            print(f"[텔레그램] 예외(무시): {e}")
    else:
        print("[dry-run] 텔레그램 보고 생략 (--run 없음)")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
