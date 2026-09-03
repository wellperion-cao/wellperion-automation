#!/usr/bin/env python3
"""AWS ERP 라이브 전수 검수 — 모듈 95개를 로그인 쿠키로 열어 응답·깨진 링크·절대경로를 표로 낸다.

    C:/Python314/python.exe scripts/erp_live_audit.py            # 표 출력 + status/erp_live_audit.json
관리자 비밀번호는 서버 /srv/erp/auth.env 에서 ssh 로 읽는다(출력 안 함).
"""
from __future__ import annotations

import html
import http.cookiejar
import json
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
B = "https://erp.wellperion.com"
MODS = REPO / "3. 웰페리온 가이드" / "erp" / "modules.json"
OUT = REPO / "status" / "erp_live_audit.json"
sys.stdout.reconfigure(encoding="utf-8")


def admin_pw() -> str:
    r = subprocess.run(["ssh", "-i", str(Path.home() / ".aws" / "wellperion-sito.pem"), "ec2-user@15.164.151.105",
                        "sudo grep ERP_ADMIN_PW /srv/erp/auth.env"], capture_output=True, text=True, timeout=40)
    return r.stdout.strip().split("=", 1)[1]


def login():
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    op.open(urllib.request.Request(B + "/auth/login", data=urllib.parse.urlencode(
        {"email": "cao@wellperion.com", "password": admin_pw(), "next": "/"}).encode()), timeout=30)
    return op


def fetch(op, path: str):
    url = B + urllib.parse.quote(path, safe="/%?=&#")
    try:
        r = op.open(url, timeout=40)
        return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        return -1, str(e)


LINK_RE = re.compile(r'(?:href|src)="([^"#?]+)')


def audit_one(op, m: dict) -> dict:
    path = "/" + m["path"].replace("../", "")
    st, body = fetch(op, path)
    row = {"id": m["id"], "group": m["group"], "name": m["name"], "path": path, "status": st,
           "abs_pages": 0, "github_io": 0, "gate_js": 0, "gas_calls": 0, "broken": []}
    if st != 200:
        return row
    row["abs_pages"] = body.count('"/wellperion-automation/')
    row["github_io"] = body.count("wellperion-cao.github.io")
    row["gate_js"] = 1 if "_assets/gate.js" in body else 0
    row["gas_calls"] = len(set(re.findall(r"script\.google\.com/macros/s/([A-Za-z0-9_-]+)", body)))
    base = path.rsplit("/", 1)[0] + "/"
    seen = set()
    for link in LINK_RE.findall(body):
        link = html.unescape(link)
        if link.startswith(("http", "mailto:", "javascript:", "data:", "tel:", "//")):
            continue
        target = urllib.parse.urljoin(base, link)
        if not target.endswith((".html", ".js", ".css", ".json")) or target in seen:
            continue
        seen.add(target)
        s2, _ = fetch(op, target)
        if s2 == 404:
            row["broken"].append(target)
    return row


def main() -> int:
    mods = json.loads(MODS.read_text(encoding="utf-8"))["modules"]
    op = login()
    with ThreadPoolExecutor(max_workers=6) as ex:
        rows = list(ex.map(lambda m: audit_one(op, m), mods))
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r for r in rows if r["status"] != 200]
    brk = [r for r in rows if r["broken"]]
    print(f"모듈 {len(rows)} · 응답 비정상 {len(bad)} · 깨진 링크 있는 화면 {len(brk)} · "
          f"절대경로 {sum(1 for r in rows if r['abs_pages'])} · github.io {sum(1 for r in rows if r['github_io'])} · "
          f"커튼 {sum(1 for r in rows if r['gate_js'])} · GAS {sum(1 for r in rows if r['gas_calls'])}")
    for r in bad:
        print(f"  [{r['status']}] {r['group']} {r['name'][:30]} {r['path']}")
    for r in brk:
        print(f"  [깨진 {len(r['broken'])}] {r['group']} {r['name'][:30]} → " + " | ".join(b.split('/')[-1][:30] for b in r["broken"][:4]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
