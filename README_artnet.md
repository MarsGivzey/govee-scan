# Art-Net -> Govee bridge

- `make_artnet_csv.py` builds `artnet_map.csv` from `devices.json` + `strips.json` (refuses to overwrite without `--force`).
- `artnet_govee.py` reads the CSV, listens for ArtDmx on UDP 6454, and drives the lights with Razer packets.
  Run: `python3 -I artnet_govee.py` (add `--dry-run -v` to print instead of send; `--port 6455` to test beside another listener).
  Stop with Ctrl-C or `pkill -TERM -f artnet_govee.py`; it turns Razer off and restores 3200K / 100%.
- CSV columns: mac, govee_id, sku (info only), n, x, universe, num_channels, start_channel, zones.
  Universe is the 0-based wire value. Channelsets are RGB triples; `zones` like `0;1;2-35` says which segments each set drives, blank = even split of x.
- Quit GLanSync first (it holds UDP 4002, needed for the scan that finds each device's IP by Govee id).

## Windows
- No pip installs; stdlib only, Python 3.8+. Run `py -3 -I artnet_govee.py` (or `python -I artnet_govee.py`). Stop with Ctrl-C (restores white).
- Allow Python through Windows Defender Firewall on the private network when prompted (needs inbound UDP 4002 for scan replies and 6454 for Art-Net).
- With several adapters (WSL, Hyper-V, VPN) the multicast scan can leave the wrong one: pass `--interface <this PC's IP on the lights' network>`.
- The Windows path is untested (written and checked on macOS only).
