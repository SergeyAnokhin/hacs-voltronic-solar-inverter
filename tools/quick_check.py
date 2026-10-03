"""Quick read-only health check: is the inverter reachable and answering?

Sends only QMOD and QPIGS (CRC-framed, read-only) over one TCP connection and prints
the mode and a few live values in about a second. Exit code 0 = OK, 1 = failure.

Usage:
    python tools/quick_check.py
    python tools/quick_check.py --host 192.168.1.47 --port 8899 --raw
"""
import argparse
import socket
import sys
import time

DEFAULT_HOST = "192.168.1.47"
DEFAULT_PORT = 8899
COMMANDS = ("QMOD", "QPIGS")  # read-only queries only (AGENTS.md section 0)
MODES = {
    "P": "power on", "S": "standby", "L": "line", "B": "battery", "F": "fault",
    "H": "power saving", "D": "shutdown", "C": "charging, output off",
}
QPIGS_FIELDS = (  # (index, label, unit)
    (0, "grid", "V"), (2, "output", "V"), (5, "load", "W"), (6, "load", "%"),
    (8, "battery", "V"), (9, "charge", "A"), (15, "discharge", "A"),
    (13, "PV", "V"), (19, "PV", "W"), (11, "heat sink", "C"),
)


def crc16(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def escape(b):
    return b + 1 if b in (0x28, 0x0D, 0x0A) else b


def frame(cmd):
    raw = cmd.encode("ascii")
    crc = crc16(raw)
    return raw + bytes([escape(crc >> 8), escape(crc & 0xFF)]) + b"\r"


def read_until_cr(sock, timeout):
    deadline = time.monotonic() + timeout
    data = b""
    while not data.endswith(b"\r"):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"no complete answer in {timeout} s (got {data!r})")
        sock.settimeout(remaining)
        chunk = sock.recv(1024)
        if not chunk:
            raise ConnectionError("connection closed by gateway")
        data += chunk
    return data


def query(sock, cmd, timeout, retries=1):
    """Send cmd; retry once on silence (the first command after idle is sometimes lost)."""
    for attempt in range(retries + 1):
        sock.sendall(frame(cmd))
        try:
            data = read_until_cr(sock, timeout)
            break
        except TimeoutError:
            if attempt == retries:
                raise
            print(f"  {cmd}: no answer, retrying")
    body = data.rstrip(b"\r")
    payload, got = body[:-2], body[-2:]
    crc = crc16(payload)
    crc_ok = got == bytes([escape(crc >> 8), escape(crc & 0xFF)])
    return payload.lstrip(b"(").decode("ascii", "replace"), crc_ok, data


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--raw", action="store_true", help="also print raw response bytes")
    args = ap.parse_args()

    t0 = time.monotonic()
    answers = {}
    try:
        with socket.create_connection((args.host, args.port), timeout=5) as sock:
            for cmd in COMMANDS:
                t = time.monotonic()
                text, crc_ok, raw = query(sock, cmd, args.timeout)
                answers[cmd] = text
                crc = "CRC ok" if crc_ok else "CRC MISMATCH"
                print(f"{cmd:6} {time.monotonic() - t:5.2f}s  {crc}  {text}")
                if args.raw:
                    print(f"       raw: {raw!r}")
                time.sleep(0.3)
    except (OSError, TimeoutError) as err:
        print(f"FAIL after {time.monotonic() - t0:.2f}s: {err}")
        return 1

    mode = answers["QMOD"].strip()
    print(f"\nMode: {mode} = {MODES.get(mode, 'UNKNOWN letter')}")
    fields = answers["QPIGS"].split()
    if len(fields) > 19:
        print("  ".join(f"{label} {fields[i]} {unit}" for i, label, unit in QPIGS_FIELDS))
    else:
        print(f"QPIGS: unexpected field count {len(fields)}")
        return 1
    print(f"OK in {time.monotonic() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
