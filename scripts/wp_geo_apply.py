# scripts/wp_geo_apply.py — 배1000 실행: JSON-LD 헤더 삽입 + robots.txt 교체 + 홈 메타설명 교체 (단일 세션, 최소 실행).
import asyncio
import json
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path.home() / "welperion-automation" / "scripts"))
from wordpress_admin_playwright import _import_playwright, _launch, WP_ADMIN_URL

CANON_VALUES_PATH = str(Path.home() / "welperion-automation" / "ssot" / "canon_values.json")


def _load_one_liner() -> str:
    """정본 = ssot/canon_values.json official_one_liner_kr. 여기서만 직독 — 문구 하드코딩 금지."""
    data = json.load(open(CANON_VALUES_PATH, encoding="utf-8"))
    for item in data["values"]:
        if item.get("key") == "official_one_liner_kr":
            return item["value"]
    raise RuntimeError("official_one_liner_kr not found in ssot/canon_values.json")


ONE_LINER = _load_one_liner()

# 구조화 데이터 정본 = 새 홈 파일 하나(3. 웰페리온 가이드/home/index.html)의 JSON-LD 그래프.
# 종전에는 같은 그래프를 이 파일에도 통째로 베껴 두고 있었다 — 2026-09-09 실측에서 질문이 홈 20개 :
# 도구 14개로 갈렸고, Organization.description 도 서로 달랐다. 시모가 홈을 고칠 때마다 시토에게
# "도구에도 옮겨 달라"고 부탁해야 하는 구조 자체가 원인이라 베끼기를 없앴다(시모 배1172 합의).
#   · 질문답변·시설 정보 = 홈 파일이 정본 (시모가 고친다)
#   · 회사 한 줄 소개    = ssot/canon_values.json 이 정본 (공식값이라 홈보다 우선한다)
HOME_HTML_PATH = str(Path.home() / "welperion-automation" / "3. 웰페리온 가이드" / "home" / "index.html")
MIN_QUESTIONS = 10   # 홈 파일이 깨졌을 때 반쪽 그래프를 라이브에 넣지 않기 위한 바닥값


def _build_json_ld() -> str:
    """새 홈의 JSON-LD 그래프를 그대로 읽어 라이브 주입본을 만든다. 못 읽거나 모양이 어긋나면 예외."""
    html = open(HOME_HTML_PATH, encoding="utf-8").read()
    graph = None
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and "@graph" in data:
            graph = data
            break
    if graph is None:
        raise RuntimeError("새 홈에서 JSON-LD @graph 를 못 찾았다 — %s" % HOME_HTML_PATH)

    types = [n.get("@type") for n in graph["@graph"]]
    for need in ("Organization", "SportsActivityLocation", "FAQPage"):
        if need not in types:
            raise RuntimeError("새 홈 그래프에 %s 가 없다 — 주입 중단" % need)
    faq = next(n for n in graph["@graph"] if n.get("@type") == "FAQPage")
    if len(faq.get("mainEntity") or []) < MIN_QUESTIONS:
        raise RuntimeError("질문이 %d개뿐이다(최소 %d) — 홈 파일이 깨졌는지 먼저 본다"
                           % (len(faq.get("mainEntity") or []), MIN_QUESTIONS))

    # 회사 한 줄 소개만 공식값으로 덮는다 — 홈 파일에는 짧은 손글씨 소개가 들어 있다(2026-09-09 실측).
    org = next(n for n in graph["@graph"] if n.get("@type") == "Organization")
    org["description"] = ONE_LINER

    body = json.dumps(graph, ensure_ascii=False, indent=1)
    return (
        "<!-- GEO(생성형 검색 최적화) 구조화 데이터 3종 — 배1000(시토) 2026-09-05,\n"
        "     정본 = home/index.html 그래프 + ssot/canon_values.json 한 줄 소개."
        " 여기서 손으로 고치지 않는다. -->\n"
        '<script type="application/ld+json">\n'
        + body
        + "\n</script>\n"
    )


JSON_LD = _build_json_ld()

ROBOTS_TXT = """# 웰페리온 공개 홈 — 사람 검색·AI 검색 모두 허용 (GEO · 배1000 시토 2026-09-05)
User-agent: *
Disallow: /wp/wp-admin/
Allow: /wp/wp-admin/admin-ajax.php

# 생성형 AI 검색 크롤러 — 명시 허용
User-agent: GPTBot
User-agent: OAI-SearchBot
User-agent: ChatGPT-User
User-agent: ClaudeBot
User-agent: anthropic-ai
User-agent: PerplexityBot
User-agent: Google-Extended
User-agent: Bingbot
User-agent: Yeti
Allow: /

Sitemap: http://wellperion.com/sitemap_index.xml
"""

HOME_META_DESC = ONE_LINER


MARKER = "GEO(생성형 검색 최적화) 구조화 데이터 3종 — 배1000"


async def step1_header_inject(page) -> str:
    await page.goto(WP_ADMIN_URL + "options-general.php?page=insert-headers-and-footers", wait_until="domcontentloaded")
    ta = page.locator("#ihaf_insert_header")
    current = await ta.input_value()
    mi = current.find(MARKER)
    if mi == -1:
        # 최초 삽입 — 기존 헤더 뒤에 새로 추가
        new_val = current.rstrip() + "\n\n" + JSON_LD
        action = "DONE(신규 삽입)"
    else:
        # 배1000 블록이 이미 있음 — FAQPage 14문답 등으로 갱신된 JSON_LD로 통째 교체
        comment_start = current.rfind("<!--", 0, mi)
        end = current.find("</script>", mi)
        if comment_start == -1 or end == -1:
            return "BLOCKED(기존 블록 경계 못 찾음 — 수동 확인 필요)"
        end += len("</script>")
        new_val = current[:comment_start] + JSON_LD.strip() + current[end:]
        action = "DONE(교체)"
    await ta.fill(new_val)
    save_btn = page.locator("input[type=submit], button[type=submit]").first
    await save_btn.click()
    await page.wait_for_timeout(1500)
    return action


async def step2_robots(page) -> str:
    """라이브 robots.txt 를 우리 판으로 바꾼다 (2026-09-11 실제로 성공한 절차).

    함정 둘 — 둘 다 여기서 겪고 고쳤다.
      ① main() 이 이 함수를 부르지 않고 있었다(9/5~9/11). 지금은 부른다.
      ② 파일이 아직 없을 때 Yoast 는 편집칸을 안 보여 주고 「Create robots.txt file」 버튼만 낸다.
         그 버튼 이름은 create_robots 이고, 누른 뒤 **페이지를 다시 열어야** 편집칸(robotsnew)이 생긴다.
         눌러 놓고 같은 화면에서 찾으면 「textarea 못 찾음」으로 끝난다.
    .htaccess 칸(htaccessnew)은 같은 화면에 나란히 있다 — 이름으로만 고른다. 잘못 건드리면 사이트가 죽는다.
    """
    await page.goto(WP_ADMIN_URL + "admin.php?page=wpseo_tools&tool=file-editor", wait_until="networkidle", timeout=45000)
    await page.wait_for_timeout(1500)
    mk = page.locator("input[name='create_robots']")
    if await mk.count():
        await mk.first.click()                      # 파일부터 만든다
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(2500)
        await page.goto(WP_ADMIN_URL + "admin.php?page=wpseo_tools&tool=file-editor",
                        wait_until="domcontentloaded", timeout=45000)
        await page.wait_for_timeout(2500)           # 다시 열어야 편집칸이 생긴다
    ta = page.locator("textarea[name='robotsnew'], textarea#robotstxt, textarea[name='robotstxt']")
    if await ta.count() == 0:
        # 텍스트영역이 여러개면 robots 라벨과 가장 가까운 것을 폭넓게 탐색
        all_ta = await page.locator("textarea").all()
        for t in all_ta:
            tid = (await t.get_attribute("id")) or ""
            if "robot" in tid.lower():
                ta = t
                break
        else:
            return "BLOCKED(robots textarea 못 찾음)"
        await ta.fill(ROBOTS_TXT)
    else:
        await ta.first.fill(ROBOTS_TXT)
    save_btn = page.locator("input[name='submitrobots']").first   # .htaccess 저장 버튼과 헷갈리지 않게 이름으로만
    if await save_btn.count():
        await save_btn.click()
        await page.wait_for_timeout(1500)
        return "DONE(저장 클릭함, 라이브 curl 재확인 필요)"
    return "BLOCKED(저장버튼 못 찾음)"


async def step3_home_meta(page) -> str:
    await page.goto(WP_ADMIN_URL + "post.php?post=6&action=edit&lang=ko", wait_until="domcontentloaded", timeout=45000)
    await page.wait_for_timeout(1500)
    box = page.locator("#wpseo_meta")
    if await box.count():
        await box.scroll_into_view_if_needed(timeout=5000)
        await page.wait_for_timeout(500)
    field = page.locator("#yoast_wpseo_metadesc")
    if await field.count() == 0:
        return "BLOCKED(메타설명 입력칸 못 찾음)"
    # 값이 JS(React 스니펫 미리보기)로 동기화되는 hidden input 일 수 있어 값 세팅 + input 이벤트 강제 발화
    await field.evaluate(
        "(el, v) => { el.value = v; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); }",
        HOME_META_DESC,
    )
    await page.wait_for_timeout(500)
    check_val = await field.input_value()
    if HOME_META_DESC not in check_val:
        return f"BLOCKED(값 반영 확인 실패: {check_val[:80]!r})"
    update_btn = page.locator("#publish")
    if await update_btn.count():
        await update_btn.click()
        await page.wait_for_timeout(3000)
        return "DONE(Update 클릭함, 라이브 curl 재확인 필요)"
    return "BLOCKED(Update 버튼 못 찾음)"


async def main():
    async_playwright = _import_playwright()
    p, ctx = await _launch(async_playwright)
    page = await ctx.new_page()
    results = {}
    try:
        results["header_inject"] = await step1_header_inject(page)
    except Exception as e:
        results["header_inject"] = f"ERROR: {e}"
    # step2_robots 는 만들어 놓고 부르지 않고 있었다(2026-09-11 실측). 그래서 라이브 robots.txt 에는
    # AI 크롤러 허용 줄이 없고, 사이트맵 줄이 /ko/wp-sitemap.xml(404)를 가리킨 채였다.
    try:
        results["robots"] = await step2_robots(page)
    except Exception as e:
        results["robots"] = f"ERROR: {e}"
    try:
        results["home_meta"] = await step3_home_meta(page)
    except Exception as e:
        results["home_meta"] = f"ERROR: {e}"

    print("=== RESULTS ===")
    for k, v in results.items():
        print(f"{k}: {v}")

    await ctx.close()


if __name__ == "__main__":
    asyncio.run(main())
