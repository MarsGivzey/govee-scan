"""Knight Rider scanner along the H7076 path, in sync on every H7076 (Razer packets, UDP 4003, discrete mode 00).
Path positions: 0 -> seg 1 ; 1..17 -> pair (2+k, 19+k) ; 18 -> seg 0   (19 positions). Head bounces, tail fades behind it.
Other SKUs (H60C1) are not touched.
Usage: python3 -I nightrider_path.py <seconds> <fps> <tail_len> <r,g,b> <kelvin> <brightness>
"""
import base64, json, socket, struct, sys, time

MCAST, SCAN_PORT, LISTEN_PORT, CTRL = "239.255.255.250", 4001, 4002, 4003
secs, fps, tail = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3])
color = tuple(int(v) for v in sys.argv[4].split(","))
kelvin, bright = int(sys.argv[5]), int(sys.argv[6])
POSITIONS = [[1]] + [[2 + k, 19 + k] for k in range(17)] + [[0]]
N = len(POSITIONS)

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
ips = sorted((ip for ip, sku in devices.items() if sku == "H7076"), key=lambda ip: int(ip.split(".")[-1]))
print(f"{len(ips)} H7076", flush=True)

send = lambda ip, m: tx.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda ip, raw: send(ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

def frame(head, direction):
    segs = [(0, 0, 0)] * 36
    for p, group in enumerate(POSITIONS):
        behind = (head - p) * direction
        level = 1.0 if behind == 0 else (1 - behind / (tail + 1)) ** 2 if 0 < behind <= tail else 0
        for s in group: segs[s] = tuple(int(c * level) for c in color)
    return pkt(0xB0, [0x00, 36] + [v for rgb in segs for v in rgb])

frames = 0
try:
    for ip in ips: razer(ip, pkt(0xB1, [1]))
    time.sleep(0.5)
    t0 = time.time()
    while time.time() - t0 < secs:
        phase = frames % (2 * (N - 1))
        head, direction = (phase, 1) if phase < N else (2 * (N - 1) - phase, -1)
        f = frame(head, direction)
        for ip in ips: razer(ip, f)
        frames += 1
        time.sleep(max(0, frames / fps - (time.time() - t0)))
    print(f"{frames} frames in {time.time() - t0:.1f}s ({frames / (time.time() - t0):.1f} fps)", flush=True)
finally:
    for ip in ips: razer(ip, pkt(0xB1, [0]))
    time.sleep(0.5)
    for ip in ips:
        send(ip, {"cmd": "turn", "data": {"value": 1}})
        send(ip, {"cmd": "brightness", "data": {"value": bright}})
        send(ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": kelvin}})
