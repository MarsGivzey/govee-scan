"""Set every Govee LAN device (union of 3 scans) to a white color temperature + brightness; also makes sure Razer mode is off.
Usage: python3 -I set_all.py <kelvin> <brightness>
"""
import base64, json, socket, struct, sys, time

MCAST, SCAN_PORT, LISTEN_PORT, CTRL = "239.255.255.250", 4001, 4002, 4003
kelvin, bright = int(sys.argv[1]), int(sys.argv[2])

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

send = lambda ip, m: tx.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
for ip in devices:
    send(ip, {"cmd": "razer", "data": {"pt": base64.b64encode(bytes.fromhex("bb0001b1000b")).decode()}})
time.sleep(0.5)
for ip in devices:
    send(ip, {"cmd": "turn", "data": {"value": 1}})
    send(ip, {"cmd": "brightness", "data": {"value": bright}})
    send(ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": kelvin}})
time.sleep(1)
for ip in devices:
    send(ip, {"cmd": "devStatus", "data": {}})
ok = {}
end = time.time() + 2
while time.time() < end:
    try: data, addr = rx.recvfrom(4096)
    except socket.timeout: continue
    try: m = json.loads(data)["msg"]
    except Exception: continue
    if m.get("cmd") == "devStatus": ok[addr[0]] = m["data"]
bad = [ip for ip, d in ok.items() if d.get("colorTemInKelvin") != kelvin or d.get("brightness") != bright or d.get("onOff") != 1]
print(f"set {len(devices)} devices to {kelvin}K at {bright}%; status read back from {len(ok)}; mismatches: {bad or 'none'}")
for ip in sorted(set(devices) - set(ok)): print("  no status reply from", ip, devices[ip])
for ip in bad: print("  ", ip, devices[ip], ok[ip])
