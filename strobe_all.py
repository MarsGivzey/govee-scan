"""Discover all Govee LAN devices (union of several scans), strobe them white via Razer packets, then set warm white.
Usage: python3 -I strobe_all.py <strobe_seconds> <interval_s> <kelvin> <brightness> [COLORS]
 COLORS = letters from RGBCMYW (e.g. CMYWCM): strobe_seconds is then spent per color, flashing that color on/off
 flash packet = mode 01, n=1 (worked on H60C1 + H7076); strobe at 1/(2*interval) Hz
"""
import base64, json, socket, struct, sys, time

MCAST, SCAN_PORT, LISTEN_PORT, CTRL = "239.255.255.250", 4001, 4002, 4003
secs, interval, kelvin, bright = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
COLORS = {"R":(255,0,0),"G":(0,255,0),"B":(0,0,255),"C":(0,255,255),"M":(255,0,255),"Y":(255,255,0),"W":(255,255,255)}
sequence = [COLORS[c] for c in (sys.argv[5] if len(sys.argv) > 5 else "W")]

def pkt(cmd, data):
    body = bytes([0xBB, 0, len(data), cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])

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
    end, last = time.time() + 3, 0
    while time.time() < end:
        if time.time() - last > 1: tx.sendto(scan, (MCAST, SCAN_PORT)); last = time.time()
        try: data, addr = rx.recvfrom(4096)
        except socket.timeout: continue
        try: m = json.loads(data)["msg"]
        except Exception: continue
        if m.get("cmd") == "scan": devices[addr[0]] = m["data"]["sku"]
    print(f"scan {rnd + 1}: {len(devices)} devices so far", flush=True)

ips = sorted(devices)
send = lambda ip, m: tx.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda ip, raw: send(ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})
frame = lambda rgb: pkt(0xB0, [0x01, 1, *rgb])
try:
    for ip in ips: razer(ip, pkt(0xB1, [1]))
    time.sleep(0.5)
    for rgb in sequence:
        end, on = time.time() + secs, True
        while time.time() < end:
            for ip in ips: razer(ip, frame(rgb if on else (0, 0, 0)))
            on = not on
            time.sleep(interval)
finally:
    for ip in ips: razer(ip, pkt(0xB1, [0]))
    time.sleep(0.5)
    for ip in ips:
        send(ip, {"cmd": "turn", "data": {"value": 1}})
        send(ip, {"cmd": "brightness", "data": {"value": bright}})
        send(ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": kelvin}})
    print(f"strobed + restored {len(ips)} devices to {kelvin}K at {bright}%:", ", ".join(f"{ip.split('.')[-1]}({devices[ip]})" for ip in ips))
