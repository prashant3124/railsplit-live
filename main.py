"""
Rail Split - FastAPI backend (SQLite: railsplit.db)

Run:   pip install -r requirements.txt
       uvicorn main:app --reload
Docs:  http://127.0.0.1:8000/docs   (try every endpoint from the browser)
"""

import os
from dotenv import load_dotenv

load_dotenv()
import re
import secrets
from datetime import date, datetime, timedelta
from typing import List
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import smtplib
from email.message import EmailMessage

import bcrypt
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from pydantic import BaseModel, Field, validator

from database import get_conn
import split_engine as eng
import fare as fare_calc

SECRET_KEY = os.getenv("JWT_SECRET", "change-this-secret-before-submitting")
ALGORITHM = "HS256"
TOKEN_HOURS = 12

SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

FRONTEND_RESET_URL = os.getenv(
    "FRONTEND_RESET_URL",
    "http://127.0.0.1:5500/index.html"
)

# EMAIL CONFIGURATION
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

SMTP_EMAIL = os.getenv("SMTP_EMAIL")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

# Frontend URL where the reset form is available
FRONTEND_RESET_URL = os.getenv(
    "FRONTEND_RESET_URL",
    "http://127.0.0.1:5500/index.html"
)

app = FastAPI(title="Rail Split API")

# frontend on VS Code Live Server (127.0.0.1:5500) or opened directly as a file ("null")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500", "http://localhost:5500", "null"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CLASS_ALIASES = {"sleeper": "SL", "sl": "SL", "3ac": "3AC", "2ac": "2AC", "1ac": "1AC"}
EMAIL_RE = re.compile(r"^\S+@\S+\.\S+$")
bearer = HTTPBearer()


# --------------------------------------request models
#registration
class RegisterIn(BaseModel):
    name: str = Field(min_length=1)
    email: str
    phone: str | None = None
    password: str = Field(min_length=8)

    @validator("password")
    def validate_password(cls, value):
        if not re.search(r"[A-Z]", value):
            raise ValueError("Password must contain an uppercase letter")

        if not re.search(r"[a-z]", value):
            raise ValueError("Password must contain a lowercase letter")

        if not re.search(r"[0-9]", value):
            raise ValueError("Password must contain a number")

        if not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError("Password must contain a special character")

        return value

#Login
class LoginIn(BaseModel):
    email: str
    password: str
    
# Forgot password request
class ForgotPasswordIn(BaseModel):
    email: str


# Reset password request
class ResetPasswordIn(BaseModel):
    token: str
    new_password: str = Field(min_length=8)

    @validator("new_password")
    def validate_new_password(cls, value):
        if not re.search(r"[A-Z]", value):
            raise ValueError(
                "Password must contain an uppercase letter"
            )

        if not re.search(r"[a-z]", value):
            raise ValueError(
                "Password must contain a lowercase letter"
            )

        if not re.search(r"[0-9]", value):
            raise ValueError(
                "Password must contain a number"
            )

        if not re.search(r"[^A-Za-z0-9]", value):
            raise ValueError(
                "Password must contain a special character"
            )

        return value

#train Search
class SearchIn(BaseModel):
    source: str                      
    destination: str
    travel_date: date
    class_name: str = "Sleeper"      # Sleeper / 3AC / 2AC / 1AC
    passengers: int = Field(default=1, ge=1, le=6)

#journey ka ek segment
class LegIn(BaseModel):
    train_id: int
    from_station_id: int
    to_station_id: int
    travel_date: date               

class PassengerIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    age: int = Field(ge=1, le=120)
    gender: str                       # Male / Female / Other
    berth_pref: str = "No preference"

    @validator("name")
    def clean_name(cls, v):
        v = v.strip()
        if not re.fullmatch(r"[A-Za-z .'-]{1,60}", v):
            raise ValueError("Passenger name can contain only letters and spaces")
        return v

    @validator("gender")
    def valid_gender(cls, v):
        if v not in ("Male", "Female", "Other"):
            raise ValueError("Gender must be Male, Female or Other")
        return v


# DEMO payment: nothing is charged. We only check the shape of what the user typed.
class PaymentIn(BaseModel):
    method: str                       # UPI / Card / NetBanking
    upi_id: str | None = None
    card_number: str | None = None
    card_expiry: str | None = None
    card_cvv: str | None = None
    bank: str | None = None


#booking request
class BookIn(BaseModel):
    class_name: str = "Sleeper"
    passengers: List[PassengerIn] = Field(min_length=1, max_length=6)
    legs: List[LegIn] = Field(min_length=1)
    payment: PaymentIn


# authentication function - For Register and login Security 
#create JWT Token
def make_token(user_id: int) -> str:
    exp = datetime.utcnow() + timedelta(hours=TOKEN_HOURS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, SECRET_KEY, algorithm=ALGORITHM)

#For logged_in user verify
def current_user_id(cred: HTTPAuthorizationCredentials = Depends(bearer)) -> int:
    try:
        return int(jwt.decode(cred.credentials, SECRET_KEY, algorithms=[ALGORITHM])["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(401, "Invalid or expired token. Please log in again.")

#hash password using bcrypt
def hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
def send_reset_email(to_email: str, reset_link: str):
    if not SMTP_EMAIL or not SMTP_PASSWORD:
        raise HTTPException(
            status_code=500,
            detail="Email service is not configured."
        )

    message = EmailMessage()
    message["Subject"] = "Rail Split - Password Reset"
    message["From"] = SMTP_EMAIL
    message["To"] = to_email

    message.set_content(
        f"""Hello,

We received a request to reset your Rail Split password.

Click the link below to set a new password:

{reset_link}

This link expires in 15 minutes.

If you did not request this, please ignore this email.

Rail Split Team
"""
    )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_EMAIL, SMTP_PASSWORD)
            server.send_message(message)

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Unable to send reset email. Check email configuration."
        )

# ---------------------------------------------------------------- db helpers
def get_class(conn, class_name: str):
    code = CLASS_ALIASES.get(class_name.strip().lower(), class_name.strip().upper())
    row = conn.execute("SELECT class_id, class_name, total_seats FROM coach_classes WHERE class_name=?",
                       (code,)).fetchone()
    if not row:
        raise HTTPException(400, f"Unknown class '{class_name}'")
    return row


def resolve_station(conn, text: str):
    """code  >  exact station name  >  exact city  >  partial name.  ('Delhi' -> New Delhi)"""
    t = text.strip()
    row = conn.execute(
        """SELECT station_id, station_code, station_name, city FROM stations
           WHERE UPPER(station_code)=UPPER(?) OR LOWER(station_name)=LOWER(?)
              OR LOWER(city)=LOWER(?) OR LOWER(station_name) LIKE LOWER(?)
           ORDER BY (UPPER(station_code)=UPPER(?)) DESC, (LOWER(station_name)=LOWER(?)) DESC,
                    (LOWER(city)=LOWER(?)) DESC, station_id LIMIT 1""",
        (t, t, t, f"%{t}%", t, t, t),
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Station '{text}' not found")
    return dict(row)


def load_train(conn, train_row, klass, travel_date: date) -> eng.TrainData:
    stops = conn.execute(
        """SELECT r.stop_sequence, r.arrival_time, r.departure_time, r.distance_km,
                  s.station_id, s.station_name, s.station_code
           FROM train_route r JOIN stations s ON s.station_id = r.station_id
           WHERE r.train_id=? ORDER BY r.stop_sequence""",
        (train_row["train_id"],),
    ).fetchall()
    rows = conn.execute(
        """SELECT from_stop_sequence, to_stop_sequence, seats_booked FROM leg_availability
           WHERE train_id=? AND class_id=? AND travel_date=?""",
        (train_row["train_id"], klass["class_id"], travel_date.isoformat()),
    ).fetchall()
    return eng.TrainData(dict(train_row), [dict(s) for s in stops], klass["total_seats"],
                         [tuple(r) for r in rows], travel_date)


# ---------------------------------------------------------------- endpoints
@app.get("/health")
def health():
    return {"status": "Rail Split backend running"}


@app.post("/register", status_code=201)
def register(body: RegisterIn):
    if not EMAIL_RE.match(body.email):
        raise HTTPException(400, "Invalid email")
    email = body.email.strip().lower()
    with get_conn() as conn:
        if conn.execute("SELECT 1 FROM users WHERE LOWER(email)=?", (email,)).fetchone():
            raise HTTPException(409, "Email already registered")
        cur = conn.execute("INSERT INTO users (name, email, phone, password) VALUES (?,?,?,?)",
                           (body.name.strip(), email, body.phone, hash_pw(body.password)))
        uid = cur.lastrowid
    return {"access_token": make_token(uid), "name": body.name.strip()}


@app.post("/login")
def login(body: LoginIn):
    with get_conn() as conn:
        user = conn.execute("SELECT user_id, name, password FROM users WHERE LOWER(email)=?",
                            (body.email.strip().lower(),)).fetchone()
        if not user:
            raise HTTPException(401, "Wrong email or password")
        stored = user["password"]
        if stored.startswith("$2"):                       # bcrypt hash
            ok = bcrypt.checkpw(body.password.encode(), stored.encode())
        else:                                             # old plain-text password from the sample data
            ok = secrets.compare_digest(stored, body.password)
            if ok:                                        # upgrade it to a hash on first successful login
                conn.execute("UPDATE users SET password=? WHERE user_id=?", (hash_pw(body.password), user["user_id"]))
        if not ok:
            raise HTTPException(401, "Wrong email or password")
    return {"access_token": make_token(user["user_id"]), "name": user["name"]}

# --------------------------------------
# FORGOT PASSWORD
# --------------------------------------

@app.post("/forgot-password")
def forgot_password(body: ForgotPasswordIn):
    email = body.email.strip().lower()

    with get_conn() as conn:
        user = conn.execute(
            """
            SELECT user_id, email
            FROM users
            WHERE LOWER(email) = ?
            """,
            (email,)
        ).fetchone()

    # Same response for registered and unregistered emails
    response = {
        "message": (
            "If this email is registered, "
            "a password reset link will be sent."
        )
    }

    if not user:
        return response

    # Create a reset token valid for 15 minutes
    expiry = datetime.utcnow() + timedelta(minutes=15)

    reset_token = jwt.encode(
        {
            "sub": str(user["user_id"]),
            "purpose": "password_reset",
            "exp": expiry
        },
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    reset_link = (
        f"{FRONTEND_RESET_URL}?token={reset_token}"
    )

    send_reset_email(user["email"], reset_link)

    return response


# --------------------------------------
# RESET PASSWORD
# --------------------------------------

@app.post("/reset-password")
def reset_password(body: ResetPasswordIn):

    # Verify reset token
    try:
        payload = jwt.decode(
            body.token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        if payload.get("purpose") != "password_reset":
            raise HTTPException(
                status_code=400,
                detail="Invalid password reset token."
            )

        user_id = int(payload["sub"])

    except HTTPException:
        raise

    except (JWTError, KeyError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Reset link is invalid or expired."
        )

    # Hash the new password and update the existing user
    hashed_password = hash_pw(body.new_password)

    with get_conn() as conn:
        user = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()

        if not user:
            raise HTTPException(
                status_code=400,
                detail="User account not found."
            )

        conn.execute(
            "UPDATE users SET password = ? WHERE user_id = ?",
            (hashed_password, user_id)
        )

    return {
        "message": "Password updated successfully. Please log in."
    }


@app.get("/stations")
def stations():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT station_id, station_code, station_name, city FROM stations ORDER BY station_name")]


def run_search(body: SearchIn):
    if body.travel_date < date.today():
        raise HTTPException(400, "Travel date cannot be in the past")

    with get_conn() as conn:
        klass = get_class(conn, body.class_name)
        src = resolve_station(conn, body.source)
        dst = resolve_station(conn, body.destination)
        if src["station_id"] == dst["station_id"]:
            raise HTTPException(400, "Source and destination are the same")

        train_rows = conn.execute("SELECT train_id, train_number, train_name FROM trains").fetchall()
        train_ids = [r["train_id"] for r in train_rows]
        cache = {}

        def load(tid, offset=0):
            if (tid, offset) not in cache:
                row = next(r for r in train_rows if r["train_id"] == tid)
                cache[(tid, offset)] = load_train(conn, row, klass, body.travel_date + timedelta(days=offset))
            return cache[(tid, offset)]

        sid, did, need = src["station_id"], dst["station_id"], body.passengers
        result = {
            "source": src, "destination": dst, "travel_date": body.travel_date.isoformat(),
            "class": klass["class_name"], "passengers": need, "result_type": "none",
            "direct": [], "same_train_splits": [], "different_train_splits": [],
        }

        # 1) direct ticket
        result["direct"] = [o for o in (eng.direct_option(load(t), sid, did, need) for t in train_ids) if o]
        if result["direct"]:
            result["result_type"] = "direct"
            return result

        # 2) split on the same train
        splits = [o for o in (eng.same_train_split(load(t), sid, did, need) for t in train_ids) if o]
        if splits:
            splits.sort(key=lambda o: (o["tickets"], -o["min_seats"]))
            result["same_train_splits"] = splits
            result["result_type"] = "same_train_split"
            return result

        # 3) split across different trains
        result["different_train_splits"] = eng.different_train_options(train_ids, load, sid, did, need)
        if result["different_train_splits"]:
            result["result_type"] = "different_train_split"
        return result



# ---------------------------------------------------------------- duration (added)


def _leg_dt(day: str, hhmm: str, day_offset: int = 0) -> datetime:
    h, m = hhmm.split(":")[:2]
    d = date.fromisoformat(day) + timedelta(days=day_offset)
    return datetime(d.year, d.month, d.day, int(h), int(m))


def fmt_duration(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}h {m:02d}m"


def enrich_option(option: dict, class_code: str = "SL", passengers: int = 1) -> dict:
    legs = option["legs"]
    grand = 0.0
    for leg in legs:
        f = fare_calc.leg_fare(leg["distance_km"], class_code, leg["train_number"], leg["train_name"])
        leg["fare"] = f
        leg["fare_total"] = fare_calc.leg_total(f, passengers)
        grand += leg["fare_total"]
    option["total_fare"] = round(grand, 2)
    for leg in legs:
        dep = _leg_dt(leg["travel_date"], leg["departure"])
        arr = _leg_dt(leg["travel_date"], leg["arrival"], leg["arrival_day_offset"])
        leg["duration_min"] = int((arr - dep).total_seconds() // 60)
        leg["duration"] = fmt_duration(leg["duration_min"])
        leg["departure_dt"], leg["arrival_dt"] = dep, arr
    total_min = int((legs[-1]["arrival_dt"] - legs[0]["departure_dt"]).total_seconds() // 60)
    for leg in legs:                       # datetimes are not JSON-friendly; drop them
        del leg["departure_dt"], leg["arrival_dt"]
    option["total_duration_min"] = total_min
    option["total_duration"] = fmt_duration(total_min)
    return option


@app.post("/search")
def search(body: SearchIn):
    result = run_search(body)
    class_code = result["class"]
    for key in ("direct", "same_train_splits", "different_train_splits"):
        result[key] = [enrich_option(o, class_code, result["passengers"]) for o in result[key]]
    return result


def new_pnr(conn) -> str:
    for _ in range(10):
        pnr = "".join(str(secrets.randbelow(10)) for _ in range(10))
        if not conn.execute("SELECT 1 FROM booking WHERE pnr_number=?", (pnr,)).fetchone():
            return pnr
    raise HTTPException(500, "Could not generate a PNR")


def apply_booking(conn, train, class_id, a_seq, b_seq, n, avail_before):
    """
    Reduce availability after a booking of n seats for stops a_seq -> b_seq.
      - the row for exactly (a, b) gets +n booked (created if it doesn't exist yet)
      - every other row whose range overlaps (a, b) also gets +n booked (capped at total seats)
    """
    tid, total, day = train.info["train_id"], train.total, train.travel_date.isoformat()
    exact = conn.execute(
        """SELECT leg_id, seats_booked FROM leg_availability WHERE train_id=? AND class_id=? AND travel_date=?
           AND from_stop_sequence=? AND to_stop_sequence=?""", (tid, class_id, day, a_seq, b_seq)).fetchone()
    if exact:
        conn.execute("UPDATE leg_availability SET seats_booked=? WHERE leg_id=?",
                     (min(total, exact["seats_booked"] + n), exact["leg_id"]))
    else:
        conn.execute(
            """INSERT INTO leg_availability (train_id, class_id, travel_date, from_stop_sequence, to_stop_sequence, seats_booked)
               VALUES (?,?,?,?,?,?)""", (tid, class_id, day, a_seq, b_seq, min(total, total - avail_before + n)))
    conn.execute(
        """UPDATE leg_availability SET seats_booked = MIN(?, seats_booked + ?)
           WHERE train_id=? AND class_id=? AND travel_date=? AND from_stop_sequence < ? AND to_stop_sequence > ?
           AND NOT (from_stop_sequence=? AND to_stop_sequence=?)""",
        (total, n, tid, class_id, day, b_seq, a_seq, a_seq, b_seq))


def validate_demo_payment(p: PaymentIn):
    """Demo only: checks the format of what was typed, never contacts any bank."""
    method = p.method.strip().lower()
    if method == "upi":
        if not p.upi_id or not re.fullmatch(r"[\w.\-]{2,}@[A-Za-z]{2,}", p.upi_id.strip()):
            raise HTTPException(400, "Enter a valid UPI ID (e.g. name@upi)")
        return "UPI"
    if method == "card":
        num = re.sub(r"\s+", "", p.card_number or "")
        if not re.fullmatch(r"\d{16}", num):
            raise HTTPException(400, "Card number must be 16 digits")
        if not re.fullmatch(r"(0[1-9]|1[0-2])/\d{2}", (p.card_expiry or "").strip()):
            raise HTTPException(400, "Card expiry must be MM/YY")
        if not re.fullmatch(r"\d{3}", (p.card_cvv or "").strip()):
            raise HTTPException(400, "CVV must be 3 digits")
        return "Card"
    if method == "netbanking":
        if not p.bank:
            raise HTTPException(400, "Please select a bank")
        return "NetBanking"
    raise HTTPException(400, "Unknown payment method")


@app.post("/book", status_code=201)
def book(body: BookIn, user_id: int = Depends(current_user_id)):
    """
    Demo booking: validates passengers -> (fake) payment -> books every leg in ONE transaction.
    If any leg has no seats, nothing is booked and no payment is recorded.
    The fare is always recalculated here on the server.
    """
    if any(l.travel_date < date.today() for l in body.legs):
        raise HTTPException(400, "Travel date cannot be in the past")
    method = validate_demo_payment(body.payment)
    n = len(body.passengers)

    with get_conn() as conn:
        klass = get_class(conn, body.class_name)
        try:
            conn.execute("BEGIN IMMEDIATE")          # write lock: two people can't take the same seats
            prepared, grand_total = [], 0.0
            for leg in body.legs:
                train_row = conn.execute("SELECT train_id, train_number, train_name FROM trains WHERE train_id=?",
                                         (leg.train_id,)).fetchone()
                if not train_row:
                    raise HTTPException(404, "Train not found")
                train = load_train(conn, train_row, klass, leg.travel_date)
                a, b = train.stop_of_station(leg.from_station_id), train.stop_of_station(leg.to_station_id)
                if not a or not b or a["stop_sequence"] >= b["stop_sequence"]:
                    raise HTTPException(400, f"Invalid stations for train {train_row['train_number']}")

                avail = train.seats(a["stop_sequence"], b["stop_sequence"])
                if avail < n:
                    raise HTTPException(409, f"Not enough seats on {train_row['train_number']} "
                                             f"{a['station_code']}->{b['station_code']} (only {avail} left). Search again.")
                km = (b["distance_km"] or 0) - (a["distance_km"] or 0)
                f = fare_calc.leg_fare(km, klass["class_name"], train_row["train_number"], train_row["train_name"])
                leg_total = fare_calc.leg_total(f, n)
                grand_total += leg_total
                prepared.append((leg, train_row, train, a, b, avail, leg_total))

            grand_total = round(grand_total, 2)
            txn = "DEMO" + "".join(str(secrets.randbelow(10)) for _ in range(12))
            pay_id = conn.execute(
                "INSERT INTO payment (user_id, transaction_id, method, amount, status) VALUES (?,?,?,?, 'SUCCESS')",
                (user_id, txn, method, grand_total)).lastrowid

            journey = []
            for leg, train_row, train, a, b, avail, leg_total in prepared:
                pnr = new_pnr(conn)
                booking_id = conn.execute(
                    """INSERT INTO booking (user_id, train_id, class_id, from_station_id, to_station_id,
                                            travel_date, num_seats, pnr_number, status, total_fare, payment_id)
                       VALUES (?,?,?,?,?,?,?,?, 'confirmed', ?, ?)""",
                    (user_id, leg.train_id, klass["class_id"], leg.from_station_id, leg.to_station_id,
                     leg.travel_date.isoformat(), n, pnr, leg_total, pay_id)).lastrowid
                for p in body.passengers:
                    conn.execute("INSERT INTO passenger (booking_id, name, age, gender, berth_pref) VALUES (?,?,?,?,?)",
                                 (booking_id, p.name, p.age, p.gender, p.berth_pref))
                apply_booking(conn, train, klass["class_id"], a["stop_sequence"], b["stop_sequence"], n, avail)
                journey.append({"pnr": pnr, "train_number": train_row["train_number"],
                                "train_name": train_row["train_name"], "from": a["station_name"],
                                "to": b["station_name"], "travel_date": leg.travel_date.isoformat(),
                                "class": klass["class_name"], "seats": n, "fare": leg_total,
                                "status": "confirmed"})
            conn.execute("COMMIT")
        except HTTPException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        except Exception as e:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise HTTPException(500, f"Booking failed: {e}")
    return {"message": "Booking confirmed", "tickets": len(journey), "journey": journey,
            "passengers": [p.dict() for p in body.passengers],
            "payment": {"transaction_id": txn, "method": method, "amount": grand_total, "status": "SUCCESS"}}


@app.get("/my-bookings")
def my_bookings(user_id: int = Depends(current_user_id)):
    with get_conn() as conn:
        rows = conn.execute(
            """SELECT b.booking_id, b.pnr_number, b.travel_date, b.status, b.num_seats, b.total_fare, b.created_at, c.class_name,
                      t.train_number, t.train_name, fs.station_name AS from_station, ts.station_name AS to_station
               FROM booking b
               JOIN trains t ON t.train_id=b.train_id
               JOIN coach_classes c ON c.class_id=b.class_id
               JOIN stations fs ON fs.station_id=b.from_station_id
               JOIN stations ts ON ts.station_id=b.to_station_id
               WHERE b.user_id=? ORDER BY b.created_at DESC, b.booking_id DESC""", (user_id,)).fetchall()
    out = []
    with get_conn() as conn:
        for r in rows:
            d = dict(r)
            d["passengers"] = [dict(p) for p in conn.execute(
                "SELECT name, age, gender FROM passenger WHERE booking_id=?", (d["booking_id"],))]
            out.append(d)
    return out


# ---------------------------------------------------------------- train status (reads timetable.db)
# timetable.db is a separate, read-only file (built by import_timetable.py). It has ~5,200 real trains,
# while railsplit.db only has the few trains that can be booked.
TT_PATH = os.getenv("TIMETABLE_DB", str(Path(__file__).resolve().parent / "timetable.db"))
TT_ALIASES = {"MMCT": "BCT", "VGLJ": "JHS"}      # codes that differ between railsplit.db and timetable.db


@contextmanager
def tt_conn():
    if not Path(TT_PATH).exists():
        raise HTTPException(503, "timetable.db not found. Run import_timetable.py first.")
    conn = sqlite3.connect(f"file:{TT_PATH}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _hm(v):
    return v[:5] if v else None


def _mins(v):
    return int(v[:2]) * 60 + int(v[3:5])


def _bookable_numbers():
    with get_conn() as conn:
        return {r["train_number"] for r in conn.execute("SELECT train_number FROM trains")}


def _train_card(r, bookable):
    return {"train_number": r["train_number"], "train_name": r["train_name"], "train_type": r["train_type"],
            "from_code": r["from_code"], "from_name": r["from_name"], "to_code": r["to_code"], "to_name": r["to_name"],
            "departure": _hm(r["departure"]), "arrival": _hm(r["arrival"]),
            "duration": fmt_duration(r["duration_min"] or 0), "distance_km": r["distance_km"],
            "bookable": r["train_number"] in bookable}


@app.get("/timetable/trains")
def timetable_search(q: str = Query(min_length=2, max_length=60), limit: int = Query(15, ge=1, le=50)):
    """Search trains by number ('12951') or name ('rajdhani', 'mumbai rajdhani')."""
    text = re.sub(r"[%_]", " ", q).strip()
    words = text.split()
    if not words:
        raise HTTPException(400, "Type a train number or name")
    name_cond = " AND ".join("train_name LIKE ?" for _ in words)
    with tt_conn() as tt:
        rows = tt.execute(
            f"""SELECT * FROM tt_train WHERE train_number LIKE ? OR ({name_cond})
                ORDER BY (train_number=?) DESC, (train_number LIKE ?) DESC, train_name LIMIT ?""",
            (text + "%", *[f"%{w}%" for w in words], text, text + "%", limit)).fetchall()
    bookable = _bookable_numbers()
    return [_train_card(r, bookable) for r in rows]


@app.get("/timetable/trains/{train_number}")
def timetable_schedule(train_number: str):
    """Full schedule of one train: every stop with arrival, departure, day and halt time."""
    with tt_conn() as tt:
        t = tt.execute("SELECT * FROM tt_train WHERE train_number=?", (train_number.strip(),)).fetchone()
        if not t:
            raise HTTPException(404, f"Train '{train_number}' not found")
        rows = tt.execute("""SELECT stop_seq, station_code, station_name, day, arrival, departure, is_halt
                             FROM tt_stop WHERE train_number=? ORDER BY stop_seq""", (t["train_number"],)).fetchall()
    stops = []
    for r in rows:
        halt_min = None
        if r["is_halt"] and r["arrival"] and r["departure"]:
            halt_min = (_mins(r["departure"]) - _mins(r["arrival"])) % 1440
        stops.append({"seq": r["stop_seq"], "station_code": r["station_code"], "station_name": r["station_name"],
                      "day": r["day"], "arrival": _hm(r["arrival"]), "departure": _hm(r["departure"]),
                      "is_halt": bool(r["is_halt"]), "halt_min": halt_min})
    card = _train_card(t, _bookable_numbers())
    card["stops"] = stops
    card["halts"] = sum(1 for s in stops if s["is_halt"])
    return card


@app.get("/timetable/station")
def timetable_station(q: str = Query(min_length=2, max_length=60), include_passing: bool = False,
                      limit: int = Query(200, ge=1, le=500)):
    """Station board: trains that stop at a station (give a code like 'NDLS' or a name like 'Kota')."""
    text = q.strip()
    code = TT_ALIASES.get(text.upper(), text.upper())
    with tt_conn() as tt:
        st = tt.execute(
            """SELECT station_code, station_name FROM tt_station
               WHERE station_code=? OR LOWER(station_name)=LOWER(?) OR LOWER(station_name) LIKE LOWER(?)
               ORDER BY (station_code=?) DESC, (LOWER(station_name)=LOWER(?)) DESC, LENGTH(station_name) LIMIT 1""",
            (code, text, f"%{re.sub(r'[%_]', ' ', text)}%", code, text)).fetchone()
        if not st:
            raise HTTPException(404, f"Station '{q}' not found")
        halt_filter = "" if include_passing else "AND s.is_halt=1"
        rows = tt.execute(
            f"""SELECT t.train_number, t.train_name, t.from_name, t.to_name, s.day, s.arrival, s.departure, s.is_halt
                FROM tt_stop s JOIN tt_train t ON t.train_number=s.train_number
                WHERE s.station_code=? {halt_filter}
                ORDER BY COALESCE(s.arrival, s.departure), t.train_number""", (st["station_code"],)).fetchall()
    bookable = _bookable_numbers()
    trains = [{"train_number": r["train_number"], "train_name": r["train_name"], "from_name": r["from_name"],
               "to_name": r["to_name"], "day": r["day"], "arrival": _hm(r["arrival"]), "departure": _hm(r["departure"]),
               "is_halt": bool(r["is_halt"]), "bookable": r["train_number"] in bookable} for r in rows[:limit]]
    return {"station_code": st["station_code"], "station_name": st["station_name"], "total": len(rows),
            "shown": len(trains), "trains": trains}
    # ---- website serve karo (ye hamesha sabse LAST mein rahe) ----
app.mount("/", StaticFiles(directory=str(Path(__file__).resolve().parent / "static"), html=True), name="site")