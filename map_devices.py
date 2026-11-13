"""Map every Govee LAN device to its stable identifiers: Govee device id (from the scan reply) + Wi-Fi MAC (from the ARP table).
Writes devices.json keyed by Govee device id, and adds mac/device_id to strips.json entries by IP.
Usage: python3 -I map_devices.py
"""
import json, os, re, socket, struct, subprocess, time

MCAST, SCAN_PORT, LISTEN_PORT = "239.255.255.250", 4001, 4002
here = os.path.dirname(os.path.abspath(__file__))
rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
rx.bind(("", LISTEN_PORT))
rx.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, struct.pack("4sl", socket.inet_aton(MCAST), socket.INADDR_ANY))
rx.settimeout(0.3)
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
scan = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode()

found = {}
for rnd in range(3):
    end, last = time.time() + 2, 0
    while time.time() < end:
        if time.time() - last > 1: tx.sendto(scan, (MCAST, SCAN_PORT)); last = time.time()
        try: data, addr = rx.recvfrom(4096)
        except socket.timeout: continue
        try: m = json.loads(data)["msg"]
        except Exception: continue
        if m.get("cmd") == "scan": found[addr[0]] = m["data"]

arp = {}
for line in subprocess.run(["arp", "-a", "-n"], capture_output=True, text=True).stdout.splitlines():
    m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-f:]+) on", line)
    if m and "incomplete" not in line:
        arp[m.group(1)] = ":".join(p.zfill(2) for p in m.group(2).split(":")).upper()   # macOS drops leading zeros

devices = {}
for ip, d in sorted(found.items(), key=lambda kv: int(kv[0].split(".")[-1])):
    devices[d["device"]] = {"ip": ip, "sku": d["sku"], "mac": arp.get(ip), "wifi_fw": d["wifiVersionSoft"]}
json.dump(devices, open(os.path.join(here, "devices.json"), "w"), indent=2)

sp = os.path.join(here, "strips.json")
strips = json.load(open(sp)) if os.path.exists(sp) else {}
for ip, s in strips.items():
    if ip in found: s["device_id"], s["mac"] = found[ip]["device"], arp.get(ip)
json.dump(strips, open(sp, "w"), indent=2)

print(f"{len(devices)} devices; MAC found for {sum(1 for d in devices.values() if d['mac'])}")
for did, d in devices.items():
    if d["sku"] in ("H61B6", "H61F2"): print(f"  {d['ip']:<14} {d['sku']:<6} mac {d['mac']}  id {did}")
