"""Slow pulsing/fading wave across all Govee LAN devices via Razer packets (UDP 4003, discrete mode 00).
H7076: 3 zones (seg 0 = down, seg 1 = up, segs 2..35 = left+right). H60C1 and other unknowns: 1 zone (3 segs same color).
Devices listed in strips.json: rolling wave at strip_n (default 8).
Brightness = smooth sine (period <period_s>), phase staggered per device and per zone; hue drifts around the wheel.
Usage: python3 -I fade_all.py <seconds> <fps> <period_s> <hue_period_s> <kelvin> <brightness> [strip_n] [gel 0..1] [warm 0..1]
"""
import base64, colorsys, json, math, os, signal, socket, struct, sys, time

MCAST, SCAN_PORT, LISTEN_PORT, CTRL = "239.255.255.250", 4001, 4002, 4003
secs, fps, period, hue_period, kelvin, bright = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6])
strip_n = int(sys.argv[7]) if len(sys.argv) > 7 else 8      # frame length for devices listed in strips.json
gel = float(sys.argv[8]) if len(sys.argv) > 8 else 0.0
warm = float(sys.argv[9]) if len(sys.argv) > 9 else 0.0      # 0..1: add red + a bit of yellow to the cool hues (blue/cyan/violet, some green)      # 0 = pure LED colors, 1 = full 70s/80s gel-on-tungsten look

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
ips = sorted(devices, key=lambda ip: int(ip.split(".")[-1]))
strips = set(json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "strips.json"))))
print(f"{len(ips)} devices", flush=True)

send = lambda ip, m: tx.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda ip, raw: send(ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

# Hue -> stage-gel look (estimates of how filtered tungsten read, NOT measured gel transmission data):
# warm colors stay rich, greens go yellow-ish/kelly, cyan turns teal, blues get deep and dim, magenta goes pink-purple.
GEL_ANCHORS = [(0.00, (255, 38, 30)), (0.07, (255, 120, 25)), (0.13, (255, 205, 70)), (0.22, (200, 215, 60)),
               (0.33, (40, 175, 70)), (0.46, (70, 170, 175)), (0.58, (70, 70, 205)), (0.67, (60, 35, 185)),
               (0.76, (140, 85, 200)), (0.88, (215, 45, 135)), (1.00, (255, 38, 30))]

def gel_rgb(hue, level):
    pure = [c * 255 for c in colorsys.hsv_to_rgb(hue, 1.0, 1.0)]
    for (h0, c0), (h1, c1) in zip(GEL_ANCHORS, GEL_ANCHORS[1:]):
        if h0 <= hue <= h1:
            f = (hue - h0) / (h1 - h0)
            gel_c = [a + (b - a) * f for a, b in zip(c0, c1)]
            break
    mixed = [p + (g - p) * gel for p, g in zip(pure, gel_c)]
    w = max(0.0, 1 - abs(hue - 0.55) / 0.32)             # coolness weight: 1 near blue, fading to 0 by warm hues
    mixed = [min(255.0, mixed[0] + 90 * warm * w), min(255.0, mixed[1] + 30 * warm * w), mixed[2]]
    return tuple(int(v * level) for v in mixed)

def zone_rgb(t, dev_phase, zone_phase):
    level = 0.5 + 0.5 * math.sin(2 * math.pi * (t / period - dev_phase - zone_phase))
    level = level ** 1.5                                   # deeper dark between pulses
    hue = (t / hue_period + dev_phase) % 1.0
    if gel > 0:
        return gel_rgb(hue, level)
    r, g, b = colorsys.hsv_to_rgb(hue, 1.0, level)
    return (int(r * 255), int(g * 255), int(b * 255))

def frame(ip, idx, t):
    dp = idx / len(ips)
    if ip in strips:                                       # strips from strips.json: rolling wave at strip_n (default 8)
        segs = [zone_rgb(t, dp, i / strip_n) for i in range(strip_n)]
        return pkt(0xB0, [0x00, strip_n] + [v for rgb in segs for v in rgb])
    if devices[ip] == "H7076":
        down, up, side = zone_rgb(t, dp, 0.0), zone_rgb(t, dp, 0.33), zone_rgb(t, dp, 0.66)
        segs = [down, up] + [side] * 34
        return pkt(0xB0, [0x00, 36] + [v for rgb in segs for v in rgb])
    c = zone_rgb(t, dp, 0.0)
    return pkt(0xB0, [0x00, 3] + list(c) * 3)

frames = 0
try:
    for ip in ips: razer(ip, pkt(0xB1, [1]))
    time.sleep(0.5)
    t0 = time.time()
    while (t := time.time() - t0) < secs:
        for idx, ip in enumerate(ips): razer(ip, frame(ip, idx, t))
        frames += 1
        time.sleep(max(0, (frames / fps) - (time.time() - t0)))
    print(f"{frames} frames in {time.time() - t0:.1f}s ({frames / (time.time() - t0):.1f} fps)", flush=True)
finally:
    for ip in ips: razer(ip, pkt(0xB1, [0]))
    time.sleep(0.5)
    for ip in ips:
        send(ip, {"cmd": "turn", "data": {"value": 1}})
        send(ip, {"cmd": "brightness", "data": {"value": bright}})
        send(ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": kelvin}})
