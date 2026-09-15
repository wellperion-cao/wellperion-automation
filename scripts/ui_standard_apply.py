"""화면 UI/UX 표준 반영기 — 안 지키는 화면에 공통 규격을 붙인다.

GM 2026-09-15 「화면 UI/UX 까지 표준화해서 전체적으로 UI/UX 가 개선되는 모습이 나와야」.
표준(scripts/ui_standard_check.py)의 ① 「공통 규격 assets/wp-ui.css 를 링크한다」가 141장 중 7장뿐이었다.
wp-ui.css 에 UX 바닥 규칙(키보드 초점·커서·움직임 줄이기·폰 글자 16px·사진 넘침)을 넣었으니,
링크 한 줄이 들어가면 그 화면의 ④·⑥ 항목 상당수가 저절로 채워진다.

하는 일 — 화면마다 딱 한 줄:
  <link rel="stylesheet" href="{상대경로}assets/wp-ui.css">
  를 <head> 의 다른 스타일보다 앞에(뷰포트 meta 다음) 넣는다. 앞에 두는 이유 = 화면 자기 CSS·
  플랫폼 토큰(platform_brand.css)이 뒤에서 이겨야 한다. wp-ui.css 는 tokens.css 를 @import 하므로
  뒤에 두면 웰페리온 랩스 화면이 베이지로 돌아간다.

안 건드리는 것:
  · 나우열M 라인(safe_commit.NAWOOLM_LINE_PREFIXES) — 업무관리 방에 알리기만 한다
  · 종합접수처 잠금 경로(status/reception_freeze.json · GM 외 수정 금지)
  · 이미 링크한 화면 · 인쇄 지면·조각(ui_standard_check.화면들 이 이미 거른다)

쓰는 법:
  C:/Python314/python.exe scripts/ui_standard_apply.py            # 무엇을 바꿀지 목록만
  C:/Python314/python.exe scripts/ui_standard_apply.py --apply    # 실제로 넣는다
그 뒤 ui_standard_check.py --저장 --ux 로 다시 재서 전·후를 표에 남긴다.
"""
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ui_standard_check as chk          # noqa: E402
from safe_commit import NAWOOLM_LINE_PREFIXES, _path_matches_any  # noqa: E402

LINK = '<link rel="stylesheet" href="{rel}assets/wp-ui.css">'

# 종합접수처 최종본 잠금(status/reception_freeze.json · GM 외 수정 금지) — 잠긴 동안은 링크도 안 넣는다
def _frozen():
    import json
    try:
        fz = json.load(io.open(os.path.join(chk.ROOT, "status", "reception_freeze.json"), encoding="utf-8"))
        return tuple(fz.get("paths", [])) if fz.get("locked") else ()
    except Exception:
        return ()
FROZEN = _frozen()
_VIEWPORT = re.compile(r"<meta[^>]+name=[\"']viewport[\"'][^>]*>", re.I)
_CHARSET = re.compile(r"<meta[^>]+charset[^>]*>", re.I)
_HEAD = re.compile(r"<head[^>]*>", re.I)


def rel_prefix(screen_rel: str) -> str:
    depth = screen_rel.count("/")
    return "../" * depth


def plan():
    out = []
    for p in chk.화면들():
        rel = p.replace("\\", "/").replace(chk.GUIDE + "/", "")
        full = os.path.join(chk.ROOT, p)
        s = io.open(full, encoding="utf-8", errors="ignore").read()
        if "<style" not in s and chk.공통규격 not in s:
            continue
        if chk.공통규격 in s:
            continue
        if _path_matches_any(p.replace("\\", "/"), NAWOOLM_LINE_PREFIXES):
            out.append((rel, "나우열M 라인 — 건너뜀(알림만)", None))
            continue
        if any(p.replace("\\", "/").startswith(x) for x in FROZEN):
            out.append((rel, "종합접수처 잠금(GM) — 건너뜀", None))
            continue
        out.append((rel, "링크 추가", full))
    return out


def insert_link(full: str, rel: str) -> bool:
    raw = io.open(full, encoding="utf-8", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    line = LINK.format(rel=rel_prefix(rel))
    for rx in (_VIEWPORT, _CHARSET, _HEAD):
        m = rx.search(raw)
        if m:
            new = raw[:m.end()] + nl + line + raw[m.end():]
            io.open(full, "w", encoding="utf-8", newline="").write(new)
            return True
    return False


def main(argv):
    apply = "--apply" in argv
    items = plan()
    todo = [x for x in items if x[2]]
    skip = [x for x in items if not x[2]]
    print(f"공통 규격 링크가 없는 화면 {len(items)}장 — 넣을 것 {len(todo)} · 나우열M 라인 건너뜀 {len(skip)}")
    for rel, why, _ in skip:
        print(f"  건너뜀  {rel}")
    done = fail = 0
    for rel, _why, full in todo:
        if not apply:
            print(f"  넣을 곳  {rel}")
            continue
        if insert_link(full, rel):
            done += 1
        else:
            fail += 1
            print(f"  실패(head 없음)  {rel}")
    if apply:
        print(f"넣음 {done} · 실패 {fail}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
