"""Read-only: scan (union of 3 rounds) then devStatus every Govee LAN device and print a table.
Usage: python3 -I read_all.py
"""
import json, socket, struct, time

MCAST, SCAN_PORT, LISTEN_PORT, CTRL = "239.255.255.250", 4001, 4002, 4003
rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
rx.bind(("", LISTEN_PORT))
rx.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, struct.pack("4sl", socket.inet_aton(MCAST), socket.INADDR_ANY))
rx.settimeout(0.3)
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
scan = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode()

devices = {}
for rnd in range(3):
    end, last = time.time() + 2, 0
    while time.time() < end:
        if time.time() - last > 1: tx.sendto(scan, (MCAST, SCAN_PORT)); last = time.time()
        try: data, addr = rx.recvfrom(4096)
        except socket.timeout: continue
        try: m = json.loads(data)["msg"]
        except Exception: continue
        if m.get("cmd") == "scan": devices[addr[0]] = m["data"]["sku"]

status = {}
for attempt in range(2):                                   # second pass asks only the ones that haven't answered
    for ip in devices:
        if ip not in status: tx.sendto(json.dumps({"msg": {"cmd": "devStatus", "data": {}}}).encode(), (ip, CTRL))
    end = time.time() + 1.5
    while time.time() < end:
        try: data, addr = rx.recvfrom(4096)
        except socket.timeout: continue
        try: m = json.loads(data)["msg"]
        except Exception: continue
        if m.get("cmd") == "devStatus": status[addr[0]] = m["data"]

print(f"{len(devices)} devices, {len(status)} answered devStatus")
for ip in sorted(devices, key=lambda ip: (devices[ip], int(ip.split('.')[-1]))):
    d = status.get(ip)
    if d is None: print(f"{ip:<14} {devices[ip]:<6} no status reply"); continue
    c = d["color"]
    print(f"{ip:<14} {devices[ip]:<6} on={d['onOff']} bri={d['brightness']:<3} rgb=({c['r']},{c['g']},{c['b']}) kelvin={d['colorTemInKelvin']}")
