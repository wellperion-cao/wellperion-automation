"""
모델 라우팅 폴백 — 단일 모델 의존 중단 리스크 대비.
근거: AI 자기학습 제안 prop_20260623_185611_d79017 (시토, GM 승인 2026-06-23).
      "특정 모델이 외부 사유로 갑자기 차단될 수 있음"(Anthropic Newsroom) → 7 C-Level 운영·08:00 보고
      파이프라인이 한 모델 차단·장애에도 멈추지 않도록 대체 모델로 자동 강등 + 텔레그램 1줄 경보.

단일 출처(약속 L01):
  - 폴백 체인 = 이 파일 MODEL_FALLBACK_CHAIN (코드 복사 금지, 자동화코드는 여기서만 읽는다).
  - 모델 ID = claude-api 스킬 정본(2026-06-24): opus=claude-opus-4-8 / sonnet=claude-sonnet-4-6 / haiku=claude-haiku-4-5.
  - 텔레그램 = telegram_bot/.env 단일 출처(INC-004 GUARDED) — 리터럴 하드코딩 없음.

사용:
  from model_router import run_claude
  text, used = run_claude(prompt, label="learning-proposer")
  if text is None:  # 전 모델 실패 → 호출부가 규칙기반 등으로 강등
      ...
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time

# ── 폴백 체인 (단일 출처) ───────────────────────────────────────────────
# 순서 = 우선순위. 앞 모델이 차단/장애/빈응답/타임아웃이면 다음으로 강등.
# 업무 연속성 기준: 판단 본업(Opus) → 표준(Sonnet) → 경량(Haiku). 한 모델이 외부 차단돼도 운영 지속.
MODEL_FALLBACK_CHAIN = [
    "claude-opus-4-8",    # 1순위: 판단·결재 본업
    "claude-sonnet-4-6",  # 2순위: 표준 강등 (품질·비용 다름)
    "claude-haiku-4-5",   # 3순위: 최후 경량 (운영 지속 우선)
]

_PER_MODEL_TIMEOUT = 180  # 모델당 호출 타임아웃(초)

# ── 재시도·백오프 하드닝 (배237 승인건 #244) ────────────────────────────
# 근거: 2026-07-01 클로드 서버 일시장애로 3모델(opus/sonnet/haiku) 전멸 →
#       규칙기반 강등 발생. 짧은 서버 blip은 수 초~수십 초 뒤 재시도로 대개
#       풀리므로, 실패(타임아웃/exit≠0/빈응답) 시 곧장 다음 모델로 강등하지
#       않고 같은 모델을 백오프 후 재시도한 뒤에만 다음 모델로 넘어간다.
_MAX_RETRIES_PER_MODEL = 2       # 모델당 최대 재시도 횟수(최초 시도 제외)
_RETRY_BACKOFFS = [4, 10]        # 재시도 전 대기(초). len == _MAX_RETRIES_PER_MODEL
# 벽시계 상한 근거(06:30 예약 실행 — 무한정 늘어지면 안 됨):
#   모델당 최악 = (1+_MAX_RETRIES_PER_MODEL)*timeout + sum(_RETRY_BACKOFFS)
#              = 3*180s + 14s = 554s(~9.2분)
#   체인 3모델 전멸(총 장애) 최악 = 3*554s ≈ 1662s(~27.7분) — 이는 opus·
#   sonnet·haiku 전부가 재시도까지 모두 실패하는 극히 드문 완전 장애 시나리오
#   뿐이며, 이 경우 기존에도 규칙기반 강등으로 넘어간다(호출부가 흡수).
#   실제 목표 시나리오인 "일시적 blip"은 1회 재시도(타임아웃+4s) 내 대개 복구.


def _alert(text: str) -> None:
    """폴백 발동·전체 실패를 텔레그램 1줄 경보. best-effort(실패해도 라우팅 무영향).
    토큰·챗ID = telegram_bot/.env 직독(SSOT). 리터럴 없음."""
    try:
        from dotenv import load_dotenv  # type: ignore
        load_dotenv()
        token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
        if not token or not chat_id:
            return
        import httpx  # type: ignore
        httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
    except Exception:
        pass  # 경보 실패가 운영을 막지 않는다


def run_claude(
    prompt: str,
    *,
    models: list[str] | None = None,
    timeout: int = _PER_MODEL_TIMEOUT,
    label: str = "",
    extra_args: list[str] | None = None,
) -> tuple[str | None, str | None]:
    """claude CLI(claude -p --model X)를 폴백 체인 따라 호출.

    반환: (응답텍스트, 사용모델) — 성공.  (None, None) — 전 모델 실패(호출부가 강등 처리).
    폴백(1순위 외 모델로 응답) 시 텔레그램 1줄 경보. 전 모델 실패 시도 경보.
    """
    chain = models or MODEL_FALLBACK_CHAIN
    claude_bin = shutil.which("claude")  # Windows: claude.cmd 풀패스(PATHEXT)
    tag = f" ({label})" if label else ""
    if not claude_bin:
        _alert(f"🚨 모델 라우팅 실패{tag} — claude CLI 미설치(PATH 미해결). 규칙기반 강등.")
        return None, None

    last_err = ""
    for i, model in enumerate(chain):
        cmd = [claude_bin, "-p", "--model", model]
        if extra_args:
            cmd.extend(extra_args)

        model_ok_out: str | None = None
        for attempt in range(_MAX_RETRIES_PER_MODEL + 1):  # 0=최초 시도, 1..N=재시도
            if attempt > 0:
                backoff = _RETRY_BACKOFFS[attempt - 1]
                print(f"[model_router] {model} 재시도 {attempt}/{_MAX_RETRIES_PER_MODEL} — {backoff}s 대기 후")
                time.sleep(backoff)

            try:
                result = subprocess.run(
                    cmd,
                    input=prompt,  # 긴 한글 프롬프트는 stdin (명령줄 길이·인코딩 한계 회피)
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                last_err = f"타임아웃({timeout}s)"
                print(f"[model_router] {model} 시도{attempt+1} {last_err}")
                continue
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                print(f"[model_router] {model} 시도{attempt+1} 예외 {last_err}")
                continue

            if result.returncode != 0:
                last_err = (result.stderr or "").strip()[:200]
                print(f"[model_router] {model} 시도{attempt+1} exit {result.returncode}: {last_err}")
                continue

            out = (result.stdout or "").strip()
            if not out:
                last_err = "빈 응답"
                print(f"[model_router] {model} 시도{attempt+1} {last_err}")
                continue

            model_ok_out = out
            break  # 이 모델 성공 — 재시도 루프 탈출

        if model_ok_out is None:
            print(f"[model_router] {model} 재시도 {_MAX_RETRIES_PER_MODEL}회 소진 — 다음 모델 강등 (마지막: {last_err})")
            continue

        if i > 0:  # 1순위가 아닌 대체 모델로 응답 = 폴백 발동
            _alert(
                f"⚠️ 모델 폴백 발동{tag}\n"
                f"{chain[0]} 차단/장애(재시도 {_MAX_RETRIES_PER_MODEL}회 후) → {model} 로 강등 처리.\n"
                f"품질·토큰비용 다를 수 있음. 1순위 모델 복구 확인 필요."
            )
            print(f"[model_router] 폴백: {chain[0]} → {model}")
        return model_ok_out, model

    _alert(
        f"🚨 전 모델 폴백 실패{tag} — 체인 {len(chain)}개 전부 모델당 재시도 {_MAX_RETRIES_PER_MODEL}회 후에도 실패"
        f"(마지막: {last_err}). 규칙기반 강등."
    )
    print(f"[model_router] 전 모델 실패(모델당 재시도 {_MAX_RETRIES_PER_MODEL}회 소진) — 마지막 오류: {last_err}")
    return None, None


if __name__ == "__main__":
    # 자가 점검(드라이): 체인·claude 존재만 확인, 실제 호출 안 함.
    print("MODEL_FALLBACK_CHAIN =", MODEL_FALLBACK_CHAIN)
    print("claude CLI 경로 =", shutil.which("claude") or "(미설치)")
