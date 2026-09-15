# -*- coding: utf-8 -*-
"""결재 완료 건의 결과보고서 A4 한 장을 만든다 (GM 지시 2026-09-15).

GM 원문: "결재완료 알림 담당자가 운영부방에 있으면 이경연실장이 전달 꼭 해주는걸로, 담당자가
전달 받았는지도 확인해서 진행 후 결과보고서까지 만들어서 SSOT 할 수 있도록 해줘. 결과보고서는
사진이나 최종금액·들어간 시간 등을 정리 + 웰리 의견" · "결재 SSOT 는 항상 A4 사이즈로 인쇄해,
대표님 결재받은 것들 보면 기준이 보일 것".

양식 기준 — 결재 현황 SSOT.html 이 인쇄하는 결재 문서(.rr-page · buildApprovalPrint 870줄)와 같다.
  WELLPERION 워드마크 머리 · @page A4 세로 · rr-info-table / rr-section-title / rr-section-body.
  다른 것 하나 — 결재란(도장칸)·서명칸을 넣지 않는다. 이 문서는 결재를 받는 서류가 아니라
  이미 끝난 결재의 결과를 적는 서류다.

SSOT 등록은 사람이 한다 — AI 는 이 링크를 방에 드릴 뿐, 결재 SSOT 행을 만들거나 상태를 바꾸지
  않는다(GM 상시 규칙 2026-08-18). 문서 맨 아래 안내 줄이 담당자에게 그 절차를 알려 준다.

쓰는 법
    python scripts/approval_result_report.py --todo-id TODO-123 \
        --photo "C:/사진/앞.jpg" --photo "https://.../뒤.jpg" \
        --final-amount 1450000 --done-at "2026-09-15 16:30" --hours 6 \
        --opinion "승인가보다 5만원 낮게 끝났다. 같은 업체로 다음 건도 묶으면 더 줄어든다."

출력: `3. 웰페리온 가이드/coo/todo/results/<todo_id>_결과보고서.html` 한 파일.
      성공 시 stdout 에 `REPORT: <절대경로>` + exit 0 / 실패 시 `FAILED: <이유>` + exit 1.
"""
from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

OUT_DIR = REPO_ROOT / "3. 웰페리온 가이드" / "coo" / "todo" / "results"
# 내용 칸의 예산 절 — 결재 화면 parseContent 와 같은 규약("===BUDGET===\n항목 | 금액").
_BUDGET_RE = re.compile(r"===BUDGET===\s*\n\s*(.+?)\s*\|\s*(\d+)")
_CAT_RE = re.compile(r"^\[\d+\]\s*")
_MID = ("이경연 실장", "이정헌 소장", "나우열M")


def esc(v) -> str:
    return html.escape(str(v or ""), quote=True)


def won(n) -> str:
    try:
        return f"{int(n):,} 원"
    except (TypeError, ValueError):
        return "-"


def fetch_row(todo_id: str) -> dict | None:
    """업무&결재 SSOT 에서 그 행 하나. 조회 자리는 rep_approval_relay.fetch_rows 하나를 쓴다."""
    from rep_approval_relay import fetch_rows
    rows = fetch_rows()
    if rows is None:
        return None
    return next((r for r in rows if str(r.get("id") or "").strip() == todo_id.strip()), {})


def kst_minute(v) -> str:
    """시트 시각값 → KST 'YYYY-MM-DD HH:MM'. ISO Z(UTC)는 +9h, 그 밖('2026-09-15 14:02:11 (페이지)')은 앞 16자.
    rep_approval_relay._kst_day 와 같은 규약인데 사람이 읽는 종이라 분까지 남긴다."""
    s = str(v or "").strip()
    if "T" in s and s.endswith("Z"):
        from datetime import datetime, timedelta
        try:
            return (datetime.strptime(s[:19], "%Y-%m-%dT%H:%M:%S") + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return s.replace("T", " ")[:16]


def approved_amount(row: dict) -> int | None:
    m = _BUDGET_RE.search(str(row.get("내용") or ""))
    return int(m.group(2)) if m else None


def approval_route(row: dict) -> str:
    """결재선 한 줄 — 화면 buildEffectiveRoute 와 같은 규칙((명시 부서장) → GM), 대표 서명본이
    있으면 전응준 대표까지. 서명된 단계엔 시각을 붙인다(빈 단계를 지어내지 않는다)."""
    manual = [s.strip() for s in str(row.get("결재요청") or "").split(",") if s.strip()]
    steps = []
    mid = next((m for m in manual if m in _MID), "")
    if mid and "김남욱GM" not in str(row.get("담당자") or ""):
        steps.append((mid, str(row.get("부서장싸인") or "").strip()))
    steps.append(("김남욱 GM", str(row.get("GM싸인") or "").strip()))
    rep = str(row.get("대표싸인") or "").strip()
    if rep and rep.upper() != "PENDING":
        steps.append(("전응준 대표", rep if not rep.startswith("http") else "서명본 수령"))
    return " → ".join(f"{n} ({kst_minute(s)})" if s and s != "서명본 수령" else
                      (f"{n} (서명본 수령)" if s else f"{n} (미서명)") for n, s in steps)


def photo_html(src: str) -> str:
    """로컬 파일은 문서 안에 담고(data URI — 링크가 끊겨도 보고서가 살아 있다), 주소는 그대로 건다.
    주소 이미지가 안 열리면 링크로 떨어진다(결재 인쇄 buildAttachmentHtml 과 같은 폴백)."""
    if src.startswith(("http://", "https://")):
        return ('<div class="rr-attach"><img class="rr-attach-img" src="%s" alt="진행 사진" '
                'onerror="this.style.display=\'none\';this.nextElementSibling.style.display=\'block\'">'
                '<a class="rr-attach-link" href="%s" style="display:none">%s</a></div>'
                % (esc(src), esc(src), esc(src)))
    p = Path(src)
    if not p.is_file():
        return '<div class="rr-attach rr-miss">사진 없음 — %s</div>' % esc(src)
    mime = mimetypes.guess_type(p.name)[0] or "image/jpeg"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return ('<div class="rr-attach"><img class="rr-attach-img" src="data:%s;base64,%s" alt="진행 사진">'
            '<div class="rr-attach-cap">%s</div></div>' % (mime, b64, esc(p.name)))


def build_html(row: dict, a: argparse.Namespace) -> str:
    approved = approved_amount(row)
    final = a.final_amount
    if approved is not None and final is not None:
        gap = final - approved
        gap_txt = ("승인가와 같음" if gap == 0 else
                   f"승인가보다 {won(abs(gap))} {'더 씀' if gap > 0 else '덜 씀'}")
        amount_rows = [("승인 금액", won(approved)), ("최종 금액", won(final)), ("차이", gap_txt)]
    elif final is not None:
        amount_rows = [("승인 금액", "결재 행에 예산 절 없음"), ("최종 금액", won(final))]
    else:
        amount_rows = []

    summary = [
        ("결재 제목", esc(row.get("업무명") or "(제목 없음)")),
        ("카테고리", esc(_CAT_RE.sub("", str(row.get("카테고리") or "")) or "-")),
        ("담당", esc(row.get("담당자") or "-")),
        ("결재선", esc(approval_route(row))),
        ("결재 완료", esc(kst_minute(row.get("결재완료시각") or row.get("GM싸인")) or "-")),
    ]
    done = [("완료 시각", esc(a.done_at or "-")), ("담당", esc(row.get("담당자") or "-"))]
    if a.hours:
        done.append(("투입 시간", esc(f"{a.hours} 시간")))

    def table(pairs):
        return ('<table class="rr-info-table">'
                + "".join(f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in pairs)
                + "</table>")

    photos = "".join(photo_html(s) for s in (a.photo or []))
    parts = [
        '<div class="rr-section-title">결재 요약</div>', table(summary),
        '<div class="rr-section-title">진행 결과</div>',
        (photos or '<div class="rr-section-body">사진 없음</div>'),
    ]
    if amount_rows:
        parts += ['<div class="rr-section-title">최종 금액</div>', table(amount_rows)]
    parts += ['<div class="rr-section-title">완료</div>', table(done)]
    if a.opinion:
        parts += ['<div class="rr-section-title">웰리 의견</div>',
                  f'<div class="rr-result-box">{esc(a.opinion)}</div>']
    parts.append('<div class="rr-note">이 문서를 결재 SSOT 에 남기려면 — 담당자께서 결재 현황 SSOT '
                 '해당 행의 <b>내용</b> 칸에 이 보고서 링크를 붙여 주세요. (AI 는 남의 SSOT 행을 '
                 '만들거나 고치지 않습니다)</div>')

    return _PAGE % {
        "title": esc(row.get("업무명") or a.todo_id),
        "todo_id": esc(a.todo_id),
        "body": "\n".join(parts),
        "today": esc(a.done_at[:10] if a.done_at else ""),
    }


# 스타일은 결재 현황 SSOT.html 인쇄(#approvalPrintArea .rr-*)와 같은 값이다 — 같은 종이로 보이게.
_PAGE = """<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<title>결과보고서 — %(title)s</title>
<style>
  @page{margin:12mm;size:A4 portrait}
  body{margin:0;background:#e9e9e9;font-family:"Malgun Gothic",sans-serif;color:#111}
  .bar{padding:10px 14px;background:#fff;border-bottom:1px solid #ccc;display:flex;gap:8px;align-items:center}
  .bar button{font:inherit;font-size:13px;font-weight:700;padding:6px 14px;border-radius:7px;border:1px solid #0b8043;background:#0b8043;color:#fff;cursor:pointer}
  .bar .ghost{background:#fff;color:#0b8043}
  .rr-page{width:186mm;min-height:257mm;margin:16px auto;padding:12mm;background:#fff;box-shadow:0 2px 12px rgba(0,0,0,.15);font-size:15px;line-height:1.6}
  .rr-header{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:14px;padding-bottom:10px;border-bottom:2px solid #111}
  .rr-wordmark{font-size:17px;font-weight:900;letter-spacing:.18em;text-transform:uppercase}
  .rr-wordmark small{display:block;font-size:10px;font-weight:600;letter-spacing:.12em;color:#666;margin-top:2px}
  .rr-doc-title{text-align:center;font-size:20px;font-weight:900;letter-spacing:.08em;margin:10px 0 14px}
  .rr-info-table{width:100%%;border-collapse:collapse;margin-bottom:12px;font-size:14px}
  .rr-info-table th{background:#f0f0f0;border:1px solid #bbb;padding:4px 8px;font-weight:700;text-align:left;width:22%%;white-space:nowrap;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  .rr-info-table td{border:1px solid #bbb;padding:4px 8px}
  .rr-section-title{font-size:15px;font-weight:700;border-left:3px solid #111;padding-left:6px;margin:14px 0 6px}
  .rr-section-body{font-size:14px;white-space:pre-wrap;word-break:break-word;padding:8px;border:1px solid #ddd;background:#fafafa;line-height:1.7}
  .rr-result-box{font-size:14px;white-space:pre-wrap;word-break:break-word;padding:8px 10px;border:2px solid #111;background:#f5f5f5;line-height:1.7}
  .rr-attach{page-break-inside:avoid;margin:6px 0}
  .rr-attach-img{display:block;max-width:100%%;max-height:360px;object-fit:contain;border:1px solid #bbb}
  .rr-attach-cap{font-size:12px;color:#666;margin-top:2px}
  .rr-attach-link{font-size:13px;word-break:break-all}
  .rr-miss{font-size:13px;color:#b00}
  .rr-note{margin-top:14px;padding:8px 10px;border:1px dashed #888;background:#fbfbf6;font-size:13px}
  .rr-footer{margin-top:12px;padding-top:6px;border-top:1px solid #bbb;display:flex;justify-content:space-between;font-size:12px;color:#666}
  @media print{body{background:#fff}.bar{display:none}.rr-page{width:auto;min-height:0;margin:0;padding:0;box-shadow:none}}
</style></head><body>
<div class="bar">
  <button onclick="window.print()">A4 인쇄</button>
  <button class="ghost" id="png">PNG 다운로드</button>
  <span style="font-size:12px;color:#666">업무 id %(todo_id)s</span>
</div>
<div class="rr-page" id="sheet">
  <div class="rr-header"><div class="rr-wordmark">WELLPERION<small>결과 보고</small></div></div>
  <div class="rr-doc-title">결 과 보 고 서</div>
%(body)s
  <div class="rr-footer"><span>A Day, Well Completed.</span><span>발행일: %(today)s</span></div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<script>
document.getElementById('png').onclick = function () {
  var btn = this;
  if (typeof html2canvas !== 'function') {
    alert('PNG 변환 기능을 불러오지 못했습니다(인터넷 연결 확인).\\n대신 [A4 인쇄] 에서 「PDF로 저장」을 쓰세요.');
    return;
  }
  btn.disabled = true; btn.textContent = '변환 중...';
  html2canvas(document.getElementById('sheet'), { scale: 2, backgroundColor: '#ffffff' })
    .then(function (cv) {
      var a = document.createElement('a');
      a.href = cv.toDataURL('image/png');
      a.download = '%(todo_id)s_결과보고서.png';
      a.click();
    })
    .catch(function () { alert('PNG 변환에 실패했습니다. [A4 인쇄] → 「PDF로 저장」을 쓰세요.'); })
    .finally(function () { btn.textContent = 'PNG 다운로드'; btn.disabled = false; });
};
</script>
</body></html>
"""


def _selfcheck() -> None:
    """금액 차이·결재선·예산 파싱 — 네트워크 없이."""
    row = {"id": "T-1", "업무명": "수영장 타일 보수", "담당자": "이정헌 소장", "카테고리": "[5] 시설",
           "결재요청": "이정헌 소장,GM", "부서장싸인": "2026-09-10 09:00:00 (페이지)",
           "GM싸인": "2026-09-11 10:20:00 (페이지)", "대표싸인": "", "결재완료시각": "2026-09-11 10:20:00",
           "내용": "본문\n===BUDGET===\n소액 유지보수 | 1500000"}
    assert approved_amount(row) == 1500000
    assert approved_amount({"내용": "예산 없음"}) is None
    assert approval_route(row) == ("이정헌 소장 (2026-09-10 09:00) → 김남욱 GM (2026-09-11 10:20)"), approval_route(row)
    assert kst_minute("2026-09-15T05:02:31.000Z") == "2026-09-15 14:02", kst_minute("2026-09-15T05:02:31.000Z")
    assert kst_minute("2026-09-15 14:02:11 (페이지)") == "2026-09-15 14:02"
    assert kst_minute("") == ""
    a = argparse.Namespace(todo_id="T-1", photo=[], final_amount=1450000,
                           done_at="2026-09-15 16:30", hours=6, opinion="승인가보다 덜 썼다")
    h = build_html(row, a)
    assert "1,450,000 원" in h and "50,000 원 덜 씀" in h, "차이 계산"
    assert "결재란" not in h and "(인)" not in h, "결과보고서에 결재란·서명칸은 없다"
    assert "결재 SSOT" in h and "size:A4 portrait" in h
    a.final_amount = 1600000
    assert "100,000 원 더 씀" in build_html(row, a)
    a.final_amount = None
    assert "최종 금액" not in build_html(row, a), "금액이 없으면 금액 절을 안 만든다"
    print("[selfcheck] approval_result_report OK")


def main() -> int:
    ap = argparse.ArgumentParser(description="결재 완료 건 → 결과보고서 A4 (GM 지시 2026-09-15)")
    ap.add_argument("--todo-id", help="업무&결재 SSOT 의 id")
    ap.add_argument("--photo", action="append", default=[], help="진행 사진(로컬 경로 또는 주소) — 여러 번")
    ap.add_argument("--final-amount", type=int, help="최종 금액(원)")
    ap.add_argument("--done-at", default="", help='완료 시각 "YYYY-MM-DD HH:MM"')
    ap.add_argument("--hours", help="투입 시간(선택)")
    ap.add_argument("--opinion", default="", help="웰리 의견")
    ap.add_argument("--selfcheck", action="store_true")
    a = ap.parse_args()
    if a.selfcheck:
        _selfcheck()
        return 0
    if not a.todo_id:
        print("FAILED: --todo-id 가 필요합니다")
        return 1
    row = fetch_row(a.todo_id)
    if row is None:
        print("FAILED: 업무 시트 조회 실패 — 만들지 않았습니다")
        return 1
    if not row:
        print(f"FAILED: id {a.todo_id} 인 행이 없습니다")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{a.todo_id}_결과보고서.html"
    out.write_text(build_html(row, a), encoding="utf-8")
    print(f"REPORT: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
