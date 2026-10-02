"""Read-only diagnostic probe for a Voltronic-compatible inverter behind an RS232<->TCP gateway.

Sends ONLY query commands (``Q...``) and prints what happens: timings, raw bytes, CRC check.
Compares the legacy strategy (new TCP connection per command, single recv) with a
streaming strategy (one connection, read until CR, CRC verified).

Usage:
    python tools/probe_inverter.py --mode both
    python tools/probe_inverter.py --mode new --save tests/fixtures/raw_responses.json
    python tools/probe_inverter.py --mode new --cmds QPIGS QPIRI --extra QPIGS2 QPI
"""
import argparse
import json
import re
import socket
import sys
import time

DEFAULT_HOST = "192.168.1.47"
DEFAULT_PORT = 8899
DEFAULT_CMDS = ["QPIGS", "QPIRI", "QPIWS", "QMOD", "QFLAG", "QID", "QVFW", "QT", "QET", "QED", "QOPPT", "QCHPT"]
QUERY_RE = re.compile(r"^Q[A-Z0-9]{1,14}$")
NO_CRC = False  # set by --no-crc
# Read-only Solar Plug "H" queries, explicitly approved by the owner (2026-10-02). Exact names only.
H_READ_ALLOWED = {
    "HSTS", "HGRID", "HOP", "HBAT", "HPV", "HPVB", "HTEMP", "HGEN", "HIMSG1",
    "HBMS1", "HBMS2", "HBMS3", "HEEP1", "HEEP2",
}
# Read-only discovery guesses (name variants without parameters), approved by the owner for research.
H_READ_ALLOWED |= {
    "HEEP0", "HEEP3", "HEEP4", "HBMS0", "HBMS4", "HIMSG0", "HIMSG2", "HIMSG3", "HGEN1", "HGEN2",
    "HSTS1", "HSTS2", "HPV1", "HPV2", "HPVB1", "HTEMP1", "HOP1", "HOP2", "HGRID1", "HBAT1", "HBAT2",
    "HDOP", "HDOP1", "HPAR", "HPAR1", "HLOAD", "HLGEN", "HCON", "HUSE", "HTIME", "HCLK", "HSCH", "HBEQ",
}
T0 = time.monotonic()


def log(msg):
    print(f"[{time.monotonic() - T0:7.2f}s] {msg}", flush=True)


def crc16(data):
    crc = 0
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def escape(b):
    return b + 1 if b in (0x28, 0x0D, 0x0A) else b


def build_frame(cmd):
    # Safety rule (AGENTS.md section 0): read-only. Refuse anything that is not a Q query.
    if not (QUERY_RE.match(cmd) or cmd in H_READ_ALLOWED):
        raise ValueError(f"refusing to send non-query command {cmd!r}")
    raw = cmd.encode("ascii")
    if NO_CRC:
        # Solar Plug / Solar of Things dongles send plain ASCII + CR (no CRC).
        return raw + b"\r"
    crc = crc16(raw)
    return raw + bytes([escape(crc >> 8), escape(crc & 0xFF)]) + b"\r"


def check_response(data):
    """Return (payload_text, crc_ok) for a raw response frame."""
    body = data.rstrip(b"\r\n")
    if len(body) < 3 or not body.startswith(b"("):
        return body.decode("ascii", "replace"), None
    payload, got = body[:-2], body[-2:]
    crc = crc16(payload)
    expect = bytes([escape(crc >> 8), escape(crc & 0xFF)])
    return payload[1:].decode("ascii", "replace"), got == expect


def legacy_fetch(host, port, cmd, timeout):
    """Same behaviour as python_scripts/get_inverter_info.py: connect, send, one recv(1024), close."""
    t = time.monotonic()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        t_conn = time.monotonic() - t
        s.sendall(build_frame(cmd))
        data = s.recv(1024)
        s.close()
        return data, t_conn, None
    except Exception as e:  # report instead of swallowing
        return b"", None, f"{type(e).__name__}: {e}"


class Stream:
    """One persistent connection; reads until CR with a deadline."""

    def __init__(self, host, port, timeout):
        self.timeout = timeout
        t = time.monotonic()
        self.s = socket.create_connection((host, port), timeout=timeout)
        log(f"connected in {time.monotonic() - t:.3f}s")

    def drain(self):
        self.s.settimeout(0.05)
        try:
            while self.s.recv(1024):
                pass
        except OSError:
            pass

    def fetch(self, cmd):
        self.drain()
        self.s.sendall(build_frame(cmd))
        deadline = time.monotonic() + self.timeout
        buf = b""
        while time.monotonic() < deadline:
            self.s.settimeout(max(0.05, deadline - time.monotonic()))
            try:
                chunk = self.s.recv(1024)
            except socket.timeout:
                break
            if not chunk:
                return buf, "connection closed by gateway"
            buf += chunk
            if buf.endswith(b"\r"):
                return buf, None
        return buf, "timeout" if not buf else "timeout (partial frame, no CR)"

    def close(self):
        self.s.close()


def report(cmd, data, elapsed, err, results):
    text, crc_ok = check_response(data) if data else ("", None)
    status = "ERR " + err if err else ("NAK" if text == "NAK" else "ok")
    log(f"{cmd:7s} {elapsed:6.3f}s  {status:12s} crc={crc_ok}  {len(data)}B  {text!r}")
    if data:
        log(f"        raw hex: {data.hex(' ')}")
    results[cmd] = {"raw_hex": data.hex(), "text": text, "crc_ok": crc_ok, "seconds": round(elapsed, 3), "error": err}


def run_legacy(host, port, cmds, gap, timeout):
    log(f"=== LEGACY: new connection per command, gap {gap}s, timeout {timeout}s ===")
    results, start = {}, time.monotonic()
    for cmd in cmds:
        t = time.monotonic()
        data, t_conn, err = legacy_fetch(host, port, cmd, timeout)
        report(cmd, data, time.monotonic() - t, err, results)
        time.sleep(gap)
    log(f"LEGACY total: {time.monotonic() - start:.2f}s")
    return results


def run_stream(host, port, cmds, gap, timeout):
    log(f"=== STREAM: one connection, read until CR, gap {gap}s, timeout {timeout}s ===")
    results, start = {}, time.monotonic()
    st = Stream(host, port, timeout)
    try:
        for cmd in cmds:
            t = time.monotonic()
            data, err = st.fetch(cmd)
            report(cmd, data, time.monotonic() - t, err, results)
            time.sleep(gap)
    finally:
        st.close()
    log(f"STREAM total: {time.monotonic() - start:.2f}s")
    return results


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default=DEFAULT_HOST)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--mode", choices=["legacy", "new", "both"], default="both")
    ap.add_argument("--cmds", nargs="+", default=DEFAULT_CMDS, help="query commands (must start with Q)")
    ap.add_argument("--extra", nargs="*", default=[], help="additional Q commands for discovery")
    ap.add_argument("--gap", type=float, help="pause between commands (default: 0.3 legacy, 0.1 new)")
    ap.add_argument("--timeout", type=float, default=2.0)
    ap.add_argument("--save", help="write all results to this JSON file")
    ap.add_argument("--no-crc", action="store_true", help="send plain ASCII + CR without CRC (Solar Plug style)")
    a = ap.parse_args()
    global NO_CRC
    NO_CRC = a.no_crc

    cmds = [c.upper() for c in a.cmds + a.extra]
    out = {}
    if a.mode in ("legacy", "both"):
        out["legacy"] = run_legacy(a.host, a.port, cmds, a.gap if a.gap is not None else 0.3, a.timeout)
    if a.mode in ("new", "both"):
        out["stream"] = run_stream(a.host, a.port, cmds, a.gap if a.gap is not None else 0.1, a.timeout)
    if a.save:
        with open(a.save, "w", encoding="utf-8") as f:
            json.dump({"host": a.host, "taken_at": time.strftime("%Y-%m-%d %H:%M:%S"), **out}, f, indent=2)
        log(f"saved {a.save}")


if __name__ == "__main__":
    sys.exit(main())
