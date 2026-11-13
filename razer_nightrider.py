"""Knight Rider scanner on a Govee strip via Razer packets (UDP 4003, discrete mode 00).
Usage: python3 -I razer_nightrider.py <ip> <n_segments> <sweeps> <fps> <tail_len> <restore r,g,b>
 one sweep = one full pass in a single direction; head bounces at the ends
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

ip, n, sweeps, fps, tail = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), float(sys.argv[4]), int(sys.argv[5])
restore = tuple(int(v) for v in sys.argv[6].split(","))
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def frame(head, direction):
    segs = []
    for i in range(n):
        behind = (head - i) * direction          # >0 means segment trails the head
        level = 1.0 if behind == 0 else (1 - behind / (tail + 1)) ** 2 if 0 < behind <= tail else 0
        segs.append((int(255 * level), 0, 0))
    return pkt(0xB0, [0x00, n] + [c for rgb in segs for c in rgb])

try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    for k in range(sweeps):
        positions = range(n) if k % 2 == 0 else range(n - 1, -1, -1)
        direction = 1 if k % 2 == 0 else -1
        for head in positions:
            razer(s, ip, frame(head, direction))
            time.sleep(1 / fps)
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", restore)), "colorTemInKelvin": 0}})
