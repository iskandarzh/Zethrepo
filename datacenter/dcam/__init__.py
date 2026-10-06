import hmac
import os
import secrets
from datetime import datetime, timedelta

from flask import Flask, abort, g, redirect, render_template, request, session, url_for

from . import const
from .db import get_db, init_app as init_db
from .util import can_edit, is_admin, now_local, today

PUBLIC_ENDPOINTS = {"auth.login", "auth.setup", "static"}
VIEWER_POST_ALLOWED = {"auth.logout", "auth.ganti_password"}


def load_secret_key(instance_path):
    """SECRET_KEY dari env, atau dibuat acak sekali lalu disimpan di instance/secret_key."""
    if os.environ.get("SECRET_KEY"):
        return os.environ["SECRET_KEY"]
    path = os.path.join(instance_path, "secret_key")
    if not os.path.exists(path):
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


def format_tgl(value):
    if not value:
        return "-"
    try:
        if "T" in value or " " in value:
            return datetime.fromisoformat(value.replace(" ", "T")).strftime("%d-%m-%Y %H:%M")
        return datetime.fromisoformat(value).strftime("%d-%m-%Y")
    except ValueError:
        return value


def format_jam(value):
    try:
        return datetime.fromisoformat(value).strftime("%H:%M")
    except (TypeError, ValueError):
        return value or "-"


def durasi(mulai, selesai=None):
    if not mulai:
        return "-"
    try:
        awal = datetime.fromisoformat(mulai)
        akhir = datetime.fromisoformat(selesai) if selesai else datetime.now()
    except ValueError:
        return "-"
    menit = max(int((akhir - awal).total_seconds() // 60), 0)
    hari, menit = divmod(menit, 1440)
    jam, menit = divmod(menit, 60)
    bagian = []
    if hari:
        bagian.append(f"{hari}h")
    if jam:
        bagian.append(f"{jam}j")
    bagian.append(f"{menit}m")
    return " ".join(bagian)


def angka(value):
    if value is None:
        return "-"
    return f"{value:g}"


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.from_mapping(
        SECRET_KEY=load_secret_key(app.instance_path),
        DATABASE=os.path.join(app.instance_path, "datacenter.db"),
        CSRF_ENABLED=True,
        SESSION_COOKIE_NAME="dcam_session",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE") == "1",
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        NAMA_DC=os.environ.get("NAMA_DC", "Data Center"),
    )
    if test_config:
        app.config.update(test_config)

    init_db(app)

    def csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_urlsafe(32)
        return session["csrf_token"]

    @app.before_request
    def sebelum_request():
        if request.method == "POST" and app.config["CSRF_ENABLED"]:
            token = request.form.get("csrf_token", "")
            if not session.get("csrf_token") or not hmac.compare_digest(token, session["csrf_token"]):
                abort(400, "Token CSRF tidak valid. Muat ulang halaman lalu coba lagi.")
        g.user = None
        uid = session.get("user_id")
        if uid is not None:
            user = get_db().execute("SELECT * FROM pengguna WHERE id = ?", (uid,)).fetchone()
            if user is None or not user["aktif"]:
                session.clear()
            else:
                g.user = user
        if request.endpoint in PUBLIC_ENDPOINTS:
            return None
        if g.user is None:
            if get_db().execute("SELECT COUNT(*) FROM pengguna").fetchone()[0] == 0:
                return redirect(url_for("auth.setup"))
            return redirect(url_for("auth.login", next=request.full_path if request.method == "GET" else None))
        if request.method == "POST" and not can_edit() and request.endpoint not in VIEWER_POST_ALLOWED:
            abort(403)
        return None

    from . import aktivitas, aset, auth, dashboard, insiden, kunjungan, laporan, patroli

    for module in (auth, dashboard, aktivitas, kunjungan, aset, patroli, insiden, laporan):
        app.register_blueprint(module.bp)

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def halaman_error(e):
        pesan = {
            403: "Anda tidak memiliki akses untuk aksi ini.",
            404: "Halaman atau data tidak ditemukan.",
        }.get(e.code, e.description)
        return render_template("error.html", kode=e.code, pesan=pesan), e.code

    app.jinja_env.globals.update(
        c=const,
        csrf_token=csrf_token,
        is_admin=is_admin,
        can_edit=can_edit,
        now_local=now_local,
        today=today,
    )
    app.jinja_env.filters.update(tgl=format_tgl, jam=format_jam, durasi=durasi, angka=angka)
    return app
