"""Walk one dot from segment <from> down to <to> on a strip, changing color each step; a yellow reference dot stays on segment 0.
Frame length is fixed at n for every step (discrete mode 00, UDP 4003). The step log maps color -> segment.
Usage: python3 -I razer_dot_walk.py <ip> <n> <from> <to> <hold_s> <restore r,g,b | NNNNK> <palette letters> [reference palette letters]
"""
import base64, json, signal, socket, sys, time

CTRL = 4003
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))      # so the cleanup in finally runs when stopped
COLORS = {"R":(255,0,0),"G":(0,255,0),"B":(0,0,255),"C":(0,255,255),"M":(255,0,255),"Y":(255,255,0),"W":(255,255,255),"K":(0,0,0)}
def pkt(cmd, data):
    body = bytes([0xBB, len(data) >> 8, len(data) & 0xFF, cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])
send = lambda s, ip, m: s.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda s, ip, raw: send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

ip, n, start, stop, hold, restore, palette = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]), sys.argv[6], sys.argv[7]
refpal = sys.argv[8] if len(sys.argv) > 8 else "Y"      # reference dot on segment 0 changes color every len(palette) steps
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    for i, pos in enumerate(range(start, stop - 1, -1)):
        letter = palette[i % len(palette)]
        segs = [COLORS["K"]] * n
        ref = refpal[(i // len(palette)) % len(refpal)]
        segs[0] = COLORS[ref]
        segs[pos] = COLORS[letter]
        raw = pkt(0xB0, [0x00, n] + [v for rgb in segs for v in rgb])
        print(time.strftime("%H:%M:%S"), f"segment {pos} = {letter}  (reference dot on segment 0 = {ref})", flush=True)
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
