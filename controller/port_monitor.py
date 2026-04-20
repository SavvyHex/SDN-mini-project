"""
SDN Port Status Monitoring Controller
Topic: Port Status Monitoring Tool
- Monitor and log switch port status changes
- Detect port up/down events
- Log changes with timestamps
- Generate alerts
- Display status
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.controller import dpset

import logging
import json
import os
import datetime
import threading
import time
from collections import defaultdict

# ── Logging setup ──────────────────────────────────────────────────────────────
LOG_DIR = "/logs"
ALERT_DIR = "/alerts"
os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(ALERT_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/controller.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("PortMonitor")


def write_alert(dpid: int, port_no: int, reason: str, state: str):
    """Append a JSON alert entry to the alerts file."""
    alert = {
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "dpid": dpid,
        "port_no": port_no,
        "reason": reason,
        "state": state,
    }
    alert_file = f"{ALERT_DIR}/alerts.json"
    with open(alert_file, "a") as f:
        f.write(json.dumps(alert) + "\n")
    logger.warning("ALERT | dpid=%s port=%s state=%s reason=%s", dpid, port_no, state, reason)


class PortStatusMonitor(app_manager.RyuApp):
    """
    Ryu application that:
      1. Installs a table-miss flow rule so all packets hit the controller (learning switch).
      2. Learns MAC→port mappings and installs unicast flow rules.
      3. Listens for PortStatus messages (port up/down/modified) and logs/alerts on changes.
      4. Periodically polls port statistics and logs them.
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # mac_to_port[dpid][mac] = port_no
        self.mac_to_port: dict[int, dict[str, int]] = defaultdict(dict)

        # port_status[dpid][port_no] = {"state": "up"|"down", "last_change": iso_ts}
        self.port_status: dict[int, dict[int, dict]] = defaultdict(dict)

        # Start the background stats-polling thread
        self._poll_thread = threading.Thread(target=self._stats_poller, daemon=True)
        self._poll_thread.start()

        # Keep references to datapaths for polling
        self._datapaths: dict[int, object] = {}

        logger.info("PortStatusMonitor controller started.")

    # ── Switch handshake ───────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Install table-miss flow entry when switch connects."""
        dp = ev.msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        self._datapaths[dp.id] = dp
        logger.info("Switch connected | dpid=%s", dp.id)

        # Table-miss: send all unmatched packets to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self._add_flow(dp, priority=0, match=match, actions=actions)

        # Request port descriptions so we can seed port_status
        req = parser.OFPPortDescStatsRequest(dp, 0)
        dp.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_desc_stats_reply_handler(self, ev):
        """Seed initial port status from the port description reply."""
        dp = ev.msg.datapath
        for port in ev.msg.body:
            if port.port_no > dp.ofproto.OFPP_MAX:
                continue
            state = "down" if (port.state & dp.ofproto.OFPPS_LINK_DOWN) else "up"
            self._update_port_status(dp.id, port.port_no, port.name.decode(), state, initial=True)

    # ── Port status events ─────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        """Handle port up/down/modify notifications from the switch."""
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        port = msg.desc
        reason_map = {
            ofp.OFPPR_ADD: "ADD",
            ofp.OFPPR_DELETE: "DELETE",
            ofp.OFPPR_MODIFY: "MODIFY",
        }
        reason = reason_map.get(msg.reason, "UNKNOWN")
        state = "down" if (port.state & ofp.OFPPS_LINK_DOWN) else "up"
        port_name = port.name.decode()

        logger.info(
            "PortStatus | dpid=%s port=%s(%s) reason=%s state=%s",
            dp.id, port.port_no, port_name, reason, state,
        )
        self._update_port_status(dp.id, port.port_no, port_name, state, reason=reason)

        # Write structured log entry
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "dpid": dp.id,
            "port_no": port.port_no,
            "port_name": port_name,
            "reason": reason,
            "state": state,
        }
        with open(f"{LOG_DIR}/port_events.json", "a") as f:
            f.write(json.dumps(entry) + "\n")

        # Alert on any port going down
        if state == "down":
            write_alert(dp.id, port.port_no, reason, state)

    def _update_port_status(self, dpid, port_no, port_name, state, reason="INITIAL", initial=False):
        prev = self.port_status[dpid].get(port_no, {})
        now_ts = datetime.datetime.utcnow().isoformat() + "Z"
        self.port_status[dpid][port_no] = {
            "port_name": port_name,
            "state": state,
            "last_change": now_ts,
            "reason": reason,
        }
        if not initial and prev.get("state") != state:
            logger.warning(
                "State CHANGE | dpid=%s port=%s %s → %s",
                dpid, port_no, prev.get("state", "UNKNOWN"), state,
            )

    # ── Packet-in (learning switch) ────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst, src = eth.dst, eth.src
        dpid = dp.id

        # Learn source MAC
        self.mac_to_port[dpid][src] = in_port

        out_port = self.mac_to_port[dpid].get(dst, ofp.OFPP_FLOOD)

        actions = [parser.OFPActionOutput(out_port)]

        # Install a flow rule for known unicast destinations
        if out_port != ofp.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self._add_flow(dp, priority=1, match=match, actions=actions, idle_timeout=30, hard_timeout=120)

        # Send the buffered packet
        data = None if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(
            datapath=dp,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None,
        )
        dp.send_msg(out)

    # ── Port statistics polling ────────────────────────────────────────────────

    def _stats_poller(self):
        """Background thread: request port stats every 10 seconds."""
        time.sleep(5)  # initial delay to let switches connect
        while True:
            for dpid, dp in list(self._datapaths.items()):
                try:
                    parser = dp.ofproto_parser
                    req = parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY)
                    dp.send_msg(req)
                except Exception as e:
                    logger.error("Stats poll error for dpid=%s: %s", dpid, e)
            time.sleep(10)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """Log per-port counters (rx/tx bytes, packets, errors, drops)."""
        dp = ev.msg.datapath
        stats_snapshot = []
        for stat in ev.msg.body:
            if stat.port_no > dp.ofproto.OFPP_MAX:
                continue
            entry = {
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "dpid": dp.id,
                "port_no": stat.port_no,
                "rx_packets": stat.rx_packets,
                "tx_packets": stat.tx_packets,
                "rx_bytes": stat.rx_bytes,
                "tx_bytes": stat.tx_bytes,
                "rx_dropped": stat.rx_dropped,
                "tx_dropped": stat.tx_dropped,
                "rx_errors": stat.rx_errors,
                "tx_errors": stat.tx_errors,
            }
            stats_snapshot.append(entry)
            logger.debug(
                "Stats | dpid=%s port=%s rx_pkt=%s tx_pkt=%s rx_bytes=%s tx_bytes=%s",
                dp.id, stat.port_no, stat.rx_packets, stat.tx_packets,
                stat.rx_bytes, stat.tx_bytes,
            )

        with open(f"{LOG_DIR}/port_stats.json", "a") as f:
            for entry in stats_snapshot:
                f.write(json.dumps(entry) + "\n")

    # ── Helper ─────────────────────────────────────────────────────────────────

    def _add_flow(self, dp, priority, match, actions, idle_timeout=0, hard_timeout=0):
        ofp = dp.ofproto
        parser = dp.ofproto_parser
        inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=dp,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        dp.send_msg(mod)