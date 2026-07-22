#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
schedule_generator.py — 스케줄 SSOT 생성기 (Phase1: --plan 미리보기 전용)

배9640 시스템 단순화 ③. 문제: 새 자동화 1개 추가에 py+bat+숨김vbs+schtasks+등록부
5파일 수작업. 목표: status/notify_registry.json 의 선언(gen 블록)에서 vbs·bat·schtasks
명령을 '생성'하는 단일 소스.

★Phase1 안전 계약: --plan(미리보기)만 구현. 디스크에 vbs/bat 쓰기·schtasks 등록/변경
0. 순수 읽기 + 표준출력. --apply 는 의도적으로 미구현(Phase2에서 GM 결재 후).

gen 블록 스키마 (notify_registry.json 항목에 선택적 append · 기존 소비자는 무시):
  "gen": {
    "task": "Wellperion-NorthStar-0630",     # 예약작업 이름(기존명 그대로여야 등가)
    "script": "scripts/northstar_recommender.py",
    "args": "",                               # 선택
    "py": "C:\\Python314\\python.exe",       # 선택(기본 C:/Python314/python.exe)
    "schedule": {"kind": "daily", "at": "06:30"},   # daily|weekly{dow}|monthly{day}|interval{every}
    "log": "logs/northstar_recommender.log",
    "hidden": true                            # true=콘솔숨김 vbs 래퍼 생성
  }
"""
import json
import os
import sys
import argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REG = os.path.join(ROOT, "status", "notify_registry.json")
DEFAULT_PY = r"C:\Python314\python.exe"


def _items(reg):
    return reg.get("items", reg) if isinstance(reg, dict) else reg


def desired_bat(gen):
    """utf-8 콘솔 래퍼 bat 내용(기존 launchers/*.bat 패턴)."""
    py = gen.get("py", DEFAULT_PY)
    script = gen["script"].replace("/", "\\")
    args = gen.get("args", "")
    log = gen.get("log", "logs\\%s.log" % os.path.splitext(os.path.basename(script))[0]).replace("/", "\\")
    return (
        "@echo off\r\n"
        "cd /d %s\r\n"
        "set PYTHONIOENCODING=utf-8\r\n"
        '"%s" -u "%s" %s >> %s 2>&1\r\n' % (ROOT, py, script, args, log)
    ).rstrip() + "\r\n"


def desired_vbs(bat_path):
    """콘솔숨김(style 0) vbs 래퍼(기존 launchers/*_hidden.vbs 패턴)."""
    return (
        "' Wellperion hidden launcher (no console window) — schedule_generator 생성\r\n"
        'CreateObject("WScript.Shell").Run "cmd /c ""%s""", 0, False\r\n' % bat_path
    )


def desired_schtasks(gen, run_target):
    """schtasks 등록 명령(등가 확인용 · Phase1은 출력만)."""
    task = gen["task"]
    sch = gen.get("schedule", {})
    kind = sch.get("kind", "daily")
    if kind == "daily":
        sc = "/SC DAILY /ST %s" % sch.get("at", "09:00")
    elif kind == "weekly":
        sc = "/SC WEEKLY /D %s /ST %s" % (sch.get("dow", "MON"), sch.get("at", "09:00"))
    elif kind == "monthly":
        sc = "/SC MONTHLY /D %s /ST %s" % (sch.get("day", "1"), sch.get("at", "09:00"))
    elif kind == "interval":
        sc = "/SC MINUTE /MO %s" % sch.get("every", "5")
    else:
        sc = "/SC DAILY /ST 09:00"
    return 'schtasks /Create /TN "%s" /TR "\\"%s\\"" %s /RL HIGHEST /F' % (task, run_target, sc)


def plan(reg, only=None):
    n = 0
    for it in _items(reg):
        gen = it.get("gen")
        if not gen:
            continue
        if it.get("trigger") != "schtasks" or it.get("state") != "live":
            continue
        if only and it.get("id") != only:
            continue
        n += 1
        base = os.path.splitext(os.path.basename(gen["script"]))[0]
        bat_path = os.path.join(ROOT, "launchers", base + ".bat")
        vbs_path = os.path.join(ROOT, "launchers", base + "_hidden.vbs")
        run_target = vbs_path if gen.get("hidden") else bat_path
        print("=" * 66)
        print("[%s]  task=%s" % (it.get("id"), gen.get("task")))
        print("  desired bat  → %s" % bat_path)
        print("  desired vbs  → %s" % vbs_path)
        print("  desired schtasks:")
        print("    " + desired_schtasks(gen, run_target if gen.get("hidden") else bat_path))
        # actual 대조: 기존 런처 파일이 있으면 존재/경로만 비교(diff는 사람이 확인)
        print("  actual vbs 존재? %s" % ("YES " + vbs_path if os.path.exists(vbs_path) else "없음(신규)"))
        # 기존 다른 이름의 런처가 있을 수 있어 등가여부는 사람이 최종 확인
    print("=" * 66)
    print("gen 선언 항목: %d개 · ★디스크/예약작업 변경 0 (미리보기 전용)" % n)
    if n == 0:
        print("(gen 블록 선언된 항목 없음)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true", help="미리보기(변경 0). 기본.")
    ap.add_argument("--apply", action="store_true", help="Phase2 예정 — 현재 차단됨")
    ap.add_argument("--id", default=None, help="특정 항목만")
    a = ap.parse_args()
    if a.apply:
        print("★ --apply 는 Phase1에서 차단됨(디스크/예약작업 변경 금지). GM 결재 후 Phase2에서 구현.")
        sys.exit(2)
    reg = json.load(open(REG, encoding="utf-8"))
    plan(reg, only=a.id)


if __name__ == "__main__":
    main()
