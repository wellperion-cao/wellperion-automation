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
  · 막지 않는다. 경고만 낸다(stderr). 턴을 막으면 되묻기 고리가 생긴다.

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


def main():
    if "--selftest" in sys.argv:
        assert offenders("기록 = 커밋 961b5a7f9", "") == ["커밋"]
        assert offenders("기록 = 커밋 961b5a7f9", "커밋 이야기하네") == []      # GM 이 먼저 쓴 낱말
        assert offenders("저장·배포 완료", "") == []
        assert offenders("master 로 올렸다", "") == ["master"]
        a, u = last_messages(os.devnull)
        assert (a, u) == ("", "")                                            # 못 읽어도 안 죽는다
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
