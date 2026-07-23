# WPML 영어 문의 페이지 연결 절차

> **목적**: 한국어 문의 페이지(id 8394, `/ko/inquiry/`)에 영어 번역 페이지가 없어 ENG 버튼이 영어 홈으로 폴백되는 문제를 해결한다.
> **환경**: wellperion.com · 테마 Salient + WPBakery + WPML(`/ko/`, `/en/`) · HTTP 전용

---

## 1. WPML에서 영어 번역 페이지 생성

### 절차 (WP 관리자 수동)

1. `http://wellperion.com/wp/wp-admin/post.php?post=8394&action=edit` 접속
2. 편집 화면 우측 또는 하단의 **WPML Language** 메타박스 확인
3. "영어(English)" 행 옆 **"+"(번역 추가)** 아이콘 클릭
   - 아이콘이 없으면 WPML > Translation Management > 수동 번역 대기열에 8394 추가 후 "Translate" 선택
4. 영어 편집 화면이 열리면 제목 입력: **"Inquiry"** (또는 "Contact Us")
5. 슬러그를 **`inquiry`** 로 설정 (WPML이 `/en/` 접두사를 자동 부여 → 최종 URL: `/en/inquiry/`)
6. 본문 주입 (아래 §2 참고)
7. 상태를 **공개(Publish)**로 저장

### 주의
- WPML Translation Editor(자체 UI)로 열릴 경우, "Edit in WordPress" 버튼으로 고전 편집기(Classic Editor) 화면으로 전환해야 WPBakery 모드에서 `[vc_raw_html]` 본문을 직접 삽입 가능.
- WPML > Languages > Language URL Format이 **"언어 코드를 URL에 추가"** 방식(`/en/...`)으로 설정돼 있는지 확인.

---

## 2. 영어 본문(`wp_inquiry_block_en.html`) 주입 방법

### 필요 파일
| 파일 | 경로 |
|---|---|
| 영어 블록 HTML | `3. 웰페리온 가이드/cmo/survey/en/wp_inquiry_block_en.html` (신규 작성 필요) |
| 한국어 원본 | `3. 웰페리온 가이드/cmo/survey/wp_inquiry_block.html` |

### 인코딩 규칙 (WPBakery `vc_raw_html`)
WPBakery는 `[vc_raw_html]` 내 콘텐츠를 `rawurldecode(base64_decode(content))` 순으로 복호화한다.
따라서 주입 시 역순 인코딩이 필요하다.

```python
# scripts/wordpress_admin_playwright.py 내 _wrap_vc_raw_html() 동일 로직
import base64, urllib.parse
enc = urllib.parse.quote(raw_html, safe="")           # rawurlencode
b64 = base64.b64encode(enc.encode("ascii")).decode()  # base64
shortcode = f"[vc_raw_html]{b64}[/vc_raw_html]"
```

### `draft-inquiry` 모드 확장 방법
현재 `draft-inquiry`는 `wp_inquiry_block.html`(한국어)만 읽도록 고정돼 있다 (`INQUIRY_BLOCK_FILE` 상수). 영어 초안 생성에 활용하려면 다음 수정이 필요하다.

```python
# 현재 (wordpress_admin_playwright.py:206)
INQUIRY_BLOCK_FILE = ROOT / "3. 웰페리온 가이드" / "cmo" / "survey" / "wp_inquiry_block.html"

# 확장안: --lang en 인자 추가 후 분기
INQUIRY_BLOCK_FILE_EN = ROOT / "3. 웰페리온 가이드" / "cmo" / "survey" / "en" / "wp_inquiry_block_en.html"
```

그리고 `run_draft_inquiry()` 내 target URL에 `&lang=en` 파라미터를 추가하면 WPML이 영어 컨텍스트 편집 화면을 연다.

```python
target = f"http://wellperion.com/wp/wp-admin/post.php?post={en_post_id}&action=edit&lang=en"
```

---

## 3. 한↔영 Translation Pair 연결 (ENG 버튼 매핑)

WPML은 translation pair(원본↔번역본 ID 쌍)를 내부 테이블(`icl_translations`)에 기록한다.
**"+번역 추가" 흐름(§1)**을 통해 생성하면 pair가 자동 등록된다.

수동으로 연결이 필요한 경우:
1. `WP 관리자 > WPML > Translation Management > All Content`
2. 한국어 페이지 8394 검색 → "Set Translation" → 영어 번역 페이지 ID 입력
3. 저장 후 `/ko/inquiry/` 언어 스위처 클릭 시 `/en/inquiry/`로 이동하는지 브라우저 확인

**ENG 버튼 작동 조건**:
- 한국어 페이지와 영어 페이지가 같은 trid(translation group id)에 등록되어야 함
- Salient 테마 언어 스위처는 현재 페이지의 trid를 기준으로 대응 언어 URL을 생성함

---

## 4. 자동화 가능 범위 vs 수동 필요 범위

### 현재 `wordpress_admin_playwright.py` 역량 요약
| 모드 | 기능 | WPML 지원 |
|---|---|---|
| `setup` | GM 로그인 세션 저장 | 없음 |
| `check` | 세션 유지 확인 | 없음 |
| `inspect` | 테마·플러그인·페이지 목록 읽기 | 없음 |
| `draft-inquiry` | 한국어 문의 초안 생성/갱신 (`wp_inquiry_block.html` 고정) | `&lang=ko` 파라미터만 |
| `publish-inquiry` | 초안 → 공개 발행, 슬러그 설정 | `&lang=ko` 파라미터만 |
| `add-menu` | 한국어 메인 메뉴(id=59)에 페이지 추가 | 없음 |

> **핵심**: WPML translation pair 생성·연결을 처리하는 모드가 없다. 현 스크립트로는 영어 페이지 본문 주입(draft·publish)까지만 자동화 가능하고, translation pair 등록은 수동이다.

### 자동화 가능 (기존 스크립트 소폭 확장)

| 항목 | 방법 | 공수 |
|---|---|---|
| 영어 초안 생성 | `draft-inquiry --lang en --post-id <EN_ID>` 모드 추가 | 소 (인자 추가 + `&lang=en` 파라미터) |
| 영어 페이지 발행 | `publish-inquiry --post-id <EN_ID> --slug inquiry` | 현재도 가능 (slug=inquiry, lang=en URL만 변경) |
| 영어 메뉴 추가 | `add-menu --post-id <EN_ID> --menu-id <EN_MENU_ID>` | 소 (영어 메뉴 ID 파악 후 인자 전달) |

### 수동 필요 (GM 또는 CTO 직접 처리)

| 항목 | 이유 | 담당 |
|---|---|---|
| **Translation pair 생성** | WPML 내부 REST API(/wp-json/wpml/v1) 또는 DB 직접 접근 필요. Playwright DOM 조작만으로 pair 등록 화면 신뢰성 낮음 | GM/CTO |
| **`wp_inquiry_block_en.html` 작성** | 영어 문의 폼 UI 콘텐츠 확정 필요 (버튼 텍스트·안내문구 번역) | CMO/CTO |
| **영어 상단 메뉴 ID 확인** | 현재 스크립트에 영어 메뉴 ID 미정의(`KOREAN_MENU_ID=59`만 존재). inspect 또는 WP Admin > Menus에서 확인 필요 | CTO |
| **WPML 언어 URL 설정 검증** | `/en/` prefix 방식 설정 여부 실측 필요 | CTO |

---

## 5. 권장 실행 순서

```
[사전] wp_inquiry_block_en.html 작성 (CMO)
       ↓
[Step 1] GM 수동: WP Admin > page 8394 편집 > WPML "+" 클릭 → 영어 페이지 신규 생성
         (이 단계에서 translation pair 자동 등록)
       ↓
[Step 2] CTO 확인: 생성된 영어 페이지 ID 메모 (URL의 post=XXXX)
       ↓
[Step 3] CTO 자동화: python scripts\wordpress_admin_playwright.py
           --mode draft-inquiry --post-id <EN_ID> (확장 후)
           또는 수동 본문 주입
       ↓
[Step 4] GM 검수: 미리보기 http://wellperion.com/wp/?page_id=<EN_ID>&preview=true
       ↓
[Step 5] CTO 자동화: python scripts\wordpress_admin_playwright.py
           --mode publish-inquiry --post-id <EN_ID> --slug inquiry
       ↓
[Step 6] CTO 확인: http://wellperion.com/en/inquiry/ 접속 + /ko/inquiry/ ENG 버튼 클릭 매핑 검증
```

---

## 6. 스크립트 신규 작업 필요성 평가

**결론: `wordpress_admin_playwright.py`에 `draft-inquiry-en` 모드 1개 추가 권장.**

| 항목 | 평가 |
|---|---|
| Translation pair 생성 자동화 | 불필요 — §1 "+번역 추가" 수동 1회로 충분하며 pair는 자동 등록됨 |
| 영어 draft/publish 자동화 | 필요 — `INQUIRY_BLOCK_FILE` 고정값과 `&lang=ko` URL 파라미터를 `--lang` 인자로 일반화 |
| 영어 메뉴 추가 자동화 | 필요(선택) — 영어 메뉴 ID를 `inspect`로 파악 후 `--menu-id` 인자로 처리 가능 |
| WPML REST API 직접 호출 | 불필요 — 현 DOM 자동화 수준으로 충분 |
