"""Random strobing across all Govee LAN devices via Razer packets (UDP 4003).
H7076 (36 segs, discrete mode 00): 3 blocks = seg 0, seg 1, segs 2..35 together (left+right strips as one color).
Everything else (H60C1, unknown SKUs): one block via mode 01, n=1 (known to work).
Start all black; every tick toggle a few random blocks on (random color) / off.
Usage: python3 -I random_strobe.py <seconds> <tick_s> <toggles_per_tick> <kelvin> <brightness>
"""
import base64, json, random, socket, struct, sys, time

MCAST, SCAN_PORT, LISTEN_PORT, CTRL = "239.255.255.250", 4001, 4002, 4003
secs, tick, toggles, kelvin, bright = float(sys.argv[1]), float(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
PALETTE = [(255,0,0),(0,255,0),(0,0,255),(0,255,255),(255,0,255),(255,255,0),(255,255,255)]
BLACK = (0, 0, 0)

def pkt(cmd, data):
    body = bytes([0xBB, 0, len(data), cmd]) + bytes(data)
    x = 0
    for b in body: x ^= b
    return body + bytes([x])

rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
rx.bind(("", LISTEN_PORT))
rx.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, struct.pack("4sl", socket.inet_aton(MCAST), socket.INADDR_ANY))
rx.settimeout(0.3)
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
scan = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode()

devices = {}
for rnd in range(3):
    end, last = time.time() + 3, 0
    while time.time() < end:
        if time.time() - last > 1: tx.sendto(scan, (MCAST, SCAN_PORT)); last = time.time()
        try: data, addr = rx.recvfrom(4096)
        except socket.timeout: continue
        try: m = json.loads(data)["msg"]
        except Exception: continue
        if m.get("cmd") == "scan": devices[addr[0]] = m["data"]["sku"]
    print(f"scan {rnd + 1}: {len(devices)} devices so far", flush=True)

ips = sorted(devices)
send = lambda ip, m: tx.sendto(json.dumps({"msg": m}).encode(), (ip, CTRL))
razer = lambda ip, raw: send(ip, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

state = {ip: ([BLACK] * 3 if devices[ip] == "H7076" else [BLACK]) for ip in ips}   # block colors per device

def push(ip):
    blocks = state[ip]
    if devices[ip] == "H7076":
        segs = [blocks[0], blocks[1]] + [blocks[2]] * 34
        razer(ip, pkt(0xB0, [0x00, 36] + [c for rgb in segs for c in rgb]))
    else:
        razer(ip, pkt(0xB0, [0x01, 1, *blocks[0]]))

all_blocks = [(ip, b) for ip in ips for b in range(len(state[ip]))]
try:
    for ip in ips: razer(ip, pkt(0xB1, [1]))
    time.sleep(0.5)
    for ip in ips: push(ip)
    end = time.time() + secs
    while time.time() < end:
        touched = set()
        for ip, b in random.sample(all_blocks, toggles):
            state[ip][b] = BLACK if state[ip][b] != BLACK else random.choice(PALETTE)
            touched.add(ip)
        for ip in touched: push(ip)
        time.sleep(tick)
finally:
    for ip in ips: razer(ip, pkt(0xB1, [0]))
    time.sleep(0.5)
    for ip in ips:
        send(ip, {"cmd": "turn", "data": {"value": 1}})
        send(ip, {"cmd": "brightness", "data": {"value": bright}})
        send(ip, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": kelvin}})
    n76 = sum(1 for ip in ips if devices[ip] == "H7076")
    print(f"done: {len(ips)} devices ({n76} H7076, {len(ips) - n76} other), restored to {kelvin}K at {bright}%")
