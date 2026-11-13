"""Alternate a Govee device between palettes via Razer packets (UDP 4003).
Usage: python3 -I razer_alternate.py <ip> <n_segments> <flips> <interval_s> <restore r,g,b> PALETTE [PALETTE ...]
  PALETTE = letters from RGBCMYW, repeated across the segments (e.g. RGBW CMYW)
"""
import base64, json, socket, sys, time

CTRL = 4003
COLORS = {"R":(255,0,0),"G":(0,255,0),"B":(0,0,255),"C":(0,255,255),"M":(255,0,255),"Y":(255,255,0),"W":(255,255,255)}

def pkt(cmd, data):
    body = bytes([0xBB, 0, len(data), cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])
def send(s, ip, msg): s.sendto(json.dumps({"msg": msg}).encode(), (ip, CTRL))
def razer(s, ip, raw): send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

ip, n, flips, interval = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
restore, palettes = tuple(int(v) for v in sys.argv[5].split(",")), sys.argv[6:]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    for i in range(flips):
        p = palettes[i % len(palettes)]
        segs = [COLORS[p[j % len(p)]] for j in range(n)]
        razer(s, ip, pkt(0xB0, [0x01, n] + [c for rgb in segs for c in rgb]))
        print(time.strftime("%H:%M:%S"), p, flush=True)
        time.sleep(interval)
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", restore)), "colorTemInKelvin": 0}})
