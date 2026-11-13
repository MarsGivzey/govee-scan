"""Rolling fade wave across every strip in strips.json, each driven at a small fixed n (Razer packets, UDP 4003, mode 00).
Segment i of strip s: brightness = sine(t/period - strip_phase - i/n), hue drifts with time + position.
How n colors map onto a strip longer than n is not verified; this assumes they are spread over the whole strip.
Usage: python3 -I fade_strips.py <seconds> <fps> <n> <period_s> <hue_period_s> <restore NNNNK>
Stop early: pkill -TERM -f fade_strips.py
"""
import base64, colorsys, json, math, os, signal, socket, sys, time

CTRL = 4003
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))      # so the cleanup in finally runs when stopped
here = os.path.dirname(os.path.abspath(__file__))
secs, fps, n, period, hue_period, restore = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5]), sys.argv[6]
strips = [ip for ip, s in json.load(open(os.path.join(here, "strips.json"))).items() if s.get("x")]
strips.sort(key=lambda ip: int(ip.split(".")[-1]))
print("strips:", strips, "n =", n, flush=True)

def pkt(cmd, data):
    body = bytes([0xBB, len(data) >> 8, len(data) & 0xFF, cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])
send = lambda s, ip, m: s.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda s, ip, raw: send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

def frame(idx, t):
    sp = idx / len(strips)
    segs = []
    for i in range(n):
        level = (0.5 + 0.5 * math.sin(2 * math.pi * (t / period - sp - i / n))) ** 1.5
        hue = (t / hue_period + sp + i / (2 * n)) % 1.0
        r, g, b = colorsys.hsv_to_rgb(hue, 1.0, level)
        segs.append((int(r * 255), int(g * 255), int(b * 255)))
    return pkt(0xB0, [0x00, n] + [v for rgb in segs for v in rgb])

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
frames = 0
try:
    for ip in strips: razer(s, ip, pkt(0xB1, [1]))
    time.sleep(0.5)
    t0 = time.time()
    while (t := time.time() - t0) < secs:
        for idx, ip in enumerate(strips): razer(s, ip, frame(idx, t))
        frames += 1
        time.sleep(max(0, frames / fps - (time.time() - t0)))
    print(f"{frames} frames in {time.time() - t0:.1f}s ({frames / (time.time() - t0):.1f} fps), packet {len(frame(0, 0))} bytes", flush=True)
finally:
    for ip in strips: razer(s, ip, pkt(0xB1, [0]))
    time.sleep(0.5)
    for ip in strips:
        send(s, ip, {"cmd": "turn", "data": {"value": 1}})
        send(s, ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": int(restore[:-1])}})
