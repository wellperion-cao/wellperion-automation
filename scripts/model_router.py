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

── 재시도 정책 v2 (GM 지시, 2026-07-02) ──────────────────────────────────
근거: 2026-07-01 실패건 원인 = 클로드 서버 일시 장애. opus·sonnet·haiku는
      같은 Anthropic 인프라를 쓰므로 하나가 죽으면 대개 다 같이 죽는다.
      "일반/서버성 오류(타임아웃·exit≠0·빈응답·5xx·레이트리밋)"에 낮은 모델로
      강등하는 건 ① 그 모델도 같이 죽어있을 확률이 높고 ② 살아있어도 판단·
      추천 품질만 깎이므로 틀렸다는 GM 지적을 반영.
  1. 일반/서버성 오류 → 같은 모델(현재 체인 위치, 보통 chain[0]=opus)을
     백오프 후 재시도. 낮은 모델로 넘어가지 않는다.
  2. 낮은 모델로의 강등은 "그 모델 자체가 막힌" 신호(_is_model_blocked)일
     때만: model not found / not available / does not exist / unknown model /
     모델 관련 4xx 류 — 이때만 즉시 다음 모델로 넘어간다(재시도 낭비 안 함).
  3. 일반 오류로 현재 모델의 재시도가 모두 소진되면 → 그대로 (None, None)
     반환(다음 모델로 자동으로 내려가지 않음). 호출부가 규칙기반 등으로 흡수.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time

# ── 폴백 체인 (단일 출처) ───────────────────────────────────────────────
# 순서 = 우선순위. 1순위(opus)가 "모델 자체 차단" 신호일 때만 다음으로 강등.
# 업무 연속성 기준: 판단 본업(Opus) → 표준(Sonnet) → 경량(Haiku). 한 모델이 외부 차단돼도 운영 지속.
MODEL_FALLBACK_CHAIN = [
    "claude-opus-4-8",    # 1순위: 판단·결재 본업 — 일반 오류는 이 모델을 재시도
    "claude-sonnet-4-6",  # 2순위: opus "모델차단" 감지 시에만 강등
    "claude-haiku-4-5",   # 3순위: 최후 경량 (sonnet도 "모델차단"일 때만)
]

_PER_MODEL_TIMEOUT = 140  # 모델당 호출 타임아웃(초) — 아래 벽시계 상한 근거 참조

# ── 재시도·백오프 하드닝 (배237 승인건 #244 → GM 재설계 2026-07-02) ─────
# 근거: 2026-07-01 클로드 서버 일시장애로 3모델(opus/sonnet/haiku) 전멸 →
#       규칙기반 강등 발생. 짧은 서버 blip은 수 초~수십 초 뒤 재시도로 대개
#       풀리므로, 실패(타임아웃/exit≠0/빈응답) 시 곧장 다음 모델로 강등하지
#       않고 같은 모델(우선 opus)을 백오프 후 재시도한다.
_MAX_RETRIES_PER_MODEL = 2       # 모델당 최대 재시도 횟수(최초 시도 제외) = 최초+2회
_RETRY_BACKOFFS = [10, 20]       # 재시도 전 대기(초). len == _MAX_RETRIES_PER_MODEL
# 벽시계 상한 근거(northstar_recommender·gm_aide_scan = 예약작업 10분(600s) 강제종료):
#   opus(우선순위) 재시도 최악 = (1+_MAX_RETRIES_PER_MODEL)*timeout + sum(_RETRY_BACKOFFS)
#                              = 3*140s + 30s = 450s(=7.5분) < 480s(8분 목표) < 600s(10분 하드컷).
#   이게 "일반 오류→규칙폴백" 주경로의 실제 상한이다(일반 오류는 낮은 모델로
#   내려가지 않고 여기서 (None, None) 반환 — 아래 정책 참조).
#   "모델차단" 강등 경로는 별도(드문 경로, GM 지시): 차단 응답은 보통 즉시
#   반환되므로(타임아웃 아님) 체인을 타고 내려가도 추가 지연이 크지 않다.
#   opus 자체가 일반오류+차단이 섞여 나오는 극단적 혼합 케이스까지 8분 상한을
#   보장하진 않으나, 이는 극히 드문 이중 장애로 별도 관리 대상이다.


# ── 모델차단 감지 (best-effort 문자열 매칭) ─────────────────────────────
# 목적: 재시도 낭비 없이 "이 모델 자체가 막혔다"를 판별해 다음 모델로 넘어갈지
# 결정. 타임아웃·5xx·레이트리밋·빈응답 등 "일반/서버성" 오류는 여기 해당 안 됨
# (그런 오류는 낮은 모델도 같이 죽어있을 확률이 높아 강등하지 않는다 — GM 지시).
_MODEL_BLOCKED_PATTERNS = [
    "model not found",
    "not_found_error",
    "model_not_found",
    "not available",
    "does not exist",
    "unknown model",
    "invalid model",
    "unsupported model",
    "no such model",
    "may not exist",             # 실측: claude CLI 실제 문구(2026-07-02 검증)
    "may not have access",       # "...It may not exist or you may not have access to it."
    "issue with the selected model",
    "pick a different model",
]


def _is_model_blocked(err: str) -> bool:
    """stderr/오류 텍스트가 '모델 자체 차단·미존재' 신호인지 best-effort 판별.
    참(True) = 다음 모델로 강등. 거짓(False) = 일반 오류(같은 모델 재시도)."""
    if not err:
        return False
    low = err.lower()
    if any(p in low for p in _MODEL_BLOCKED_PATTERNS):
        return True
    # 모델 관련 4xx(400/404 등) — "model" 언급과 4xx 상태코드가 함께 나오면 차단으로 간주
    if "model" in low and re.search(r"\b4\d{2}\b", low):
        return True
    return False


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
    """claude CLI(claude -p --model X)를 재시도 정책 v2에 따라 호출.

    정책:
      - 일반/서버성 오류(타임아웃·exit≠0·빈응답 등) → 같은 모델을 백오프 후 재시도.
        재시도(_MAX_RETRIES_PER_MODEL회) 다 소진되면 다음 모델로 내려가지 않고
        바로 (None, None) 반환(호출부가 규칙기반 등으로 강등).
      - "모델 자체가 막힌" 신호(_is_model_blocked) → 재시도 없이 즉시 다음 모델로 강등.

    반환: (응답텍스트, 사용모델) — 성공.  (None, None) — 실패(호출부가 강등 처리).
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
        blocked = False
        for attempt in range(_MAX_RETRIES_PER_MODEL + 1):  # 0=최초 시도, 1..N=재시도(일반 오류만)
            if attempt > 0:
                backoff = _RETRY_BACKOFFS[attempt - 1]
                print(f"[model_router] {model} 재시도 {attempt}/{_MAX_RETRIES_PER_MODEL} — {backoff}s 대기 후 (같은 모델, 강등 아님)")
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
                print(f"[model_router] {model} 시도{attempt+1} {last_err} — 일반오류(같은 모델 재시도)")
                continue
            except Exception as e:
                last_err = f"{type(e).__name__}: {e}"
                print(f"[model_router] {model} 시도{attempt+1} 예외 {last_err} — 일반오류(같은 모델 재시도)")
                continue

            if result.returncode != 0:
                # claude CLI는 "모델 없음/접근불가" 류 에러를 stderr가 아니라
                # stdout에 쓴다(실측 2026-07-02: "There's an issue with the
                # selected model..."). 강등 판별은 stdout+stderr 합쳐서 본다.
                err_text = ((result.stderr or "") + "\n" + (result.stdout or "")).strip()
                last_err = err_text[:200] or f"exit {result.returncode} (메시지 없음)"
                if _is_model_blocked(err_text):
                    blocked = True
                    print(f"[model_router] {model} 모델차단 감지→강등: {last_err}")
                    _alert(
                        f"⚠️ 모델차단 감지→강등{tag}\n"
                        f"{model} 모델차단 신호({last_err[:120]}) → 다음 모델로 강등 시도."
                    )
                    break  # 재시도 없이 즉시 다음 모델로
                print(f"[model_router] {model} 시도{attempt+1} exit {result.returncode}: {last_err} — 일반오류(같은 모델 재시도)")
                continue

            out = (result.stdout or "").strip()
            if not out:
                last_err = "빈 응답"
                print(f"[model_router] {model} 시도{attempt+1} {last_err} — 일반오류(같은 모델 재시도)")
                continue

            model_ok_out = out
            break  # 이 모델 성공 — 재시도 루프 탈출

        if model_ok_out is not None:
            if i > 0:  # 1순위가 아닌 대체 모델로 응답 = 앞서 모델차단 감지로 강등된 케이스(위에서 이미 경보 발송됨)
                print(f"[model_router] 강등 완료: {chain[i-1]} → {model}")
            return model_ok_out, model

        if blocked:
            continue  # 다음 모델로 (경보는 감지 시점에 이미 발송, 재시도 낭비 없이 즉시 강등)

        # 일반 오류로 이 모델의 재시도가 모두 소진 — 다음 모델로 내려가지 않고 바로 종료
        _alert(
            f"🚨 모델 라우팅 실패{tag} — {model} {_MAX_RETRIES_PER_MODEL}회 재시도 후 실패→규칙폴백"
            f"(일시적 서버장애로 판단, 강등 안 함). 마지막 오류: {last_err}"
        )
        print(f"[model_router] {model} 재시도 {_MAX_RETRIES_PER_MODEL}회 소진(일반오류) — 규칙폴백. 마지막: {last_err}")
        return None, None

    _alert(
        f"🚨 전 모델 차단{tag} — 체인 {len(chain)}개 전부 모델차단 감지 후 소진"
        f"(마지막: {last_err}). 규칙기반 강등."
    )
    print(f"[model_router] 전 모델 차단 소진 — 마지막 오류: {last_err}")
    return None, None


if __name__ == "__main__":
    # 자가 점검(드라이): 체인·claude 존재만 확인, 실제 호출 안 함.
    print("MODEL_FALLBACK_CHAIN =", MODEL_FALLBACK_CHAIN)
    print("claude CLI 경로 =", shutil.which("claude") or "(미설치)")
