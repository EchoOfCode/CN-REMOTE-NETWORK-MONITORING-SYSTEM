#!/usr/bin/env python3
"""
Ryu OpenFlow 1.3 Controller with L2 Learning Switch & REST Mitigation API
Part of the Network Health Monitoring & SDN Attack Simulation System.

Run command:
    ryu-manager ryu_sdn_controller.py --wsapi-port 8080
"""

import json
import time
import logging
from webob import Response

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.app.wsgi import ControllerBase, WSGIApplication, route

SDN_INSTANCE_KEY = 'ryu_sdn_controller_instance'


class RyuSDNController(app_manager.RyuApp):
    """
    OpenFlow 1.3 L2 Learning Switch with REST API for dynamic attack mitigation.
    Installs OpenFlow DROP rules upon anomaly notifications from the C2 server.
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(RyuSDNController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.flow_rules = []
        self.blocked_ips = []
        self.logger.setLevel(logging.INFO)

        # Register WSGI REST Controller
        wsgi = kwargs.get('wsgi')
        if wsgi:
            wsgi.register(SDNRestController, {SDN_INSTANCE_KEY: self})
            self.logger.info("[RYU] WSGI REST Controller registered on port 8080")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Invoked on switch connection. Installs default table-miss entry (priority 0)
        to send unknown packets to controller.
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        self.datapaths[datapath.id] = datapath

        self.logger.info(f"[RYU] Switch connected! DPID: {datapath.id:016x}")

        # Table-miss entry: match all packets, send to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, priority=0, match=match, actions=actions)
        self.logger.info("[RYU] Table-miss flow entry installed (priority=0 -> CONTROLLER)")

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=0, hard_timeout=0):
        """Helper function to install standard OpenFlow flow rules."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id is not None and buffer_id != ofproto.OFP_NO_BUFFER:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                priority=priority,
                match=match,
                instructions=inst,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=inst,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout
            )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """
        L2 Learning Switch packet-in handler.
        Learns MAC addresses and forwards packets to destination port or floods.
        """
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # Ignore LLDP control packets
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src
        dpid = datapath.id

        self.mac_to_port.setdefault(dpid, {})

        # Learn source MAC to avoid flooding next time
        self.mac_to_port[dpid][src] = in_port

        # Determine output port
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Install forwarding flow rule if destination port is learned
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, priority=1, match=match, actions=actions, buffer_id=msg.buffer_id)
                return
            else:
                self.add_flow(datapath, priority=1, match=match, actions=actions)

        # Forward the current packet
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    def install_drop_rule(self, src_ip, agent_id="Unknown", target_ip="ALL"):
        """
        Installs an OpenFlow DROP rule (priority 1000, empty instructions)
        matching packets from src_ip (IPv4).
        """
        rule_id = f"flow_drop_{src_ip}_{int(time.time())}"
        rule = {
            "rule_id": rule_id,
            "dpid": 1,
            "priority": 1000,
            "match": {"eth_type": 2048, "ipv4_src": src_ip},
            "action": "DROP",
            "installed_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "agent_id": agent_id,
            "target_ip": target_ip
        }

        if src_ip not in self.blocked_ips:
            self.blocked_ips.append(src_ip)
        self.flow_rules.append(rule)

        # Push OFPFlowMod to all connected datapaths
        for dpid, datapath in self.datapaths.items():
            parser = datapath.ofproto_parser
            # Match IPv4 packets originating from attacker IP
            match = parser.OFPMatch(eth_type=0x0800, ipv4_src=src_ip)
            # Empty instructions in OpenFlow 1.3 instructs switch to DROP matched packets
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=1000,
                match=match,
                instructions=[]
            )
            datapath.send_msg(mod)
            self.logger.info(f"🔴 [SDN MITIGATION] Installed DROP rule for {src_ip} ({agent_id}) on DPID {dpid:016x}")

        return rule

    def remove_drop_rule(self, src_ip):
        """
        Removes OpenFlow DROP rule matching src_ip using OFPFC_DELETE_STRICT.
        """
        if src_ip in self.blocked_ips:
            self.blocked_ips.remove(src_ip)
        self.flow_rules = [r for r in self.flow_rules if r["match"].get("ipv4_src") != src_ip]

        # Push OFPFC_DELETE_STRICT to all connected datapaths
        for dpid, datapath in self.datapaths.items():
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser
            match = parser.OFPMatch(eth_type=0x0800, ipv4_src=src_ip)
            mod = parser.OFPFlowMod(
                datapath=datapath,
                command=ofproto.OFPFC_DELETE_STRICT,
                priority=1000,
                match=match,
                out_port=ofproto.OFPP_ANY,
                out_group=ofproto.OFPG_ANY
            )
            datapath.send_msg(mod)
            self.logger.info(f"🟢 [SDN UNBLOCK] Removed DROP rule for {src_ip} on DPID {dpid:016x}")


class SDNRestController(ControllerBase):
    """
    REST API controller exposed via Ryu's WSGI interface.
    Exposes endpoints for statistics, mitigation (DROP), and unblocking.
    """
    def __init__(self, req, link, data, **config):
        super(SDNRestController, self).__init__(req, link, data, **config)
        self.sdn_app = data[SDN_INSTANCE_KEY]

    @route('sdn', '/api/v1/sdn/stats', methods=['GET'])
    def get_stats(self, req, **kwargs):
        """Returns switch health, active flow rules, and blocked IPs."""
        data = {
            "status": "ONLINE",
            "switch": {
                "switch_id": "s1",
                "dpid": "0000000000000001",
                "active_flows": len(self.sdn_app.flow_rules),
                "blocked_ips": list(self.sdn_app.blocked_ips)
            },
            "active_rules": self.sdn_app.flow_rules
        }
        return Response(content_type='application/json', body=json.dumps(data).encode('utf-8'))

    @route('sdn', '/api/v1/sdn/mitigate', methods=['POST'])
    def mitigate(self, req, **kwargs):
        """Installs OpenFlow DROP rule for the specified attacker IP."""
        try:
            body = req.json if hasattr(req, 'json') and req.json is not None else json.loads(req.body.decode('utf-8'))
        except Exception:
            return Response(status=400, content_type='application/json', body=json.dumps({"error": "Invalid JSON"}).encode('utf-8'))

        src_ip = body.get('src_ip')
        agent_id = body.get('agent_id', 'Unknown')
        target_ip = body.get('target_ip', 'ALL')

        if not src_ip:
            return Response(status=400, content_type='application/json', body=json.dumps({"error": "src_ip is required"}).encode('utf-8'))

        rule = self.sdn_app.install_drop_rule(src_ip, agent_id, target_ip)

        res = {
            "status": "SUCCESS",
            "action": "FLOWMOD_DROP_INSTALLED",
            "rule": rule
        }
        return Response(content_type='application/json', body=json.dumps(res).encode('utf-8'))

    @route('sdn', '/api/v1/sdn/unblock', methods=['POST'])
    def unblock(self, req, **kwargs):
        """Removes OpenFlow DROP rule for the specified IP."""
        try:
            body = req.json if hasattr(req, 'json') and req.json is not None else json.loads(req.body.decode('utf-8'))
        except Exception:
            return Response(status=400, content_type='application/json', body=json.dumps({"error": "Invalid JSON"}).encode('utf-8'))

        src_ip = body.get('src_ip')
        if not src_ip:
            return Response(status=400, content_type='application/json', body=json.dumps({"error": "src_ip is required"}).encode('utf-8'))

        self.sdn_app.remove_drop_rule(src_ip)

        res = {
            "status": "SUCCESS",
            "action": "FLOWMOD_REMOVED",
            "src_ip": src_ip
        }
        return Response(content_type='application/json', body=json.dumps(res).encode('utf-8'))
