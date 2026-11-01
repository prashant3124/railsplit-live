import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

# railsplit.db must sit in the same folder as main.py (or set the RAILSPLIT_DB environment variable)
DB_PATH = os.getenv("RAILSPLIT_DB", str(Path(__file__).resolve().parent / "railsplit.db"))

if not Path(DB_PATH).exists():
    raise SystemExit(f"Database file not found: {DB_PATH}\n"
                     "Copy railsplit.db next to main.py (or run setup_database.py first).")


@contextmanager
def get_conn():
    """One connection per request. isolation_level=None -> we control transactions with BEGIN/COMMIT."""
    conn = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------- schema upgrade (runs automatically, safe to repeat)
# Approximate rail km of each station along its corridor (demo values).
_WEST = {"MMCT": 0, "BVI": 30, "ST": 263, "BRC": 392, "RTM": 655, "NAD": 710, "KOTA": 919, "NDLS": 1384}
_SOUTH = {"MAS": 0, "BZA": 431, "KMT": 538, "WL": 690, "BPQ": 925, "NGP": 1091, "ET": 1385, "BPL": 1481,
          "VGLJ": 1771, "GWL": 1876, "AGC": 1992, "NZM": 2177, "NDLS": 2182}
_KOTA_NZM = {"KOTA": 0, "NZM": 465}


def _fill_distances(conn):
    """train_route.distance_km = km from the train's first stop."""
    trains = [r[0] for r in conn.execute("SELECT train_id FROM trains")]
    for tid in trains:
        stops = conn.execute(
            """SELECT r.route_id, s.station_code FROM train_route r
               JOIN stations s ON s.station_id=r.station_id
               WHERE r.train_id=? ORDER BY r.stop_sequence""", (tid,)).fetchall()
        codes = [c for _, c in stops]
        table = next((t for t in (_KOTA_NZM, _WEST, _SOUTH) if all(c in t for c in codes)), None)
        if table is None:
            continue
        origin = table[codes[0]]
        for route_id, code in stops:
            conn.execute("UPDATE train_route SET distance_km=? WHERE route_id=? AND distance_km IS NULL",
                         (abs(table[code] - origin), route_id))


def ensure_schema():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(train_route)")}
        if "distance_km" not in cols:
            conn.execute("ALTER TABLE train_route ADD COLUMN distance_km INTEGER")
        bcols = {r[1] for r in conn.execute("PRAGMA table_info(booking)")}
        if "total_fare" not in bcols:
            conn.execute("ALTER TABLE booking ADD COLUMN total_fare REAL")
        if "payment_id" not in bcols:
            conn.execute("ALTER TABLE booking ADD COLUMN payment_id INTEGER")
        conn.execute("""CREATE TABLE IF NOT EXISTS passenger (
            passenger_id INTEGER PRIMARY KEY AUTOINCREMENT,
            booking_id   INTEGER NOT NULL REFERENCES booking(booking_id),
            name         VARCHAR(100) NOT NULL,
            age          INTEGER NOT NULL,
            gender       VARCHAR(10) NOT NULL,
            berth_pref   VARCHAR(20))""")
        conn.execute("""CREATE TABLE IF NOT EXISTS payment (
            payment_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL REFERENCES users(user_id),
            transaction_id VARCHAR(30) UNIQUE NOT NULL,
            method         VARCHAR(20) NOT NULL,
            amount         REAL NOT NULL,
            status         VARCHAR(20) NOT NULL,
            created_at     DATETIME DEFAULT CURRENT_TIMESTAMP)""")
        _fill_distances(conn)
        conn.commit()
    finally:
        conn.close()


ensure_schema()