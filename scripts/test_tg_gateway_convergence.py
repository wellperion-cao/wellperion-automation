"""배255(2026-08-08 웰리 지적) — 텔레그램 sendMessage 발신은 관문(tg_outbound_log.send)
하나만 지나야 한다. naver_talktalk_custommenu.py·publish_digest.py 가 requests/urllib 로
api.telegram.org sendMessage 를 직접 두드리던 것을 관문 경유로 수렴했다(2026-08-17).

sendPhoto 는 관문에 없는 경로라 그대로 두기로 했다(GM 지시) — 그 경로까지 없애지 않는다,
sendMessage 직접 호출만 사라졌는지 확인한다.

실행: C:/Python314/python.exe scripts/test_tg_gateway_convergence.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TARGETS = ["naver_talktalk_custommenu.py", "publish_digest.py"]


def main() -> int:
    for name in TARGETS:
        src = (ROOT / name).read_text(encoding="utf-8")
        assert "/sendMessage" not in src, (
            f"{name} 에 sendMessage 직접 호출이 남아있다 — tg_outbound_log.send() 관문 경유로 바꿔야 한다"
        )
        assert "tg_outbound_log import" in src, f"{name} 이 발신 관문(tg_outbound_log)을 import 하지 않는다"
    print(f"OK — {', '.join(TARGETS)} 모두 sendMessage 직접호출 0건 + 관문 import 확인")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
