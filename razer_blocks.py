"""Hold one Razer frame of n segments colored in blocks (UDP 4003, discrete mode 00).
Packet length is a 16-bit big-endian value in bytes 1-2 (needed when 3*n+2 > 255; layout beyond 255 is an INFERENCE
from the community doc's "extended size" byte, small packets are byte-identical to the 1-byte form).
Usage: python3 -I razer_blocks.py <ip> <n> <block_size> <palette letters> <hold_s> <restore r,g,b | NNNNK>
"""
import base64, json, socket, sys, time

CTRL = 4003
COLORS = {"R":(255,0,0),"G":(0,255,0),"B":(0,0,255),"C":(0,255,255),"M":(255,0,255),"Y":(255,255,0),"W":(255,255,255),"K":(0,0,0)}

def pkt(cmd, data):
    body = bytes([0xBB, len(data) >> 8, len(data) & 0xFF, cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])
assert pkt(0xB1, [1]) == base64.b64decode("uwABsQEK")
send = lambda s, ip, m: s.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda s, ip, raw: send(s, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

ip, n, block, palette, hold, restore = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4], float(sys.argv[5]), sys.argv[6]
segs = [COLORS[palette[(i // block) % len(palette)]] for i in range(n)]
raw = pkt(0xB0, [0x00, n] + [v for rgb in segs for v in rgb])
print(f"n={n} block={block} blocks={-(-n // block)} packet={len(raw)} bytes, header {raw[:4].hex()}", flush=True)
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
    razer(s, ip, pkt(0xB1, [1])); time.sleep(0.5)
    end = time.time() + hold
    while time.time() < end:
        razer(s, ip, raw)
        time.sleep(2)
finally:
    razer(s, ip, pkt(0xB1, [0])); time.sleep(0.5)
    send(s, ip, {"cmd": "turn", "data": {"value": 1}})
    if restore.endswith("K"):
        send(s, ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": int(restore[:-1])}})
    else:
        send(s, ip, {"cmd": "colorwc", "data": {"color": dict(zip("rgb", (int(v) for v in restore.split(",")))), "colorTemInKelvin": 0}})
