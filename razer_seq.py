"""Send a sequence of single-color frames of given segment counts, holding each (UDP 4003, discrete mode 00).
Token = <letter><n>[+<letter><n>...], e.g. G48 = 48 segments all green, K47+R1 = 47 black then 1 red.  Letters R G B C M Y W K.
Usage: python3 -I razer_seq.py <ip> <hold_s> <restore r,g,b | NNNNK> TOKEN [TOKEN ...]
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

ip, hold, restore, tokens = sys.argv[1], float(sys.argv[2]), sys.argv[3], sys.argv[4:]
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    for t in tokens:
        runs = [(part[0], int(part[1:])) for part in t.split("+")]      # e.g. K47+R1 = 47 black then 1 red
        n = sum(count for _, count in runs)
        raw = pkt(0xB0, [0x00, n] + [v for letter, count in runs for v in list(COLORS[letter]) * count])
        print(time.strftime("%H:%M:%S"), t, flush=True)
        end = time.time() + hold
        while time.time() < end:
            razer(s, ip, raw)
            time.sleep(min(1, hold))      # short holds: one frame per token
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    if restore.endswith("K"):
        send(s, ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": int(restore[:-1])}})
    else:
        send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", (int(v) for v in restore.split(",")))), "colorTemInKelvin": 0}})
