# 북극성 추천 카드 샘플 (드라이런 · 실발송 아님)
생성: 2026-07-07 16:12:45 · 두뇌=ClaudeCLI · 대상=ceo/cmo/coo/cto/cpo
발효 게이트: 텔레그램 send·cron·봇 재기동 전부 금지 — GM go 별건.

## 카드 본문(텔레그램 HTML parse_mode)
```
🧭 <b>웰리의 오늘의 북극성 한 수</b>
📅 2026-07-07 (화)  ·  웰리 추천 1건

📦 <b>통합 회원 관리</b> <i>(시포)</i> · <a href="https://wellperion-cao.github.io/wellperion-automation/cpo/member/%EB%AC%B8%EC%9D%98%ED%9A%8C%EC%9B%90.html">대표 페이지</a>
   🎯 통합 회원 관리 → 🌟 문의→체험→가입 전환 퍼널 가시화 · 회원 라이프사이클 관리
<b>문의→응대 17.8% 대낙폭 구간 진단·개통 — 신규문의 진행상태 기록 독려 배선(최대 퍼널 누수점)</b> ⛴️여객선
     👉 첫 행동: 26년신규문의 시트에서 &#x27;응대 진행상태 미기록&#x27; 신규문의 건을 집계해 낙폭이 실누수인지 기록누락인지 1차 분리한다
     📈 예상 효과: 문의→응대 낙폭(현 17.8%)의 원인 규명 + 진행상태 입력 완료율 상승 배선 1개(응대 미입력 건 자동 리마인더/독려), 퍼널 가시화 SSOT의 최대 구멍 1개 봉합
     ★ 왜 1순위: 퍼널 최대 누수점이면서 담당(시포) active 0으로 여력이 있고 active 중복이 없어, 오늘 착수 시 전사 전환율에 가장 큰 상류 레버가 된다

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
