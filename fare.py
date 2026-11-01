"""
fare.py - Indian-Railways-style fare calculator (DEMO values, approximate).

Fare = base fare (distance slabs x class rate x train-type multiplier, with a minimum)
     + reservation charge + superfast surcharge
     + GST 5% (AC classes only, on the three items above)
     + catering (Rajdhani, AC classes, journeys >= 500 km)
     + convenience fee (per ticket, like IRCTC; GST 18% on it)
All amounts are in rupees and are computed on the SERVER, so the frontend can't tamper with them.
"""

# rupees per km for the first slab (0-500 km); later slabs are cheaper, like real IR tariffs
CLASS_RATE = {"SL": 0.62, "3AC": 1.60, "2AC": 2.30, "1AC": 3.90}
SLABS = [(500, 1.00), (1000, 0.85), (10 ** 9, 0.70)]        # (upto km, share of the first-slab rate)

MIN_BASE = {"SL": 120, "3AC": 300, "2AC": 400, "1AC": 700}
RESERVATION = {"SL": 20, "3AC": 40, "2AC": 50, "1AC": 60}
SUPERFAST = {"SL": 30, "3AC": 45, "2AC": 45, "1AC": 75}
CATERING = {"SL": 0, "3AC": 400, "2AC": 500, "1AC": 700}    # Rajdhani only
CONVENIENCE = {"SL": 15, "3AC": 30, "2AC": 30, "1AC": 30}   # per ticket
AC_CLASSES = {"3AC", "2AC", "1AC"}
TYPE_MULTIPLIER = {"Rajdhani": 1.25, "Superfast": 1.0, "Express": 1.0}


def train_type(train_number: str, train_name: str) -> str:
    if "rajdhani" in train_name.lower():
        return "Rajdhani"
    if str(train_number)[:2] in ("12", "22", "20"):
        return "Superfast"
    return "Express"


def base_fare(km: int, class_code: str, ttype: str) -> float:
    rate, prev, total = CLASS_RATE[class_code], 0, 0.0
    for upto, share in SLABS:
        part = min(km, upto) - prev
        if part <= 0:
            break
        total += part * rate * share
        prev = upto
    total *= TYPE_MULTIPLIER[ttype]
    return max(float(MIN_BASE[class_code]), round(total))


def leg_fare(km: int, class_code: str, train_number: str, train_name: str) -> dict:
    """Fare for ONE seat on ONE ticket (one leg)."""
    ttype = train_type(train_number, train_name)
    base = base_fare(km, class_code, ttype)
    reservation = RESERVATION[class_code]
    superfast = SUPERFAST[class_code] if ttype in ("Rajdhani", "Superfast") else 0
    gst = round((base + reservation + superfast) * 0.05) if class_code in AC_CLASSES else 0
    catering = CATERING[class_code] if ttype == "Rajdhani" and km >= 500 else 0
    convenience = round(CONVENIENCE[class_code] * 1.18, 2)    # fee + 18% GST on the fee
    per_seat = base + reservation + superfast + gst + catering
    return {
        "distance_km": km, "train_type": ttype,
        "base_fare": base, "reservation": reservation, "superfast": superfast,
        "gst": gst, "catering": catering,
        "fare_per_seat": per_seat,
        "convenience_fee": convenience,        # once per ticket, not per seat
    }


def leg_total(f: dict, passengers: int) -> float:
    return round(f["fare_per_seat"] * passengers + f["convenience_fee"], 2)
