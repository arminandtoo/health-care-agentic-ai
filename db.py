import hashlib
import os
import sqlite3
from datetime import date, timedelta

DB_PATH = "data.db"

# saturday to wednesday, 9:00 to 17:00, one hour sessions
WORK_DAYS = [5, 6, 0, 1, 2]
HOURS = [f"{h:02d}:00" for h in range(9, 17)]
DAY_NAMES = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, salt BLOB, password_hash BLOB)")
    conn.execute("CREATE TABLE IF NOT EXISTS appointments (day TEXT, hour TEXT, username TEXT, UNIQUE(day, hour))")
    return conn


def hash_password(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)


def login(username, password):
    """Returns True if password is correct. First login creates the user."""
    with connect() as conn:
        row = conn.execute("SELECT salt, password_hash FROM users WHERE username = ?", (username,)).fetchone()
        if row is None:
            salt = os.urandom(16)
            conn.execute("INSERT INTO users VALUES (?, ?, ?)", (username, salt, hash_password(password, salt)))
            return True
        return hash_password(password, row[0]) == row[1]


def next_work_days(count=7):
    days = []
    d = date.today()
    while len(days) < count:
        d += timedelta(days=1)
        if d.weekday() in WORK_DAYS:
            days.append(d)
    return days


def seed_sample_data():
    # sample data: sundays and tuesdays are fully booked
    with connect() as conn:
        for d in next_work_days(14):
            if d.weekday() in (6, 1):
                for h in HOURS:
                    conn.execute("INSERT OR IGNORE INTO appointments VALUES (?, ?, ?)", (d.isoformat(), h, "sample"))


def free_slots():
    with connect() as conn:
        booked = set(conn.execute("SELECT day, hour FROM appointments").fetchall())
    result = {}
    for d in next_work_days():
        label = f"{DAY_NAMES[d.weekday()]} {d.isoformat()}"
        result[label] = [h for h in HOURS if (d.isoformat(), h) not in booked]
    return result


def my_appointments(username):
    with connect() as conn:
        rows = conn.execute(
            "SELECT day, hour FROM appointments WHERE username = ? AND day >= ? ORDER BY day, hour",
            (username, date.today().isoformat()),
        ).fetchall()
    return [f"{DAY_NAMES[date.fromisoformat(d).weekday()]} {d} ساعت {h}" for d, h in rows]


def book(username, day, hour):
    try:
        d = date.fromisoformat(day)
    except ValueError:
        return "تاریخ نامعتبر است. فرمت درست: YYYY-MM-DD"
    if d <= date.today() or d.weekday() not in WORK_DAYS or hour not in HOURS:
        return "این زمان جزو ساعات کاری مشاور نیست."
    try:
        with connect() as conn:
            conn.execute("INSERT INTO appointments VALUES (?, ?, ?)", (day, hour, username))
    except sqlite3.IntegrityError:
        return "این وقت قبلا رزرو شده است."
    return f"وقت مشاوره برای {DAY_NAMES[d.weekday()]} {day} ساعت {hour} رزرو شد."


def cancel(username, day, hour):
    with connect() as conn:
        cur = conn.execute("DELETE FROM appointments WHERE day = ? AND hour = ? AND username = ?", (day, hour, username))
    if cur.rowcount == 0:
        return "رزروی با این مشخصات برای شما پیدا نشد."
    return "رزرو لغو شد."
