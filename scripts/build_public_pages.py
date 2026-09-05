"""공개 화면 5장(6+4장) 정적 서빙 빌드 — 배1019 (시우 2026-09-05).

정본 = 아래 SRC 목록의 워드프레스 조각(vc_raw_html 원문, "3. 웰페리온 가이드/coo|cmo/..."). 이 스크립트는
그 조각을 표준 <!doctype html> 문서로 감싸 "3. 웰페리온 가이드/public/{ko,en}/*.html" 에 산출물로 낸다.
조각이 바뀌면 이 스크립트를 다시 실행해 산출물을 갱신한다 — 산출물 자체를 직접 고치지 않는다.

실행: C:/Python314/python.exe scripts/build_public_pages.py
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
GUIDE = ROOT / "3. 웰페리온 가이드"
PUBLIC = GUIDE / "public"

# (출력 상대경로, 언어, <title>, body page-id, 소스 조각 경로)
PAGES = [
    ("ko/reception.html", "ko", "웰페리온 종합접수처", "8434",
     GUIDE / "coo/reception/reception_block.html"),
    ("ko/lookup.html", "ko", "웰페리온 조회", "8584",
     GUIDE / "coo/reception/wp_lookup_block.html"),
    ("ko/inquiry.html", "ko", "웰페리온 문의", "8394",
     GUIDE / "cmo/survey/wp_inquiry_block.html"),
    ("ko/inquiry-form.html", "ko", "웰페리온 문의 폼", "8460",
     GUIDE / "cmo/survey/wp_inquiry_form.html"),
    ("ko/lost-found.html", "ko", "웰페리온 습득물 보기", "8462",
     GUIDE / "coo/reception/wp_lost_found_gallery_block.html"),
    ("ko/lost-found-register.html", "ko", "웰페리온 습득물 접수(직원)", "8464",
     GUIDE / "coo/reception/wp_lost_found_register_block.html"),
    ("en/reception.html", "en", "Wellperion Reception Desk", "8751",
     GUIDE / "coo/reception/wp_reception_block_en.html"),
    ("en/lookup.html", "en", "Wellperion Lookup", "8741",
     GUIDE / "coo/reception/wp_lookup_block_en.html"),
    ("en/inquiry.html", "en", "Wellperion Inquiry", "8408",
     GUIDE / "cmo/survey/wp_inquiry_form_en.html"),
    ("en/lost-found.html", "en", "Wellperion Lost & Found", "8772",
     GUIDE / "coo/reception/wp_lost_found_gallery_block_en.html"),
]

TEMPLATE = """<!-- 산출물 — 직접 수정 금지. 정본 = {src_rel} · 재생성 = scripts/build_public_pages.py -->
<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
</head>
<body class="page-id-{page_id}">
{fragment}
</body>
</html>
"""


ASSET_LINK = 'href="../../assets/wp-typography.css"'
# 조각은 자기 위치("3. 웰페리온 가이드/coo|cmo/.../*.html", 2단 깊이) 기준 상대경로로 이 CSS 를 가리킨다.
# public/ko|en/*.html 도 우연히 2단 깊이라 조각을 그대로 두면 값은 같지만, 실서비스 URL(/ko/reception 등)은
# 1단 깊이라 "../../"가 사이트 루트를 뚫고 나가 깨진다(로컬 실측으로 확인) — 그래서 절대경로로 고쳐 낸다.
ASSET_LINK_FIXED = 'href="/assets/wp-typography.css"'


def build():
    PUBLIC.mkdir(exist_ok=True)
    (PUBLIC / "ko").mkdir(exist_ok=True)
    (PUBLIC / "en").mkdir(exist_ok=True)
    asset_out = PUBLIC / "assets" / "wp-typography.css"
    asset_out.parent.mkdir(exist_ok=True)
    asset_out.write_text((GUIDE / "assets/wp-typography.css").read_text(encoding="utf-8"), encoding="utf-8")
    for out_rel, lang, title, page_id, src in PAGES:
        fragment = src.read_text(encoding="utf-8").replace(ASSET_LINK, ASSET_LINK_FIXED)
        src_rel = src.relative_to(ROOT).as_posix()
        html = TEMPLATE.format(src_rel=src_rel, lang=lang, title=title,
                                page_id=page_id, fragment=fragment)
        out_path = PUBLIC / out_rel
        # GM 지시 2026-09-05 — 종합접수처 최종본 잠금: 잠긴 출력 페이지는 다시 쓰지 않는다
        import precommit_reception_freeze_guard as _frz
        if _frz.blocked_paths([out_path.relative_to(ROOT).as_posix()]):
            print(f"skip(잠금) {out_path.relative_to(ROOT).as_posix()}"); continue
        out_path.write_text(html, encoding="utf-8")
        print(f"built {out_path.relative_to(ROOT).as_posix()}  <- {src_rel}")


if __name__ == "__main__":
    build()
