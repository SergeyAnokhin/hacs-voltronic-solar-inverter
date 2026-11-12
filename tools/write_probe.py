"""OWNER-ONLY manual tester for setting commands. The agent never runs this script.

Sends ONE setting command (or a few named variants) to the inverter, prints the raw
answer bytes (waiting several seconds in case it comes late), and shows which tokens of a
read-only snapshot (HSTS HEEP1 HEEP2 HGEN QMOD by default) changed. Use it to find out
whether a command is understood, what it answers, and where the change shows up.

STOP the Home Assistant integration (or disable it) first: the gateway serves one client.

Examples:
    python tools/write_probe.py "PDAULON01"                 # asks before sending
    python tools/write_probe.py "^S???DAT261112221500" --yes
    python tools/write_probe.py --try ACLT 12 18            # sends 4 variants, asking before each
    python tools/write_probe.py --try ACCT 1 2 --snapshot HEEP2

Commands are sent WITH CRC unless --no-crc. Dangerous commands (factory reset, clearing the
energy counters, calibration shifts, CRC-mode switch, frequency, EEPROM save) are refused.
"""

import argparse
import re
import socket
import sys
import time

from probe_inverter import DEFAULT_HOST, DEFAULT_PORT, H_READ_ALLOWED, QUERY_RE, crc16, escape

# Never send these (docs/settings-map.md, "Never send"). Matched as prefixes.
REFUSED_PREFIXES = ("PF", "^S???CLE", "BTA", "IVA", "F5", "F6", "HOSTCRC", "PSAVE", "RTEY", "POPM", "POP3")
DEFAULT_SNAPSHOT = ["HSTS", "HEEP1", "HEEP2", "HGEN", "QMOD"]


def frame(text: str, crc: bool) -> bytes:
    raw = text.encode("ascii")
    if not crc:
        return raw + b"\r"
    c = crc16(raw)
    return raw + bytes([escape(c >> 8), escape(c & 0xFF)]) + b"\r"


def drain(sock: socket.socket) -> None:
    sock.settimeout(0.2)
    try:
        while sock.recv(1024):
            pass
    except OSError:
        pass


def read_until_cr(sock: socket.socket, timeout: float) -> bytes:
    buf, end = b"", time.monotonic() + timeout
    while time.monotonic() < end:
        sock.settimeout(max(0.05, end - time.monotonic()))
        try:
            chunk = sock.recv(1024)
        except socket.timeout:
            break
        if not chunk:
            break
        buf += chunk
        if buf.endswith(b"\r"):
            break
    return buf


def query(sock: socket.socket, name: str) -> str | None:
    """Read-only query: Q... with CRC, allow-listed H... without. Returns the payload or None."""
    if name in H_READ_ALLOWED:
        data = frame(name, crc=False)
    elif QUERY_RE.fullmatch(name):
        data = frame(name, crc=True)
    else:
        raise SystemExit(f"refusing to read {name!r}: not a Q query or an allow-listed H query")
    drain(sock)
    sock.sendall(data)
    raw = read_until_cr(sock, 2.0)
    body = raw.rstrip(b"\r")
    if not body.startswith(b"("):
        return None
    text = body[1:].decode("ascii", "replace")
    return text if name in H_READ_ALLOWED else text[:-2]  # Q answers end with 2 CRC bytes


def snapshot(sock: socket.socket, names: list[str]) -> dict[str, list[str]]:
    result = {}
    for name in names:
        for _ in range(2):  # the first command after an idle period is sometimes lost
            payload = query(sock, name)
            if payload is not None:
                break
        result[name] = (payload or "").split()
        time.sleep(0.3)
    return result


def show_diff(before: dict[str, list[str]], after: dict[str, list[str]]) -> None:
    changed = False
    for name, old in before.items():
        new = after.get(name, [])
        for i in range(max(len(old), len(new))):
            a = old[i] if i < len(old) else "-"
            b = new[i] if i < len(new) else "-"
            if a != b:
                changed = True
                print(f"    changed {name}[{i}]: {a} -> {b}")
    if not changed:
        print("    no change in the snapshot")


def send_and_report(sock, text: str, *, crc: bool, wait: float, pre_delay: float) -> None:
    if pre_delay:
        time.sleep(pre_delay)
    drain(sock)
    data = frame(text, crc)
    print(f"  sending {text!r}  hex: {data.hex(' ')}")
    start = time.monotonic()
    sock.sendall(data)
    raw = b""
    end = start + wait
    while time.monotonic() < end:
        sock.settimeout(max(0.05, end - time.monotonic()))
        try:
            chunk = sock.recv(1024)
        except socket.timeout:
            break
        if not chunk:
            print("  connection closed by the gateway")
            break
        raw += chunk
        if raw.endswith(b"\r"):
            break
    took = time.monotonic() - start
    if raw:
        print(f"  answer after {took:.2f} s: {raw!r}  hex: {raw.hex(' ')}")
    else:
        print(f"  NO answer within {wait:.0f} s")


def variants(kind: str, start: int, end: int) -> list[tuple[str, bool, float]]:
    """(text, with_crc, pre_delay) candidates for the schedule setters (ACLT = output, ACCT = charger)."""
    hh = f"{start:02d}-{end:02d}"
    body = f"{kind}{hh}"
    return [
        (f"^S???{body}", True, 0.0),  # as in the vendor tool (what the integration sends)
        (f"^S???{body}", True, 2.0),  # the tool waits 1-2 s before sending
        (f"^S{len(body) + 3:03d}{body}", True, 0.0),  # PI18-style length digits instead of "???"
        (f"^S???{kind}{start:02d}{end:02d}", True, 0.0),  # without the hyphen
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", help="exact command text, e.g. PDAULON01")
    ap.add_argument("--try", dest="try_kind", nargs=3, metavar=("ACLT|ACCT", "START", "END"),
                    help="send the known variants of a schedule setter, one at a time")
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--no-crc", action="store_true", help="send without CRC")
    ap.add_argument("--wait", type=float, default=8.0, help="seconds to wait for an answer (default 8)")
    ap.add_argument("--pre-delay", type=float, default=0.0, help="pause before sending (single command)")
    ap.add_argument("--snapshot", nargs="*", default=DEFAULT_SNAPSHOT, help="read-only queries before / after")
    ap.add_argument("--yes", action="store_true", help="do not ask before sending")
    args = ap.parse_args()

    if bool(args.command) == bool(args.try_kind):
        ap.error("give either a command or --try ACLT|ACCT START END")
    jobs: list[tuple[str, bool, float]]
    if args.try_kind:
        kind, start, end = args.try_kind[0].upper(), int(args.try_kind[1]), int(args.try_kind[2])
        if kind not in ("ACLT", "ACCT") or not (0 <= start <= 23 and 0 <= end <= 23):
            ap.error("--try needs ACLT or ACCT and hours 0..23")
        jobs = variants(kind, start, end)
    else:
        jobs = [(args.command, not args.no_crc, args.pre_delay)]
    for text, _, _ in jobs:
        if not re.fullmatch(r"[\x20-\x7e]{2,40}", text) or text.startswith(REFUSED_PREFIXES):
            print(f"refusing {text!r}", file=sys.stderr)
            return 2

    sock = socket.create_connection((args.host, args.port), timeout=5)
    try:
        before = snapshot(sock, args.snapshot)
        print("snapshot before:", {k: " ".join(v) for k, v in before.items()})
        for text, crc, pre_delay in jobs:
            if not args.yes:
                if input(f"Send {text!r} ({'with' if crc else 'without'} CRC, pre-delay {pre_delay} s)? [y/N] ").lower() != "y":
                    print("  skipped")
                    continue
            send_and_report(sock, text, crc=crc, wait=args.wait, pre_delay=pre_delay)
            time.sleep(2.0)
            after = snapshot(sock, args.snapshot)
            show_diff(before, after)
            before = after
    finally:
        sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
