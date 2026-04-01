# 🤖 AI-Driven WAN Failover Agent

This project demonstrates an autonomous AI agent that manages Wide Area Network (WAN) failover in a simulated environment. Instead of relying on static, hardcoded thresholds (e.g., "failover if 3 pings drop"), this agent uses Google's Gemini Large Language Model (LLM) to analyze real-time network telemetry and make intelligent routing decisions.

## 🏗️ Architecture & Topology

The lab is built using [Containerlab](https://containerlab.dev/) and runs two Linux containers powered by [FRRouting (FRR)](https://frrouting.org/):
* **Router 1 & Router 2**: Connected via two distinct links.
  * **Primary Link**: `eth1` (10.0.0.0/30)
  * **Backup Link**: `eth2` (10.0.1.0/30)

The AI Agent runs externally, constantly monitoring the health of the primary link and using Docker commands to dynamically alter the static routing tables within the containers when anomalies are detected.

## ✨ Key Features
* **Generative AI Decision Engine**: Uses `gemini-2.5-flash` to evaluate complex network states (packet loss and latency) rather than nested `if/else` logic.
* **Dynamic Route Manipulation**: Automatically injects and removes IP routes to reroute traffic seamlessly.
* **Real-time Telemetry Parsing**: Extracts ICMP metrics directly from Alpine Linux network interfaces.
* **Stateful Failback**: The AI understands when a link has stabilized and safely returns traffic to the primary path.


## 🚀 Getting Started

### Prerequisites
* Docker
* [Containerlab](https://containerlab.dev/install/)
* Python 3.8+
* A free [Google Gemini API Key](https://aistudio.google.com/)

### 1. Deploy the Network Topology
Spin up the virtual routers using Containerlab:
```bash
sudo clab deploy -t topology.clab.yml

![Screenshot 2026-04-02 000553](https://github.com/user-attachments/assets/e073156b-825c-46d2-9d03-afeb967b25a1)

