"""Find how many Razer segments a Govee device accepts (UDP 4003).
Step n sends the first n of R,G,B,C,M,Y,W (cycled); frames with too many segments are dropped by the device,
so the last step that visibly changes is its segment count.
Usage: python3 -I razer_probe_max.py [palette=CMYW] [mode=00|01] <ip> <hold_s> <restore r,g,b | NNNNK> n [n ...]
"""
import base64, json, signal, socket, sys, time

CTRL = 4003
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))      # so the cleanup in finally runs when stopped
COLORS = {"R":(255,0,0),"G":(0,255,0),"B":(0,0,255),"C":(0,255,255),"M":(255,0,255),"Y":(255,255,0),"W":(255,255,255)}
NAMES = "RGBCMYW"   # default palette; override with palette=CMYW as the first argument

def pkt(cmd, data):
    body = bytes([0xBB, 0, len(data), cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])
def send(s, ip, msg): s.sendto(json.dumps({"msg": msg}).encode(), (ip, CTRL))
def razer(s, ip, raw): send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

argv = sys.argv[1:]
MODE = 0x01   # byte after B0: 00 discrete segments, 01 gradient
while argv[0].startswith(("palette=", "mode=")):
    k, v = argv.pop(0).split("=")
    if k == "palette": NAMES = v
    else: MODE = int(v, 16)
PALETTE = [COLORS[c] for c in NAMES]
ip, hold, restore, counts = argv[0], float(argv[1]), argv[2], [int(n) for n in argv[3:]]   # restore = "r,g,b" or "2800K"
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    for n in counts:
        segs = [PALETTE[i % len(PALETTE)] for i in range(n)]
        razer(s, ip, pkt(0xB0, [MODE, n] + [c for rgb in segs for c in rgb]))
        print(time.strftime("%H:%M:%S"), f"mode={MODE:02x} n={n}", "".join(NAMES[i % len(NAMES)] for i in range(n)), flush=True)
        time.sleep(hold)
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    if restore.endswith("K"):
        send(s, ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": int(restore[:-1])}})
    else:
        send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", (int(v) for v in restore.split(",")))), "colorTemInKelvin": 0}})
