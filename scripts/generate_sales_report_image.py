#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/generate_sales_report_image.py — 매출보고 이미지 자체 생성기(텔레그램 사진 불필요)

배경(2026-07-07 CTO): 카톡 완전자동 9시 무인 발송 파이프라인의 1단계.
    텔레그램 9시 매출보고(GAS `매출보고_자동발송.js` sendDailyReport)와 **동일한 범위
    (H2:S21, '보고' 탭, gid=2009735088)** 를 cao 구글세션이 저장된 Playwright 퍼시스턴트
    프로필(profiles/danggn — 당근 업로더 scripts/danggn_upload_playwright.py 와 동일 세션
    재사용)로 직접 PDF export 후 PNG로 렌더한다. 텔레그램 사진을 기다리거나 다운로드할
    필요가 없어져 9시 무인 오케스트레이터(scripts/kakao_auto_daily_report.py)가 곧바로
    이 스크립트를 호출해 최신 이미지를 스스로 만들어낼 수 있다.

세션 실효 처리(절대 원칙): export 응답이 application/pdf가 아니면(구글 로그인 페이지로
리다이렉트 등 = 세션만료 신호) **무조건 실패 처리**한다 — 낡은(stale) 이미지로 그냥
진행하는 것은 절대 금지. 실패 시 OWNER 텔레그램(.env 직독, 하드코딩 금지)로 경보 발송 후
exit 1.

사용:
    python scripts/generate_sales_report_image.py                     # 오늘 날짜 기준 archive 저장
    python scripts/generate_sales_report_image.py --date 20260707     # 특정 날짜로 archive 저장
    python scripts/generate_sales_report_image.py --out C:\\...\\x.png  # archive 저장 + 이 경로에도 추가 저장

출력: 성공 시 stdout에 `IMAGE: <절대경로>` + exit 0. 실패 시 `FAILED: <이유>` + exit 1.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Windows 콘솔(cp949) 한글 깨짐 방지
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
PERSISTENT_PROFILE_DIR = ROOT / "profiles" / "danggn"  # cao 구글세션(당근 업로더와 프로필 공유 재사용)
ROOMS_CONFIG = Path(__file__).resolve().parent / "kakao_rooms.json"  # archive_dir SSOT는 카톡 전송기와 공유
ENV_PATH = ROOT / "telegram_bot" / ".env"

# ══════════════════════════════════════════════════════════════════════════
# 매출보고 시트 좌표 — GAS 매출보고_자동발송.js(9시 텔레그램 발송)와 동일 범위(H2:S21).
# 시트id·gid·range·export 파라미터는 여기 상수로만 관리(하드코딩 산재 금지).
# ══════════════════════════════════════════════════════════════════════════
SHEET_ID = "1ycSEBbXjcU_suNu9B5HsEXQW0XosaW8fGtO0XfGprqc"
SHEET_GID = "2009735088"
SHEET_RANGE = "H2:S21"
SHEET_EDIT_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
EXPORT_URL = (
    f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=pdf"
    f"&gid={SHEET_GID}&range={SHEET_RANGE}&size=A3&portrait=false&scale=4"
    f"&top_margin=0.05&bottom_margin=0.05&left_margin=0.05&right_margin=0.05"
    f"&gridlines=false&printtitle=false&sheetnames=false&fzr=false"
)

ARCHIVE_FILENAME_FMT = "웰페리온_일일보고_%Y%m%d.png"
DEFAULT_ARCHIVE_DIR = ROOT / "1. AI자료_아카이브" / "10_매출보고"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def get_archive_dir() -> Path:
    """kakao_rooms.json의 archive_dir 재사용(카톡 전송기·9시 오케스트레이터와 동일 저장 위치 SSOT)."""
    try:
        cfg = json.loads(ROOMS_CONFIG.read_text(encoding="utf-8"))
        raw = cfg.get("archive_dir")
        if raw:
            return Path(raw).expanduser()
    except Exception as exc:
        log(f"[경고] kakao_rooms.json archive_dir 읽기 실패(기본값 사용): {exc}")
    return DEFAULT_ARCHIVE_DIR


def _load_env(path: Path) -> dict:
    """key=value .env 파싱(주석·빈줄 무시) — scripts/telegram_health_check.py와 동일 방식(직독, 하드코딩 금지)."""
    env: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    except Exception as exc:
        log(f"[경고] .env 읽기 실패: {exc}")
    return env


def send_owner_alert(message: str) -> None:
    """OWNER 텔레그램 DM으로 실패 경보(best-effort — 경보 발송 자체 실패는 무시하고 계속 진행)."""
    try:
        import requests
        env = _load_env(ENV_PATH)
        token = env.get("TELEGRAM_BOT_TOKEN", "")
        owner_id = env.get("OWNER_ID") or env.get("TELEGRAM_CHAT_ID", "")
        if not token or not owner_id:
            log("[경고] TELEGRAM_BOT_TOKEN/OWNER_ID(.env) 없음 — 경보 발송 생략")
            return
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": int(owner_id), "text": message},
            timeout=15,
        )
        if resp.status_code != 200 or not resp.json().get("ok", False):
            log(f"[경고] 경보 발송 실패: status={resp.status_code} body={resp.text[:200]}")
        else:
            log("OWNER 텔레그램 경보 발송 완료")
    except Exception as exc:
        log(f"[경고] 경보 발송 예외(무시): {exc}")


def _launch_context(p):
    """profiles/danggn 퍼시스턴트 프로필로 브라우저 컨텍스트 실행.
    channel="chrome" 우선 시도(GM 설치 크롬의 실제 로그인 세션 활용) → 실패 시 기본
    chromium으로 폴백(danggn_upload_playwright.py의 launch_persistent_context 옵션과
    동일 원칙 — headless=False, no_viewport, --start-maximized)."""
    launch_kwargs = dict(
        user_data_dir=str(PERSISTENT_PROFILE_DIR),
        headless=False,
        args=["--start-maximized"],
        no_viewport=True,
    )
    try:
        context = p.chromium.launch_persistent_context(channel="chrome", **launch_kwargs)
        log("Playwright 실행: channel=chrome")
        return context
    except Exception as exc:
        log(f"channel=chrome 실행 실패({exc}) — 기본 chromium으로 폴백")
        return p.chromium.launch_persistent_context(**launch_kwargs)


def export_pdf(out_pdf: Path) -> "tuple[bool, str]":
    """Google Sheets export를 PDF로 받아 저장. 반환: (성공여부, 실패사유)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        context = None
        try:
            context = _launch_context(p)

            # 1차 시그널: 시트 편집 페이지 안착 확인(로그인 리다이렉트=세션만료를 export 요청 전에 조기 탐지)
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(SHEET_EDIT_URL, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(2500)
            cur_url = page.url
            log(f"시트 편집 페이지 현재 URL: {cur_url}")
            if "accounts.google.com" in cur_url or "signin" in cur_url.lower():
                return False, f"구글 세션만료(cao 재로그인 필요) — 로그인 페이지로 리다이렉트됨({cur_url})"

            # 2차 시그널(최종 판정): export 응답 content-type이 pdf가 아니면 실패
            resp = context.request.get(EXPORT_URL, timeout=60_000)
            ct = resp.headers.get("content-type", "")
            status = resp.status
            log(f"export 응답 status={status} content-type={ct}")
            if status != 200 or "pdf" not in ct.lower():
                return False, f"구글 세션만료(cao 재로그인 필요) — export 응답이 PDF 아님(status={status}, content-type={ct})"

            body = resp.body()
            out_pdf.parent.mkdir(parents=True, exist_ok=True)
            out_pdf.write_bytes(body)
            log(f"PDF 저장: {out_pdf} ({len(body)} bytes)")
            return True, ""
        except Exception as exc:
            return False, f"Playwright 실행/요청 예외 — {exc}"
        finally:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass


def pdf_to_png(pdf_path: Path, png_path: Path) -> None:
    """PDF 1페이지를 dpi=300으로 PNG 렌더(PyMuPDF/fitz)."""
    import fitz  # PyMuPDF
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[0]
        pix = page.get_pixmap(dpi=300)
        png_path.parent.mkdir(parents=True, exist_ok=True)
        pix.save(str(png_path))
    finally:
        doc.close()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="매출보고 이미지 자체 생성(구글시트→PDF→PNG, 텔레그램 사진 불필요)")
    ap.add_argument("--out", default=None, help="지정 시 archive 저장과 별개로 이 경로에도 추가 저장")
    ap.add_argument("--date", default=None, help="보고 날짜 YYYYMMDD(기본 오늘) — archive 파일명에 사용")
    args = ap.parse_args()

    if sys.platform != "win32":
        print("FAILED: 이 스크립트는 Windows(Playwright+cao 세션) 전용입니다.")
        return 1

    target_date = datetime.now()
    if args.date:
        try:
            target_date = datetime.strptime(args.date, "%Y%m%d")
        except ValueError:
            print(f"FAILED: --date 형식 오류({args.date}, YYYYMMDD 필요)")
            return 1

    archive_dir = get_archive_dir()
    month_dir = archive_dir / target_date.strftime("%Y-%m")
    png_path = month_dir / target_date.strftime(ARCHIVE_FILENAME_FMT)
    pdf_tmp = month_dir / (target_date.strftime("웰페리온_일일보고_%Y%m%d") + "_tmp.pdf")

    ok, reason = export_pdf(pdf_tmp)
    if not ok:
        msg = f"⚠️ 매출보고 자동생성 실패 — {reason}"
        log(msg)
        send_owner_alert(msg)
        print(f"FAILED: {reason}")
        return 1

    try:
        pdf_to_png(pdf_tmp, png_path)
    except Exception as exc:
        msg = f"⚠️ 매출보고 자동생성 실패 — PDF→PNG 변환 오류: {exc}"
        log(msg)
        send_owner_alert(msg)
        print(f"FAILED: PDF→PNG 변환 오류 — {exc}")
        return 1
    finally:
        try:
            pdf_tmp.unlink(missing_ok=True)
        except Exception:
            pass

    if args.out:
        try:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(png_path.read_bytes())
            log(f"추가 저장: {out_path}")
        except Exception as exc:
            log(f"[경고] --out 추가 저장 실패(무시, archive 저장 자체는 성공): {exc}")

    print(f"IMAGE: {png_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
