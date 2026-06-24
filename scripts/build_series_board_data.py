"""AI 시리즈 보드 데이터 빌더 — 로드맵.md(정본) → series_data.json(파생 미러).

정본 = instagram/_AI시리즈_로드맵.md (사람이 손대는 단 하나의 출처).
파생 = 3. 웰페리온 가이드/cmo/series/series_data.json (이 스크립트만 갱신, 사람 손 금지).
이유 = 라이브(GitHub Pages) 루트가 '3. 웰페리온 가이드/'라 instagram/ 의 .md 는 404 →
       가이드허브 아래에서 fetch 가능한 JSON 으로 미러링해야 보드가 읽을 수 있다.

★ 파싱은 ig_series_producer.py 의 검증된 파서를 그대로 재사용 → producer 가 읽는 것과
   보드가 보여주는 것이 100% 동일(정합 보장, 복사 발산 차단 — INC-001 철학).

M5 검수/발행 상태는 보드가 review_queue.json 을 라이브로 직접 읽어 병합한다(여기서 안 굳힘).

실행: .venv\\Scripts\\python scripts\\build_series_board_data.py
"""
import importlib.util
import io
import json
import re
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
OUT = ROOT / "3. 웰페리온 가이드" / "cmo" / "series" / "series_data.json"

# producer 모듈 로드(검증된 파서 재사용)
_spec = importlib.util.spec_from_file_location("_p", ROOT / "scripts" / "ig_series_producer.py")
_p = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_p)


def _extract_route(text: str) -> str:
    """§1 표의 '노선' 행 값을 추출(없으면 빈 문자열)."""
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] == "노선":
            return cells[1]
    return ""


def _extract_principles(text: str) -> list[dict]:
    """§2.5 글쓰기·소재 2원칙(| 원칙 | 내용 |) 행 추출."""
    out: list[dict] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) == 2 and cells[0] in ("글 간결·핵심만", "현실 반영(실제 작업)"):
            out.append({"name": cells[0], "detail": cells[1]})
    return out


def _slides_from_card(card: dict) -> list[dict]:
    """카드 dict 의 SLIDE_* 키를 장 순서대로 정렬한 리스트로."""
    keys = [k for k in card if k.startswith("SLIDE_")]

    def _no(k: str) -> int:
        m = re.search(r"SLIDE_(\d+)", k)
        return int(m.group(1)) if m else 99

    keys.sort(key=_no)
    slides = []
    for k in keys:
        label = k.replace("SLIDE_", "").replace("_", " ").strip()
        slides.append({"label": label, "text": card[k]})
    return slides


def main() -> None:
    text = _p.ROADMAP.read_text(encoding="utf-8")
    episodes_raw = _p.parse_roadmap_episodes(text)
    cards_raw = _p.parse_episode_cards(text)
    cfg = _p.parse_season_config(text)

    episodes = []
    for e in episodes_raw:
        episodes.append(
            {
                "num": e["num"],
                "num_raw": e["num_raw"],
                "date": e["date"],
                "title": e["title"],
                "message": e["message"],
                "roadmap_status": e["status"],
                "has_card": e["num"] in cards_raw,
            }
        )

    cards = {}
    for num, c in cards_raw.items():
        cards[str(num)] = {
            "hook": c.get("HOOK", ""),
            "connect_prev": c.get("CONNECT_PREV", ""),
            "connect_next": c.get("CONNECT_NEXT", ""),
            "slides": _slides_from_card(c),
            "question": c.get("QUESTION", ""),
            "reality_guard": c.get("REALITY_GUARD", ""),
        }

    data = {
        "_doc": "AI 시리즈 보드 파생 데이터 — 정본=instagram/_AI시리즈_로드맵.md. 이 파일은 build_series_board_data.py 자동생성, 사람 손대지 말 것.",
        "source": "instagram/_AI시리즈_로드맵.md",
        "season_label": cfg.get("SEASON2_LABEL", ""),
        "route": _extract_route(text),
        "principles": _extract_principles(text),
        "episodes": episodes,
        "cards": cards,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(data, io.open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[OK] series_data.json 생성 — 편 {len(episodes)}개, 카드 {len(cards)}개 → {OUT}")
    print(f"     노선={'있음' if data['route'] else '없음'} / 원칙 {len(data['principles'])}개 / 시즌라벨={data['season_label']!r}")


if __name__ == "__main__":
    main()
