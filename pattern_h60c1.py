"""Cycle a list of per-segment patterns on every H60C1 (discrete mode 00) via Razer packets (UDP 4003).
Pattern letters: R G B C M Y W, K = black. One pattern per frame.
Usage: python3 -I pattern_h60c1.py <cycles> <step_s> <kelvin> <brightness> PATTERN [PATTERN ...]   e.g. RKK KGK KKB KKK
"""
import base64, json, socket, struct, sys, time

MCAST, SCAN_PORT, LISTEN_PORT, CTRL = "239.255.255.250", 4001, 4002, 4003
cycles, step, kelvin, bright, patterns = int(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), sys.argv[5:]
COLORS = {"R":(255,0,0),"G":(0,255,0),"B":(0,0,255),"C":(0,255,255),"M":(255,0,255),"Y":(255,255,0),"W":(255,255,255),"K":(0,0,0)}

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
    end, last = time.time() + 2, 0
    while time.time() < end:
        if time.time() - last > 1: tx.sendto(scan, (MCAST, SCAN_PORT)); last = time.time()
        try: data, addr = rx.recvfrom(4096)
        except socket.timeout: continue
        try: m = json.loads(data)["msg"]
        except Exception: continue
        if m.get("cmd") == "scan": devices[addr[0]] = m["data"]["sku"]
ips = sorted(ip for ip, sku in devices.items() if sku == "H60C1")
print(f"{len(ips)} H60C1: {', '.join(ip.split('.')[-1] for ip in ips)}", flush=True)

send = lambda ip, m: tx.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda ip, raw: send(ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})
def frame(p):
    segs = [COLORS[c] for c in p]
    return pkt(0xB0, [0x00, len(segs)] + [v for rgb in segs for v in rgb])
try:
    for ip in ips: razer(ip, pkt(0xB1, [1]))
    time.sleep(0.5)
    t0 = time.time()
    for _ in range(cycles):
        for p in patterns:
            for ip in ips: razer(ip, frame(p))
            time.sleep(step)
    print(f"sent {cycles * len(patterns)} frames in {time.time() - t0:.1f}s", flush=True)
finally:
    for ip in ips: razer(ip, pkt(0xB1, [0]))
    time.sleep(0.5)
    for ip in ips:
        send(ip, {"cmd": "turn", "data": {"value": 1}})
        send(ip, {"cmd": "brightness", "data": {"value": bright}})
        send(ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": kelvin}})
