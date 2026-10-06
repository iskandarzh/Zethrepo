from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .aset import daftar_ruang
from .db import audit, get_db, get_or_404
from .util import admin_required, arg_date, f_datetime, f_int, f_str, now_local, safe_next, today

bp = Blueprint("kunjungan", __name__, url_prefix="/kunjungan")

SELECT_KUNJUNGAN = """
SELECT k.*, r.kode AS kode_ruang, a.nomor AS nomor_aktivitas, a.judul AS judul_aktivitas
FROM kunjungan k
LEFT JOIN ruang r ON r.id = k.ruang_id
LEFT JOIN aktivitas a ON a.id = k.aktivitas_id
"""


def daftar_aktivitas_aktif():
    return get_db().execute(
        """SELECT id, nomor, judul, vendor, ruang_id FROM aktivitas
           WHERE status IN ('diajukan', 'disetujui', 'berlangsung') ORDER BY mulai_rencana"""
    ).fetchall()


@bp.route("/")
def daftar():
    q = request.args.get("q", "").strip()
    di_dalam = request.args.get("di_dalam") == "1"
    tanggal = arg_date("tanggal", None if di_dalam or q else today())
    sql = SELECT_KUNJUNGAN + " WHERE 1 = 1"
    params = []
    if di_dalam:
        sql += " AND k.keluar IS NULL"
    if tanggal:
        sql += " AND date(k.masuk) <= ? AND (k.keluar IS NULL OR date(k.keluar) >= ?)"
        params += [tanggal, tanggal]
    if q:
        sql += " AND (k.nama LIKE ? OR k.perusahaan LIKE ? OR k.no_identitas LIKE ? OR k.tujuan LIKE ?)"
        params += [f"%{q}%"] * 4
    rows = get_db().execute(sql + " ORDER BY k.masuk DESC LIMIT 500", params).fetchall()
    return render_template("kunjungan/list.html", rows=rows, q=q, di_dalam=di_dalam, tanggal=tanggal or "")


def _form_data():
    data = {
        "nama": f_str("nama", "Nama tamu", True),
        "perusahaan": f_str("perusahaan"),
        "no_identitas": f_str("no_identitas"),
        "telepon": f_str("telepon"),
        "tujuan": f_str("tujuan", "Tujuan kunjungan", True),
        "ruang_id": f_int("ruang_id"),
        "aktivitas_id": f_int("aktivitas_id"),
        "pendamping": f_str("pendamping"),
        "kartu_akses": f_str("kartu_akses"),
        "masuk": f_datetime("masuk", "Waktu masuk", True),
        "keluar": f_datetime("keluar", "Waktu keluar"),
        "catatan": f_str("catatan"),
    }
    if data["keluar"] and data["keluar"] < data["masuk"]:
        raise ValueError("Waktu keluar tidak boleh sebelum waktu masuk")
    db = get_db()
    if data["ruang_id"] and not db.execute("SELECT 1 FROM ruang WHERE id = ?", (data["ruang_id"],)).fetchone():
        raise ValueError("Ruang tidak ditemukan")
    if data["aktivitas_id"] and not db.execute("SELECT 1 FROM aktivitas WHERE id = ?", (data["aktivitas_id"],)).fetchone():
        raise ValueError("Aktivitas tidak ditemukan")
    return data


def _render_form(kunjungan, form):
    return render_template(
        "kunjungan/form.html", kunjungan=kunjungan, form=form, ruangs=daftar_ruang(), aktivitas=daftar_aktivitas_aktif()
    )


@bp.route("/baru", methods=["GET", "POST"])
def baru():
    if request.method == "POST":
        try:
            data = _form_data()
        except ValueError as e:
            flash(str(e), "danger")
            return _render_form(None, request.form)
        db = get_db()
        cols = list(data)
        db.execute(
            f"INSERT INTO kunjungan ({', '.join(cols)}, dicatat_oleh) VALUES ({', '.join('?' * len(cols))}, ?)",
            [data[k] for k in cols] + [g.user["id"]],
        )
        audit("check-in", "kunjungan", f"{data['nama']} ({data['perusahaan'] or '-'})")
        db.commit()
        flash(f"{data['nama']} tercatat masuk", "success")
        return redirect(url_for("kunjungan.daftar"))
    form = {"masuk": now_local()}
    aid = request.args.get("aktivitas_id", type=int)
    if aid:
        a = get_db().execute("SELECT * FROM aktivitas WHERE id = ?", (aid,)).fetchone()
        if a:
            form.update(aktivitas_id=a["id"], ruang_id=a["ruang_id"], perusahaan=a["vendor"], tujuan=a["judul"])
    return _render_form(None, form)


@bp.route("/<int:kid>/edit", methods=["GET", "POST"])
def edit(kid):
    kunjungan = get_or_404("kunjungan", kid)
    if request.method == "POST":
        try:
            data = _form_data()
        except ValueError as e:
            flash(str(e), "danger")
            return _render_form(kunjungan, request.form)
        db = get_db()
        db.execute(
            f"UPDATE kunjungan SET {', '.join(f'{k} = ?' for k in data)} WHERE id = ?", [data[k] for k in data] + [kid]
        )
        audit("ubah", "kunjungan", data["nama"])
        db.commit()
        flash("Data kunjungan diperbarui", "success")
        return redirect(url_for("kunjungan.daftar"))
    return _render_form(kunjungan, kunjungan)


@bp.route("/<int:kid>/keluar", methods=["POST"])
def checkout(kid):
    kunjungan = get_or_404("kunjungan", kid)
    if kunjungan["keluar"]:
        flash(f"{kunjungan['nama']} sudah tercatat keluar", "warning")
    else:
        db = get_db()
        db.execute("UPDATE kunjungan SET keluar = ? WHERE id = ?", (max(now_local(), kunjungan["masuk"]), kid))
        audit("check-out", "kunjungan", kunjungan["nama"])
        db.commit()
        flash(f"{kunjungan['nama']} tercatat keluar", "success")
    return redirect(safe_next(request.form.get("next"), url_for("kunjungan.daftar")))


@bp.route("/<int:kid>/hapus", methods=["POST"])
@admin_required
def hapus(kid):
    kunjungan = get_or_404("kunjungan", kid)
    db = get_db()
    db.execute("DELETE FROM kunjungan WHERE id = ?", (kid,))
    audit("hapus", "kunjungan", kunjungan["nama"])
    db.commit()
    flash("Data kunjungan dihapus", "success")
    return redirect(url_for("kunjungan.daftar"))
