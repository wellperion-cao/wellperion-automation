# 260616 슬라이드 빌드 — 혼자 쓰던 AI를 직원에게 넘기다 (AI 시리즈 #16 · namuk.wellperion)
# 텍스트 중심(사진 없음) · 브랜드 BLACK 배경 + 베이지 타이포 · main 프리셋
# 기존 발행분과 통일 = 정확히 6장. compose_text_slide(main) SSOT, 디자인 코드 재발명 금지.
# 확정 카드: 로드맵 §5.1 producer-episode-card-16. 시즌2(실전편).
#  앵글: AI는 대표 혼자 쓰는 도구가 아니다 — 직원에게 쥐여주니 직원이 시스템을 함께 키운다.
#  #15(점검 루프 메커니즘)에서 주체를 시스템→사람으로 확장. 실재: 운영부 직원 Claude 교육(진행중)+지원부 점검 앱 이슈→원클릭 매뉴얼 승격(라이브).
#  1 표지(SEASON2 라벨) / 2 왜=나만 쓰면 병목 / 3 어떻게1=매일 하는 일부터·자동집계 / 4 어떻게2=발견 원클릭→모두의 자산 / 5 그래서=함께 키우는 시스템 / 6 마무리·CTA
#  ★현실 가드: '전 직원이 AI로 ERP를 만든다'는 과장 금지(운영부 교육 시작 단계). '코딩으로 만든다'가 아니라 '쓰면서 키운다'. 안 한 기능 지어내기 금지.
# 톤: 개인계정 GM 1인칭, 조직을 이끄는 리더. how-to. 광고 아님. 전문용어 금지. 초등학생 눈높이.
# 로고: W 심볼만(logo_style="symbol", 개인계정 규칙). CTA: 저장·댓글·팔로우 정본(2026-06-10 GM 개정).
# 실행: .venv\Scripts\python instagram\namuk.wellperion\260616_AI16_AI를직원에게\build_slides.py
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from slide_compositor import compose_text_slide  # noqa: E402
from publish_register import register_publish  # noqa: E402

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260616_AI16_AI를직원에게"
OUT = FOLDER / "output"

# 시즌2(실전편) 공통 라벨 — 표지 eng_sub 자리 텍스트 (로드맵 §2.6 단일출처)
SEASON2_LABEL = "SEASON 2 · 실전편"

# 제작완료 자동 등록용 메타
QUEUE_ID = "CMO-2026-06-16-AI16-AI를직원에게"
QUEUE_TITLE = "AI #16편 — 혼자 쓰던 AI를 직원에게 넘기다(개인계정)"
QUEUE_CHANNEL = "인스타그램 (namuk.wellperion)"
ACCOUNT = "namuk.wellperion"
LOCATION = "웰페리온 스포츠클럽"
MENTIONS = []  # 기본 없음. 실제 협업 상대가 있는 편에만 그때 지정

CAPTION = (
    "오늘은 'AI를 직원에게 넘긴' 이야기예요.\n\n"
    "저는 한동안 AI를 저 혼자 썼어요.\n"
    "근데 그러니까 결국 모든 게 제 손을 거치더라고요. 제가 병목이었어요.\n\n"
    "그래서 운영부 직원들에게 먼저 AI 쓰는 법을 알려줬어요. 딱 30분이요.\n\n"
    "거창하게 시작 안 했어요. 매일 하는 일부터요.\n"
    "직원이 폰으로 점검을 체크하면 결과가 자동으로 모여요.\n"
    "점검하다 문제를 발견하면 버튼 하나, 다음부터 그 항목이 모두의 점검표에 떠요.\n\n"
    "한 사람의 발견이 회사 전체의 자산이 되는 거예요.\n"
    "시스템은 제가 다 만든 게 아니라, 쓰는 사람이 함께 키우는 거였어요.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 직원에게 가장 먼저 쥐여줄 AI 작업은 뭔가요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #실전편 #스포츠클럽 #리더십 #조직운영 #한남동 #웰페리온"
)

# compose_text_slide 분기: eng_title 있으면 표지(라벨 대제목 + 한글 부제), 없으면 본문(kor_title 헤딩 + body)
# 정확히 6장 — 표지(1) + 왜(2) + 어떻게1(3) + 어떻게2·핵심(4) + 그래서(5) + 마무리/CTA(6, main() 별도)
# 표지 eng_title 자리에 SEASON2_LABEL 텍스트만(별도 그래픽 뱃지 합성 없음). 시즌2 전 편 공통.
SLIDES = [
    dict(  # 1장 표지 (시즌2 라벨 + 한글 제목)
        kor_title="혼자 쓰던 AI를\n직원에게 넘겼다",
        eng_title=SEASON2_LABEL,
    ),
    dict(  # 2장 왜 = 나만 쓰면 병목은 나
        kor_title="AI를 나만 쓰면\n병목은 나예요",
        body="혼자 쓰니 결국\n모든 게 제 손을 거쳤어요.\n직원이 쓰면 회사가 커요.\n그래서 운영부 직원들에게\n먼저 30분, 쓰는 법을 알려줬어요.",
    ),
    dict(  # 3장 어떻게1 = 매일 하는 일부터 · 자동집계
        kor_title="거창하게\n시작 안 했어요",
        body="매일 하는 일부터요.\n직원이 폰으로 점검을 체크하면\n결과가 자동으로 모여요.\n따로 취합 안 해요.",
    ),
    dict(  # 4장 어떻게2 핵심 = 발견 원클릭 → 모두의 자산
        kor_title="발견 하나가\n모두의 자산이 돼요",
        body="점검하다 문제를 찾으면\n버튼 하나 누르면 끝.\n다음 점검부터 그 항목이\n모두의 표에 떠요.\n한 사람의 발견이 회사 전체 것이 돼요.",
    ),
    dict(  # 5장 그래서 = 함께 키우는 시스템
        kor_title="만드는 게 아니라\n함께 키워요",
        body="시스템은 제가 다 만든 게 아니에요.\n쓰는 사람이 키워요.\nAI는 그걸 모아 정리해줄 뿐.\n운영부부터 시작해\n넓혀가는 중이에요.",
    ),
]


def build_montage(paths: list[Path], out_path: Path, cols: int = 3) -> None:
    """전체 슬라이드를 1장으로 합성한 검수 미리보기 (cols x rows 그리드)."""
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


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    # 구 산출물 폐기 (버전업 시 이전 데이터 폐기 원칙)
    for old in OUT.glob("post_*"):
        old.unlink()
    for old in OUT.glob("_검수_미리보기_*.png"):
        old.unlink()

    # 개인계정(namuk.wellperion) = 'W' 심볼만 미니멀 로고 (2026-06-02 GM 결정)
    # 풀 로고 금지.
    LOGO_STYLE = "symbol"

    paths = []
    for i, slide in enumerate(SLIDES, start=1):
        out = OUT / f"post_{i}.jpg"
        r = compose_text_slide(output=out, brand_key="main", logo_style=LOGO_STYLE, **slide)
        paths.append(out)
        print(f"[OK] {out.name} - {r['layout']} ({r['size_kb']}KB)")

    # 마지막 장 = 편별 마무리 제목(#11+ 실전 노선) + 저장·댓글·팔로우 CTA 정본(2026-06-10 GM 개정)
    last_out = OUT / f"post_{len(SLIDES) + 1}.jpg"
    r = compose_text_slide(
        output=last_out,
        brand_key="main",
        logo_style=LOGO_STYLE,
        kor_title="시스템은 만드는 게 아니라\n함께 키우는 것",
        body="나중에 따라하려면 저장\n직원에게 가장 먼저 쥐여줄 AI 작업은 뭔가요 댓글로 알려주세요\n이런 AI 활용기 계속 보고 싶으면 팔로우",
    )
    print(f"[OK] {last_out.name} - signature/CTA card ({r['size_kb']}KB)")
    paths.append(last_out)

    montage = OUT / f"_검수_미리보기_{len(paths)}장.png"
    build_montage(paths, montage, cols=3)
    print(f"\n총 {len(paths)}장 생성 + 미리보기 → {montage}")

    # 제작완료 = 자동 등록(M5 upsert) + 텔레그램(1줄+montage) 발송.
    slides_rel = [p.relative_to(ROOT).as_posix() for p in paths]
    register_publish(
        content_folder=FOLDER,
        slug="260616_AI16_AI를직원에게",
        montage_path=montage,
        caption=CAPTION,
        location=LOCATION,
        mentions=MENTIONS,
        account=ACCOUNT,
        slides=slides_rel,
        queue_id=QUEUE_ID,
        title=QUEUE_TITLE,
        channel=QUEUE_CHANNEL,
    )


if __name__ == "__main__":
    main()
