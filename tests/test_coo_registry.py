# -*- coding: utf-8 -*-
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import coo_registry as R


def test_registry_loads_shared_file():
    reg = R.load_registry()
    assert isinstance(reg.get("modules"), list)
    assert len(reg["modules"]) >= 1


def test_registry_schema_valid_for_coo_modules():
    reg = R.load_registry()
    assert R.validate_registry(reg) == []


def test_cto_modules_preserved_not_touched_by_coo_consumer():
    # 2026-07-24 웰리 승인 병합(34→26): cto-aide-gap-detector→ceo-gm-aide 흡수,
    # cto-check-gas→coo-check-status 흡수(둘 다 등록부 삭제, 코드 불변). 픽스처를
    # 현재 생존 cto-* id로 갱신 — 테스트 취지(coo 소비자가 타 도메인 모듈을
    # 훼손하지 않는지)는 그대로.
    reg = R.load_registry()
    ids = [m["id"] for m in reg["modules"]]
    # 2026-07-31: cto-inquiry-read-snapshot 삭제(중복 등록). 같은 GAS 호출·같은 산출물
    # (inquiry_snapshot_*.json)·같은 3분 예약작업을 cpo-inquiry-snapshot 과 둘이 등록하고
    # 있었다. 하트비트를 실제로 남기는 쪽은 cpo 하나뿐이었다 — cto 항목은 종이 등록이었다.
    assert "cto-automation-health" in ids
    assert "cto-weekly-page-hygiene" in ids
    assert "cto-inquiry-read-snapshot" not in ids


def test_iter_coo_returns_only_coo_owned_modules():
    reg = R.load_registry()
    coo_mods = R.iter_coo(reg)
    assert coo_mods, "coo 모듈이 하나도 없음"
    assert all(m["owner_role"] == "coo" for m in coo_mods)
    assert all(not m["id"].startswith("cto-") for m in coo_mods)


def test_pilot_check_status_enabled_and_wired():
    reg = R.load_registry()
    m = R.get_module(reg, "coo-check-status")
    assert m is not None
    assert m["owner_role"] == "coo"
    assert m["enabled"] is True
    assert m["notify_spec"]["daily"] is True
    assert m["data_source"]["kind"] == "gas"


def test_iter_enabled_returns_all_enabled_coo_modules():
    reg = R.load_registry()
    enabled = {m["id"] for m in R.iter_enabled(reg)}
    # coo-ops-fill-board 는 GM 지시 2026-08-29 로 전체 폐기(모듈·스크립트·예약·보드 전부 삭제).
    # 이 목록은 그 전부터 등록부와 어긋나 있었다 — coo-schedule-ssot·coo-monthly-ops 는 등록부에
    # 없는 id 였고 coo-reception(2026-08-13 독립)은 빠져 있었다. 실제 등록부에 맞춘다.
    assert enabled == {"coo-check-status", "coo-work-approval", "coo-reception", "coo-notice"}


def test_daily_trend_parses_and_dedups_by_date(tmp_path, monkeypatch):
    """운영 추이 원장 — 마감 넘김 건수를 문구에서 집고, 같은 날은 줄을 갈아 끼운다.

    이 원장이 끊기면 '나아지고 있나'에 답할 수 없으므로(GM 2026-08-29) 최소 검사를 남긴다.
    """
    import coo_report_line as C

    monkeypatch.setattr(C, "_TREND_PATH", str(tmp_path / "coo_daily.jsonl"))
    detail = "■ 진행 중 — 활성 43건\n■ 마감 넘긴 일 — 3건 · 어떤 일(운영 정책·83일 초과)"
    rec = C.append_daily_trend(detail)
    assert rec["업무_마감넘김"] == 3
    C.append_daily_trend(detail)                      # 같은 날 두 번
    lines = (tmp_path / "coo_daily.jsonl").read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1, "같은 날짜는 한 줄이어야 한다"
    # 문구가 없으면 0 으로 메우지 않고 비운다(약속 L25 — 안 쌓인 날과 진짜 0 을 구분)
    assert C.append_daily_trend("")["업무_마감넘김"] is None


def test_workapproval_module_enabled_and_wired():
    reg = R.load_registry()
    m = R.get_module(reg, "coo-work-approval")
    assert m is not None
    assert m["owner_role"] == "coo"
    assert m["enabled"] is True
    assert m["notify_spec"]["daily"] is True
    assert m["data_source"]["kind"] == "gas"
