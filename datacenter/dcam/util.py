from datetime import date, datetime
from functools import wraps

from flask import abort, g, request


def now_local():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def today():
    return date.today().isoformat()


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.user is None or g.user["peran"] != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def is_admin():
    return g.get("user") is not None and g.user["peran"] == "admin"


def can_edit():
    return g.get("user") is not None and g.user["peran"] in ("admin", "operator")


def safe_next(value, fallback):
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return fallback


def f_str(name, label=None, required=False):
    value = request.form.get(name, "").strip()
    if required and not value:
        raise ValueError(f"{label or name} wajib diisi")
    return value or None


def f_int(name, label=None, required=False, minimum=None):
    value = f_str(name, label, required)
    if value is None:
        return None
    try:
        number = int(value)
    except ValueError:
        raise ValueError(f"{label or name}: '{value}' bukan angka bulat")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label or name} minimal {minimum}")
    return number


def f_float(name, label=None, required=False):
    value = f_str(name, label, required)
    if value is None:
        return None
    try:
        return float(value.replace(",", "."))
    except ValueError:
        raise ValueError(f"{label or name}: '{value}' bukan angka")


def f_datetime(name, label=None, required=False):
    value = f_str(name, label, required)
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value).strftime("%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError(f"{label or name}: format tanggal/jam tidak valid")


def f_choice(name, choices, label=None, default=None):
    value = request.form.get(name, "").strip() or default
    if value not in choices:
        raise ValueError(f"{label or name} tidak valid")
    return value


def arg_date(name, default=None):
    value = request.args.get(name, "").strip()
    try:
        return date.fromisoformat(value).isoformat() if value else default
    except ValueError:
        return default
