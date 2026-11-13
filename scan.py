"""Discover Govee LAN-API devices on the local network.

Sends the documented multicast scan to 239.255.255.250:4001 and listens on UDP 4002.
Then sends a devStatus query to each responder to see what it reports.
Usage: python3 -I scan.py [seconds]
"""
import json, socket, struct, sys, time

DURATION = float(sys.argv[1]) if len(sys.argv) > 1 else 5.0
MCAST, SCAN_PORT, LISTEN_PORT, CTRL_PORT = "239.255.255.250", 4001, 4002, 4003

rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
rx.bind(("", LISTEN_PORT))
rx.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
              struct.pack("4sl", socket.inet_aton(MCAST), socket.INADDR_ANY))
rx.settimeout(0.5)

tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
scan = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode()

found = {}
end = time.time() + DURATION
last_send = 0
while time.time() < end:
    if time.time() - last_send > 1.5:
        tx.sendto(scan, (MCAST, SCAN_PORT)); last_send = time.time()
    try:
        data, addr = rx.recvfrom(4096)
    except socket.timeout:
        continue
    try:
        msg = json.loads(data)["msg"]
    except Exception:
        continue
    if msg.get("cmd") == "scan":
        found[addr[0]] = msg["data"]

print(f"found {len(found)} device(s)")
for ip, d in found.items():
    print(json.dumps({"ip": ip, **d}))

# status query (LAN control must be enabled per-device in the Govee Home app)
for ip in found:
    tx.sendto(json.dumps({"msg": {"cmd": "devStatus", "data": {}}}).encode(), (ip, CTRL_PORT))
end = time.time() + 2
while time.time() < end:
    try:
        data, addr = rx.recvfrom(4096)
    except socket.timeout:
        continue
    if b"devStatus" in data:
        print("status", addr[0], data.decode(errors="replace"))
