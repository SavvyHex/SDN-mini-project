# SDN Port Status Monitoring Tool

**Course Project – SDN Mininet Simulation (Orange Problem)**

> Monitor and log switch port status changes, detect port up/down events, generate alerts, and display live status using an OpenFlow SDN controller.

---

## Problem Statement

In traditional networks, port status changes (link up/down events) are detected passively via SNMP or proprietary vendor tools. In an SDN environment, the controller has **global visibility** of the entire network. This project leverages that visibility to build a real-time **Port Status Monitoring System** using:

- **Ryu** – Python-based OpenFlow 1.3 controller
- **Mininet** – Software-defined network emulator
- **Open vSwitch (OVS)** – Soft switch implementing OpenFlow
- **Docker** – Containerised deployment for reproducibility

### What It Does

| Feature | Details |
|---|---|
| Port event detection | `EventOFPPortStatus` captures ADD / DELETE / MODIFY events |
| Structured logging | JSON log lines in `/logs/port_events.json` and `/logs/port_stats.json` |
| Alert generation | Any `DOWN` event appended to `/alerts/alerts.json` |
| Live dashboard | `view_status.py` refreshes every 5 s with colour-coded status |
| Learning switch | MAC learning + unicast flow rules (so normal traffic flows) |
| Statistics polling | Per-port rx/tx bytes, packets, drops, errors every 10 s |
| REST API | Ryu's `ofctl_rest` exposed on port 8080 |

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│              Docker Host (privileged)            │
│                                                  │
│  ┌─────────────────────┐   ┌──────────────────┐  │
│  │  sdn-controller     │   │  sdn-mininet     │  │
│  │  (Ryu + port_mon)   │◄──│  (OVS + topo)   │  │
│  │  port 6633 (OF)     │   │  network_mode:   │  │
│  │  port 8080 (REST)   │   │  host            │  │
│  └─────────┬───────────┘   └──────────────────┘  │
│            │ shared volumes                       │
│  ┌─────────▼───────────┐                         │
│  │  sdn-log-viewer     │                         │
│  │  port 9090 (HTTP)   │                         │
│  └─────────────────────┘                         │
└──────────────────────────────────────────────────┘
```

### Mininet Topology

```
h1 (10.0.0.1) ──┐
h2 (10.0.0.2) ──┤── s1 ────────── s2 ──┬── h4 (10.0.0.4)
h3 (10.0.0.3) ──┘  (OVS)         (OVS) └── h5 (10.0.0.5)
```

---

## Prerequisites

| Tool | Version tested |
|---|---|
| Docker | 24+ |
| Docker Compose | 2.x (plugin) |
| Linux kernel | 5.x+ (for OVS namespace support) |

> **macOS / Windows:** Mininet requires a Linux kernel. Run inside a Linux VM (e.g. UTM, Multipass, WSL2 with OVS).

---

## Setup & Execution

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/sdn-port-monitor.git
cd sdn-port-monitor
```

### 2. Build Docker images

```bash
make build
# or
docker compose build
```

### 3. Start the controller (background)

```bash
make up
# or
docker compose up controller log-viewer
```

The controller is ready when you see:
```
sdn-controller | Listening OpenFlow at 0.0.0.0:6633
```

### 4. Run test scenarios

**Scenario A – Normal forwarding (all ports UP)**
```bash
make scenario-a
# or
RUN_MODE=scenario_a docker compose up --abort-on-container-exit
```

**Scenario B – Port failure simulation**
```bash
make scenario-b
# or
RUN_MODE=scenario_b docker compose up --abort-on-container-exit
```

**Both scenarios (full demo)**
```bash
make full-demo
```

**Interactive Mininet CLI**
```bash
RUN_MODE=demo docker compose up mininet
# inside CLI:
mininet> pingall
mininet> h1 ping h4 -c 5
mininet> s1 ip link set s1-eth3 down
mininet> h1 ping h3 -c 3
```

---

## Monitoring & Viewing Results

### Live status dashboard
```bash
make status
# or
docker exec -it sdn-controller python3 /app/view_status.py
```

### View alerts only
```bash
make alerts
```

### Flow tables
```bash
make flow-tables
# or (inside Mininet CLI)
mininet> sh ovs-ofctl -O OpenFlow13 dump-flows s1
```

### Ryu REST API
```bash
# List all switches
curl http://localhost:8080/v1.0/topology/switches

# Get flow rules for a switch (replace <dpid>)
curl http://localhost:8080/stats/flow/<dpid>

# Get port stats
curl http://localhost:8080/stats/port/<dpid>
```

### Log file browser
Open http://localhost:9090 in your browser to browse:
- `logs/port_events.json` – port state change events
- `logs/port_stats.json` – periodic statistics snapshots
- `logs/scenario_a.log` – Scenario A results
- `logs/scenario_b.log` – Scenario B results
- `alerts/alerts.json` – alert log

---

## Expected Output

### Scenario A – Normal Forwarding

```
SCENARIO A: Normal Forwarding (all ports UP)
* Pinging h1 → h2 (same switch)
64 bytes from 10.0.0.2: icmp_seq=1 ttl=64 time=0.XX ms
...
* iperf throughput h1 → h4
[  3]  0.0-5.0 sec  XXX MBytes  XXX Mbits/sec
```

### Scenario B – Port Failure

```
SCENARIO B: Port Failure Simulation
* Bringing s1-eth3 (h3 port) DOWN...
[controller log] ALERT | dpid=1 port=3 state=down reason=MODIFY
* h1 pings h3 after port is DOWN
ping: connect: Network is unreachable   ← Expected failure
* Restoring s1-eth3 UP...
[controller log] State CHANGE | dpid=1 port=3 down → up
* h1 pings h3 after port is UP again
64 bytes from 10.0.0.3: icmp_seq=1 ttl=64 time=0.XX ms
```

### Alert JSON Example

```json
{"timestamp": "2025-01-01T12:00:00Z", "dpid": 1, "port_no": 3, "reason": "MODIFY", "state": "down"}
{"timestamp": "2025-01-01T12:00:05Z", "dpid": 1, "port_no": 3, "reason": "MODIFY", "state": "up"}
```

### Flow Table Example

```
cookie=0x0, duration=30s, table=0, priority=0,actions=CONTROLLER:65535
cookie=0x0, duration=10s, table=0, priority=1,in_port=1,dl_src=00:00:00:00:00:01,dl_dst=00:00:00:00:00:04,actions=output:4
```

---

## SDN Concepts Demonstrated

| Concept | Where |
|---|---|
| Controller–switch interaction | `EventOFPSwitchFeatures` + `EventOFPPortStatus` |
| Flow rule design (match–action) | `_add_flow()` with `OFPMatch` and `OFPActionOutput` |
| Table-miss rule | Priority 0, action = CONTROLLER |
| Unicast flow rule | Priority 1, idle_timeout=30, hard_timeout=120 |
| Packet-in event handling | `packet_in_handler` with MAC learning |
| Port monitoring | `port_status_handler` + periodic stats polling |
| Alert generation | `write_alert()` on any DOWN event |

---

## Performance Metrics

| Metric | Tool | Where |
|---|---|---|
| Latency | `ping` | Scenario A/B logs |
| Throughput | `iperf` | Scenario A log |
| Flow table changes | `ovs-ofctl dump-flows` | Saved to `/logs/` |
| Port counters | OFP Port Stats Reply | `/logs/port_stats.json` |

---

## Cleanup

```bash
make down    # stop containers
make clean   # remove images + volumes
```

---

## References

1. Ryu SDN Framework – https://ryu-sdn.org/
2. Mininet Walkthrough – http://mininet.org/walkthrough/
3. OpenFlow 1.3 Specification – https://opennetworking.org/software-defined-standards/specifications/
4. Open vSwitch Documentation – https://docs.openvswitch.org/
5. Docker Compose Reference – https://docs.docker.com/compose/