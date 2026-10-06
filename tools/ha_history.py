"""Read-only export of entity history from a copied Home Assistant recorder database.

Opens the SQLite file in read-only mode (never writes to it). Local time is the time zone
of the machine running the script. See docs/local-data.md.

Usage:
    python tools/ha_history.py list [PATTERN]                      entities with history (SQL LIKE, e.g. %vevor_elfin%)
    python tools/ha_history.py states ENTITY [ENTITY ...] [--from 2026-10-05] [--to 2026-10-06] [--csv out.csv]
    python tools/ha_history.py stats ENTITY [ENTITY ...] [--short] [--from ...] [--to ...] [--csv out.csv]
"""
import argparse
import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "local_data" / "home-assistant_v2.db"


def connect(path):
    return sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)


def ts(text):
    return datetime.fromisoformat(text).timestamp() if text else None


def fmt(t):
    return datetime.fromtimestamp(t).isoformat(sep=" ", timespec="seconds") if t is not None else ""


def time_filter(column, args):
    sql, params = "", []
    if args.date_from:
        sql += f" and {column} >= ?"
        params.append(ts(args.date_from))
    if args.date_to:
        sql += f" and {column} < ?"
        params.append(ts(args.date_to))
    return sql, params


def cmd_list(con, args):
    pattern = args.pattern or "%"
    rows = con.execute(
        """select m.entity_id, count(*), min(s.last_updated_ts), max(s.last_updated_ts)
           from states s join states_meta m using(metadata_id)
           where m.entity_id like ? group by m.entity_id order by m.entity_id""",
        (pattern,),
    ).fetchall()
    stats = dict(
        (r[0], r[1:]) for r in con.execute(
            """select m.statistic_id, m.unit_of_measurement, count(*), min(s.start_ts)
               from statistics s join statistics_meta m on m.id = s.metadata_id
               where m.statistic_id like ? group by m.statistic_id""",
            (pattern,),
        )
    )
    print(f"{'entity_id':60} {'states':>7} {'states from':19} {'states to':19}  long-term stats")
    for entity, count, first, last in rows:
        st = stats.pop(entity, None)
        st_txt = f"{st[1]} h from {fmt(st[2])[:10]} [{st[0] or ''}]" if st else "-"
        print(f"{entity:60} {count:7} {fmt(first):19} {fmt(last):19}  {st_txt}")
    for entity, (unit, count, first) in sorted(stats.items()):
        print(f"{entity:60} {0:7} {'':19} {'':19}  {count} h from {fmt(first)[:10]} [{unit or ''}]")


def cmd_states(con, args):
    where, params = time_filter("s.last_updated_ts", args)
    marks = ",".join("?" * len(args.entities))
    rows = con.execute(
        f"""select s.last_updated_ts, m.entity_id, s.state
            from states s join states_meta m using(metadata_id)
            where m.entity_id in ({marks}){where} order by s.last_updated_ts""",
        [*args.entities, *params],
    )
    write(args, ["time", "entity_id", "state"], ((fmt(t), e, v) for t, e, v in rows))


def cmd_stats(con, args):
    table = "statistics_short_term" if args.short else "statistics"
    where, params = time_filter("s.start_ts", args)
    marks = ",".join("?" * len(args.entities))
    rows = con.execute(
        f"""select s.start_ts, m.statistic_id, s.mean, s.min, s.max, s.state, s.sum
            from {table} s join statistics_meta m on m.id = s.metadata_id
            where m.statistic_id in ({marks}){where} order by s.start_ts""",
        [*args.entities, *params],
    )
    write(args, ["start", "entity_id", "mean", "min", "max", "state", "sum"],
          ((fmt(r[0]), *r[1:]) for r in rows))


def write(args, header, rows):
    out = open(args.csv, "w", newline="", encoding="utf-8") if args.csv else sys.stdout
    try:
        w = csv.writer(out)
        w.writerow(header)
        n = 0
        for row in rows:
            w.writerow(row)
            n += 1
    finally:
        if args.csv:
            out.close()
    print(f"{n} rows", file=sys.stderr)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--db", default=DEFAULT_DB, help="recorder database (default: local_data/home-assistant_v2.db)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list").add_argument("pattern", nargs="?")
    for name in ("states", "stats"):
        sp = sub.add_parser(name)
        sp.add_argument("entities", nargs="+")
        sp.add_argument("--from", dest="date_from", help="local date/time, ISO (2026-10-05 or 2026-10-05T08:00)")
        sp.add_argument("--to", dest="date_to", help="local date/time, ISO, exclusive")
        sp.add_argument("--csv", help="write CSV here instead of stdout")
        if name == "stats":
            sp.add_argument("--short", action="store_true", help="5-minute statistics instead of hourly")
    args = p.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")  # units such as °C on a Windows console
    con = connect(args.db)
    {"list": cmd_list, "states": cmd_states, "stats": cmd_stats}[args.cmd](con, args)


if __name__ == "__main__":
    main()
