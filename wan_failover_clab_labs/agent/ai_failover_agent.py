#!/usr/bin/env python3
"""
AI-Driven WAN Failover Agent
Uses an LLM (Generative AI) to analyze network telemetry and make
intelligent routing decisions.
"""

import subprocess
import time
import logging
import re
import os
import google.generativeai as genai
from datetime import datetime

# ── Setup AI Agent ──────────────────────────────────────
# Ensure you export your API key in your terminal before running:
# export GEMINI_API_KEY="your_api_key_here"
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
model = genai.GenerativeModel('gemini-1.5-flash')

# ── Logging setup ──────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(), logging.FileHandler('ai_failover.log')]
)
log = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────
CONFIG = {
    "primary_link": {"name": "WAN-LINK-1-PRIMARY", "router1_ip": "10.0.0.1", "router2_ip": "10.0.0.2"},
    "backup_link": {"name": "WAN-LINK-2-BACKUP", "router1_ip": "10.0.1.1", "router2_ip": "10.0.1.2"},
    "router1_container": "clab-wan-failover-router1",
    "router2_container": "clab-wan-failover-router2",
    "destination_network": "192.168.2.0/24",
    "check_interval": 10,  # Increased slightly to give AI time to think
    "ping_count": 3,
    "ping_timeout": 2,
}

state = {
    "active_link": "primary",
    "total_failovers": 0
}

# ── Helper functions ───────────────────────────────────
def run_in_container(container, command):
    cmd = f"sudo docker exec {container} {command}"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def get_ping_metrics(container, target_ip):
    """Pings the target and extracts packet loss and average latency."""
    count = CONFIG["ping_count"]
    timeout = CONFIG["ping_timeout"]
    cmd = f"ping -c {count} -W {timeout} {target_ip}"
    code, out, err = run_in_container(container, cmd)
    
    # Parse packet loss
    loss_match = re.search(r'(\d+)% packet loss', out)
    packet_loss = int(loss_match.group(1)) if loss_match else 100
    
    # Parse latency (Fixed regex to support Alpine Linux in the FRR container)
    rtt_match = re.search(r'min/avg/max.*? = [\d\.]+/(.*?)/', out)
    
    if packet_loss == 100:
        avg_latency = 0.0  # Latency doesn't exist if all packets drop
    else:
        avg_latency = float(rtt_match.group(1)) if rtt_match else 999.0
        
    return packet_loss, avg_latency



def execute_routing_change(action):
    """Executes the physical routing changes based on AI decisions."""
    r1 = CONFIG["router1_container"]
    r2 = CONFIG["router2_container"]
    dest = CONFIG["destination_network"]
    
    primary_gw_r1, backup_gw_r1 = CONFIG["primary_link"]["router2_ip"], CONFIG["backup_link"]["router2_ip"]
    primary_gw_r2, backup_gw_r2 = CONFIG["primary_link"]["router1_ip"], CONFIG["backup_link"]["router1_ip"]

    if action == "FAILOVER" and state["active_link"] == "primary":
        log.warning("🤖 AI AGENT TRIGGERED FAILOVER TO BACKUP!")
        run_in_container(r1, f"ip route del {dest} via {primary_gw_r1}")
        run_in_container(r1, f"ip route add {dest} via {backup_gw_r1} metric 5")
        run_in_container(r2, f"ip route del 192.168.1.0/24 via {primary_gw_r2}")
        run_in_container(r2, f"ip route add 192.168.1.0/24 via {backup_gw_r2} metric 5")
        state["active_link"] = "backup"
        state["total_failovers"] += 1

    elif action == "FAILBACK" and state["active_link"] == "backup":
        log.info("🤖 AI AGENT TRIGGERED FAILBACK TO PRIMARY!")
        run_in_container(r1, f"ip route del {dest} via {backup_gw_r1}")
        run_in_container(r1, f"ip route add {dest} via {primary_gw_r1} metric 10")
        run_in_container(r2, f"ip route del 192.168.1.0/24 via {backup_gw_r2}")
        run_in_container(r2, f"ip route add 192.168.1.0/24 via {primary_gw_r2} metric 10")
        state["active_link"] = "primary"

def ask_ai_for_decision(packet_loss, latency):
    """Prompts the LLM with strict boolean logic to force the correct routing decision."""
    prompt = f"""
    You are a strictly logical network routing AI. Read the State and apply the Rules precisely.

    State:
    - Active Link: {state['active_link']}
    - Packet Loss: {packet_loss}%
    - Latency: {latency} ms

    Rules:
    - Return "FAILOVER" if Active Link is 'primary' AND (Packet Loss >= 50 OR Latency >= 300).
    - Return "FAILBACK" if Active Link is 'backup' AND (Packet Loss == 0 AND Latency < 100).
    - Return "STAY" for any other condition.

    Based on the Rules, output exactly ONE word (FAILOVER, FAILBACK, or STAY):
    """
    
    try:
        response = model.generate_content(prompt)
        decision = response.text.strip().upper()
        
        # Parse the strict output
        if "FAILOVER" in decision: return "FAILOVER"
        if "FAILBACK" in decision: return "FAILBACK"
        return "STAY"
    except Exception as e:
        log.error(f"AI API Error: {e}")
        return "STAY" # Failsafe

# ── Main monitoring loop ───────────────────────────────
def main():
    log.info("🤖 AI WAN Failover Agent started!")
    if not os.environ.get("GEMINI_API_KEY"):
        log.error("Please set the GEMINI_API_KEY environment variable!")
        return

    while True:
        try:
            # Gather telemetry from the primary link
            loss, latency = get_ping_metrics(
                CONFIG["router1_container"],
                CONFIG["primary_link"]["router2_ip"]
            )
            
            log.info(f"Telemetry -> Primary Loss: {loss}%, Latency: {latency}ms")
            
            # Ask the AI Agent to decide
            ai_decision = ask_ai_for_decision(loss, latency)
            log.info(f"AI Decision: {ai_decision}")
            
            # Execute the decision
            execute_routing_change(ai_decision)
            
            time.sleep(CONFIG["check_interval"])

        except KeyboardInterrupt:
            log.info("\nAI Agent stopped by user.")
            break
        except Exception as e:
            log.error(f"System error: {e}")
            time.sleep(CONFIG["check_interval"])

if __name__ == "__main__":
    main()