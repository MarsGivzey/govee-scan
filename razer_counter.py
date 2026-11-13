"""n incrementer: send frames of n = start, start+step, .. up to end (negative step counts down); segments 0,1,2 show the STEP INDEX (n - start) / step
as three base-6 digits (high, mid, low) with R=0 G=1 B=2 C=3 M=4 Y=5; all other segments black.
When the strip stops accepting longer frames the counter freezes.
Usage: python3 -I razer_counter.py <ip> <start_n> <end_n> <step> <hold_s> <restore r,g,b | NNNNK>
Decode: freeze colors (d2, d1, d0) -> index = 36*d2 + 6*d1 + d0 -> last good n = start_n + step * index
"""
import base64, json, signal, socket, sys, time

CTRL = 4003
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))      # so the cleanup in finally runs when stopped
DIGITS = "RGBCMY"
COLORS = {"R":(255,0,0),"G":(0,255,0),"B":(0,0,255),"C":(0,255,255),"M":(255,0,255),"Y":(255,255,0)}
def pkt(cmd, data):
    body = bytes([0xBB, len(data) >> 8, len(data) & 0xFF, cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])
send = lambda s, ip, m: s.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda s, ip, raw: send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

ip, start, stop, step, hold, restore = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]), sys.argv[6]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    for n in range(start, stop + (1 if step > 0 else -1), step):      # negative step counts down
        v = (n - start) // step
        d2, d1, d0 = DIGITS[v // 36 % 6], DIGITS[v // 6 % 6], DIGITS[v % 6]
        segs = [COLORS[d2], COLORS[d1], COLORS[d0]] + [(0, 0, 0)] * (n - 3)
        raw = pkt(0xB0, [0x00, n] + [c for rgb in segs for c in rgb])
        print(time.strftime("%H:%M:%S"), f"n={n} index={v} -> {d2}{d1}{d0}", flush=True)
        end = time.time() + hold
        while time.time() < end:
            razer(s, ip, raw)
            time.sleep(0.5)
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    if restore.endswith("K"):
        send(s, ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": int(restore[:-1])}})
    else:
        send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", (int(v) for v in restore.split(",")))), "colorTemInKelvin": 0}})
