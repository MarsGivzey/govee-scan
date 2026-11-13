"""Cycle Govee devices through R G B C M Y W via Razer packets (LAN API, UDP 4003).
Reuses the packet builders from razer_flash.py's layout (frame layout confirmed working 2026-11-12, segments=1).
Usage: python3 -I razer_cycle.py <steps> <interval_s> ip=r,g,b [ip=r,g,b ...]   (r,g,b = color to restore afterwards)
"""
import base64, json, socket, sys, time

CTRL = 4003
COLORS = [(255,0,0),(0,255,0),(0,0,255),(0,255,255),(255,0,255),(255,255,0),(255,255,255)]

def pkt(cmd, data):
    body = bytes([0xBB, 0, len(data), cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])

def send(s, ip, msg): s.sendto(json.dumps({"msg": msg}).encode(), (ip, CTRL))
def razer(s, ip, raw): send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

steps, interval = int(sys.argv[1]), float(sys.argv[2])
targets = {a.split("=")[0]: tuple(int(v) for v in a.split("=")[1].split(",")) for a in sys.argv[3:]}
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    for ip in targets: razer(s, ip, pkt(0xB1, [1]))
    time.sleep(0.5)
    for i in range(steps):
        r, g, b = COLORS[i % len(COLORS)]
        for ip in targets: razer(s, ip, pkt(0xB0, [0x01, 1, r, g, b]))
        time.sleep(interval)
finally:
    for ip in targets: razer(s, ip, pkt(0xB1, [0]))
    time.sleep(0.5)
    for ip, (r, g, b) in targets.items():
        send(s, ip, {"cmd": "turn", "data": {"value": 1}})
        send(s, ip, {"cmd": "colorwc", "data": {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": 0}})
