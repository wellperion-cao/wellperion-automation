#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
erp_modules_build.py — ERP 앱 셸 모듈 목록 자동 생성 (2026-09-03 시토)

무엇:
  `3. 웰페리온 가이드/erp/index.html` 이 그리는 카드 목록
  `3. 웰페리온 가이드/erp/modules.json` 을 정본에서 자동 생성한다.

왜:
  전에는 modules.json 을 손으로 적어 3모듈만 있었다. C레벨이 화면을 하나 만들 때마다
  사람이 목록에 또 적어야 했고, 안 적으면 ERP 홈에서 영영 안 보였다. 손 목록은
  '한 곳만 본다'(약속 L01) 위반이다 — 화면 파일 자체가 정본이면 된다.

정본(읽기만 · 여기서 절대 고치지 않는다):
  - `3. 웰페리온 가이드/{role}/**.html`  : 실제 화면 파일 = 목록의 뿌리
  - `ssot/ownership_map.json`            : 역할·닉네임 (가이드 루트 페이지 소유 판정)
  - `ssot/kpi.json` roles.{role}.staff   : 카드에 적는 담당 실무진
  - `status/module_registry.json`        : 자동화 등록부 — 화면을 가리키는 항목이 있으면 설명 한 줄

거르는 기준(사람이 여는 화면만):
  `*_block.html`·`*_template.html` = 다른 페이지에 끼워 넣는 조각,
  `tmp/`·`_assets/`·`status/`·`reports/` = 산출물·부품 폴더,
  `<title>` 없는 파일 = 완성된 화면이 아니다.

멱등: 같은 입력이면 같은 출력(생성 시각 같은 변동 필드를 넣지 않는다).

사용:
  C:/Python314/python.exe scripts/erp_modules_build.py            # 생성·역할별 건수 출력
  C:/Python314/python.exe scripts/erp_modules_build.py --check    # 생성 없이 경로 실재 검사만
  C:/Python314/python.exe scripts/erp_modules_build.py --pre-commit  # 훅 전용(변경 있을 때만·조용히)

종료코드: 0 정상 / 1 --check 에서 없는 경로 발견. --pre-commit 은 항상 0(fail-open).
"""

import html
import io
import json
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(REPO, "3. 웰페리온 가이드")
OUT_REL = "3. 웰페리온 가이드/erp/modules.json"

# 역할 → (닉네임, 화면에 쓸 그룹 이름). 순서 = ERP 홈에 그려지는 섹션 순서.
ROLE_ORDER = [
    ("ceo", "웰리"),
    ("cpo", "시포"),
    ("cmo", "시모"),
    ("coo", "시우"),
    ("cto", "시토"),
    ("cbo", "시보"),
    ("chro", "시로"),
    ("cfo", "시뽀"),
    ("gm", "GM"),
]

# 가이드 루트 .html 은 폴더로 소유를 못 가른다. 소유 판정 근거 = ssot/ownership_map.json
# primary_surface(웰리=AI운영한장 / 시토=자율작업현황 / 시우=전사회의) + 2026-08-05 GM 확정
# (월간운영계획은 GM 소관). 파일명 매칭은 오히려 깨지기 쉬워 여기 일곱 줄로 못 박는다.
ROOT_PAGES = {
    "wellperion_guide(main).html": "ceo",
    "항해지도.html": "ceo",
    "wellperion_dashboard_web.html": "cpo",
    "자율현황.html": "cto",
    "전사회의.html": "coo",
    "월간운영계획.html": "gm",
    # ★2026-09-03 GM 지시 "일단 다 AWS ERP에 넣어두고 하나씩 정리해야할듯" — 역할 폴더 밖에 있어
    #   자동 수집에 안 걸리던 화면들. 웰리 전수조사(저장소 HTML 198 · 등록 95)에서 나온 것들이다.
    "onboarding/직원교육_30분.html": "coo",    # 운영부 신입 교육 — 인사 기밀이 아니라 실무 교육이다
    "onboarding/game.html": "coo",             # 위와 짝(신입 퀴즈)
    "coo/notice/notice_template.html": "coo",  # 공지 서식 — 실무진이 공지 만들 때 연다
    "home/index.html": "cmo",                  # 대외 홈(한국어)
    "home/en/index.html": "cmo",               # 대외 홈(영문)
}
# 루트에서 뺀 것: index.html(= erp 셸과 같은 입구·중복), northstar_today.html·헌법한장.html
# (둘 다 meta refresh 로 다른 화면에 넘기는 안내 껍데기 — 아래 page_title 이 걸러낸다).

# 핵심 3모듈 — 맨 위에 고정으로 올린다. 이름·설명·담당은 GM 이 쓰던 표현 그대로 둔다.
CORE = {
    "cpo/member/membership.html": {
        "id": "member", "name": "회원",
        "desc": "멤버십·강습 회원 등록과 상태를 한 곳에서 관리한다.",
        "staff": "이경연 실장", "roles": ["admin"],
    },
    "cpo/문의현황.html": {
        "id": "inquiry", "name": "문의",
        "desc": "홈페이지·전화·현장으로 들어온 문의를 접수부터 등록까지 따라간다.",
        "staff": "이경연 실장", "roles": ["admin", "staff"],
    },
    "coo/check/시설부 체계.html": {
        "id": "check", "name": "점검",
        "desc": "시설 일일 점검과 고장 접수 현황을 본다.",
        "staff": "이정헌 소장", "roles": ["admin", "staff"],
    },
}

SKIP_DIRS = {"tmp", "_assets", "status", "reports"}
TITLE_RE = re.compile(r"<title>(.*?)</title>", re.S | re.I)


def read_json(rel):
    p = os.path.join(REPO, rel)
    try:
        with io.open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def page_title(path):
    """<title> 안의 글. 없으면 None(= 화면이 아니라고 본다)."""
    try:
        with io.open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(8000)
    except Exception:
        return None
    # url= 이 붙은 refresh 만 = 다른 화면으로 넘기는 안내 껍데기(카드로 세우면 중복).
    # url 없는 refresh 는 화면 자동 새로고침이라 멀쩡한 화면이다 — 거르면 안 된다.
    if re.search(r'http-equiv\s*=\s*["\']?refresh[^>]*url\s*=', head, re.I):
        return None
    m = TITLE_RE.search(head)
    if not m:
        return None
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1))).strip()
    # &middot; 같은 엔티티가 카드 이름에 글자 그대로 찍히는 것을 막는다(2026-09-03 실측).
    t = html.unescape(t)
    return t or None


def is_screen(rel):
    """사람이 눌러 여는 화면인가."""
    parts = rel.split("/")
    if any(p in SKIP_DIRS for p in parts[:-1]):
        return False
    base = parts[-1]
    return not (base.endswith("_block.html") or base.endswith("_template.html"))


def registry_desc():
    """자동화 등록부에서 화면 파일을 가리키는 항목의 설명 한 줄. {파일명: 설명}"""
    out = {}
    for m in read_json("status/module_registry.json").get("modules", []):
        feature = (m.get("feature") or "").strip()
        if not feature:
            continue
        line = re.split(r"[.\n]|\s—\s|\s\[", feature)[0].strip()
        if len(line) > 90:
            line = line[:88].rstrip() + "…"
        for name in re.findall(r"([^\"'\s/·]+\.html)", json.dumps(m, ensure_ascii=False)):
            out.setdefault(name, line)
    return out


def make_id(role, rel):
    slug = re.sub(r"[^0-9A-Za-z가-힣]+", "-", os.path.splitext(rel.split("/", 1)[-1])[0]).strip("-")
    return "%s-%s" % (role, slug.lower())


def build():
    # 카드 한 줄에 들어갈 만큼만 — kpi.json 의 staff 는 웰리처럼 괄호로 긴 부연이 붙기도 한다.
    staff_of = {r: (v.get("staff") or "").split("(")[0].strip(" ·")
                for r, v in read_json("ssot/kpi.json").get("roles", {}).items()}
    nick_of = dict(ROLE_ORDER)
    # 닉네임은 ownership_map 이 정본 — 다르면 그쪽을 따른다.
    for r in read_json("ssot/ownership_map.json").get("roles", []):
        key = (r.get("title") or "").lower()
        if key in nick_of and r.get("nick"):
            nick_of[key] = r["nick"]

    descs = registry_desc()
    items = []
    seen = set()

    def add(role, rel):
        # ROOT_PAGES 는 사람이 골라 적은 목록이라 is_screen 판정을 건너뛴다.
        # (공지 서식은 파일명이 _template 이라 조각으로 걸러지는데, 실제로는 실무진이 여는 화면이다.)
        if rel in seen or (rel not in ROOT_PAGES and not is_screen(rel)):
            return
        title = page_title(os.path.join(GUIDE, rel))
        if not title:
            return
        seen.add(rel)
        core = CORE.get(rel)
        items.append({
            "id": core["id"] if core else make_id(role, rel),
            "core": bool(core),
            "group": nick_of.get(role, role),
            "role": role,
            "name": core["name"] if core else title,
            "desc": (core["desc"] if core else descs.get(os.path.basename(rel), "")),
            "path": "../" + rel,
            "staff": (core["staff"] if core else staff_of.get(role, "")),
            "roles": core["roles"] if core else ["admin", "staff"],
        })

    for role, _ in ROLE_ORDER:
        base = os.path.join(GUIDE, role)
        if not os.path.isdir(base):
            continue
        found = []
        for dp, _dn, fn in os.walk(base):
            for f in fn:
                if f.endswith(".html"):
                    found.append(os.path.relpath(os.path.join(dp, f), GUIDE).replace("\\", "/"))
        for rel in sorted(found):
            add(role, rel)
    for fname, role in sorted(ROOT_PAGES.items()):
        add(role, fname)

    order = {r: i for i, (r, _) in enumerate(ROLE_ORDER)}
    core_rank = {v["id"]: i for i, v in enumerate(CORE.values())}  # 회원 → 문의 → 점검
    items.sort(key=lambda m: (0, core_rank[m["id"]], "") if m["core"]
               else (1, order.get(m["role"], 99), m["name"]))
    return items


def write(items):
    doc = {
        "_doc": "ERP 앱 셸(erp/index.html)이 그리는 모듈 카드 목록. 손으로 고치지 마라 — "
                "scripts/erp_modules_build.py 가 화면 파일·ssot/ownership_map.json·ssot/kpi.json·"
                "status/module_registry.json 에서 만든다. 카드를 늘리려면 화면을 만들면 되고, "
                "담당자 이름을 바꾸려면 ssot/kpi.json 을 고친다.",
        "_generator": "scripts/erp_modules_build.py",
        "modules": items,
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2) + "\n"
    out = os.path.join(REPO, OUT_REL)
    old = ""
    if os.path.exists(out):
        with io.open(out, encoding="utf-8") as f:
            old = f.read()
    if old == text:
        return False
    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return True


def missing_paths(items):
    bad = []
    for m in items:
        p = os.path.join(GUIDE, "erp", m["path"].replace("/", os.sep))
        if not os.path.isfile(os.path.normpath(p)):
            bad.append(m["path"])
    return bad


# 이 중 하나라도 이번 커밋에 staged 면 목록을 다시 만든다. 경로 대조가 아니라 git pathspec 으로
# 물어본다 — 한글 경로가 name-only 출력에서 8진 이스케이프로 나와 문자열 비교가 깨지기 때문.
TRIGGER = ["3. 웰페리온 가이드/*.html", "ssot/ownership_map.json",
           "ssot/kpi.json", "status/module_registry.json"]


def staged_trigger():
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--"] + TRIGGER, cwd=REPO)
    except Exception:
        return False
    return bool(out.strip())


def main():
    args = sys.argv[1:]

    if "--pre-commit" in args and not staged_trigger():
        return 0

    items = build()
    bad = missing_paths(items)

    if "--check" in args:
        print("[erp-modules] %d건 · 없는 경로 %d건" % (len(items), len(bad)))
        for b in bad:
            print("  없음:", b)
        return 1 if bad else 0

    changed = write(items)

    if "--pre-commit" in args:
        if changed:
            subprocess.call(["git", "add", "--", OUT_REL], cwd=REPO)
            print("[erp-modules] modules.json 재생성 %d건 — 이번 커밋에 포함" % len(items))
        return 0

    counts = {}
    for m in items:
        counts[m["group"]] = counts.get(m["group"], 0) + 1
    print("[erp-modules] %s (%d건 · %s)" % (OUT_REL, len(items), "변경" if changed else "변경 없음"))
    for _role, nick in ROLE_ORDER:
        if counts.get(nick):
            print("  %-4s %3d" % (nick, counts[nick]))
    print("  핵심 %d · 없는 경로 %d" % (sum(1 for m in items if m["core"]), len(bad)))
    for b in bad:
        print("  없음:", b)
    return 0


def _selftest():
    """python scripts/erp_modules_build.py --selftest — 거르는 규칙이 살아있는지만 본다."""
    assert is_screen("cpo/member/membership.html")
    assert not is_screen("cmo/survey/wp_inquiry_block.html")
    assert not is_screen("coo/notice/notice_template.html")
    assert not is_screen("coo/tmp/뭔가.html")
    assert make_id("cpo", "cpo/member/lesson.html") == "cpo-member-lesson"
    items = build()
    assert items and items[0]["core"], "핵심 모듈이 맨 위가 아니다"
    assert [m["id"] for m in items if m["core"]] == ["member", "inquiry", "check"]
    assert not missing_paths(items), "없는 경로가 있다"
    ids = [m["id"] for m in items]
    assert len(ids) == len(set(ids)), "id 중복"
    print("selftest OK ·", len(items), "건")


if __name__ == "__main__":
    if "--selftest" in sys.argv[1:]:
        _selftest()
    else:
        sys.exit(main())
