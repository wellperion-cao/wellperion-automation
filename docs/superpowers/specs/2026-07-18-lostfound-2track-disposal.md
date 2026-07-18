# 습득물 처분 2트랙 정합 (유실물법) — Stage 2 시스템 정렬

> COO 시우 · 2026-07-18 · GM 승인(절충 2트랙 + A안 월사이클 유지)
> 선행: 가이드 페이지 `lost_found_guide.html` 발행 완료(bd707d8b). 본 스펙 = 가이드와 시스템 일치.

## 배경
GM 유실물법 규정 2문서 ↔ 라이브 시스템 충돌. 현 `_lfAutoDispose_`는 **전 물품을 습득월+2에 일괄 폐기** = 일반·고가품 임의폐기(횡령 소지). GM 결정: 월 사이클(수집→공지→처분) 유지, **처분 단계만 물품별 분기**.

## 처분 모델 (습득월 M → M+1 공지 → M+2 처분)
| 물품구분 | 처분월(M+2) 동작 | 상태 |
|---|---|---|
| 🟢 소모품(consumable) | **자동 폐기** (현행 유지, 소모품 한정) | 폐기물(DISPOSED) |
| 🟡 일반품(general) | **폐기 안 함 → 경찰 제출 대상 자동 표시** | 경찰인계(POLICE) |
| 🔴 고가·중요품(valuable) | 즉시 별도보관(접수 안내) + 처분월 경찰 제출 대상 | 경찰인계(POLICE) |

## 변경 (백엔드 = `.deploy-voc/VOC_배포.js` 라이브 정본 + 가이드 사본 `coo/voc/apps_script_voc.js` 동기)
1. **데이터 모델**: `LF_HEADERS` 맨 끝에 `category:'물품구분'` append(positional write 제약 — 중간삽입 금지). `_lfGetSheet_` 헤더 자가치유가 빈칸 보강.
2. **상태**: `LF_STATUS`에 `POLICE:'경찰인계'` 추가(기존 POSTED/HANDED/DISPOSED 유지). 처분일 기록 재사용=`disposedAt`(라벨 유지, 경찰인계도 처분일로 기록) 또는 신규 `processedAt` 검토 → **disposedAt 재사용**(컬럼 최소화, 의미=처분일).
3. **sweep 분기** (`_lfAutoDispose_`, 습득월+2 도래 시):
   - `category==='consumable'` → 폐기물(DISPOSED)·disposedAt (현행)
   - `category` in (general/valuable) 또는 **미분류(빈값)** → 경찰인계(POLICE)·disposedAt(=처분일). **폐기 아님.**
   - ★안전 기본값: 카테고리 빈값=경찰인계 트랙(자동폐기 안 함) → 기존 데이터 임의폐기 위험 즉시 제거.
4. **lf_submit**: payload `category` 접수·저장. 없으면 'general' 기본.
5. **lf_disposal / lf_gallery**: 응답에 category 포함. 처분예정·처분완료 산출 시 트랙(폐기/경찰) 구분 필드 제공.

## 프론트 (GitHub Pages = 커밋 즉시 라이브 · WP주입본 2종 재주입)
- `lost_found_register.html`(+`wp_lost_found_register_block.html`): 물품 구분 **select 추가**(소모품/일반/고가·중요, 기본 일반) + payload `category`. stale "30일 자동폐기" 정책문구 → 월사이클+2트랙으로 교체. 고가·중요=즉시 별도보관 안내.
- `lost_found_gallery.html`(+`wp_lost_found_gallery_block.html`): 카드에 물품구분 배지(🟢/🟡/🔴). 임박배지 "⏳ M월 **처분**예정"(폐기→처분 표현). 처분완료 기록에 폐기/경찰인계 구분.
- `lost_found_disposal.html`(Pages 단독): 처분예정을 **폐기(소모품)/경찰제출(일반·고가)** 로 나눠 표시. 처분완료도 구분. A3 인쇄 유지.

## 배포·검증
- GAS: `.deploy-voc`에서 clasp push+deploy(in-place, /exec 유지) — 수동 재배포(clasp≠웹앱배포). 배포 전 백업.
- WP 재주입: register·gallery 2블록 `wordpress_admin_playwright.py` draft-page 주입(발행유지·즉시라이브).
- 검증: ①GAS 테스트 접수(각 카테고리)→sweep 시뮬(월인덱스)→상태 정확 ②Pages 3p 시크릿크롬 콘솔0 ③WP 2p 라이브 마커. 회귀=기존 게시중·수령완료 무손상.
- ★기존 데이터: 카테고리 빈값=경찰인계 트랙 → **자동폐기 즉시 중단**(위험 제거). 소모품(우산 등)은 직원이 소모품 지정 시 폐기 재개.

## 후속(비목표·명시)
- 경찰 '제출완료' 별도 상태(현 MVP=경찰인계 표시까지). 카테고리 일괄 재분류 UI. 알림 연동.
