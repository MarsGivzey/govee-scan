"""Strobe one Govee device with frames of n segments (Razer packets, UDP 4003, discrete mode 00).
Usage: python3 -I strobe_one.py <ip> <n> <seconds> <interval_s> <color letter> <restore r,g,b | NNNNK>
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

ip, n, secs, interval, color, restore = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), sys.argv[5], sys.argv[6]
on = pkt(0xB0, [0x00, n] + list(COLORS[color]) * n)
off = pkt(0xB0, [0x00, n] + [0, 0, 0] * n)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
flashes = 0
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    t0, lit = time.time(), True
    while time.time() - t0 < secs:
        razer(s, ip, on if lit else off)
        flashes += lit
        lit = not lit
        time.sleep(interval)
    print(f"{flashes} flashes in {time.time() - t0:.1f}s at n={n}", flush=True)
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    if restore.endswith("K"):
        send(s, ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": int(restore[:-1])}})
    else:
        send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", (int(v) for v in restore.split(",")))), "colorTemInKelvin": 0}})
