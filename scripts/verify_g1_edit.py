"""
G1 edit bug verification (a2758c9 fix)
Scenario A: endDate update -> refetch retention
Scenario B: status=complete -> refetch retention
Test item only - real data untouched
"""
import urllib.request
import urllib.parse
import json
import time
import sys
import io

# Force UTF-8 stdout on Windows CP949
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

GAS_URL = (
    "https://script.google.com/macros/s/"
    "AKfycbxDwFkrxK1YIaEoSNcuw2MiHiZQ-7o5N6311ytksSyeEd86ZFOhLknOWqQgNArQvZ-7/exec"
)
TODAY = "2026-06-07"
TEST_ID = "verify-g1-edit-" + str(int(time.time()))
TEST_TITLE = "[TEST] G1 edit verify (auto-delete)"

results = []


def gas_call(params, label):
    qs = urllib.parse.urlencode(params)
    url = GAS_URL + "?" + qs
    req = urllib.request.Request(url, headers={"User-Agent": "WP-Verify/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode("utf-8")
        data = json.loads(body)
        return data
    except Exception as e:
        print(f"  [HTTP ERROR] {label}: {e}")
        return None


def check(label, actual, expected):
    ok = str(actual).strip() == str(expected).strip()
    tag = "PASS" if ok else "FAIL"
    print(f"  [{tag}] {label}: expected={repr(expected)}, got={repr(actual)}")
    results.append((label, ok))
    return ok


def find_row(rows, tid):
    for r in rows:
        if str(r.get("id", "")).strip() == str(tid).strip():
            return r
    return None


def get_rows(res):
    if not res:
        return []
    return res.get("data") or res.get("todos") or []


# ── STEP 1: add test item ──────────────────────────────
print("\n[STEP 1] Add test item")
add_res = gas_call(
    {
        "action": "todo_add",
        "id": TEST_ID,
        "title": TEST_TITLE,
        "owner": "verify-bot",
        "category": "[3] test",
        "content": "auto-delete after verify",
        "startDate": TODAY,
        "endDate": "",
        "status": "진행중",
        "creator": "verify-bot",
    },
    "todo_add",
)
add_ok = add_res.get("ok") if add_res else False
print(f"  add response: ok={add_ok}")
time.sleep(5)

# ── STEP 2: confirm item exists (retry 3x for GAS cache) ──
print("\n[STEP 2] Confirm item in todo_list (retry x3)")
row1 = None
for attempt in range(3):
    res = gas_call(
        {"action": "todo_list", "_": str(int(time.time()))},
        f"todo_list attempt {attempt + 1}",
    )
    rows = get_rows(res)
    row1 = find_row(rows, TEST_ID)
    if row1:
        print(f"  found on attempt {attempt + 1}")
        break
    print(f"  attempt {attempt + 1}: not found yet, retrying in 4s...")
    time.sleep(4)

check("item_exists", bool(row1), True)
if row1:
    print(f"  status={row1.get('상태')}, endDate={row1.get('종료일')}")
if not row1:
    print("  FATAL: item not found after retries — GAS add may have failed")
    sys.exit(1)

# ── STEP 3: Scenario A — update endDate ───────────────
print("\n[STEP 3] Scenario A: update endDate -> 2026-06-30")
END_NEW = "2026-06-30"
upd_a = gas_call(
    {"action": "todo_update", "id": TEST_ID, "endDate": END_NEW},
    "todo_update(endDate)",
)
print(f"  update response: ok={upd_a.get('ok') if upd_a else None}")
time.sleep(5)

res_a = gas_call(
    {"action": "todo_list", "_": str(int(time.time()))}, "todo_list(after A)"
)
row_a = find_row(get_rows(res_a), TEST_ID)
actual_end = str(row_a.get("종료일", "") if row_a else "").strip()
end_ok = END_NEW in actual_end or actual_end.startswith("2026-06-30")
tag = "PASS" if end_ok else "FAIL"
print(f"  [{tag}] endDate_retained: expected contains '2026-06-30', got={repr(actual_end)}")
results.append(("endDate_retained", end_ok))

# ── STEP 4: Scenario B — update status=완료 ───────────
print("\n[STEP 4] Scenario B: update status -> 완료")
upd_b = gas_call(
    {"action": "todo_update", "id": TEST_ID, "status": "완료"},
    "todo_update(status=완료)",
)
print(f"  update response: ok={upd_b.get('ok') if upd_b else None}")
time.sleep(5)

res_b = gas_call(
    {"action": "todo_list", "_": str(int(time.time()))}, "todo_list(after B)"
)
row_b = find_row(get_rows(res_b), TEST_ID)
actual_st = str(row_b.get("상태", "") if row_b else "").strip()
check("status_retained", actual_st, "완료")

# ── STEP 5: delete test item ──────────────────────────
print("\n[STEP 5] Delete test item (cleanup)")
del_res = gas_call(
    {"action": "todo_delete", "id": TEST_ID},
    "todo_delete",
)
print(f"  delete response: ok={del_res.get('ok') if del_res else None}")
time.sleep(5)

res_d = gas_call(
    {"action": "todo_list", "_": str(int(time.time()))}, "todo_list(after delete)"
)
row_d = find_row(get_rows(res_d), TEST_ID)
check("item_deleted", row_d is None, True)

# ── Final summary ─────────────────────────────────────
print("\n" + "=" * 50)
total = len(results)
passed = sum(1 for _, ok in results if ok)
print(f"Result: {passed}/{total} PASS")
for label, ok in results:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")

if passed == total:
    print("\nFINAL: PASS — GAS round-trip all assertions passed")
    sys.exit(0)
else:
    print("\nFINAL: FAIL — some assertions failed")
    sys.exit(1)
