```markdown
# 🤖 AI-Driven WAN Failover Agent

An autonomous AI agent that manages Wide Area Network (WAN) failover in a simulated Hub-and-Spoke environment. 

Instead of relying on traditional, rigid SLA tracking scripts (e.g., "failover if 3 pings drop"), this project uses an LLM (Google Gemini 2.5 Flash) to act as a virtual network engineer. It analyzes real-time network telemetry to make intelligent, dynamic routing decisions.

---

## 💡 Why Build This? (Motivation)

While dynamic routing protocols (like BGP or OSPF) are undeniably the best approach for WAN failover, the reality is that many firms still rely on static routing for Hub-to-Spoke route advertisement due to legacy constraints, strict security policies, or architectural simplicity. 

I decided to use this common real-world networking constraint as an opportunity to get my hands dirty with Artificial Intelligence. While this AI-driven static failover agent isn't perfect, it serves as a practical, hands-on first leap into bridging the gap between traditional Network Engineering and Generative AI!

---

## 📖 What It Does

This project simulates a Hub-and-Spoke network topology with dual WAN links (Primary and Backup). An external Python AI Agent constantly monitors the health of the primary link. 

If the primary link degrades or fails, the AI Agent evaluates the telemetry (packet loss and latency) and autonomously rewrites the static routing tables on the virtual routers to seamlessly shift traffic to the backup link. Once the primary link stabilizes, the AI safely fails the traffic back.

## 🧠 How It Works (Architecture & Flow)

1. **The Network (Containerlab):** * **Routers:** Two Linux containers running [FRRouting (FRR)](https://frrouting.org/) act as the Hub and Spoke routers.
   * **Endpoints:** Two Alpine Linux containers act as the `hub-server` (172.16.11.10) and `spoke-host` (192.168.10.9).
   * **Links:** The routers are connected by two distinct point-to-point links (Primary and Backup).
2. **The Telemetry:** The Python agent continuously sends ICMP echo requests across the primary link and parses the raw output to extract packet loss percentages and average latency metrics.
3. **The AI Decision Engine:** The agent feeds this telemetry into Google's Gemini LLM using strict Boolean logic prompts. 
4. **Dynamic Routing:** Based on the AI's response (`FAILOVER`, `FAILBACK`, or `STAY`), the Python script uses `docker exec` to inject or delete `ip route` commands inside the FRR containers, altering the path of the internal LAN traffic.

---

## ⚙️ Prerequisites

To run this lab locally, you will need a Linux environment (Ubuntu/Debian recommended) with the following installed:

* **Docker:** Engine to run the containers.
* **[Containerlab](https://containerlab.dev/install/):** Network topology orchestration tool.
* **Python 3.8+:** With the `python3-venv` package installed.
* **Google Gemini API Key:** You can get a free API key from [Google AI Studio](https://aistudio.google.com/).

---

## 🚀 Step-by-Step Deployment Guide

Follow these steps to deploy the network, start the AI agent, and test the failover mechanism.

### Step 1: Deploy the Network Topology
Ensure you are in the root directory of the project where `topology.clab.yml` is located. Deploy the virtual network using Containerlab:

```bash
sudo clab deploy -t topology.clab.yml
```
*Wait for Containerlab to pull the FRR and Alpine images and wire the virtual interfaces together.*

### Step 2: Setup the Python Virtual Environment
Navigate to the `agent` directory to isolate your Python dependencies:

```bash
cd agent
python3 -m venv venv
```

Activate the virtual environment:
```bash
source venv/bin/activate
```

Install the required Python packages (including the Google Generative AI SDK):
```bash
pip install -r requirements.txt
```

### Step 3: Start the AI Failover Agent
Export your Gemini API key into your terminal environment so the script can authenticate:

```bash
export GEMINI_API_KEY="your_actual_api_key_here"
```

Run the AI agent:
```bash
python3 ai_failover_agent.py
```
*Leave this terminal window open. You will see the agent begin logging the telemetry and the AI's routing decisions.*

### Step 4: Test the Failover
Open a **new terminal window** to simulate a failure and observe the traffic shift.

**1. Start a continuous ping from the Spoke to the Hub:**
```bash
sudo docker exec -it clab-wan-failover-spoke-host ping 172.16.11.10
```
*You should see successful replies routing across the Primary link.*

**2. Simulate a Primary Link Failure:**
While the ping is running, bring down the Primary interface (`eth1`) on Router 1:
```bash
sudo docker exec clab-wan-failover-router1 ip link set eth1 down
```

**3. Watch the Magic:**
Look at your first terminal window. You will see the agent detect `100% packet loss`. The AI will output `FAILOVER`, and the script will rewrite the routing tables. 
Look back at your ping terminal—after a brief interruption, the pings will resume as traffic flows over the Backup link!

**4. Trigger a Failback:**
Bring the Primary interface back up:
```bash
sudo docker exec clab-wan-failover-router1 ip link set eth1 up
```
The AI agent will detect the recovery, output `FAILBACK`, and restore the original routing tables.

---

## 🧹 Cleanup

When you are done testing, you can destroy the lab environment to free up system resources. Run this from the root directory:

```bash
sudo clab destroy -t topology.clab.yml
```

## 📜 License
This project is licensed under the [GNU General Public License v3.0](LICENSE).
```
