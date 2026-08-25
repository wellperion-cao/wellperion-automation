"""카톡 중복 발신 가드가 방 이름 표기 차이를 같은 방으로 보는지 검사한다.

배경(2026-08-17 시토): 방 찾기(_room_core_key)는 「★ 운영부」와 「★운영부」를 같은 방으로
보내는데, 중복 가드(_dedup_signature / check_near_dup)만 방 이름 원문을 키로 써서 두 방으로
봤다. 그래서 표기가 다른 호출부가 하나라도 남아 있으면 같은 내용이 같은 방에 두 번 나갔다.
실측: 2026-08-15 발신 로그에 두 표기가 같은 날 함께 등장.

실행: C:/Python314/python.exe scripts/test_kakao_dedup_roomkey.py
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.pop("SKIP_KAKAO_DEDUP_GUARD", None)

import kakao_report_sender as k  # noqa: E402

VARIANTS = ["★ 운영부", "★운영부", "★  운영부"]


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        k.DEDUP_LEDGER_PATH = Path(tmp) / "ledger.json"

        # 1) 표기만 다른 같은 방 = 같은 서명
        sigs = {k._dedup_signature(v, "본문") for v in VARIANTS}
        assert len(sigs) == 1, f"표기별 서명이 갈렸다: {sigs}"

        # 2) 다른 방은 여전히 다른 서명(정규화가 방을 뭉개면 안 된다)
        assert k._dedup_signature("★운영부", "본문") != k._dedup_signature("★부서장", "본문")

        # 3) 정확일치 가드: 공백형으로 보낸 뒤 무공백형이 차단되는가
        k.record_dedup_sent("★ 운영부", text="어제 운영부 정리 · 8/16")
        assert k.check_dedup("★운영부", text="어제 운영부 정리 · 8/16"), "표기 다르면 중복을 못 잡는다"
        assert not k.check_dedup("★부서장", text="어제 운영부 정리 · 8/16"), "다른 방까지 막으면 안 된다"

        # 4) 근접중복 가드: 낱말이 크게 겹치면 표기가 달라도 잡는가
        hit, ratio = k.check_near_dup("★운영부", "어제 운영부 정리 · 8/16 접수 3건 완료 2건 남음")
        assert hit, f"근접중복을 표기 차이로 놓쳤다(겹침 {ratio:.2f})"

        # 5) 접수 전달문: 접수번호만 다른 두 번째 접수는 통과해야 한다
        RELAY_TMPL = (
            "🔔 새 접수 안내\n접수번호: RECEPTION-{n}\n이름: 홍길동\n내용: 골프 강습 문의\n"
            "처리: 담당자 배정 예정\n링크: https://wellperion.com/reception"
        )
        k.record_dedup_sent("★부서장", text=RELAY_TMPL.format(n=131))
        hit2, ratio2 = k.check_near_dup("★부서장", RELAY_TMPL.format(n=132))
        assert not hit2, f"접수번호가 다른 전달문을 근접중복으로 막았다(겹침 {ratio2:.2f})"

        # 6) 같은 접수번호 재발송은 여전히 잡아야 한다
        hit3, ratio3 = k.check_near_dup("★부서장", RELAY_TMPL.format(n=131))
        assert hit3, f"같은 접수번호 재발송을 통과시켰다(겹침 {ratio3:.2f})"

    print("OK — 방 이름 표기 차이를 중복 가드가 같은 방으로 본다")
    print("OK — 접수번호 다른 전달문은 통과, 같은 번호 재발송은 차단")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
