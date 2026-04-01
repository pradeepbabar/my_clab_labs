#!/usr/bin/env python3
"""
WAN Failover Agent
Monitors two WAN links and automatically switches
static routes when primary link goes down.
"""

import subprocess
import time
import logging
import yaml
import os
import requests
from datetime import datetime

# ── Logging setup ──────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('failover.log')
    ]
)
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────
CONFIG = {
    "primary_link": {
        "name": "WAN-LINK-1-PRIMARY",
        "router1_ip": "10.0.0.1",
        "router2_ip": "10.0.0.2",
        "interface": "eth1"
    },
    "backup_link": {
        "name": "WAN-LINK-2-BACKUP",
        "router1_ip": "10.0.1.1",
        "router2_ip": "10.0.1.2",
        "interface": "eth2"
    },
    "router1_container": "clab-wan-failover-router1",
    "router2_container": "clab-wan-failover-router2",
    "destination_network": "192.168.2.0/24",
    "check_interval": 5,       # seconds between checks
    "failure_threshold": 3,    # failed pings before failover
    "recovery_threshold": 3,   # successful pings before failback
    "ping_count": 3,
    "ping_timeout": 2,
#    "telegram_token": "",      # add your bot token here
#    "telegram_chat_id": "",    # add your chat ID here
}

# ── State ──────────────────────────────────────────────
state = {
    "active_link": "primary",
    "primary_fail_count": 0,
    "primary_ok_count": 0,
    "last_failover": None,
    "total_failovers": 0
}

# ── Helper functions ───────────────────────────────────

def run_in_container(container, command):
    """Run a command inside a ContainerLab container."""
    cmd = f"sudo docker exec {container} {command}"
    result = subprocess.run(
        cmd, shell=True,
        capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr


def ping_link(container, target_ip):
    """Ping target IP from inside container."""
    count = CONFIG["ping_count"]
    timeout = CONFIG["ping_timeout"]
    cmd = f"ping -c {count} -W {timeout} {target_ip}"
    code, out, err = run_in_container(container, cmd)
    return code == 0


def get_active_route(container, destination):
    """Get the currently active route for destination."""
    cmd = f"ip route show {destination}"
    code, out, err = run_in_container(container, cmd)
    return out.strip()


def add_route(container, destination, gateway, metric):
    """Add a static route in the container."""
    cmd = f"ip route add {destination} via {gateway} metric {metric}"
    code, out, err = run_in_container(container, cmd)
    return code == 0


def del_route(container, destination, gateway):
    """Delete a static route in the container."""
    cmd = f"ip route del {destination} via {gateway}"
    code, out, err = run_in_container(container, cmd)
    return code == 0

'''
def send_telegram(message):
    """Send Telegram notification."""
    token = CONFIG.get("telegram_token")
    chat_id = CONFIG.get("telegram_chat_id")
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": chat_id,
            "text": f"🔁 WAN FAILOVER AGENT\n{message}",
            "parse_mode": "HTML"
        }, timeout=5)
    except Exception as e:
        log.warning(f"Telegram notification failed: {e}")
'''

def do_failover_to_backup():
    """Switch traffic from primary to backup link."""
    log.warning("=" * 50)
    log.warning("FAILOVER TRIGGERED — Switching to BACKUP link!")
    log.warning("=" * 50)

    r1 = CONFIG["router1_container"]
    r2 = CONFIG["router2_container"]
    dest = CONFIG["destination_network"]
    primary_gw_r1 = CONFIG["primary_link"]["router2_ip"]  # 10.0.0.2
    backup_gw_r1  = CONFIG["backup_link"]["router2_ip"]   # 10.0.1.2

    # On Router1 — lower backup metric to make it preferred
    del_route(r1, dest, primary_gw_r1)
    add_route(r1, dest, backup_gw_r1, 5)  # metric 5 = now preferred
    log.info(f"Router1: Route switched to backup gateway {backup_gw_r1}")

    # On Router2 — switch return path too
    primary_gw_r2 = CONFIG["primary_link"]["router1_ip"]  # 10.0.0.1
    backup_gw_r2  = CONFIG["backup_link"]["router1_ip"]   # 10.0.1.1
    del_route(r2, "192.168.1.0/24", primary_gw_r2)
    add_route(r2, "192.168.1.0/24", backup_gw_r2, 5)
    log.info(f"Router2: Route switched to backup gateway {backup_gw_r2}")

    state["active_link"] = "backup"
    state["last_failover"] = datetime.now().isoformat()
    state["total_failovers"] += 1

    msg = (
        f"⚠️ PRIMARY link DOWN!\n"
        f"Switched to BACKUP link\n"
        f"Time: {state['last_failover']}\n"
        f"Total failovers: {state['total_failovers']}"
    )
    log.warning(msg)
#    send_telegram(msg)


def do_failback_to_primary():
    """Switch traffic back to primary link when recovered."""
    log.info("=" * 50)
    log.info("FAILBACK — Primary link recovered! Switching back.")
    log.info("=" * 50)

    r1 = CONFIG["router1_container"]
    r2 = CONFIG["router2_container"]
    dest = CONFIG["destination_network"]
    primary_gw_r1 = CONFIG["primary_link"]["router2_ip"]
    backup_gw_r1  = CONFIG["backup_link"]["router2_ip"]

    # Restore primary as preferred on Router1
    del_route(r1, dest, backup_gw_r1)
    add_route(r1, dest, primary_gw_r1, 10)
    add_route(r1, dest, backup_gw_r1, 20)
    log.info(f"Router1: Route restored to primary gateway {primary_gw_r1}")

    # Restore on Router2
    primary_gw_r2 = CONFIG["primary_link"]["router1_ip"]
    backup_gw_r2  = CONFIG["backup_link"]["router1_ip"]
    del_route(r2, "192.168.1.0/24", backup_gw_r2)
    add_route(r2, "192.168.1.0/24", primary_gw_r2, 10)
    add_route(r2, "192.168.1.0/24", backup_gw_r2, 20)
    log.info(f"Router2: Route restored to primary gateway {primary_gw_r2}")

    state["active_link"] = "primary"
    state["primary_fail_count"] = 0

    msg = (
        f"✅ PRIMARY link RECOVERED!\n"
        f"Traffic switched back to primary\n"
        f"Time: {datetime.now().isoformat()}"
    )
    log.info(msg)
#    send_telegram(msg)


def print_status():
    """Print current status to terminal."""
    primary_ip = CONFIG["primary_link"]["router2_ip"]
    active = state["active_link"].upper()
    fails = state["primary_fail_count"]
    total = state["total_failovers"]
    print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
          f"Active: {active} | "
          f"Primary fail count: {fails} | "
          f"Total failovers: {total}   ", end="", flush=True)


# ── Main monitoring loop ───────────────────────────────

def main():
    log.info("WAN Failover Agent started!")
    log.info(f"Monitoring primary link: {CONFIG['primary_link']['name']}")
    log.info(f"Backup link: {CONFIG['backup_link']['name']}")
    log.info(f"Check interval: {CONFIG['check_interval']}s")
    log.info(f"Failure threshold: {CONFIG['failure_threshold']} consecutive fails")
#    send_telegram("🚀 WAN Failover Agent started and monitoring links!")

    while True:
        try:
            primary_up = ping_link(
                CONFIG["router1_container"],
                CONFIG["primary_link"]["router2_ip"]
            )

            if state["active_link"] == "primary":
                if not primary_up:
                    state["primary_fail_count"] += 1
                    log.warning(
                        f"Primary link FAIL "
                        f"({state['primary_fail_count']}"
                        f"/{CONFIG['failure_threshold']})"
                    )
                    if state["primary_fail_count"] >= CONFIG["failure_threshold"]:
                        do_failover_to_backup()
                else:
                    state["primary_fail_count"] = 0

            elif state["active_link"] == "backup":
                if primary_up:
                    state["primary_ok_count"] += 1
                    log.info(
                        f"Primary link recovering... "
                        f"({state['primary_ok_count']}"
                        f"/{CONFIG['recovery_threshold']})"
                    )
                    if state["primary_ok_count"] >= CONFIG["recovery_threshold"]:
                        do_failback_to_primary()
                        state["primary_ok_count"] = 0
                else:
                    state["primary_ok_count"] = 0

            print_status()
            time.sleep(CONFIG["check_interval"])

        except KeyboardInterrupt:
            log.info("\nAgent stopped by user.")
            break
        except Exception as e:
            log.error(f"Agent error: {e}")
            time.sleep(CONFIG["check_interval"])


if __name__ == "__main__":
    main()