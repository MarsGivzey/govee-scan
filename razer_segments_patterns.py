"""Send explicit per-segment patterns to one Govee device via Razer packets (UDP 4003).
Edit PATTERNS below. Usage: python3 -I razer_segments_patterns.py <ip> <hold_s> <restore r,g,b> [mode]
  mode = byte after B0: 00 discrete segments, 01 gradient (default 01; earlier tests were all 01)
"""
import base64, json, socket, sys, time

CTRL = 4003
R, G, B, C, M, Y = (255,0,0), (0,255,0), (0,0,255), (0,255,255), (255,0,255), (255,255,0)
PATTERNS = [("RG", [R, G]), ("CMY", [C, M, Y]), ("RGBR", [R, G, B, R])]

def pkt(cmd, data):
    body = bytes([0xBB, 0, len(data), cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])
def send(s, ip, msg): s.sendto(json.dumps({"msg": msg}).encode(), (ip, CTRL))
def razer(s, ip, raw): send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

ip, hold, restore = sys.argv[1], float(sys.argv[2]), tuple(int(v) for v in sys.argv[3].split(","))
mode = int(sys.argv[4], 16) if len(sys.argv) > 4 else 0x01
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    for name, segs in PATTERNS:
        raw = pkt(0xB0, [mode, len(segs)] + [c for rgb in segs for c in rgb])
        razer(s, ip, raw)
        print(time.strftime("%H:%M:%S"), f"mode={mode:02x} n={len(segs)} {name}", raw.hex(), flush=True)
        time.sleep(hold)
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", restore)), "colorTemInKelvin": 0}})
