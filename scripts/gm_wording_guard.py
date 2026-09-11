#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GM 화면에 내부 낱말이 나가는지 턴 끝에 잡는다 (GM 지시 2026-09-09 · Stop 훅).

GM 원문: "또 기록 커밋 이야기하네, 저장 배포로 통일 시켜달라고 계속 이야기하는데? 박제하지않았어?"

왜 필요한가
  같은 날 17:46 에 시우가 **도구가 찍는 문구**를 저장·배포로 바꿨다(커밋 327adba89). 그런데 그 뒤로도
  보고 표 끝줄이 계속 「기록 = 커밋 961b5a7f9」로 나갔다 — 도구는 고쳤는데 **사람(AI)이 쓰는 문장**은
  안 고쳐졌기 때문이다. 문서에 한 줄 더 적는 것으로는 안 잡힌다(오늘 하루에만 세 번 더 나갔다).
  그래서 턴이 끝날 때 실제로 나간 글을 읽어 세는 자리를 둔다.

무엇을 잡나
  GM 화면에 그대로 찍히면 안 되는 내부 낱말 — 커밋 · 푸시 · master · 브랜치 · 스위퍼 · cherry-pick ·
  origin. 대신 쓸 말 = 저장 / 배포 / 저장·배포 완료.

무엇은 안 잡나
  · GM 이 그 낱말을 먼저 쓴 턴(예: 지금 이 지시처럼 "커밋 이야기하네") — 되받아 답해야 한다.
  · 낱말·줄글 검사는 막지 않는다. 경고만 낸다(stderr).
  · 8요소 표 검사(검사 A·B)만 막는다 — stderr + exit 2. GM 지시 2026-09-10 이 다섯 번 반복돼서다.

자체점검: python scripts/gm_wording_guard.py --selftest
"""
import json
import os
import sys

# 내부 낱말 → GM 화면에서 쓸 말. 여기 없는 말은 잡지 않는다(과잉 경고 금지).
BANNED = {
    "커밋": "저장",
    "푸시": "배포",
    "브랜치": "(빼거나 '저장 줄기')",
    "스위퍼": "(빼기 — 배포가 알아서 된다)",
    "cherry-pick": "(빼기)",
    "master": "(빼기)",
    "origin": "(빼기)",
}


def last_messages(transcript_path):
    """(마지막 assistant 글, 마지막 user 글). 못 읽으면 ('', '')."""
    assistant, user = "", ""
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return "", ""
    for raw in reversed(lines):
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except ValueError:
            continue
        msg = row.get("message") or {}
        role = msg.get("role") or row.get("type")
        content = msg.get("content")
        text = ""
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text = "\n".join(c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text")
        if not text.strip():
            continue
        if role == "assistant" and not assistant:
            assistant = text
        elif role == "user" and not user:
            user = text
        if assistant and user:
            break
    return assistant, user


def offenders(assistant_text, user_text):
    """GM 화면에 나간 내부 낱말. GM 이 먼저 쓴 낱말은 뺀다."""
    return [w for w in BANNED if w in assistant_text and w not in user_text]


# ── 표 밖 줄글 (GM 지시 2026-09-10) ───────────────────────────────────────────────
#   GM 원문: "표로 안보여주고 또 이상하게 정리해주네, 이상하게 정리해주는 구조를 삭제할 순 없나?"
#   약속 L18 은 이미 「표가 본문 · 표 밖 줄글은 표로 못 담는 것만」인데, 문서로만 있어서
#   계속 새어 나갔다(같은 지적 반복). 그래서 낱말 검사와 같은 자리에서 줄 수를 센다.
#   허용 = 표 위 상태 결론 1줄 + 맨 끝 기록위치 1줄 + 판단 이유 2줄 = 4줄.
#   막지 않는다. 경고만 낸다(이 파일의 다른 검사와 같은 규칙).
PROSE_LIMIT = 4


def prose_lines(assistant_text):
    """표·목록·제목·코드를 뺀 '줄글' 줄만 센다. 표가 없는 답(코드 설명 등)은 대상 밖 — 빈 목록."""
    lines, in_code, out, has_table = assistant_text.splitlines(), False, [], False
    for ln in lines:
        s = ln.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not s:
            continue
        if s.startswith("|"):
            has_table = True
            continue
        if s.startswith(("#", ">", "-", "*", "·", "▪")) or s[:2].rstrip(".").isdigit():
            continue      # 제목·인용·목록은 줄글이 아니다(한눈에 읽힌다)
        out.append(s)
    return out if has_table else []


def prose_offense(assistant_text):
    """줄글이 허용치를 넘었으면 (넘은 줄 수, 예시 한 줄). 아니면 None."""
    ps = prose_lines(assistant_text)
    if len(ps) <= PROSE_LIMIT:
        return None
    longest = max(ps, key=len)
    return len(ps), (longest[:60] + "…" if len(longest) > 60 else longest)


# ── 8요소 표 (GM 지시 2026-09-10 · 하루 네 번 + 09-11 한 번 = 다섯 번 같은 지적) ─────────
#   경고만 내던 자리라 지켜지지 않았다. 검사 A(8요소 표 아님)·B(표 두 장)는 **막는다**(exit 2).
#   낱말·줄글 검사는 지금처럼 경고만 — 한꺼번에 막으면 되묻기 고리가 생긴다.
EIGHT = [("📌", "GM 요청"), ("🔍", "실측"), ("✅", "반영"),
         ("🔎", "검수"), ("📤", "배포"), ("⏱", "소요"), ("💡", "더 나았을 방법")]
TOOL_TABLES = ("🧭 오늘의 항로", "🥁 쿵짝표")   # 도구가 내는 정해진 표 = 대상 밖
FORMAT_HINT = (
    "  GM 지시 2026-09-10(4회 반복) = GM 화면에 내는 표는 8요소 표 하나뿐이다.\n"
    "  순서 고정: 📌 GM 요청 | 🔍 실측 | ✅ 반영 | 🔎 검수 | 📤 배포 | ⏱ 소요 | 💡 더 나았을 방법 | 👉 GM 액션(필요할 때만)\n"
    "  물음이 없는 턴도 같은 표를 쓴다 — 📌 칸에 '무엇 때문에 내는 보고인지'를 적으면 성립한다.\n"
    "  이 표로 다시 써라.\n")


def _body(assistant_text):
    """코드블록·빈 줄을 뺀 줄들."""
    out, in_code = [], False
    for ln in assistant_text.splitlines():
        s = ln.strip()
        if s.startswith("```"):
            in_code = not in_code
            continue
        if in_code or not s:
            continue
        out.append(s)
    return out


def format_offense(assistant_text):
    """검사 A·B. 위반이면 되돌릴 글, 아니면 None."""
    if any(t in assistant_text for t in TOOL_TABLES):
        return None                                      # 도구가 낸 정해진 표
    body = _body(assistant_text)
    if not body:
        return None                                      # 코드 블록만 있는 답
    if not any(s.startswith("|") for s in body) and len(body) <= 2:
        return None                                      # 표 없는 짧은 답(한 줄 확인·되묻기)
    missing = ["%s %s" % (m, n) for m, n in EIGHT if m not in assistant_text]
    if missing:
        return ("[GM 답변 형식] 8요소 표가 아니다 — 빠진 칸: %s\n" % ", ".join(missing)) + FORMAT_HINT
    if assistant_text.count("📌") > 1:
        return ("[GM 답변 형식] 8요소 표가 두 장이다(📌 %d개) — 한 턴에 한 장이다.\n"
                "  보조 표는 8요소 표 아래 최대 1장(목록·비교처럼 표로만 담기는 것)이고, 📌 는 붙이지 않는다.\n"
                % assistant_text.count("📌")) + FORMAT_HINT
    # 검사 C — 한 요소를 여러 줄로 늘리지 않는다(GM 지적 2026-09-11 「표 완전 최악이네」).
    #   8요소 표는 8행이다. 실측을 네 줄, 반영을 세 줄로 쪼개면 표가 11행이 되고 구조가 무너져
    #   어느 것이 결론인지 안 보인다. 할 말이 많으면 칸 안에서 줄이고 나머지는 보조 표로 내린다.
    dup = [("%s %s" % (m, n), assistant_text.count(m)) for m, n in EIGHT
           if assistant_text.count(m) > 1]
    if dup:
        return ("[GM 답변 형식] 같은 요소가 여러 줄이다 — %s\n"
                "  8요소 표는 8행 고정이다. 한 요소 = 한 줄. 내용이 많으면 그 칸 안에서 줄여 쓰고,\n"
                "  목록이 필요하면 표 아래 보조 표 한 장으로 내린다.\n"
                % ", ".join("%s %d줄" % (k, v) for k, v in dup)) + FORMAT_HINT
    return None


def main():
    if "--selftest" in sys.argv:
        assert offenders("기록 = 커밋 961b5a7f9", "") == ["커밋"]
        assert offenders("기록 = 커밋 961b5a7f9", "커밋 이야기하네") == []      # GM 이 먼저 쓴 낱말
        assert offenders("저장·배포 완료", "") == []
        assert offenders("master 로 올렸다", "") == ["master"]
        table = "| 📌 GM 요청 | 무엇 |\n|---|---|\n| ✅ 반영 | 했다 |"
        assert prose_offense("결론 한 줄\n" + table + "\n기록 = 저장·배포 완료") is None
        assert prose_offense(table + "\n" + "\n".join("줄글%d 입니다." % i for i in range(6)))[0] == 6
        assert prose_offense("표 없는 답인데 줄글이 다섯 줄이다.\n" * 6) is None   # 표 없는 답은 대상 밖
        assert prose_offense(table + "\n- 목록은 줄글이 아니다\n" * 9) is None
        a, u = last_messages(os.devnull)
        assert (a, u) == ("", "")                                            # 못 읽어도 안 죽는다
        full = ("| 📌 GM 요청 | 무엇 |\n|---|---|\n| 🔍 실측 | 쟀다 |\n| ✅ 반영 | 했다 |\n"
                "| 🔎 검수 | 봤다 |\n| 📤 배포 | 올렸다 |\n| ⏱ 소요 | 3분 |\n| 💡 더 나았을 방법 | 없다 |")
        assert format_offense(full) is None                                  # 8요소 다 있으면 통과
        half = format_offense("| 📌 GM 요청 | 무엇 |\n|---|---|\n| 🔍 실측 | 쟀다 |\n| ✅ 반영 | 했다 |\n| 💡 더 나았을 방법 | 없다 |")
        assert half and "🔎 검수" in half and "📤 배포" in half and "⏱ 소요" in half
        two = format_offense(full + "\n\n" + full)
        assert two and "두 장" in two                                        # 📌 두 번 = 위반
        assert format_offense("🧭 오늘의 항로\n| 배 | 상태 |\n|---|---|\n| 1101 | 진행 |") is None
        assert format_offense("🥁 쿵짝표\n| 지시 | 한 것 |\n|---|---|\n| a | b |") is None
        assert format_offense("네, 맞다.\n어느 쪽을 말하는 건가?") is None    # 표 없는 짧은 답
        assert format_offense("```\ncode only\n```") is None
        print("selftest ok")
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    path = payload.get("transcript_path") or ""
    if not path:
        return 0
    assistant, user = last_messages(path)
    if not assistant:
        return 0
    bad = offenders(assistant, user)
    if bad:
        fix = " · ".join("%s→%s" % (w, BANNED[w]) for w in bad)
        sys.stderr.write(
            "[GM 화면 낱말] 방금 답에 내부 낱말이 나갔다: %s\n"
            "  GM 지시(2026-09-09) = 저장·배포로 통일. 도구 문구는 이미 그렇게 찍는다(시우 327adba89).\n"
            "  고칠 것: %s\n" % (", ".join(bad), fix))
    long_prose = prose_offense(assistant)
    if long_prose:
        n, sample = long_prose
        sys.stderr.write(
            "[GM 화면 줄글] 방금 답에 표 밖 줄글이 %d줄 나갔다(허용 %d줄).\n"
            "  GM 지시(2026-09-10) = 표가 본문. 표로 담을 수 있는 말은 표 안으로 옮긴다.\n"
            "  본보기: %s\n" % (n, PROSE_LIMIT, sample))
    bad_format = format_offense(assistant)
    if bad_format:
        sys.stderr.write(bad_format)
        return 2                       # 막는다 — 경고만으로는 같은 지적이 다섯 번 났다
    return 0


if __name__ == "__main__":
    sys.exit(main())
