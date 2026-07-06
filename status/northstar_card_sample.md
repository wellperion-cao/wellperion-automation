# 북극성 추천 카드 샘플 (드라이런 · 실발송 아님)
생성: 2026-07-06 15:49:56 · 두뇌=ClaudeCLI · 대상=ceo/cmo/coo/cto/cpo
발효 게이트: 텔레그램 send·cron·봇 재기동 전부 금지 — GM go 별건.

## 카드 본문(텔레그램 HTML parse_mode)
```
🧭 <b>웰리의 오늘의 북극성 한 수</b>
📅 2026-07-06 (월)  ·  웰리 추천 1건

📦 <b>M2 대시보드</b> <i>(시모)</i> · <a href="https://wellperion-cao.github.io/wellperion-automation/wellperion_guide(main).html#M2">대표 페이지</a>
   🎯 채널별 문의·클릭·전환 집계 · 문의흐름지도 · 월간보고서(월 선택) → 🌟 노출 → 회원 전환 엔진 완성 (무인 자동화 + 전환율 목표)
<b>측정 개통 후 첫 산출물 — &#x27;어느 채널이 실제 문의를 만드나&#x27; 채널별 전환 리포트 1장</b> ⛴️여객선
     👉 첫 행동: 채널별 클릭수(직접526·카페43·IG25·블로그18·당근2) + 문의 UTM 귀속 데이터를 조인해 &#x27;클릭→문의 전환율&#x27; 채널별 표 1장 생성
     📈 예상 효과: 채널별 클릭→문의 전환율 리포트 1장(예: 카페 X%·IG Y%) → 다음 콘텐츠 예산·소재를 실측으로 배분하는 첫 근거
     ★ 왜 1순위: 측정만 켜놓고 인사이트를 안 뽑으면 전환 엔진 북극성이 반쪽 — 지금 데이터가 살아있는 이 순간 첫 채널별 전환 1장이 회사 성장(문의 유입) 레버를 실측으로 돌리는 가장 높은 한 수

👉 아래 버튼으로 승인하세요 — 승인 시 그 배가 G1 큐(_queue)에 등록·즉시 착수.
📊 표로 자세히: https://wellperion-cao.github.io/wellperion-automation/%EC%9E%90%EC%9C%A8%ED%98%84%ED%99%A9.html
```

## 인라인 버튼 레이아웃(reply_markup)
```json
{
  "inline_keyboard": [
    [
      {
        "text": "✅ 승인",
        "callback_data": "ns:0:approve"
      }
    ],
    [
      {
        "text": "⚓ 보류",
        "callback_data": "ns:hold"
      }
    ]
  ]
}
```
