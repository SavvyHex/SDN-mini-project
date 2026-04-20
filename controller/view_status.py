#!/usr/bin/env python3
"""
Alert & Status Viewer
---------------------
Usage (inside controller container or with mounted /logs and /alerts):
    python3 view_status.py               # live tail mode
    python3 view_status.py --once        # print current state and exit
    python3 view_status.py --alerts      # print alert summary only
"""

import json
import os
import sys
import time
import argparse
import datetime
from collections import defaultdict

LOG_DIR = os.environ.get("LOG_DIR", "/logs")
ALERT_DIR = os.environ.get("ALERT_DIR", "/alerts")

RESET  = "\033[0m"
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"


def read_jsonl(path):
    """Read all JSON lines from a file; return list of dicts."""
    entries = []
    if not os.path.exists(path):
        return entries
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def print_port_events():
    events = read_jsonl(f"{LOG_DIR}/port_events.json")
    if not events:
        print(f"{YELLOW}No port events logged yet.{RESET}")
        return
    print(f"\n{BOLD}{CYAN}══ Port Events (latest 20) ══{RESET}")
    header = f"{'Timestamp':<28} {'DPID':<8} {'Port':<6} {'Name':<12} {'State':<6} {'Reason'}"
    print(header)
    print("─" * len(header))
    for e in events[-20:]:
        state_col = GREEN + "UP  " + RESET if e.get("state") == "up" else RED + "DOWN" + RESET
        print(
            f"{e.get('timestamp',''):<28} "
            f"{e.get('dpid',''):<8} "
            f"{e.get('port_no',''):<6} "
            f"{e.get('port_name',''):<12} "
            f"{state_col:<6} "
            f"{e.get('reason','')}"
        )


def print_alerts():
    alerts = read_jsonl(f"{ALERT_DIR}/alerts.json")
    if not alerts:
        print(f"{GREEN}No alerts generated.{RESET}")
        return
    print(f"\n{BOLD}{RED}══ Alerts ({len(alerts)} total) ══{RESET}")
    header = f"{'Timestamp':<28} {'DPID':<8} {'Port':<6} {'State':<6} {'Reason'}"
    print(header)
    print("─" * len(header))
    for a in alerts:
        print(
            f"{a.get('timestamp',''):<28} "
            f"{a.get('dpid',''):<8} "
            f"{a.get('port_no',''):<6} "
            f"{RED}{a.get('state',''):<6}{RESET} "
            f"{a.get('reason','')}"
        )


def print_latest_stats():
    """Show most recent stats snapshot per (dpid, port)."""
    entries = read_jsonl(f"{LOG_DIR}/port_stats.json")
    if not entries:
        return
    # Keep only latest per (dpid, port_no)
    latest = {}
    for e in entries:
        key = (e.get("dpid"), e.get("port_no"))
        latest[key] = e

    print(f"\n{BOLD}{CYAN}══ Latest Port Statistics ══{RESET}")
    header = (
        f"{'DPID':<8} {'Port':<6} {'RX pkts':>10} {'TX pkts':>10} "
        f"{'RX bytes':>12} {'TX bytes':>12} {'RX drop':>8} {'TX drop':>8}"
    )
    print(header)
    print("─" * len(header))
    for (dpid, port_no), e in sorted(latest.items()):
        print(
            f"{dpid:<8} {port_no:<6} "
            f"{e.get('rx_packets',0):>10} {e.get('tx_packets',0):>10} "
            f"{e.get('rx_bytes',0):>12} {e.get('tx_bytes',0):>12} "
            f"{e.get('rx_dropped',0):>8} {e.get('tx_dropped',0):>8}"
        )


def live_tail():
    """Refresh the display every 5 seconds."""
    try:
        while True:
            os.system("clear")
            print(f"{BOLD}SDN Port Status Monitor – {datetime.datetime.utcnow().isoformat()}Z{RESET}")
            print_port_events()
            print_latest_stats()
            print_alerts()
            print(f"\n{YELLOW}[Refreshing every 5s – Ctrl+C to quit]{RESET}")
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nExiting.")


def main():
    parser = argparse.ArgumentParser(description="SDN Port Status Viewer")
    parser.add_argument("--once", action="store_true", help="Print once and exit")
    parser.add_argument("--alerts", action="store_true", help="Print alerts only and exit")
    args = parser.parse_args()

    if args.alerts:
        print_alerts()
    elif args.once:
        print_port_events()
        print_latest_stats()
        print_alerts()
    else:
        live_tail()


if __name__ == "__main__":
    main()