# 새 #13 M5 등록 + 텔레그램 [승인]카드 — register_publish 1회 호출(수동 경로 send_card=True)
import sys
from pathlib import Path
ROOT = Path(r"C:\Users\jjky0\welperion-automation")
sys.path.insert(0, str(ROOT / "scripts"))
from publish_register import register_publish

FOLDER = ROOT / "instagram" / "namuk.wellperion" / "260613_AI13_문의반응보고방향을정한다"
OUT = FOLDER / "output"
montage = OUT / "_검수_미리보기_6장.png"
slides = [(OUT / f"post_{i}.jpg").relative_to(ROOT).as_posix() for i in range(1, 7)]

CAPTION = (
    "콘텐츠를 감으로 만들지 않아요.\n\n"
    "글을 올리면, 문의가 '어느 글 보고 왔는지'\n"
    "AI가 채널·글별로 한곳에 모아줘요.\n"
    "어떤 글이 문의를 한 장으로 보여요.\n\n"
    "그래서 정하는 법이 바뀌었어요.\n"
    "문의가 붙는 방향은 더 만들고,\n"
    "반응 없는 방향은 미련 없이 접어요.\n"
    "한 번에 맞히는 게 아니라, 반응 보고 방향을 바꾸는 거예요.\n\n"
    "감이 아니라 반응으로 정합니다.\n\n"
    "📌 나중에 따라하려면 저장\n"
    "💬 반응 없는 콘텐츠, 어떻게 하세요? 댓글로 알려주세요\n"
    "👀 이런 AI 활용기 계속 보고 싶으면 팔로우\n\n"
    "#AI #AI활용 #마케팅 #콘텐츠 #데이터 #스포츠클럽 #리더십 #한남동 #웰페리온"
)

register_publish(
    content_folder=FOLDER,
    slug="260613_AI13_문의반응보고방향을정한다",
    montage_path=montage,
    caption=CAPTION,
    location="웰페리온 스포츠클럽",
    mentions=[],
    account="namuk.wellperion",
    slides=slides,
    queue_id="CMO-2026-06-13-AI13-문의반응방향",
    title="AI #13편 — 문의가 들어오게끔 AI가 스스로 수정(개인계정)",
    channel="인스타그램 (namuk.wellperion)",
    send_card=True,
)
