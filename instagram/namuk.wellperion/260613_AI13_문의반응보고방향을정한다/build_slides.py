# 260613 슬라이드 빌드 — 문의 반응을 AI가 모아 보여주고, 되는 방향은 밀고 안 되면 접는다 (AI 시리즈 #13 · namuk.wellperion)
# 텍스트 중심 · main 프리셋 · 정확히 6장 · 렌더 전용(register_publish 미호출 — 웰리 검수 후 별도 등록)
import sys
from pathlib import Path
from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260613_AI13_문의반응보고방향을정한다"
OUT = FOLDER / "output"

SLIDES = [
    dict(  # 1 표지
        kor_title="문의가 들어오게끔\nAI가 스스로 수정해줘요",
        eng_title="What Actually Works",
    ),
    dict(  # 2 문제 — 감으로 올리던 시절
        kor_title="예전엔 감으로\n올렸어요",
        body="인스타든 블로그든 일단 올리고,\n반응이 좋은지 나쁜지도 모른 채\n다음 걸 또 올렸어요.\n잘 된 건지 아닌지, 알 수가 없었죠.",
    ),
    dict(  # 3 어떻게 — AI가 문의를 한곳에 모아줌
        kor_title="이제 문의를\n한곳에서 봐요",
        body="문의가 들어오면 '어느 글 보고 왔는지'\nAI가 채널·글별로 모아줘요.\n대시보드 한 장으로,\n어떤 글이 문의를 부르는지 눈에 보여요.",
    ),
    dict(  # 4 판단 — 되면 밀고 안 되면 접고
        kor_title="되면 밀고\n안 되면 접어요",
        body="문의가 붙는 글은 같은 결로 더 만들고,\n반응 없는 글은 미련 없이 접어요.\n다음 방향을 감이 아니라\n숫자로 정하게 됐어요.",
    ),
    dict(  # 5 통찰 — 한 번에 맞히는 게 아니다
        kor_title="한 번에 맞히려\n안 해요",
        body="처음부터 정답을 못 맞혀도 괜찮아요.\n반응을 보고 방향만 바꾸면 되니까.\n매일 조금씩,\n문의가 들어오는 쪽으로 옮겨갑니다.",
    ),
]


def build_montage(paths, out_path, cols=3):
    thumbs = [Image.open(p).convert("RGB") for p in paths]
    tw, th = thumbs[0].size
    scale = 0.5
    cw, chh = int(tw * scale), int(th * scale)
    gap = 18
    bg = (24, 22, 23)
    rows = (len(thumbs) + cols - 1) // cols
    canvas_w = cols * cw + (cols + 1) * gap
    canvas_h = rows * chh + (rows + 1) * gap
    canvas = Image.new("RGB", (canvas_w, canvas_h), bg)
    for i, t in enumerate(thumbs):
        r, c = divmod(i, cols)
        x = gap + c * (cw + gap)
        y = gap + r * (chh + gap)
        canvas.paste(t.resize((cw, chh), Image.LANCZOS), (x, y))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out_path, "PNG")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("post_*"):
        old.unlink()
    for old in OUT.glob("_검수_미리보기_*.png"):
        old.unlink()

    LOGO_STYLE = "symbol"  # 개인계정 namuk = W 심볼만
    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 6장(마지막) = 편별 마무리 제목(#11+ 자유) + 저장·댓글·팔로우 CTA(2026-06-10 정본). DM·고정슬로건 금지.
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="감이 아니라\n반응으로 정한다",
        body="나중에 따라하려면 저장\n반응 없는 콘텐츠, 어떻게 하세요? 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
    )
    print(f"[OK] {last_out.name} - closing/CTA ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")


if __name__ == "__main__":
    main()
