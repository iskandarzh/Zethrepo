from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from .aset import daftar_ruang
from .const import FASILITAS, KONDISI
from .db import audit, get_db, get_or_404
from .util import admin_required, arg_date, f_choice, f_datetime, f_float, f_int, f_str, now_local

bp = Blueprint("patroli", __name__, url_prefix="/patroli")

SELECT_PATROLI = """
SELECT p.*, r.kode AS kode_ruang, r.nama AS nama_ruang, r.suhu_min, r.suhu_max, r.rh_min, r.rh_max,
       u.username AS petugas, u.nama AS nama_petugas
FROM patroli p
JOIN ruang r ON r.id = p.ruang_id
LEFT JOIN pengguna u ON u.id = p.petugas_id
"""


def temuan(p):
    """Daftar (pesan, warna) untuk pembacaan di luar batas atau fasilitas tidak normal."""
    hasil = []
    for nilai, lo, hi, nama, satuan in (
        (p["suhu"], p["suhu_min"], p["suhu_max"], "Suhu", "°C"),
        (p["kelembaban"], p["rh_min"], p["rh_max"], "Kelembaban", "%"),
    ):
        if nilai is None:
            continue
        if hi is not None and nilai > hi:
            hasil.append((f"{nama} {nilai:g}{satuan} > batas {hi:g}{satuan}", "danger"))
        elif lo is not None and nilai < lo:
            hasil.append((f"{nama} {nilai:g}{satuan} < batas {lo:g}{satuan}", "danger"))
    for kolom, label in FASILITAS:
        if p[kolom] == "gangguan":
            hasil.append((f"{label}: gangguan", "danger"))
        elif p[kolom] == "perhatian":
            hasil.append((f"{label}: perlu perhatian", "warning"))
    return hasil


@bp.route("/")
def daftar():
    dari = arg_date("dari")
    sampai = arg_date("sampai")
    ruang_id = request.args.get("ruang_id", type=int)
    hanya_temuan = request.args.get("temuan") == "1"
    sql = SELECT_PATROLI + " WHERE 1 = 1"
    params = []
    if dari:
        sql += " AND date(p.waktu) >= ?"
        params.append(dari)
    if sampai:
        sql += " AND date(p.waktu) <= ?"
        params.append(sampai)
    if ruang_id:
        sql += " AND p.ruang_id = ?"
        params.append(ruang_id)
    rows = [(r, temuan(r)) for r in get_db().execute(sql + " ORDER BY p.waktu DESC LIMIT 500", params)]
    if hanya_temuan:
        rows = [(r, t) for r, t in rows if t]
    return render_template(
        "patroli/list.html", rows=rows, ruangs=daftar_ruang(), dari=dari or "", sampai=sampai or "",
        ruang_id=ruang_id, hanya_temuan=hanya_temuan,
    )


def _form_data():
    data = {
        "waktu": f_datetime("waktu", "Waktu", True),
        "ruang_id": f_int("ruang_id", "Ruang", True),
        "suhu": f_float("suhu", "Suhu"),
        "kelembaban": f_float("kelembaban", "Kelembaban"),
        "catatan": f_str("catatan"),
    }
    for kolom, label in FASILITAS:
        data[kolom] = f_choice(kolom, KONDISI, label, "normal")
    if data["kelembaban"] is not None and not 0 <= data["kelembaban"] <= 100:
        raise ValueError("Kelembaban harus 0–100%")
    if not get_db().execute("SELECT 1 FROM ruang WHERE id = ?", (data["ruang_id"],)).fetchone():
        raise ValueError("Ruang tidak ditemukan")
    return data


def _render_form(patroli, form):
    return render_template("patroli/form.html", patroli=patroli, form=form, ruangs=daftar_ruang())


@bp.route("/baru", methods=["GET", "POST"])
@bp.route("/<int:pid>/edit", methods=["GET", "POST"])
def form(pid=None):
    patroli = get_or_404("patroli", pid) if pid else None
    if request.method == "POST":
        try:
            data = _form_data()
        except ValueError as e:
            flash(str(e), "danger")
            return _render_form(patroli, request.form)
        db = get_db()
        cols = list(data)
        if patroli:
            db.execute(f"UPDATE patroli SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?", [data[k] for k in cols] + [pid])
        else:
            cur = db.execute(
                f"INSERT INTO patroli ({', '.join(cols)}, petugas_id) VALUES ({', '.join('?' * len(cols))}, ?)",
                [data[k] for k in cols] + [g.user["id"]],
            )
            pid = cur.lastrowid
        audit("ubah" if patroli else "tambah", "patroli", f"ruang #{data['ruang_id']} {data['waktu']}")
        db.commit()
        row = db.execute(SELECT_PATROLI + " WHERE p.id = ?", (pid,)).fetchone()
        hasil = temuan(row)
        if hasil:
            flash("Patroli disimpan dengan temuan: " + "; ".join(t for t, _ in hasil), "warning")
        else:
            flash("Patroli disimpan, semua kondisi normal", "success")
        return redirect(url_for("patroli.daftar"))
    initial = patroli or {"waktu": now_local(), "ruang_id": request.args.get("ruang_id", type=int)}
    return _render_form(patroli, initial)


@bp.route("/<int:pid>/hapus", methods=["POST"])
@admin_required
def hapus(pid):
    get_or_404("patroli", pid)
    db = get_db()
    db.execute("DELETE FROM patroli WHERE id = ?", (pid,))
    audit("hapus", "patroli", f"#{pid}")
    db.commit()
    flash("Data patroli dihapus", "success")
    return redirect(url_for("patroli.daftar"))
