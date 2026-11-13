"""Art-Net (ArtDmx, UDP 6454) -> Govee LAN Razer bridge.

Config is a CSV (default artnet_map.csv next to this script), one row per device:
  mac, govee_id, n, x, universe, num_channels, start_channel     required
  sku                                                            optional, informational
  zones                                                          optional, e.g. "0;1;2-35": the segments each channelset drives
- universe: Art-Net port-address as on the wire (0-based; some software shows it 1-based). start_channel is 1-based, 1..512.
- num_channels = 3 x channelsets (RGB each). A channelset colours every segment in its zone; segments in no zone stay black.
- zones blank = split the x attached segments evenly across the channelsets.
- n = segments per frame (the controller's limit), x = segments actually attached. Frames are always n long, mode 00.
- IPs are looked up from the Govee scan reply by govee_id (DHCP-proof); mac is only cross-checked against ARP.

Sending: on any channel change the frame goes out immediately and again --repeat-delay-ms later (2 sends per change);
a device whose channels haven't moved gets its frame re-sent every --keepalive seconds so it stays in Razer mode.
On exit (SIGINT/SIGTERM): razer off, then turn on + brightness + colour temperature restore.
GLanSync holds UDP 4002; quit it first.

Usage: python3 -I artnet_govee.py [--csv PATH] [--port 6454] [--keepalive 5] [--repeat-delay-ms 20] [--rescan 30]
                                  [--restore-kelvin 3200] [--restore-brightness 100] [--dry-run] [-v]
"""
import argparse, base64, csv, json, os, re, select, signal, socket, struct, subprocess, sys, time

MCAST, SCAN_PORT, LISTEN_PORT, CTRL = "239.255.255.250", 4001, 4002, 4003
OP_DMX = 0x5000
HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED = ["mac", "govee_id", "n", "x", "universe", "num_channels", "start_channel"]

def log(msg): print(time.strftime("%H:%M:%S"), msg, flush=True)

def pkt(cmd, data):
    body = bytes([0xBB, len(data) >> 8, len(data) & 0xFF, cmd]) + bytes(data)   # 16-bit length: frames over 255 data bytes need it
    x = 0
    for b in body: x ^= b
    return body + bytes([x])

ENABLE, DISABLE = pkt(0xB1, [1]), pkt(0xB1, [0])

def parse_zones(text, count, x, where):
    if text.strip():
        zones = []
        for part in text.split(";"):
            lo, _, hi = part.strip().partition("-")
            zones.append((int(lo), int(hi or lo)))
        if len(zones) != count: raise ValueError(f"{where}: {len(zones)} zones but num_channels gives {count} channelsets")
    else:
        if count > x: raise ValueError(f"{where}: {count} channelsets but only x={x} segments")
        zones = [(k * x // count, (k + 1) * x // count - 1) for k in range(count)]
    for lo, hi in zones:
        if not 0 <= lo <= hi < x: raise ValueError(f"{where}: zone {lo}-{hi} is outside the {x} attached segments")
    return zones

class Device:
    def __init__(self, row, where):
        miss = [c for c in REQUIRED if not (row.get(c) or "").strip()]
        if miss: raise ValueError(f"{where}: missing {', '.join(miss)}")
        self.mac, self.id = row["mac"].strip().upper(), row["govee_id"].strip().upper()
        self.sku = (row.get("sku") or "").strip()
        self.n, self.x = int(row["n"]), int(row["x"])
        self.universe, self.nch, self.start = int(row["universe"]), int(row["num_channels"]), int(row["start_channel"])
        if not 1 <= self.n <= 255: raise ValueError(f"{where}: n={self.n} must be 1..255")
        if not 1 <= self.x <= self.n: raise ValueError(f"{where}: x={self.x} must be 1..n")
        if not 0 <= self.universe <= 0x7FFF: raise ValueError(f"{where}: universe {self.universe} out of range")
        if self.nch < 3 or self.nch % 3: raise ValueError(f"{where}: num_channels={self.nch} must be a positive multiple of 3")
        if not 1 <= self.start or self.start - 1 + self.nch > 512: raise ValueError(f"{where}: channels {self.start}..{self.start - 1 + self.nch} leave the 512-channel universe")
        self.zones = parse_zones(row.get("zones") or "", self.nch // 3, self.x, where)
        self.name = f"{self.sku or 'device'} {self.id}"
        self.ip = None
        self.chan = bytearray(self.nch)
        self.frame = self.build()
        self.last_tx = 0.0
        self.due = []            # monotonic times at which to send the current frame again
        self.sent = 0

    def build(self):
        segs = bytearray(3 * self.n)
        for z, (lo, hi) in enumerate(self.zones):
            for s in range(lo, hi + 1): segs[3 * s:3 * s + 3] = self.chan[3 * z:3 * z + 3]
        return pkt(0xB0, [0x00, self.n] + list(segs))

def load_csv(path):
    devs, seen = [], set()
    with open(path, newline="") as f:
        rd = csv.DictReader(f)
        for need in REQUIRED:
            if need not in (rd.fieldnames or []): sys.exit(f"{path}: no '{need}' column")
        for i, row in enumerate(rd, start=2):
            try: d = Device(row, f"{os.path.basename(path)} line {i}")
            except ValueError as e: sys.exit(str(e))
            if d.id in seen: sys.exit(f"{path} line {i}: duplicate govee_id {d.id}")
            seen.add(d.id)
            devs.append(d)
    for i, a in enumerate(devs):
        for b in devs[i + 1:]:
            if a.universe == b.universe and a.start < b.start + b.nch and b.start < a.start + a.nch:
                log(f"warning: {a.name} and {b.name} overlap on universe {a.universe} (they will mirror each other there)")
    return devs

def parse_artdmx(data):
    if len(data) < 18 or data[:8] != b"Art-Net\x00": return None
    if struct.unpack_from("<H", data, 8)[0] != OP_DMX: return None
    universe = struct.unpack_from("<H", data, 14)[0] & 0x7FFF      # SubUni low byte + Net high byte, 15 bits
    length = struct.unpack_from(">H", data, 16)[0]
    return universe, data[18:18 + length]

def arp_table():
    macs = {}
    try: out = subprocess.run(["arp", "-a"] if os.name == "nt" else ["arp", "-a", "-n"], capture_output=True, text=True).stdout
    except OSError: return macs
    for line in out.splitlines():
        m = re.search(r"\((\d+\.\d+\.\d+\.\d+)\) at ([0-9a-f:]+) on", line)                 # macOS / Linux: "? (10.0.0.5) at aa:bb:.. on en0"
        w = re.match(r"\s*(\d+\.\d+\.\d+\.\d+)\s+([0-9a-f]{2}(?:-[0-9a-f]{2}){5})\s", line, re.I)   # Windows: "  10.0.0.5   aa-bb-..   dynamic"
        if (m and "incomplete" not in line) or w:
            ip, mac = (m.group(1), m.group(2).split(":")) if m else (w.group(1), w.group(2).split("-"))
            macs[ip] = ":".join(p.zfill(2) for p in mac).upper()   # macOS drops leading zeros
    return macs

def reusable(sock):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"): sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)   # not on Windows
    return sock

def default_lan_ip():          # the address of the interface that routes off-box; a UDP connect() sends nothing
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 9))
        return s.getsockname()[0]
    except OSError: return None
    finally: s.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=os.path.join(HERE, "artnet_map.csv"))
    ap.add_argument("--port", type=int, default=6454)
    ap.add_argument("--keepalive", type=float, default=5.0)
    ap.add_argument("--repeat-delay-ms", type=float, default=20.0)
    ap.add_argument("--rescan", type=float, default=30.0)
    ap.add_argument("--restore-kelvin", type=int, default=3200)
    ap.add_argument("--restore-brightness", type=int, default=100)
    ap.add_argument("--interface", help="local IP of the NIC on the lights' network (default: the default-route NIC); matters on Windows with several adapters (WSL, Hyper-V, VPN)")
    ap.add_argument("--dry-run", action="store_true", help="no network output to devices; print what would be sent")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    devs = load_csv(args.csv)
    by_id = {d.id: d for d in devs}
    by_universe = {}
    for d in devs: by_universe.setdefault(d.universe, []).append(d)
    log(f"{len(devs)} devices from {args.csv}; listening for Art-Net universes {sorted(by_universe)} on UDP {args.port}")

    stop = []
    for s in (signal.SIGINT, signal.SIGTERM): signal.signal(s, lambda *_: stop.append(1))

    iface = args.interface or default_lan_ip()
    log(f"multicast scan interface: {iface or 'OS default'}")
    art = reusable(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
    art.bind(("", args.port))
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    if iface: tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(iface))
    socks = [art]
    scan_rx = None
    if not args.dry_run:
        scan_rx = reusable(socket.socket(socket.AF_INET, socket.SOCK_DGRAM))
        scan_rx.bind(("", LISTEN_PORT))
        scan_rx.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, socket.inet_aton(MCAST) + socket.inet_aton(iface or "0.0.0.0"))
        socks.append(scan_rx)
    scan_msg = json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode()

    def send_json(d, m):
        if args.dry_run: log(f"[dry-run] {d.name}: {json.dumps(m)[:120]}")
        else: tx.sendto(json.dumps({"msg": m}).encode(), (d.ip, CTRL))

    def razer(d, raw):
        if args.dry_run and raw not in (ENABLE, DISABLE): log(f"[dry-run] {d.name}: frame {raw.hex()}")
        elif args.dry_run: log(f"[dry-run] {d.name}: {'enable' if raw == ENABLE else 'disable'}")
        else: send_json(d, {"cmd": "razer", "data": {"pt": base64.b64encode(raw).decode()}})

    def push(d, now):
        razer(d, d.frame)
        d.last_tx, d.sent = now, d.sent + 1

    def bring_up(d, now):          # razer on (twice), then the current frame twice once the device has had a moment to switch
        razer(d, ENABLE); razer(d, ENABLE)
        d.due = [now + 0.5, now + 0.55]
        d.last_tx = now

    def on_scan_reply(data, addr, now, unknown):
        try: m = json.loads(data)["msg"]
        except Exception: return
        if m.get("cmd") != "scan": return
        info = m["data"]
        d = by_id.get(info["device"].upper())
        if d is None:
            if info["device"] not in unknown:
                unknown.add(info["device"]); log(f"scanned but not in the CSV, ignoring: {info.get('sku')} {addr[0]} {info['device']}")
            return
        if d.ip != addr[0]:
            log(f"{d.name}: {'found' if d.ip is None else 'moved from ' + d.ip + ' to'} {addr[0]}")
            d.ip = addr[0]
            bring_up(d, now)

    rx_stats = {"pkts": 0, "seen": set(), "since": time.monotonic()}

    def on_artnet(data, now, addr):
        rx_stats["pkts"] += 1
        parsed = parse_artdmx(data)
        if parsed is None:
            key = (addr[0], "not-dmx", data[8:10].hex() if data[:7] == b"Art-Net" else "not-artnet")
            if key not in rx_stats["seen"]:
                rx_stats["seen"].add(key)
                log(f"art-net: ignoring non-ArtDmx packet from {addr[0]} ({len(data)} bytes, {key[2]})")
            return
        universe, dmx = parsed
        key = (addr[0], universe)
        if key not in rx_stats["seen"]:
            rx_stats["seen"].add(key)
            mapped = "mapped" if universe in by_universe else "NOT in the CSV, ignored"
            log(f"art-net: first ArtDmx from {addr[0]} universe {universe} ({len(dmx)} channels, {mapped}; max channel value {max(dmx, default=0)})")
        for d in by_universe.get(universe, ()):
            seg = dmx[d.start - 1:d.start - 1 + d.nch]
            if not seg: continue
            new = bytearray(d.chan)
            new[:len(seg)] = seg                 # a short packet only updates the channels it carries
            if new == d.chan: continue
            d.chan = new
            d.frame = d.build()
            if d.ip is None: continue            # picked up by bring_up once the device is found
            if args.verbose: log(f"{d.name}: channels {d.start}..{d.start + d.nch - 1} changed")
            push(d, now)
            if args.repeat_delay_ms > 0: d.due.append(now + args.repeat_delay_ms / 1000)
            else: push(d, now)

    if args.dry_run:
        now = time.monotonic()
        for d in devs: d.ip = "dry-run"; bring_up(d, now)

    unknown, scans_sent, next_scan, arp_check_at = set(), 0, time.monotonic(), time.monotonic() + 10
    try:
        while not stop:
            now = time.monotonic()
            if not args.dry_run and now >= next_scan:
                tx.sendto(scan_msg, (MCAST, SCAN_PORT))
                scans_sent += 1
                unresolved = any(d.ip is None for d in devs)
                next_scan = now + (1.0 if unresolved and scans_sent < 8 else args.rescan)
            if arp_check_at and now >= arp_check_at:
                arp_check_at = 0
                if not args.dry_run:
                    macs = arp_table()
                    for d in devs:
                        if d.ip is None: log(f"{d.name}: not found on the network")
                        elif macs.get(d.ip) is None: log(f"{d.name}: {d.ip} has no ARP entry, MAC not checked")
                        elif macs[d.ip] != d.mac: log(f"warning: {d.name} at {d.ip} has MAC {macs[d.ip]}, CSV says {d.mac}")
            timeout = 0.5
            for d in devs:
                if d.ip is not None:
                    timeout = min(timeout, max(0.0, d.last_tx + args.keepalive - now), *(max(0.0, t - now) for t in d.due))
            ready, _, _ = select.select(socks, [], [], timeout)
            now = time.monotonic()
            if now - rx_stats["since"] >= 10:
                if rx_stats["pkts"]: log(f"art-net: {rx_stats['pkts']} packets in the last {now - rx_stats['since']:.0f} s")
                rx_stats["pkts"], rx_stats["since"] = 0, now
            for s in ready:
                try: data, addr = s.recvfrom(4096)
                except ConnectionResetError: continue      # Windows surfaces ICMP port-unreachable as a recv error
                if s is art: on_artnet(data, now, addr)
                else: on_scan_reply(data, addr, now, unknown)
            for d in devs:
                if d.ip is None: continue
                while d.due and d.due[0] <= now:
                    d.due.pop(0); push(d, now)
                if now - d.last_tx >= args.keepalive:
                    if args.verbose: log(f"{d.name}: keepalive")
                    push(d, now)
    finally:
        log("stopping: razer off, restoring white")
        live = [d for d in devs if d.ip is not None]
        for d in live: razer(d, DISABLE)
        time.sleep(0.5)
        for rnd in range(2):                      # a single colorwc right after a stream often doesn't stick
            for d in live:
                send_json(d, {"cmd": "turn", "data": {"value": 1}})
                send_json(d, {"cmd": "brightness", "data": {"value": args.restore_brightness}})
                send_json(d, {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}, "colorTemInKelvin": args.restore_kelvin}})
            if rnd == 0: time.sleep(1.0)
        log("frames sent: " + ", ".join(f"{d.id[-5:]}={d.sent}" for d in devs))

main()
