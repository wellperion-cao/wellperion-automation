# -*- coding: utf-8 -*-
"""발행방식 드리프트 검증기 (2026-07-24 · 배9964).

정본 = ssot/publish_channels.json — 채널별 '어떻게 발행하는가' 단일 출처.
이 스크립트는 그 선언과 실제 코드/데이터를 대조해 어긋난 지점만 잡아낸다.
읽기 전용이다 — 어떤 파일도 쓰지 않고, 커밋도 발행도 하지 않는다.

검사:
  A. review_queue.json 의 channel 실측값 → SSOT match 규칙으로 커버리지 판정
  B. SSOT 가 선언한 publisher/profile/state 경로 실존
  C. SSOT 선언(match·publisher·status_on_*)이 판정 중심축 코드에 실제 배선됐는지
  D. 채널 키워드 중복 정의 지점 — known 목록 생존 + 새 후보 탐지
  E. 죽은코드 후보 파일의 실행 호출부 재확인

사용:
  python scripts\\publish_channels_check.py            # 사람이 읽는 요약
  python scripts\\publish_channels_check.py --json      # 기계 판독용 JSON 병기

종료코드: 경고 0건=0, 1건 이상=1.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(r"C:\Users\jjky0\welperion-automation")
SSOT_PATH = ROOT / "ssot" / "publish_channels.json"
QUEUE_PATH = ROOT / "3. 웰페리온 가이드" / "cmo" / "review" / "review_queue.json"
SCRIPTS_DIR = ROOT / "scripts"

# 검사 D 새 중복 탐지용 채널 키워드 5종 (SSOT 채널명과 별개 — 사람이 코드에 흔히 쓰는 리터럴)
CHANNEL_KEYWORDS = ["블로그", "카페", "당근", "카카오", "인스타"]

# 검사 E 저장소 훑기 대상 확장자 — "실행 호출부(import·subprocess/python 인자)"는 구문상
# 코드·실행스크립트에만 존재한다. .md·.json·.txt 는 문서·이력·데이터 언급이 섞여 있으면
# 실제 호출부가 아닌데도 걸려 SSOT 의 '문서·이력 언급만'이라는 기존 판정과 모순되는 오탐을
# 만든다(2026-07-24 최초 실행에서 실측 — 확장자를 코드성으로 좁혀 배제).
SCAN_EXTS = {".py", ".bat", ".ps1", ".xml"}
# 검사 E 훑기에서 통째로 건너뛸 디렉토리명(대소문자 무시 없이 정확 일치)
SCAN_SKIP_DIRS = {
    ".git", "_archive", "node_modules", ".venv", "__pycache__", ".omc",
    "profiles", "instagram", "images", "backup", "poc-evidence",
    # .claude/worktrees = 저장소 전체를 복제한 임시 작업트리 — 여기 있는 사본은
    # '별도 호출부'가 아니라 같은 파일의 중복 체크아웃이라 오탐만 만든다(2026-07-24 실측).
    "worktrees",
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path)


class Result:
    """검사 하나의 결과 묶음 — OK/WARN/INFO 라인을 모은다."""

    def __init__(self, name: str):
        self.name = name
        self.warns: list[str] = []
        self.infos: list[str] = []  # 알림(정보성 — 종료코드에 영향 없음, 예: SSOT 갱신 권고)
        # 요약 줄 오버라이드(선택) — 기본 "경고 N건, 알림 N건" 대신 이 문자열을 쓴다.
        # 검사 D 처럼 "몇 건을 조용히 넘겼는지"를 숫자로 밝혀야 하는 경우에 사용
        # (배9820 GM 지적 — 매번 십수 건이 뜨면 아무도 안 본다. 제외 건수를 숨기지 않는다).
        self.summary: str | None = None

    def warn(self, msg: str) -> None:
        self.warns.append(msg)

    def info(self, msg: str) -> None:
        self.infos.append(msg)

    @property
    def ok(self) -> bool:
        return not self.warns


def channel_matches(value: str, ch: dict) -> bool:
    if ch["match_kind"] == "substring":
        return ch["match"] in value
    if ch["match_kind"] == "regex":
        return re.search(ch["match"], value, re.IGNORECASE) is not None
    raise ValueError(f"알 수 없는 match_kind: {ch['match_kind']}")


def check_a_coverage(ssot: dict) -> Result:
    """검사 A — review_queue.json 의 channel 실측값 커버리지."""
    r = Result("A. 채널 값 커버리지")
    channels = ssot["channels"]
    if not QUEUE_PATH.exists():
        r.warn(f"큐 파일 없음: {_rel(QUEUE_PATH)}")
        return r
    try:
        items = _read_json(QUEUE_PATH)
    except Exception as exc:
        r.warn(f"큐 파일 파싱 실패: {exc}")
        return r
    if not isinstance(items, list):
        r.warn("큐 파일이 리스트가 아님")
        return r

    values = sorted({str(it.get("channel", "")).strip() for it in items})
    for value in values:
        label = value or "(빈값)"
        matched = [ch for ch in channels if channel_matches(value, ch)]
        if len(matched) == 0:
            r.warn(f"미상 채널값 '{label}' — 어느 SSOT 채널에도 안 걸림"
                   f"(라이브에서 '발행보류(채널확인)'로 떨어짐)")
            continue
        if len(matched) >= 2:
            keys = ", ".join(ch["key"] for ch in matched)
            r.warn(f"채널값 '{label}' 이(가) 채널 {len(matched)}개에 동시 매칭({keys}) — 판정 모호(순서 의존)")
        ch = matched[0]
        if value and value not in ch.get("observed_values", []):
            r.info(f"채널값 '{label}' 이(가) '{ch['key']}'({ch['label']})로 판정되나 "
                   f"observed_values 에 없음 — SSOT 갱신 필요")
    return r


def check_b_paths(ssot: dict) -> Result:
    """검사 B — publisher/profile/state 경로 실존."""
    r = Result("B. 파일·프로필 실존")
    for ch in ssot["channels"]:
        key, label = ch["key"], ch["label"]
        publisher = ROOT / ch["publisher"]
        if not publisher.exists():
            r.warn(f"[{label}] publisher 없음: {ch['publisher']}")
        auth = ch.get("auth", {})
        profile = auth.get("profile")
        if profile:
            p = ROOT / profile
            if not p.exists():
                r.warn(f"[{label}] auth.profile 없음: {profile}")
        state = auth.get("state")
        if state:
            s = ROOT / state
            if not s.exists():
                r.warn(f"[{label}] auth.state 없음: {state}")
    return r


def check_c_wiring(ssot: dict) -> Result:
    """검사 C — SSOT 선언이 판정 중심축 코드에 실제 배선됐는지."""
    r = Result("C. 선언↔코드 배선 일치")
    axis = ssot["판정_중심축"]
    axis_path = ROOT / axis["file"]
    if not axis_path.exists():
        r.warn(f"판정 중심축 파일 없음: {axis['file']}")
        return r
    text = axis_path.read_text(encoding="utf-8", errors="replace")

    for ch in ssot["channels"]:
        key, label = ch["key"], ch["label"]
        if ch["match_kind"] == "substring" and ch["match"] not in text:
            r.warn(f"[{label}] match 문자열 '{ch['match']}' 이 {axis['file']} 안에 없음(분기 조건 소실 의심)")
        pub_name = Path(ch["publisher"]).name
        if pub_name not in text:
            r.warn(f"[{label}] publisher 파일명 '{pub_name}' 이 {axis['file']} 안에 없음(배선 소실 의심)")
        for field in ("status_on_success", "status_on_fail", "status_on_url_miss"):
            val = ch.get(field)
            if val and val not in text:
                r.warn(f"[{label}] {field}='{val}' 가 {axis['file']} 안에 없음")

    unknown_status = axis.get("미상채널_정책", {}).get("status")
    if unknown_status and unknown_status not in text:
        r.warn(f"미상채널_정책.status='{unknown_status}' 가 {axis['file']} 안에 없음")
    return r


def _iter_code_lines(text: str):
    """전체 줄 주석('#'로 시작하는 줄, 좌우 공백 무시)을 뺀 코드 줄만 순회."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        yield line


def check_d_duplicates(ssot: dict) -> Result:
    """검사 D — 채널 키워드 중복 정의 지점: known 생존 확인 + 새 후보 탐지."""
    r = Result("D. 중복 정의 감시")
    dup = ssot["중복_정의_지점"]
    known_entries = dup["known"]
    known_files = {entry["file"] for entry in known_entries}
    for entry in known_entries:
        p = ROOT / entry["file"]
        if not p.exists():
            r.info(f"known 중복 정의 파일이 사라짐: {entry['file']} ({entry['what']}) — SSOT 갱신 필요")

    # 검토 완료(라우팅 판정 아님) 목록 — 채널 키워드는 3개 이상 나오지만 '채널→동작'
    # 판정 로직이 없는 파일들(집계·문구·테스트 등). 사람이 파일별 사유와 함께 SSOT 에
    # 등재해 둔 것만 제외한다.
    # ★왜 필요한가: 이 검사는 넓은 휴리스틱이라 그대로 두면 매 실행 15건 넘게 뜬다.
    #   "첫날 55건 뜨면 아무도 안 본다"(배9820 GM 지적)는 여기서도 똑같이 성립한다 —
    #   경고는 사람이 손댈 게 있을 때만 떠야 한다. 대신 몇 건을 넘겼는지는 아래에서
    #   반드시 숫자로 밝힌다(조용한 은폐 금지).
    # 옛 SSOT(이 항목이 없는 버전)에서는 빈 집합 → 종전 동작으로 안전 폴백.
    reviewed = dup.get("검토됨_라우팅아님") or {}
    reviewed_entries = reviewed.get("files", [])
    reviewed_files = {e["file"] for e in reviewed_entries}
    for entry in reviewed_entries:
        if not (ROOT / entry["file"]).exists():
            r.info(f"검토됨_라우팅아님 파일이 사라짐: {entry['file']} ({entry['why']}) — SSOT 갱신 필요")

    axis_file = ssot["판정_중심축"]["file"]
    # 이 검증기 자신도 제외 — CHANNEL_KEYWORDS 상수 목록 자체가 5개 키워드를 나열해
    # 자기 자신을 '새 중복 정의 후보'로 오탐한다(2026-07-24 최초 실행에서 실측).
    self_rel = _rel(Path(__file__).resolve())
    excluded = known_files | reviewed_files | {axis_file, self_rel}

    candidates: list[str] = []
    if SCRIPTS_DIR.is_dir():
        for py in sorted(SCRIPTS_DIR.glob("*.py")):
            rel = _rel(py)
            if rel in excluded:
                continue
            try:
                text = py.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            code_text = "\n".join(_iter_code_lines(text))
            found = [kw for kw in CHANNEL_KEYWORDS if kw in code_text]
            if len(found) >= 3:
                candidates.append(f"{rel} — 키워드 {len(found)}개 동시 등장({', '.join(found)})")
    for c in candidates:
        r.warn(f"새 중복 정의 후보: {c}")
    # 몇 건을 제외했는지 항상 밝힌다 — 조용히 넘기면 '깨끗함'으로 오해된다.
    # 건수는 known/검토됨 리스트의 항목(entry) 수 기준(같은 파일에 항목이 여러 개면
    # 그만큼 검토 흔적이 많다는 뜻 — 파일 수로 뭉개지 않는다).
    r.summary = (
        f"새 사본 {len(candidates)}건 "
        f"(known {len(known_entries)}건·검토됨 {len(reviewed_entries)}건 제외)"
    )
    return r


_IMPORT_RE_CACHE: dict[str, re.Pattern] = {}


def check_e_dead_code(ssot: dict) -> Result:
    """검사 E — 죽은코드 후보 파일의 실행 호출부(import/subprocess 인자) 재확인."""
    r = Result("E. 죽은코드 후보 재확인")
    dup = ssot["중복_정의_지점"]
    for entry in dup.get("죽은코드_후보", []):
        rel_file = entry["file"]
        target = ROOT / rel_file
        if not target.exists():
            r.info(f"죽은코드 후보 파일이 사라짐: {rel_file} — SSOT 갱신 필요")
            continue
        stem = target.stem  # 확장자 뺀 모듈명(import 탐지용)
        basename = target.name  # subprocess 인자 탐지용(파일명 그대로)

        import_re = re.compile(r"\bimport\s+" + re.escape(stem) + r"\b|\bfrom\s+" + re.escape(stem) + r"\s+import\b")
        callers: list[str] = []
        for path in _iter_scan_files():
            if path == target:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            if basename in text or import_re.search(text):
                callers.append(_rel(path))
            if len(callers) >= 5:
                break
        if callers:
            r.warn(f"죽은코드 후보로 SSOT 에 등록됐지만 실행 호출부 재발견: {rel_file} ← {', '.join(callers[:5])}"
                   f" (SSOT 판정 재검토 필요)")
        else:
            r.info(f"죽은코드 후보 재확인: {rel_file} — 실행 호출부 여전히 0건(SSOT 판정 유지)")
    return r


def _iter_scan_files():
    """검사 E용 저장소 훑기 — 대용량/무관 디렉토리 제외, 텍스트 확장자만."""
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCAN_EXTS:
            continue
        parts = set(path.relative_to(ROOT).parts)
        if parts & SCAN_SKIP_DIRS:
            continue
        rel = _rel(path)
        if rel.startswith("status/backups/"):
            continue
        if re.match(r"^status/_queue.*\.json$", rel):
            continue
        yield path


def main() -> int:
    ap = argparse.ArgumentParser(description="발행방식 드리프트 검증기(읽기 전용)")
    ap.add_argument("--json", action="store_true", help="기계 판독용 JSON 결과도 출력")
    args = ap.parse_args()

    if not SSOT_PATH.exists():
        print(f"[ERROR] SSOT 없음: {_rel(SSOT_PATH)}")
        return 1
    ssot = _read_json(SSOT_PATH)

    results = [
        check_a_coverage(ssot),
        check_b_paths(ssot),
        check_c_wiring(ssot),
        check_d_duplicates(ssot),
        check_e_dead_code(ssot),
    ]

    total_warns = sum(len(r.warns) for r in results)
    print("=== 발행방식 드리프트 검증 결과 ===")
    for r in results:
        tag = "OK" if r.ok else "WARN"
        # summary 가 있으면 그걸 쓴다 — 검사 D 처럼 '몇 건을 제외했는지'를 반드시
        # 드러내야 하는 경우. 없으면 기본 집계 줄.
        body = r.summary or f"경고 {len(r.warns)}건, 알림 {len(r.infos)}건"
        print(f"[{tag}] {r.name} — {body}")
        for w in r.warns:
            print(f"    ⚠ {w}")
        for i in r.infos:
            print(f"    ℹ {i}")
    print("-----------------------------------")
    print(f"총 경고: {total_warns}건")

    if args.json:
        payload = {
            "ok": total_warns == 0,
            "total_warnings": total_warns,
            "checks": [
                {"name": r.name, "warnings": r.warns, "infos": r.infos}
                for r in results
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 1 if total_warns else 0


if __name__ == "__main__":
    sys.exit(main())
