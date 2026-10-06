import sqlite3

import click
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .const import PERAN
from .db import audit, get_db, get_or_404
from .util import admin_required, safe_next

bp = Blueprint("auth", __name__, cli_group=None)

MIN_PASSWORD = 8


def validasi_password(password, konfirmasi):
    if len(password) < MIN_PASSWORD:
        raise ValueError(f"Password minimal {MIN_PASSWORD} karakter")
    if password != konfirmasi:
        raise ValueError("Konfirmasi password tidak sama")


def jumlah_pengguna():
    return get_db().execute("SELECT COUNT(*) FROM pengguna").fetchone()[0]


def mulai_sesi(user_id):
    session.clear()
    session.permanent = True
    session["user_id"] = user_id


def buat_pengguna(form, peran):
    username = form.get("username", "").strip()
    nama = form.get("nama", "").strip()
    password = form.get("password", "")
    if not username:
        raise ValueError("Username wajib diisi")
    if peran not in PERAN:
        raise ValueError("Peran tidak valid")
    validasi_password(password, form.get("konfirmasi", ""))
    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO pengguna (username, nama, peran, password_hash) VALUES (?, ?, ?, ?)",
            (username, nama, peran, generate_password_hash(password)),
        )
    except sqlite3.IntegrityError:
        raise ValueError(f"Username '{username}' sudah dipakai")
    return cur.lastrowid


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if jumlah_pengguna() > 0:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        try:
            uid = buat_pengguna(request.form, "admin")
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("auth/setup.html", form=request.form)
        get_db().commit()
        mulai_sesi(uid)
        flash("Akun admin dibuat. Selamat datang!", "success")
        return redirect(url_for("dashboard.index"))
    return render_template("auth/setup.html", form={})


@bp.route("/login", methods=["GET", "POST"])
def login():
    if jumlah_pengguna() == 0:
        return redirect(url_for("auth.setup"))
    if g.user is not None:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = get_db().execute("SELECT * FROM pengguna WHERE username = ?", (username,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Username atau password salah", "danger")
            return render_template("auth/login.html", username=username), 401
        if not user["aktif"]:
            flash("Akun dinonaktifkan. Hubungi admin.", "danger")
            return render_template("auth/login.html", username=username), 403
        mulai_sesi(user["id"])
        return redirect(safe_next(request.args.get("next"), url_for("dashboard.index")))
    return render_template("auth/login.html", username="")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Anda telah keluar", "success")
    return redirect(url_for("auth.login"))


@bp.route("/pengguna", methods=["GET", "POST"])
@admin_required
def pengguna():
    db = get_db()
    form = {}
    if request.method == "POST":
        try:
            buat_pengguna(request.form, request.form.get("peran", "operator"))
            audit("tambah", "pengguna", request.form.get("username", "").strip())
            db.commit()
            flash("Pengguna ditambahkan", "success")
            return redirect(url_for("auth.pengguna"))
        except ValueError as e:
            flash(str(e), "danger")
            form = request.form
    users = db.execute("SELECT * FROM pengguna ORDER BY username").fetchall()
    return render_template("auth/pengguna.html", users=users, form=form)


@bp.route("/pengguna/<int:uid>/edit", methods=["GET", "POST"])
@admin_required
def pengguna_edit(uid):
    user = get_or_404("pengguna", uid)
    if request.method == "POST":
        peran = request.form.get("peran", user["peran"])
        aktif = 1 if request.form.get("aktif") else 0
        db = get_db()
        password = request.form.get("password", "")
        try:
            if peran not in PERAN:
                raise ValueError("Peran tidak valid")
            if uid == g.user["id"] and (peran != "admin" or not aktif):
                raise ValueError("Tidak bisa menurunkan peran atau menonaktifkan akun sendiri")
            if password:
                validasi_password(password, request.form.get("konfirmasi", ""))
                db.execute("UPDATE pengguna SET password_hash = ? WHERE id = ?", (generate_password_hash(password), uid))
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("auth/pengguna_edit.html", user=user)
        db.execute(
            "UPDATE pengguna SET nama = ?, peran = ?, aktif = ? WHERE id = ?",
            (request.form.get("nama", "").strip(), peran, aktif, uid),
        )
        audit("ubah", "pengguna", f"{user['username']} (peran={peran}, aktif={aktif}{', reset password' if password else ''})")
        db.commit()
        flash("Pengguna diperbarui", "success")
        return redirect(url_for("auth.pengguna"))
    return render_template("auth/pengguna_edit.html", user=user)


@bp.route("/pengguna/<int:uid>/hapus", methods=["POST"])
@admin_required
def pengguna_hapus(uid):
    if uid == g.user["id"]:
        flash("Tidak bisa menghapus akun sendiri", "danger")
        return redirect(url_for("auth.pengguna"))
    user = get_or_404("pengguna", uid)
    db = get_db()
    db.execute("DELETE FROM pengguna WHERE id = ?", (uid,))
    audit("hapus", "pengguna", user["username"])
    db.commit()
    flash("Pengguna dihapus", "success")
    return redirect(url_for("auth.pengguna"))


@bp.route("/akun/password", methods=["GET", "POST"])
def ganti_password():
    if request.method == "POST":
        if not check_password_hash(g.user["password_hash"], request.form.get("password_lama", "")):
            flash("Password lama salah", "danger")
            return render_template("auth/ganti_password.html")
        try:
            validasi_password(request.form.get("password", ""), request.form.get("konfirmasi", ""))
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("auth/ganti_password.html")
        db = get_db()
        db.execute(
            "UPDATE pengguna SET password_hash = ? WHERE id = ?",
            (generate_password_hash(request.form["password"]), g.user["id"]),
        )
        audit("ganti password", "pengguna", g.user["username"])
        db.commit()
        flash("Password berhasil diganti", "success")
        return redirect(url_for("dashboard.index"))
    return render_template("auth/ganti_password.html")


@bp.route("/audit")
@admin_required
def log_audit():
    rows = get_db().execute(
        """SELECT a.*, p.username FROM audit a LEFT JOIN pengguna p ON p.id = a.pengguna_id
           ORDER BY a.id DESC LIMIT 500"""
    ).fetchall()
    return render_template("auth/audit.html", rows=rows)


@bp.cli.command("set-password")
@click.argument("username")
@click.password_option()
def set_password_command(username, password):
    """Buat pengguna admin baru atau reset password pengguna yang ada."""
    if len(password) < MIN_PASSWORD:
        raise click.ClickException(f"Password minimal {MIN_PASSWORD} karakter")
    db = get_db()
    hashed = generate_password_hash(password)
    if db.execute("SELECT 1 FROM pengguna WHERE username = ?", (username,)).fetchone():
        db.execute("UPDATE pengguna SET password_hash = ?, aktif = 1 WHERE username = ?", (hashed, username))
        click.echo(f"Password '{username}' diperbarui")
    else:
        db.execute("INSERT INTO pengguna (username, peran, password_hash) VALUES (?, 'admin', ?)", (username, hashed))
        click.echo(f"Pengguna admin '{username}' dibuat")
    db.commit()
