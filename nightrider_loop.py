"""Endless Knight Rider on every H7076 (Razer packets, UDP 4003, discrete mode 00), in sync.
Path: seg 1 -> pairs (2+k, 19+k) k=0..16 -> seg 0, head bounces with a fading tail.
Each round = <bounces> there-and-back passes in one random color, then <gap_s> of black, then a new color
(hue at least 0.15 away from the last). Runs until SIGTERM/SIGINT; cleanup then sets <kelvin>/<brightness>.
Other SKUs (H60C1) are not touched.
Usage: python3 -I nightrider_loop.py <bounces> <fps> <tail_len> <gap_s> <kelvin> <brightness>
Stop:  pkill -TERM -f nightrider_loop.py
"""
import base64, colorsys, json, random, signal, socket, struct, sys, time

MCAST, SCAN_PORT, LISTEN_PORT, CTRL = "239.255.255.250", 4001, 4002, 4003
bounces, fps, tail, gap = int(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
kelvin, bright = int(sys.argv[5]), int(sys.argv[6])
POSITIONS = [[1]] + [[2 + k, 19 + k] for k in range(17)] + [[0]]
N = len(POSITIONS)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))      # so the finally block runs

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
print(f"{len(ips)} H7076, looping", flush=True)

send = lambda ip, m: tx.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda ip, raw: send(ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})
push = lambda f: [razer(ip, f) for ip in ips]

def frame(color, head=None, direction=1):
    segs = [(0, 0, 0)] * 36
    if head is not None:
        for p, group in enumerate(POSITIONS):
            behind = (head - p) * direction
            level = 1.0 if behind == 0 else (1 - behind / (tail + 1)) ** 2 if 0 < behind <= tail else 0
            for s in group: segs[s] = tuple(int(c * level) for c in color)
    return pkt(0xB0, [0x00, 36] + [v for rgb in segs for v in rgb])

last_hue, rounds = None, 0
try:
    for ip in ips: razer(ip, pkt(0xB1, [1]))
    time.sleep(0.5)
    while True:
        hue = random.random()
        while last_hue is not None and min(abs(hue - last_hue), 1 - abs(hue - last_hue)) < 0.15: hue = random.random()
        last_hue = hue
        color = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 1.0, 1.0))
        heads = ([(h, 1) for h in range(N)] + [(h, -1) for h in range(N - 2, -1, -1)]) * bounces
        t0 = time.time()
        for i, (h, d) in enumerate(heads):
            push(frame(color, h, d))
            time.sleep(max(0, (i + 1) / fps - (time.time() - t0)))
        push(frame(color))                                  # all black between rounds
        time.sleep(gap)
        rounds += 1
        print(f"round {rounds} color {color}", flush=True)
finally:
    for ip in ips: razer(ip, pkt(0xB1, [0]))
    time.sleep(0.5)
    for ip in ips:
        send(ip, {"cmd": "turn", "data": {"value": 1}})
        send(ip, {"cmd": "brightness", "data": {"value": bright}})
        send(ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": kelvin}})
    print(f"stopped after {rounds} rounds; restored {len(ips)} H7076 to {kelvin}K at {bright}%", flush=True)
