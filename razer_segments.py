"""Probe how many Razer segments a Govee device accepts (LAN API, UDP 4003).
Each step: n segments, first=red, last=blue, middle=green; hold <hold_s>; print timestamped marker.
Usage: python3 -I razer_segments.py <ip> <hold_s> <restore r,g,b> n [n ...]
"""
import base64, json, socket, sys, time

CTRL = 4003
def pkt(cmd, data):
    body = bytes([0xBB, 0, len(data), cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])
def send(s, ip, msg): s.sendto(json.dumps({"msg": msg}).encode(), (ip, CTRL))
def razer(s, ip, raw): send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

ip, hold, restore, counts = sys.argv[1], float(sys.argv[2]), tuple(int(v) for v in sys.argv[3].split(",")), [int(n) for n in sys.argv[4:]]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    for n in counts:
        segs = [(255,0,0)] + [(0,255,0)] * max(n - 2, 0) + ([(0,0,255)] if n > 1 else [])
        razer(s, ip, pkt(0xB0, [0x01, n] + [c for rgb in segs for c in rgb]))
        print(time.strftime("%H:%M:%S"), f"n={n}", flush=True)
        time.sleep(hold)
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", restore)), "colorTemInKelvin": 0}})
