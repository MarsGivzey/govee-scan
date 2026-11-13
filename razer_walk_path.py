"""Light groups of Govee segments in a given order via Razer packets (UDP 4003, discrete mode 00).
Usage: python3 -I razer_walk_path.py <ip> <n_segments> <step_s> <lit r,g,b> <restore r,g,b> <group> [group ...]
  group = comma-separated segment indices lit together, e.g. 0  2,19  18,35  1
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

ip, n, step = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
lit = tuple(int(v) for v in sys.argv[4].split(","))
restore = tuple(int(v) for v in sys.argv[5].split(","))
groups = [[int(i) for i in g.split(",")] for g in sys.argv[6:]]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    for g in groups:
        segs = [lit if j in g else (0, 0, 0) for j in range(n)]
        razer(s, ip, pkt(0xB0, [0x00, n] + [c for rgb in segs for c in rgb]))
        print(time.strftime("%H:%M:%S"), g, flush=True)
        time.sleep(step)
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", restore)), "colorTemInKelvin": 0}})
