"""
split_engine.py - core "Rail Split" logic. Pure Python: no database, no FastAPI.

How your leg_availability table is read
---------------------------------------
Each row = (train, class, date, from_stop_sequence, to_stop_sequence, seats_booked)
and means: "for a journey from stop `from` to stop `to`, `seats_booked` seats are already taken".
Free seats for that exact range = total_seats - seats_booked.

Most stop pairs have no row of their own, so availability of any pair (a, b) is derived like this:
  1. a row for exactly (a, b) exists                    -> use it
  2. rows that COVER (a, b) exist (they start at/before a and end at/after b)
        a seat free for the long range is also free for the short one -> take the best of them (safe, never over-promises)
  3. rows INSIDE (a, b) exist                           -> availability can't be more than the smallest of them
  4. nothing is recorded                                -> nothing booked -> all seats free

Search priority:  1) direct   2) split on the SAME train   3) split across DIFFERENT trains
"""

MIN_LAYOVER_MIN = 30       # shortest allowed change between two trains
MAX_LAYOVER_MIN = 12 * 60  # longest wait we will suggest
MAX_DAY_OFFSET = 3         # train B may start up to this many days after train A's travel date


# ---------------------------------------------------------------- time helpers
def parse_hhmm(value):
    if not value:
        return None
    h, m = str(value).split(":")[:2]
    return int(h) * 60 + int(m)


def fmt_hhmm(minutes):
    return None if minutes is None else f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def add_absolute_times(stops):
    """
    Adds arr_abs / dep_abs = minutes since midnight of the day the train leaves its origin.
    Handles overnight trains (clock goes 23:xx -> 00:xx -> day +1).
    """
    cur = None
    for s in stops:
        for key, abs_key in (("arrival_time", "arr_abs"), ("departure_time", "dep_abs")):
            t = parse_hhmm(s[key])
            if t is None:
                s[abs_key] = None
                continue
            if cur is None:
                cand = t
            else:
                cand = (cur // 1440) * 1440 + t
                if cand < cur:
                    cand += 1440
            s[abs_key] = cand
            cur = cand
    return stops


# ---------------------------------------------------------------- availability
def pair_availability(total, rows, a, b):
    """rows = [(from_seq, to_seq, seats_booked), ...] for one train/class/date."""
    exact = [bk for f, t, bk in rows if f == a and t == b]
    if exact:
        return max(0, total - max(exact))
    covering = [total - bk for f, t, bk in rows if f <= a and t >= b]
    if covering:
        return max(0, max(covering))
    inside = [total - bk for f, t, bk in rows if a <= f and t <= b]
    if inside:
        return max(0, min(inside))
    return total


def _station(stop):
    return {"id": stop["station_id"], "name": stop["station_name"], "code": stop["station_code"]}


class TrainData:
    """One train, on one travel date, for one class."""

    def __init__(self, info, stops, total_seats, rows, travel_date):
        self.info = info                       # {train_id, train_number, train_name}
        self.stops = add_absolute_times(stops)
        self.total = total_seats
        self.rows = rows
        self.travel_date = travel_date
        self._by_station = {s["station_id"]: s for s in self.stops}
        self._by_seq = {s["stop_sequence"]: s for s in self.stops}

    def stop_of_station(self, station_id):
        return self._by_station.get(station_id)

    def seats(self, a_seq, b_seq):
        return pair_availability(self.total, self.rows, a_seq, b_seq)

    def leg(self, a_seq, b_seq, seats=None):
        a, b = self._by_seq[a_seq], self._by_seq[b_seq]
        return {
            "train_id": self.info["train_id"],
            "train_number": self.info["train_number"],
            "train_name": self.info["train_name"],
            "travel_date": self.travel_date.isoformat(),
            "from_station": _station(a),
            "to_station": _station(b),
            "departure": fmt_hhmm(a["dep_abs"]),
            "arrival": fmt_hhmm(b["arr_abs"]),
            "arrival_day_offset": b["arr_abs"] // 1440 - a["dep_abs"] // 1440,   # 1 = reaches next day
            "seats_available": self.seats(a_seq, b_seq) if seats is None else seats,
            "distance_km": (b.get("distance_km") or 0) - (a.get("distance_km") or 0),
        }


# ---------------------------------------------------------------- 1. direct
def direct_option(train, src_id, dst_id, need=1):
    a, b = train.stop_of_station(src_id), train.stop_of_station(dst_id)
    if not a or not b or a["stop_sequence"] >= b["stop_sequence"]:
        return None
    seats = train.seats(a["stop_sequence"], b["stop_sequence"])
    if seats < need:
        return None
    return {"tickets": 1, "min_seats": seats,
            "legs": [train.leg(a["stop_sequence"], b["stop_sequence"], seats)]}


# ---------------------------------------------------------------- 2. same-train split
def same_train_split(train, src_id, dst_id, need=1):
    """
    Fewest-ticket chain of seat-available segments from src to dst on ONE train.
    DP over stops: best[j] = (tickets needed to reach stop j, biggest bottleneck seat count, previous stop).
    """
    a, b = train.stop_of_station(src_id), train.stop_of_station(dst_id)
    if not a or not b or a["stop_sequence"] >= b["stop_sequence"]:
        return None

    seqs = [s["stop_sequence"] for s in train.stops
            if a["stop_sequence"] <= s["stop_sequence"] <= b["stop_sequence"]]
    n = len(seqs)
    best = [None] * n
    best[0] = (0, 10 ** 9, None)

    for j in range(1, n):
        for i in range(j):
            if best[i] is None:
                continue
            f = train.seats(seqs[i], seqs[j])
            if f < need:
                continue
            cand = (best[i][0] + 1, min(best[i][1], f), i)
            cur = best[j]
            if cur is None or (cand[0], -cand[1]) < (cur[0], -cur[1]):
                best[j] = cand

    if best[-1] is None:
        return None
    legs, j = [], n - 1
    while best[j][2] is not None:
        i = best[j][2]
        legs.append(train.leg(seqs[i], seqs[j]))
        j = i
    legs.reverse()
    if len(legs) < 2:
        return None
    return {"tickets": len(legs), "legs": legs, "min_seats": min(l["seats_available"] for l in legs)}


# ---------------------------------------------------------------- 3. different-train split
def different_train_options(train_ids, load, src_id, dst_id, need=1, limit=5):
    """
    Train A: src -> X, Train B: X -> dst.  `load(train_id, day_offset)` returns a TrainData for travel_date + offset.
    Train B may run the same day or the next day; we take the first one that gives a layover of
    MIN_LAYOVER_MIN .. MAX_LAYOVER_MIN minutes at X.
    """
    options = []
    for ta in train_ids:
        A = load(ta, 0)
        sa = A.stop_of_station(src_id)
        if not sa:
            continue
        for stop in A.stops:
            x = stop["station_id"]
            if stop["stop_sequence"] <= sa["stop_sequence"] or x == dst_id or stop["arr_abs"] is None:
                continue
            f1 = A.seats(sa["stop_sequence"], stop["stop_sequence"])
            if f1 < need:
                continue
            for tb in train_ids:
                if tb == ta:
                    continue
                for offset in range(MAX_DAY_OFFSET + 1):   # was (0, 1): too short when train A reaches X on day 2+
                    B = load(tb, offset)
                    sx, sd = B.stop_of_station(x), B.stop_of_station(dst_id)
                    if not sx or not sd or sx["stop_sequence"] >= sd["stop_sequence"] or sx["dep_abs"] is None:
                        break
                    layover = sx["dep_abs"] + offset * 1440 - stop["arr_abs"]
                    if not (MIN_LAYOVER_MIN <= layover <= MAX_LAYOVER_MIN):
                        continue
                    f2 = B.seats(sx["stop_sequence"], sd["stop_sequence"])
                    if f2 >= need:
                        options.append({
                            "tickets": 2, "layover_min": layover, "change_at": _station(stop),
                            "min_seats": min(f1, f2),
                            "legs": [A.leg(sa["stop_sequence"], stop["stop_sequence"], f1),
                                     B.leg(sx["stop_sequence"], sd["stop_sequence"], f2)],
                        })
                    break
    options.sort(key=lambda o: o["layover_min"])
    return options[:limit]