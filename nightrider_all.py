"""Knight Rider on every strip in strips.json at once (Razer packets, UDP 4003, discrete mode 00), heads in sync as a
fraction of each strip's attached length x (frame length n per strip). One head color per round, black gap between rounds.
Usage: python3 -I nightrider_all.py <fps> <sweep_s> <bounces_per_round> <gap_s> <color letters, e.g. RGBCMYR> <restore NNNNK>
Stop early: pkill -TERM -f nightrider_all.py   (cleanup restores every strip)
"""
import base64, json, os, signal, socket, sys, time

CTRL = 4003
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))      # so the cleanup in finally runs when stopped
COLORS = {"R":(255,0,0),"G":(0,255,0),"B":(0,0,255),"C":(0,255,255),"M":(255,0,255),"Y":(255,255,0),"W":(255,255,255)}
here = os.path.dirname(os.path.abspath(__file__))
fps, sweep_s, bounces, gap, letters, restore = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), sys.argv[5], sys.argv[6]
strips = {ip: s for ip, s in json.load(open(os.path.join(here, "strips.json"))).items() if s.get("x")}
print("strips:", {ip: (s["n"], s["x"]) for ip, s in strips.items()}, flush=True)

def pkt(cmd, data):
    body = bytes([0xBB, len(data) >> 8, len(data) & 0xFF, cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])
send = lambda s, ip, m: s.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda s, ip, raw: send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

def frame(strip, color, phase):
    n, x = strip["n"], strip["x"]
    frac, direction = (phase, 1) if phase <= 1 else (2 - phase, -1)
    head = round(frac * (x - 1))
    tail = max(2, round(0.12 * x))
    segs = [(0, 0, 0)] * n
    if color:
        for i in range(x):
            behind = (head - i) * direction
            level = 1.0 if behind == 0 else (1 - behind / (tail + 1)) ** 2 if 0 < behind <= tail else 0
            segs[i] = tuple(int(c * level) for c in color)
    return pkt(0xB0, [0x00, n] + [v for rgb in segs for v in rgb])

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rounds = 0
try:
    for ip in strips: razer(s, ip, pkt(0xB1, [1]))
    time.sleep(0.5)
    for letter in letters:
        color, round_s, t0, frames = COLORS[letter], bounces * 2 * sweep_s, time.time(), 0
        print(time.strftime("%H:%M:%S"), "round", rounds + 1, letter, flush=True)
        while time.time() - t0 < round_s:
            phase = ((time.time() - t0) / sweep_s) % 2          # 0..1 forward, 1..2 back
            for ip, st in strips.items(): razer(s, ip, frame(st, color, phase))
            frames += 1
            time.sleep(max(0, frames / fps - (time.time() - t0)))
        for ip, st in strips.items(): razer(s, ip, frame(st, None, 0))      # black between rounds
        time.sleep(gap)
        rounds += 1
finally:
    for ip in strips: razer(s, ip, pkt(0xB1, [0]))
    time.sleep(0.5)
    for ip in strips:
        send(s, ip, {"cmd": "turn", "data": {"value": 1}})
        send(s, ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": int(restore[:-1])}})
    print(f"done after {rounds} rounds; restored {len(strips)} strips to {restore}", flush=True)
