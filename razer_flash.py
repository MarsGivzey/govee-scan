"""Flash Govee devices red/off via the Razer streaming packets (LAN API, UDP 4003).

Packet layout (community docs): BB <len16> <cmd> <data...> <xor of all prior bytes>
 enable  = BB 00 01 B1 01 0A   disable = BB 00 01 B1 00 0B   (matches Govee's published pt values)
 frame   = BB <len16> B0 <data: 01? n r g b ...> <xor>   (frame layout is UNVERIFIED)
Usage: python3 -I razer_flash.py <flashes> <segments> ip [ip ...]
"""
import base64, json, socket, sys, time

CTRL = 4003

def pkt(cmd, data):
    body = bytes([0xBB, 0, len(data), cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])

def send(sock, ip, msg):
    sock.sendto(json.dumps({"msg": msg}).encode(), (ip, CTRL))

def razer(sock, ip, raw):
    send(sock, ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

flashes, segs, ips = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3:]
assert pkt(0xB1, [1]) == base64.b64decode("uwABsQEK") and pkt(0xB1, [0]) == base64.b64decode("uwABsQAL")

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
frame = lambda rgb: pkt(0xB0, [0x01, segs] + list(rgb) * segs)
try:
    for ip in ips: razer(s, ip, pkt(0xB1, [1]))
    time.sleep(0.5)
    for _ in range(flashes):
        for rgb in ((255, 0, 0), (0, 0, 0)):
            for ip in ips: razer(s, ip, frame(rgb))
            time.sleep(0.4)
finally:
    for ip in ips: razer(s, ip, pkt(0xB1, [0]))
    time.sleep(0.5)
    for ip in ips:
        send(s, ip, {"cmd": "devStatus", "data": {}})
