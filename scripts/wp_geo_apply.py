# scripts/wp_geo_apply.py — 배1000 실행: JSON-LD 헤더 삽입 + robots.txt 교체 + 홈 메타설명 교체 (단일 세션, 최소 실행).
import asyncio
import sys
sys.path.insert(0, r"C:\Users\jjky0\welperion-automation\scripts")
from wordpress_admin_playwright import _import_playwright, _launch, WP_ADMIN_URL

JSON_LD = """<!-- GEO(생성형 검색 최적화) 구조화 데이터 3종 — 배1000(시토) 2026-09-05, 정본=ssot/canon_values.json -->
<script type="application/ld+json">
{
 "@context": "https://schema.org",
 "@graph": [
  {
   "@type": "Organization",
   "@id": "https://wellperion.com/#org",
   "name": "웰페리온",
   "alternateName": ["Wellperion", "주식회사 웰페리온"],
   "url": "https://wellperion.com/",
   "telephone": "+82-2-6261-1200",
   "slogan": "하루의 완성, 웰페리온",
   "description": "웰페리온은 서울 한남동에 있는 약 3,000평 규모의 정원제 스포츠클럽입니다. 수영·P.T·필라테스·골프·스쿼시·발레·바레 강습과 사우나·스파를 회원제로 운영하며, 투어와 상담은 예약제입니다.",
   "address": {
    "@type": "PostalAddress",
    "streetAddress": "서빙고로 413, 101동 지1층 101호",
    "addressLocality": "용산구",
    "addressRegion": "서울특별시",
    "addressCountry": "KR"
   },
   "contactPoint": {
    "@type": "ContactPoint",
    "telephone": "+82-2-6261-1200",
    "contactType": "customer service",
    "availableLanguage": ["ko", "en"],
    "url": "http://wellperion.com/ko/inquiry/"
   }
  },
  {
   "@type": "SportsActivityLocation",
   "@id": "https://wellperion.com/#club",
   "name": "웰페리온 스포츠클럽",
   "parentOrganization": { "@id": "https://wellperion.com/#org" },
   "url": "https://wellperion.com/",
   "telephone": "+82-2-6261-1200",
   "address": {
    "@type": "PostalAddress",
    "streetAddress": "서빙고로 413, 101동 지1층 101호",
    "addressLocality": "용산구",
    "addressRegion": "서울특별시",
    "addressCountry": "KR"
   },
   "areaServed": ["한남동", "용산구", "서울"],
   "description": "웰페리온은 서울 한남동에 있는 약 3,000평 규모의 정원제 스포츠클럽입니다. 수영·P.T·필라테스·골프·스쿼시·발레·바레 강습과 사우나·스파를 회원제로 운영하며, 투어와 상담은 예약제입니다.",
   "openingHoursSpecification": [
    { "@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday","Tuesday","Wednesday","Thursday","Friday"], "opens": "06:00", "closes": "22:30" },
    { "@type": "OpeningHoursSpecification", "dayOfWeek": ["Saturday","Sunday"], "opens": "08:00", "closes": "20:00" }
   ],
   "amenityFeature": [
    { "@type": "LocationFeatureSpecification", "name": "P.T", "value": true },
    { "@type": "LocationFeatureSpecification", "name": "필라테스", "value": true },
    { "@type": "LocationFeatureSpecification", "name": "수영장", "value": true },
    { "@type": "LocationFeatureSpecification", "name": "골프(GDR·QED)", "value": true },
    { "@type": "LocationFeatureSpecification", "name": "스쿼시", "value": true },
    { "@type": "LocationFeatureSpecification", "name": "체조", "value": true },
    { "@type": "LocationFeatureSpecification", "name": "G.X", "value": true },
    { "@type": "LocationFeatureSpecification", "name": "사우나", "value": true },
    { "@type": "LocationFeatureSpecification", "name": "스파", "value": true }
   ],
   "isAccessibleForFree": false,
   "publicAccess": false
  },
  {
   "@type": "FAQPage",
   "@id": "https://wellperion.com/#faq",
   "mainEntity": [
    { "@type": "Question", "name": "웰페리온은 예약 없이 방문할 수 있나요?", "acceptedAnswer": { "@type": "Answer", "text": "투어·상담은 사전 예약제로만 진행합니다. 예약 없이 방문하는 워크인 등록은 운영하지 않습니다. 문의: wellperion.com/ko/inquiry" } },
    { "@type": "Question", "name": "멤버십은 어떻게 운영되나요?", "acceptedAnswer": { "@type": "Answer", "text": "정원제로 운영합니다. 정원이 찼을 때는 대기 멤버십을 함께 운영하며, 자세한 안내는 상담 시 드립니다." } },
    { "@type": "Question", "name": "가입은 어떻게 하나요?", "acceptedAnswer": { "@type": "Answer", "text": "문의 페이지(wellperion.com/ko/inquiry)에서 투어·상담을 예약하고, 방문 상담 후 가입합니다. 정원이 찼을 때는 대기 멤버십을 안내합니다." } },
    { "@type": "Question", "name": "운영 시간은 어떻게 되나요?", "acceptedAnswer": { "@type": "Answer", "text": "평일 06:00~22:30, 주말·공휴일 08:00~20:00. 휴관일은 신정, 설·추석 명절 연휴, 매월 둘째·넷째 주 일요일입니다." } },
    { "@type": "Question", "name": "어디에 있나요?", "acceptedAnswer": { "@type": "Answer", "text": "서울특별시 용산구 서빙고로 413, 101동 지1층(한남동). 대표 전화 02-6261-1200." } },
    { "@type": "Question", "name": "어떤 시설을 이용할 수 있나요?", "acceptedAnswer": { "@type": "Answer", "text": "수영·트레이닝·골프(GDR·QED 2종 타석)·스쿼시·체조·필라테스·사우나·스파를 한 공간에서 이용합니다." } },
    { "@type": "Question", "name": "강습도 예약제인가요?", "acceptedAnswer": { "@type": "Answer", "text": "네. 성인 강습(수영·P.T·필라테스·골프·스쿼시·발레·바레)과 유소년 강습 모두 사전 예약제로 진행하며, 워크인 등록은 운영하지 않습니다." } },
    { "@type": "Question", "name": "유소년 강습은 어떤 종목이 있나요?", "acceptedAnswer": { "@type": "Answer", "text": "수영, 스쿼시, KPGA 주니어 골프, 체조, 브래드리틀 뮤지컬 아카데미가 있습니다. 대상 연령과 일정은 종목별로 상담 시 안내합니다." } },
    { "@type": "Question", "name": "영어로 진행되는 강습이 있나요?", "acceptedAnswer": { "@type": "Answer", "text": "강습은 기본적으로 한국어로 진행합니다. 영어 강습은 뮤지컬·수영·스쿼시만 가능하며, 문의 페이지로 문의해 주세요." } },
    { "@type": "Question", "name": "운동복이나 수건은 준비되어 있나요?", "acceptedAnswer": { "@type": "Answer", "text": "네. 운동복·양말·수건·샤워 어메니티가 구비되어 있고, 수영 이용 시 바스타올을 드립니다. 실내용 운동화만 준비해 주세요. 수영을 하시는 분은 수영복·수영모·수경을 준비해 주세요." } },
    { "@type": "Question", "name": "스파·살롱·카페도 있나요?", "acceptedAnswer": { "@type": "Answer", "text": "파트너 시설로 Cinq Mondes(생크몽드) 스파, beautévu 살롱, CUPS 카페가 함께 있습니다. 이용 안내는 대표 전화 02-6261-1200으로 문의해 주세요." } },
    { "@type": "Question", "name": "규모는 어느 정도인가요?", "acceptedAnswer": { "@type": "Answer", "text": "서울 용산구 한남동, 약 3,000평 규모의 단일 공간입니다." } },
    { "@type": "Question", "name": "한남동에서 멤버십으로 운영하는 스포츠클럽인가요?", "acceptedAnswer": { "@type": "Answer", "text": "네. 웰페리온은 서울 용산구 한남동에 있는 정원제 스포츠클럽으로, 회원 정원 1,000명 안에서 멤버십으로 운영합니다. 정원이 찼을 때는 대기 멤버십을 안내합니다." } },
    { "@type": "Question", "name": "용산구에 정원제로 운영하는 회원제 스포츠클럽이 있나요?", "acceptedAnswer": { "@type": "Answer", "text": "웰페리온은 서울 한남동에 있는 약 3,000평 규모의 정원제 스포츠클럽입니다. 수영·P.T·필라테스·골프·스쿼시·발레·바레 강습과 사우나·스파를 회원제로 운영하며, 투어와 상담은 예약제입니다." } }
   ]
  }
 ]
}
</script>
"""

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

HOME_META_DESC = "웰페리온은 서울 한남동에 있는 약 3,000평 규모의 정원제 스포츠클럽입니다. 수영·P.T·필라테스·골프·스쿼시·발레·바레 강습과 사우나·스파를 회원제로 운영하며, 투어와 상담은 예약제입니다."


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
    await page.goto(WP_ADMIN_URL + "admin.php?page=wpseo_tools&tool=file-editor", wait_until="networkidle", timeout=45000)
    await page.wait_for_timeout(1500)
    create_link = page.locator("a:has-text('create one here'), button:has-text('create one here')")
    if await create_link.count():
        await create_link.first.click()
        await page.wait_for_timeout(1500)
    ta = page.locator("textarea#robotstxt, textarea[name='robotstxt']")
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
    save_btn = page.locator("button:has-text('Save changes to robots.txt'), input[value*='Save']").first
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
