"""Hold one Razer frame built from a segment spec (UDP 4003, discrete mode 00).
Spec = space-separated tokens: letters R G B C M Y W K (K = black), optionally 'LETTERS*N' to repeat the run N times.
  e.g.  "K*48 RGBCMYRGBCMY K*4"  = 48 black, 12 colored, 4 black (64 segments)
Usage: python3 -I razer_spec.py <ip> <hold_s> <restore r,g,b | NNNNK> <spec tokens...>
"""
import base64, json, socket, sys, time

CTRL = 4003
COLORS = {"R":(255,0,0),"G":(0,255,0),"B":(0,0,255),"C":(0,255,255),"M":(255,0,255),"Y":(255,255,0),"W":(255,255,255),"K":(0,0,0)}
def pkt(cmd, data):
    body = bytes([0xBB, len(data) >> 8, len(data) & 0xFF, cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])
send = lambda s, ip, m: s.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda s, ip, raw: send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

ip, hold, restore, tokens = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4:]
letters = ""
for t in tokens:
    run, _, times = t.partition("*")
    letters += run * (int(times) if times else 1)
segs = [COLORS[c] for c in letters]
raw = pkt(0xB0, [0x00, len(segs)] + [v for rgb in segs for v in rgb])
print(f"n={len(segs)} packet={len(raw)} bytes; first lit segments: {[i for i, c in enumerate(letters) if c != 'K'][:20]}", flush=True)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    end = time.time() + hold
    while time.time() < end:
        razer(s, ip, raw)
        time.sleep(2)
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    if restore.endswith("K"):
        send(s, ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": int(restore[:-1])}})
    else:
        send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", (int(v) for v in restore.split(",")))), "colorTemInKelvin": 0}})
