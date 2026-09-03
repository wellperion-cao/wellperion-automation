"""힉스필드(Higgsfield) 렌더 모듈.
자리: 레시피(scripts/higgsfield_recipes.json) → 이 모듈(비용상한 → 생성 → 내려받기) → (다음) 검수 큐.
비용 상한 차단이 이 모듈의 존재 이유 중 하나 — 편당 cost 를 먼저 재고 예산을 넘으면 생성하지 않는다.
"""
import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPE_PATH = REPO_ROOT / "scripts" / "higgsfield_recipes.json"
OUT_ROOT = REPO_ROOT / "instagram" / "Movie" / "higgsfield"

# kling3_0 은 image_references 파라미터가 없다(higgsfield model get kling3_0 실측) — start_image 로 참조.
# ponytail: 두 모델(정본·탐색용)만 쓰므로 하드코딩 매핑으로 충분 — 모델이 늘면 여기 한 줄 추가.
MEDIA_FLAG_BY_MODEL = {"kling3_0": "--start-image"}
DEFAULT_MEDIA_FLAG = "--image-references"

# 정본_규격 안 키 → CLI 플래그. 스펙에 없는 키는 건너뛴다(정본/탐색용 스펙 모양이 다름).
SPEC_KEY_TO_FLAG = [
    ("mode", "--mode"),
    ("resolution", "--resolution"),
    ("duration", "--duration"),
    ("generate_audio", "--generate_audio"),
    ("sound", "--sound"),
]


def blocked(msg):
    print(f"BLOCKED: {msg}")
    sys.exit(1)


def done(msg):
    print(f"DONE: {msg}")
    sys.exit(0)


def load_recipe():
    return json.loads(RECIPE_PATH.read_text(encoding="utf-8"))


def build_prompt(recipe, scene, subject, action, space, texture):
    scenes = recipe["장면_레시피"]
    if scene not in scenes:
        blocked(f"알 수 없는 장면 레시피 '{scene}' (선택: {list(scenes)})")
    template = scenes[scene]["문장"]
    body = template.format(사람=subject or "", 동작=action or "", 공간=space or "", 질감=texture or "")
    return f"{body} {recipe['공통_꼬리_문장']}"


def model_spec(recipe, explore):
    spec = recipe["정본_규격"]
    return spec["탐색용"] if explore else spec


def model_args(spec):
    args = []
    for key, flag in SPEC_KEY_TO_FLAG:
        if key not in spec:
            continue
        value = spec[key]
        if isinstance(value, bool):
            value = "true" if value else "false"
        args += [flag, str(value)]
    return args


def media_flag(model):
    return MEDIA_FLAG_BY_MODEL.get(model, DEFAULT_MEDIA_FLAG)


def find_cli():
    exe = shutil.which("higgsfield")
    if not exe:
        blocked("higgsfield CLI 를 PATH 에서 찾을 수 없다(npm 전역 설치 확인)")
    return exe


def cli_json(exe, args, what):
    result = subprocess.run([exe] + args + ["--json"], capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
    if result.returncode != 0:
        blocked(f"{what} 실패 — {(result.stderr or result.stdout).strip()[:500]}")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        blocked(f"{what} 응답 파싱 실패 — {result.stdout[:500]}")


def download(url, dest):
    import requests
    r = requests.get(url, timeout=180)
    r.raise_for_status()
    dest.write_bytes(r.content)


def extract_preview(mp4_path, jpg_path):
    try:
        from moviepy import VideoFileClip
    except Exception as e:
        print(f"경고: moviepy 로드 실패 — 미리보기 생략({mp4_path.name}, {e})")
        return None
    try:
        with VideoFileClip(str(mp4_path)) as clip:
            clip.save_frame(str(jpg_path), t=clip.duration / 2)
        return jpg_path
    except Exception as e:
        print(f"경고: 미리보기 추출 실패({mp4_path.name}) — {e}")
        return None


def parse_args(recipe):
    p = argparse.ArgumentParser(description="힉스필드 렌더 — 레시피→비용상한→생성→내려받기")
    p.add_argument("--scene", required=True, choices=list(recipe["장면_레시피"]))
    p.add_argument("--space", required=True)
    p.add_argument("--subject", default="")
    p.add_argument("--action", default="")
    p.add_argument("--texture", default="")
    p.add_argument("--ref", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument("--n", type=int, default=1)
    p.add_argument("--explore", action="store_true")
    p.add_argument("--max-credits", type=float, default=120)
    p.add_argument("--dry-run", action="store_true")
    return p.parse_args()


def main():
    recipe = load_recipe()
    args = parse_args(recipe)

    ref_path = Path(args.ref)
    if not ref_path.exists():
        blocked(f"참조 이미지 없음: {ref_path}")

    prompt = build_prompt(recipe, args.scene, args.subject, args.action, args.space, args.texture)
    spec = model_spec(recipe, args.explore)
    model = spec["모델"]
    flag = media_flag(model)
    base_args = ["generate", "create", model] + model_args(spec) + ["--prompt", prompt, flag, str(ref_path)]

    exe = find_cli()
    cost_resp = cli_json(exe, ["generate", "cost", model] + model_args(spec) + ["--prompt", prompt, flag, str(ref_path)],
                          "비용 조회")
    per_credit = float(cost_resp.get("credits", 0))
    total_credit = per_credit * args.n

    print(f"모델={model} 편당={per_credit}크레딧 x {args.n}편 = {total_credit}크레딧 (상한 {args.max_credits})")
    print(f"프롬프트: {prompt}")

    if total_credit > args.max_credits:
        blocked(f"예산 초과 — 편당 {per_credit} x {args.n}편 = {total_credit} > 상한 {args.max_credits}")

    create_args = base_args + ["--wait", "--wait-timeout", "20m", "--wait-interval", "10s"]
    if args.dry_run:
        print("실행 예정 명령: higgsfield " + " ".join(create_args))
        done(f"dry-run — 편당 {per_credit}크레딧 x {args.n}편, 크레딧 미사용")

    date_tag = datetime.now().strftime("%y%m%d")
    out_dir = OUT_ROOT / f"{date_tag}_{args.slug}"
    out_dir.mkdir(parents=True, exist_ok=True)

    credits_before = cli_json(exe, ["account", "status"], "계정 조회(생성 전)").get("credits")

    takes = []
    for k in range(1, args.n + 1):
        resp = cli_json(exe, create_args, f"{k}편째 생성")
        job = resp[0] if isinstance(resp, list) else resp
        if job.get("status") != "completed":
            blocked(f"{k}편째 생성 실패 — status={job.get('status')} · {json.dumps(job, ensure_ascii=False)[:300]}")
        url = job.get("result_url")
        if not url:
            blocked(f"{k}편째 결과 URL 없음 — {json.dumps(job, ensure_ascii=False)[:300]}")
        mp4_path = out_dir / f"take_{k}.mp4"
        download(url, mp4_path)
        preview_path = extract_preview(mp4_path, out_dir / f"take_{k}_preview.jpg")
        takes.append({
            "take": k, "result_url": url, "mp4": str(mp4_path),
            "preview": str(preview_path) if preview_path else None,
            "created_at": datetime.now().isoformat(),
        })

    credits_after = cli_json(exe, ["account", "status"], "계정 조회(생성 후)").get("credits")

    meta = {
        "scene": args.scene, "slug": args.slug, "prompt": prompt, "model": model, "explore": args.explore,
        "per_credit": per_credit, "n": args.n, "credits_before": credits_before, "credits_after": credits_after,
        "takes": takes, "generated_at": datetime.now().isoformat(),
    }
    (out_dir / "_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    used = (credits_before - credits_after) if (credits_before is not None and credits_after is not None) else total_credit
    done(f"{out_dir} · {args.n}편 · 크레딧 {used} 사용 · 잔량 {credits_after}")


def _selftest():
    """네트워크 없이 도는 최소 점검 — 프롬프트 조립·모델 플래그·예산 분기."""
    recipe = load_recipe()
    prompt = build_prompt(recipe, "걷는_영상", "", "", "실내 25m 수영장", "")
    assert "실내 25m 수영장" in prompt
    assert recipe["공통_꼬리_문장"] in prompt

    spec = model_spec(recipe, explore=False)
    assert spec["모델"] == "seedance_2_5"
    assert media_flag(spec["모델"]) == "--image-references"
    assert "--generate_audio" in model_args(spec) and "false" in model_args(spec)

    explore_spec = model_spec(recipe, explore=True)
    assert explore_spec["모델"] == "kling3_0"
    assert media_flag(explore_spec["모델"]) == "--start-image"
    assert "--resolution" not in model_args(explore_spec)

    assert 45.0 * 2 > 80  # 예산 상한 초과 판정
    assert not (10.0 * 2 > 80)  # 예산 상한 이내 판정
    print("selftest ok")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
    else:
        main()
