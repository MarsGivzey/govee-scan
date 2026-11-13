"""Knight Rider scanner along one linear Govee strip (Razer packets, UDP 4003, discrete mode 00).
Usage: python3 -I nightrider_strip.py <ip> <n_segments> <seconds> <fps> <tail_len> <r,g,b> <restore r,g,b | NNNNK> [active]
 active = attached segments (default n): the frame is n long but the head only moves along the first <active>
"""
import base64, json, signal, socket, sys, time

CTRL = 4003
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))      # so the cleanup in finally runs when stopped
def pkt(cmd, data):
    body = bytes([0xBB, len(data) >> 8, len(data) & 0xFF, cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])
send = lambda s, ip, m: s.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda s, ip, raw: send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

ip, n, secs, fps, tail = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
color, restore = tuple(int(v) for v in sys.argv[6].split(",")), sys.argv[7]
active = int(sys.argv[8]) if len(sys.argv) > 8 else n

def frame(head, direction):
    segs = []
    for i in range(n):
        if i >= active:
            segs.append((0, 0, 0)); continue
        behind = (head - i) * direction
        level = 1.0 if behind == 0 else (1 - behind / (tail + 1)) ** 2 if 0 < behind <= tail else 0
        segs.append(tuple(int(c * level) for c in color))
    return pkt(0xB0, [0x00, n] + [v for rgb in segs for v in rgb])

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
frames = 0
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    t0 = time.time()
    while time.time() - t0 < secs:
        phase = frames % (2 * (active - 1))
        head, direction = (phase, 1) if phase < active else (2 * (active - 1) - phase, -1)
        razer(s, ip, frame(head, direction))
        frames += 1
        time.sleep(max(0, frames / fps - (time.time() - t0)))
    print(f"{frames} frames in {time.time() - t0:.1f}s ({frames / (time.time() - t0):.1f} fps)", flush=True)
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    if restore.endswith("K"):
        send(s, ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": int(restore[:-1])}})
    else:
        send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", (int(v) for v in restore.split(",")))), "colorTemInKelvin": 0}})
