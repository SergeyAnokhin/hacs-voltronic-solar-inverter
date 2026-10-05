"""Read-only power-balance logger for the self-consumption / hidden-PV tests.

Every PERIOD s on one TCP connection: QMOD, QPIGS (CRC) and HGRID, HPV (no CRC,
owner-approved read-only H queries). Appends one CSV row per cycle.
Run only while the HA integration is disabled: the gateway mixes answers between clients.
Samples whose CRC or format is wrong are dropped (logged as errors).

Usage:
    python tools/balance_logger.py log.csv     (stop with Ctrl+C)
"""
import csv
import socket
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from quick_check import DEFAULT_HOST, DEFAULT_PORT, frame, read_until_cr, crc16, escape  # noqa: E402

PERIOD = 5.0
GAP = 0.2
TIMEOUT = 1.5
ALLOWED = {"QMOD", "QPIGS", "HGRID", "HPV"}  # read-only only (AGENTS.md section 0)
FIELDS = [
    "time", "mode", "load_w", "load_va", "batt_v", "chg_a", "dis_a", "pv_v", "pv_a", "pv_w19",
    "hpv_v", "hpv_a", "hpv_w", "grid_w", "grid_v", "bus_v", "status", "status2", "batt_w", "losses_w",
]


def ask(sock, cmd):
    assert cmd in ALLOWED
    plain = cmd.startswith("H")
    sock.sendall(cmd.encode() + b"\r" if plain else frame(cmd))
    data = read_until_cr(sock, TIMEOUT).rstrip(b"\r")
    if not plain:
        payload, got = data[:-2], data[-2:]
        crc = crc16(payload)
        if got != bytes([escape(crc >> 8), escape(crc & 0xFF)]):
            raise ValueError(f"{cmd}: bad CRC")
        data = payload
    if b"\r" in data or not data.startswith(b"("):
        raise ValueError(f"{cmd}: mixed answer {data!r}")
    return data[1:].decode("ascii")


def cycle(sock):
    mode = ask(sock, "QMOD"); time.sleep(GAP)
    q = ask(sock, "QPIGS").split(); time.sleep(GAP)
    if len(q) < 21 or len(q[16]) != 8:
        raise ValueError(f"QPIGS: unexpected {q}")
    g = ask(sock, "HGRID").split(); time.sleep(GAP)
    h = ask(sock, "HPV").split()
    if len(g) < 7 or len(h) < 3 or not g[6][0] in "+-":
        raise ValueError(f"H: unexpected {g} {h}")
    v, chg, dis = float(q[8]), int(q[9]), int(q[15])
    load, pv19, grid = int(q[5]), int(q[19]), int(g[6])
    batt = v * (dis - chg)
    return {
        "time": datetime.now().strftime("%H:%M:%S"), "mode": mode,
        "load_w": load, "load_va": int(q[4]), "batt_v": v, "chg_a": chg, "dis_a": dis,
        "pv_v": float(q[13]), "pv_a": float(q[12]), "pv_w19": pv19,
        "hpv_v": float(h[0]), "hpv_a": float(h[1]), "hpv_w": int(h[2]),
        "grid_w": grid, "grid_v": float(q[0]), "bus_v": int(q[7]),
        "status": q[16], "status2": q[20], "batt_w": round(batt, 1),
        "losses_w": round(pv19 + batt + grid - load, 1),
    }


def main(path):
    sock = None
    with open(path, "a", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        if f.tell() == 0:
            w.writeheader()
        while True:
            start = time.monotonic()
            try:
                if sock is None:
                    sock = socket.create_connection((DEFAULT_HOST, DEFAULT_PORT), timeout=3)
                row = cycle(sock)
                w.writerow(row); f.flush()
                print(" ".join(f"{k}={row[k]}" for k in FIELDS), flush=True)
            except Exception as err:  # drop the connection so answers cannot shift
                print(f"{datetime.now():%H:%M:%S} error: {err}", flush=True)
                if sock is not None:
                    sock.close()
                sock = None
            time.sleep(max(0.5, PERIOD - (time.monotonic() - start)))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # OS error texts may be localized
    main(sys.argv[1])
