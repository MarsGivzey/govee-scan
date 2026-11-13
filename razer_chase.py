"""Chase + strobe across Govee devices via Razer packets (LAN API, UDP 4003).
Usage: python3 -I razer_chase.py <laps> <hop_s> <strobe_steps> <strobe_s> ip=r,g,b [ip=r,g,b ...]
 chase order = argument order; r,g,b = color restored afterwards.
"""
import base64, json, socket, sys, time

CTRL = 4003
LAP_COLORS = [(255,0,0),(0,255,0),(0,0,255),(0,255,255),(255,0,255),(255,255,0),(255,255,255)]

def pkt(cmd, data):
    body = bytes([0xBB, 0, len(data), cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])

def send(s, ip, msg): s.sendto(json.dumps({"msg": msg}).encode(), (ip, CTRL))
def razer(s, ip, raw): send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})
def color(s, ip, rgb): razer(s, ip, pkt(0xB0, [0x01, 1, *rgb]))

laps, hop, sn, sint = int(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4])
targets = {a.split("=")[0]: tuple(int(v) for v in a.split("=")[1].split(",")) for a in sys.argv[5:]}
ips = list(targets)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    for ip in ips: razer(s, ip, pkt(0xB1, [1]))
    time.sleep(0.5)
    for lap in range(laps):
        c = LAP_COLORS[lap % len(LAP_COLORS)]
        for lit in ips:
            for ip in ips: color(s, ip, c if ip == lit else (0, 0, 0))
            time.sleep(hop)
    for ip in ips: color(s, ip, (0, 0, 0))
    time.sleep(0.4)
    for i in range(sn):
        c = (255, 255, 255) if i % 2 == 0 else (0, 0, 0)
        for ip in ips: color(s, ip, c)
        time.sleep(sint)
finally:
    for ip in ips: razer(s, ip, pkt(0xB1, [0]))
    time.sleep(0.5)
    for ip, (r, g, b) in targets.items():
        send(s, ip, {"cmd": "turn", "data": {"value": 1}})
        send(s, ip, {"cmd": "colorwc", "data": {"color": {"r": r, "g": g, "b": b}, "colorTemInKelvin": 0}})
