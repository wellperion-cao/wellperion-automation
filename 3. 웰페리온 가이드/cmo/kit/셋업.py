# -*- coding: utf-8 -*-
"""마케팅 자동화 셋업 — 새 업체 하나를 받을 때 처음부터 끝까지 이 파일 하나로 시작한다.

무엇을 하나
-----------
1) `새업체_마케팅설정.json` 을 읽어 **못 받은 칸과 잘못 적은 칸**을 알려 준다.
2) 다 채워졌으면 그 업체의 작업 폴더를 만들고, 브랜드 값과 금지어를 업체 것으로 깐다.
3) AWS 에 올릴 요청서 한 장(`aws요청.json`)을 뽑아 준다 — 서버 반영은 담당이 이 한 장으로 한다.

왜 이렇게 나눴나
----------------
발행기(인스타·블로그·카페·당근·카카오)는 지금 웰페리온 계정에 값이 박혀 있다(실측 15곳).
그래서 "받아서 누르면 남의 업체 계정으로 글이 나간다"고 말할 수 없다.
이 셋업이 지금 확실히 해 주는 것은 **정보를 받아 정리하고, 업체 값을 코드 밖으로 빼내
작업 폴더까지 세우는 것**이다. 채널별 실제 발행 연결은 아래 표에 상태를 그대로 적어 둔다.

쓰는 법
-------
    python 셋업.py                       # 지금 설정이 어디까지 찼는지 본다
    python 셋업.py --설치                # 작업 폴더를 만들고 업체 값을 깐다
    python 셋업.py --설정 다른파일.json   # 다른 설정 파일로
    python 셋업.py --자가점검            # 이 도구 자체가 제대로 도는지
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
기본설정 = HERE / "새업체_마케팅설정.json"

# 반드시 있어야 셋업이 시작되는 칸. (경로, 사람이 읽는 이름)
필수 = [
    ("tenant.id", "업체 번호·영문 이름 (예: 3_spogym)"),
    ("tenant.name", "상호(한글)"),
    ("tenant.type", "업종 한 줄"),
    ("brand.one_liner", "업체를 한 줄로"),
    ("brand.tone", "말투 기준"),
    ("cta.inquiry_url", "문의를 받는 곳"),
    ("cadence.posts_per_week", "주 몇 회 내보낼지"),
    ("cadence.approval_channel", "승인받을 곳(카톡방 등)"),
]

# 있으면 훨씬 좋지만 없어도 시작은 되는 칸.
권장 = [
    ("brand.colors.primary", "대표 색"),
    ("brand.logo_file", "로고 파일"),
    ("channels.instagram", "인스타 주소"),
    ("channels.naver_place", "네이버 플레이스"),
    ("kpi.inquiries_per_month", "지금 월 문의 건수(기준선)"),
    ("tenant.owner_contact.channel", "대표님 연락 채널"),
]

# 채널별로 오늘 실제로 어디까지 되는가. 지어내지 않고 실측대로 적는다(2026-09-09).
채널상태 = [
    ("인스타그램", "계정 이름만 바꾸면 됨", "사람이 한 번 로그인"),
    ("네이버 블로그", "계정 이름만 바꾸면 됨", "사람이 한 번 로그인"),
    ("네이버 카페", "카페 번호·게시판 번호까지 바꿔야 함", "업체 카페가 있을 때만"),
    ("당근", "비즈프로필 번호를 바꿔야 함", "구글 로그인 1회"),
    ("카카오 채널", "채널 아이디를 바꿔야 함", "사람이 한 번 로그인"),
]

_색 = re.compile(r"^#[0-9A-Fa-f]{6}$")
_주소 = re.compile(r"^https?://")
_아이디 = re.compile(r"^[0-9]+_[a-z0-9_]+$")


def 값(설정: dict, 경로: str):
    """'brand.colors.primary' 처럼 점으로 이어진 자리를 찾아 준다. 없으면 None."""
    현재 = 설정
    for 조각 in 경로.split("."):
        if not isinstance(현재, dict) or 조각 not in 현재:
            return None
        현재 = 현재[조각]
    return 현재


def 비었나(v) -> bool:
    return v is None or v == "" or v == [] or v == {}


def 형식검사(설정: dict) -> list[str]:
    """적히긴 했는데 형식이 틀린 칸. 셋업 뒤에 조용히 깨지는 것을 여기서 잡는다."""
    문제 = []
    tid = 값(설정, "tenant.id")
    if tid and not _아이디.match(str(tid)):
        문제.append(f"tenant.id 「{tid}」 — 번호_영문소문자 형식으로 적으세요 (예: 3_spogym)")
    for 자리 in ("brand.colors.primary", "brand.colors.accent", "brand.colors.background"):
        c = 값(설정, 자리)
        if c and not _색.match(str(c)):
            문제.append(f"{자리} 「{c}」 — #RRGGBB 여섯 자리로 적으세요")
    for 자리 in ("cta.inquiry_url", "cta.reservation_url"):
        u = 값(설정, 자리)
        if u and not _주소.match(str(u)):
            문제.append(f"{자리} 「{u}」 — http 로 시작하는 주소여야 합니다")
    주당 = 값(설정, "cadence.posts_per_week")
    if 주당 is not None and not (isinstance(주당, int) and 0 < 주당 <= 21):
        문제.append(f"cadence.posts_per_week 「{주당}」 — 1~21 사이 숫자로 적으세요")
    return 문제


def 금지어자기모순(설정: dict) -> list[str]:
    """업체가 쓰지 않기로 한 말이 정작 자기 소개문에 들어 있는 경우.
    우리 쪽에서 실제로 났던 사고다 — 값만 바꾸고 소개문을 안 고쳐 옛 문구가 계속 나갔다."""
    말들 = [t.get("term") for t in (값(설정, "terms.forbidden") or []) if isinstance(t, dict)]
    말들 = [m for m in 말들 if m]
    글 = " ".join(
        str(값(설정, 자리) or "")
        for 자리 in ("brand.one_liner", "brand.positioning", "brand.tone")
    )
    return [f"금지어 「{m}」 가 업체 소개문에 그대로 있습니다" for m in 말들 if m.lower() in 글.lower()]


def 점검(설정: dict) -> dict:
    빠진필수 = [(p, n) for p, n in 필수 if 비었나(값(설정, p))]
    빠진권장 = [(p, n) for p, n in 권장 if 비었나(값(설정, p))]
    return {
        "빠진필수": 빠진필수,
        "빠진권장": 빠진권장,
        "형식오류": 형식검사(설정),
        "모순": 금지어자기모순(설정),
    }


def 보고(설정: dict, 결과: dict) -> None:
    이름 = 값(설정, "tenant.name") or "(상호 미입력)"
    print(f"\n■ {이름} — 마케팅 자동화 셋업 점검\n")
    총필수 = len(필수)
    찬필수 = 총필수 - len(결과["빠진필수"])
    print(f"  꼭 필요한 칸  {찬필수}/{총필수}")
    print(f"  있으면 좋은 칸 {len(권장) - len(결과['빠진권장'])}/{len(권장)}\n")

    if 결과["빠진필수"]:
        print("  ▶ 이것부터 받아야 시작합니다")
        for 경로, 이름표 in 결과["빠진필수"]:
            print(f"     · {이름표}   ({경로})")
        print()
    if 결과["형식오류"]:
        print("  ▶ 적히긴 했는데 형식이 틀립니다")
        for m in 결과["형식오류"]:
            print(f"     · {m}")
        print()
    if 결과["모순"]:
        print("  ▶ 서로 어긋납니다")
        for m in 결과["모순"]:
            print(f"     · {m}")
        print()
    if 결과["빠진권장"]:
        print("  ▶ 나중에 받아도 되지만 없으면 아쉬운 것")
        for 경로, 이름표 in 결과["빠진권장"]:
            print(f"     · {이름표}   ({경로})")
        print()

    if not 결과["빠진필수"] and not 결과["형식오류"] and not 결과["모순"]:
        print("  ✅ 시작할 수 있습니다 —  python 셋업.py --설치\n")
    else:
        print("  ⏸ 아직 시작하지 않습니다. 위 항목을 채운 뒤 다시 실행하세요.\n")

    print("  채널별 지금 상태")
    for 채널, 코드, 사람 in 채널상태:
        print(f"     {채널:9s} 코드: {코드:26s} 사람: {사람}")
    print()


def 설치(설정: dict, 결과: dict) -> Path:
    if 결과["빠진필수"] or 결과["형식오류"] or 결과["모순"]:
        raise SystemExit("아직 설치하지 않습니다 — 위 점검을 먼저 통과하세요.")

    tid = 값(설정, "tenant.id")
    폴더 = HERE / "업체" / tid
    (폴더 / "콘텐츠").mkdir(parents=True, exist_ok=True)
    (폴더 / "자산").mkdir(parents=True, exist_ok=True)

    # 업체 브랜드 값 — 우리 ssot/brand.json 이 하는 일을 업체마다 한 벌씩.
    (폴더 / "brand.json").write_text(
        json.dumps(
            {
                "_정본": f"{폴더.name} 브랜드 값. 색·말투를 바꾸려면 여기를 고친다.",
                "tenant": 값(설정, "tenant"),
                "brand": 값(설정, "brand"),
                "cta": 값(설정, "cta"),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # 업체 금지어 — 우리 ssot/forbidden_terms.json 과 같은 모양이라 같은 검사기가 읽는다.
    (폴더 / "forbidden_terms.json").write_text(
        json.dumps(
            {
                "_doc": f"{값(설정, 'tenant.name')} 대외 금지어. scripts/forbidden_scan.py 가 읽는 모양 그대로.",
                "scan_globs": [f"업체/{tid}/콘텐츠/**"],
                "exclude_globs": [],
                "exclude_dir_names": [".git", "__pycache__"],
                "terms": [t for t in (값(설정, "terms.forbidden") or []) if t.get("term")],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # AWS 반영 요청 한 장 — 서버는 담당이 이 값으로 만든다(열쇠는 이 꾸러미에 없다).
    (폴더 / "aws요청.json").write_text(
        json.dumps(
            {
                "_무엇": "이 업체를 AWS 에 올려 달라는 요청서. 담당에게 이 파일 하나만 주면 된다.",
                "tenant_id": tid,
                "site_dir": f"/srv/www/{tid}",
                "public_url": f"https://erp.wellperion.com/{tid.split('_', 1)[-1]}/",
                "faq_dir": f"/srv/erp/faq/{tid}",
                "필요한_것": [
                    "업체 폴더 만들기",
                    "공개 location 한 줄 추가(로그인 없이 열리게 · 검색 노출은 막고)",
                    "프로필 올리기",
                    "https 200 확인",
                ],
                "요청일": date.today().isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    (폴더 / "지금할일.md").write_text(
        "\n".join(
            [
                f"# {값(설정, 'tenant.name')} — 셋업 다음 걸음",
                "",
                "## 1. 사람이 해야 하는 것",
                "- [ ] 채널마다 브라우저에서 한 번 로그인 (계정은 업체에서 받는다)",
                f"- [ ] 승인받을 곳 정하기 — 지금 적힌 곳: {값(설정, 'cadence.approval_channel')}",
                "- [ ] 로고·사진 원본을 `자산/` 에 넣기",
                "",
                "## 2. 담당에게 넘기는 것",
                "- [ ] `aws요청.json` 한 장 전달 — 서버 자리와 공개 주소가 만들어진다",
                "",
                "## 3. 이렇게 나오면 성공",
                f"- 공개 주소가 열린다: https://erp.wellperion.com/{tid.split('_', 1)[-1]}/",
                "- `brand.json` 의 색·말투대로 첫 콘텐츠 한 장이 나온다",
                f"- 주 {값(설정, 'cadence.posts_per_week')}회 일정이 승인 채널에 뜬다",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"\n  ✅ 만들었습니다 → {폴더}")
    for f in ("brand.json", "forbidden_terms.json", "aws요청.json", "지금할일.md"):
        print(f"     · {f}")
    print("\n  다음 = 지금할일.md 를 여세요.\n")
    return 폴더


def 자가점검() -> None:
    """이 도구가 실제로 잡는지 본다 — '한 번도 걸러 낸 적 없는 검사기'를 만들지 않으려는 최소 확인."""
    빈설정 = json.loads(기본설정.read_text(encoding="utf-8"))
    r = 점검(빈설정)
    assert len(r["빠진필수"]) == len(필수), "빈 템플릿인데 필수 칸이 찼다고 나온다"

    나쁜설정 = {
        "tenant": {"id": "스포짐", "name": "테스트", "type": "헬스"},
        "brand": {"one_liner": "프리미엄 라이프스타일 클럽입니다", "tone": "정중히",
                  "colors": {"primary": "빨강"}},
        "terms": {"forbidden": [{"term": "프리미엄 라이프스타일", "replace": "정원제"}]},
        "cta": {"inquiry_url": "wellperion.com"},
        "cadence": {"posts_per_week": 99, "approval_channel": "카톡"},
    }
    r2 = 점검(나쁜설정)
    assert any("tenant.id" in m for m in r2["형식오류"]), "id 형식 오류를 못 잡는다"
    assert any("primary" in m for m in r2["형식오류"]), "색 형식 오류를 못 잡는다"
    assert any("inquiry_url" in m for m in r2["형식오류"]), "주소 형식 오류를 못 잡는다"
    assert any("posts_per_week" in m for m in r2["형식오류"]), "발행 횟수 범위를 못 잡는다"
    assert r2["모순"], "금지어가 소개문에 있는데 못 잡는다"

    좋은설정 = {
        "tenant": {"id": "3_spogym", "name": "스포짐", "type": "헬스장",
                   "owner_contact": {"channel": "카톡"}},
        "brand": {"one_liner": "동네에서 가장 오래 연 헬스장", "tone": "담담하게",
                  "colors": {"primary": "#221F20"}},
        "terms": {"forbidden": [{"term": "프리미엄 라이프스타일", "replace": "정원제"}]},
        "cta": {"inquiry_url": "https://example.com/문의"},
        "cadence": {"posts_per_week": 3, "approval_channel": "대표님 카톡"},
    }
    r3 = 점검(좋은설정)
    assert not r3["빠진필수"] and not r3["형식오류"] and not r3["모순"], r3
    print("자가점검 OK — 빈칸·형식·자기모순 셋 다 잡는다")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--설정", type=Path, default=기본설정)
    ap.add_argument("--설치", action="store_true")
    ap.add_argument("--자가점검", action="store_true")
    a = ap.parse_args()

    if a.자가점검:
        자가점검()
        return

    설정 = json.loads(a.설정.read_text(encoding="utf-8"))
    결과 = 점검(설정)
    보고(설정, 결과)
    if a.설치:
        설치(설정, 결과)


if __name__ == "__main__":
    main()
