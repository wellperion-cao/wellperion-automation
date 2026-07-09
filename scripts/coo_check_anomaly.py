# -*- coding: utf-8 -*-
"""COO 모듈 이상 즉시 텔레그램 알림 (레지스트리 anomaly_immediate 구동). 기본 dry-run."""
import argparse
import coo_registry as R


def run_anomaly_check(reg=None, fetch_fn=None, notifier=None, dry_run=True) -> dict:
    reg = reg or R.load_registry()
    fetch = fetch_fn or R._http_get_json
    alerts = []
    sent = 0
    for m in R.iter_enabled(reg):
        if not m["telegram"].get("anomaly_immediate"):
            continue
        try:
            st = R.fetch_check_status(m, fetch_fn=fetch)
        except Exception:
            continue
        if not st["anomaly"]:
            continue
        msg = f"⚠ <b>{m['name']} 이상</b>\n" + "\n".join(f"• {r}" for r in st["reasons"])
        alerts.append(msg)
        if not dry_run and notifier is not None:
            notifier.send(msg)
            sent += 1
    return {"alerts": alerts, "sent": sent}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--send", action="store_true", help="실발송(기본=dry-run)")
    args = ap.parse_args()
    notifier = None
    if args.send:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "wellperion-agents"))
        from telegram_notifier import TelegramNotifier
        notifier = TelegramNotifier()
    res = run_anomaly_check(notifier=notifier, dry_run=not args.send)
    print(f"이상 {len(res['alerts'])}건 · 발송 {res['sent']}건")
    for a in res["alerts"]:
        print("---\n" + a)


if __name__ == "__main__":
    main()
