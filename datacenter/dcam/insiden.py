from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .aset import daftar_perangkat, daftar_ruang
from .const import KATEGORI_INSIDEN, SEVERITY, STATUS_INSIDEN
from .db import audit, get_db, get_or_404
from .util import admin_required, f_choice, f_datetime, f_int, f_str, now_local

bp = Blueprint("insiden", __name__, url_prefix="/insiden")

SELECT_INSIDEN = """
SELECT i.*, r.kode AS kode_ruang, d.nama AS nama_perangkat, u.username AS pelapor, u.nama AS nama_pelapor
FROM insiden i
LEFT JOIN ruang r ON r.id = i.ruang_id
LEFT JOIN perangkat d ON d.id = i.perangkat_id
LEFT JOIN pengguna u ON u.id = i.pelapor_id
"""
URUT_SEVERITY = "CASE i.severity WHEN 'kritis' THEN 0 WHEN 'tinggi' THEN 1 WHEN 'sedang' THEN 2 ELSE 3 END"


@bp.route("/")
def daftar():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    severity = request.args.get("severity", "")
    sql = SELECT_INSIDEN + " WHERE 1 = 1"
    params = []
    if q:
        sql += " AND (i.judul LIKE ? OR i.nomor LIKE ? OR i.deskripsi LIKE ?)"
        params += [f"%{q}%"] * 3
    if status == "aktif":
        sql += " AND i.status != 'selesai'"
    elif status in STATUS_INSIDEN:
        sql += " AND i.status = ?"
        params.append(status)
    if severity in SEVERITY:
        sql += " AND i.severity = ?"
        params.append(severity)
    rows = get_db().execute(sql + " ORDER BY i.waktu_kejadian DESC LIMIT 500", params).fetchall()
    return render_template("insiden/list.html", rows=rows, q=q, status=status, severity=severity)


def _form_data():
    data = {
        "judul": f_str("judul", "Judul", True),
        "kategori": f_choice("kategori", KATEGORI_INSIDEN, "Kategori"),
        "severity": f_choice("severity", SEVERITY, "Severity"),
        "ruang_id": f_int("ruang_id"),
        "perangkat_id": f_int("perangkat_id"),
        "waktu_kejadian": f_datetime("waktu_kejadian", "Waktu kejadian", True),
        "deskripsi": f_str("deskripsi"),
        "penanganan": f_str("penanganan"),
        "status": f_choice("status", STATUS_INSIDEN, "Status", "terbuka"),
        "waktu_selesai": f_datetime("waktu_selesai", "Waktu selesai"),
    }
    if data["status"] == "selesai":
        data["waktu_selesai"] = data["waktu_selesai"] or max(now_local(), data["waktu_kejadian"])
        if not data["penanganan"]:
            raise ValueError("Isi penanganan sebelum menutup insiden")
    else:
        data["waktu_selesai"] = None
    if data["waktu_selesai"] and data["waktu_selesai"] < data["waktu_kejadian"]:
        raise ValueError("Waktu selesai tidak boleh sebelum waktu kejadian")
    db = get_db()
    if data["ruang_id"] and not db.execute("SELECT 1 FROM ruang WHERE id = ?", (data["ruang_id"],)).fetchone():
        raise ValueError("Ruang tidak ditemukan")
    if data["perangkat_id"] and not db.execute("SELECT 1 FROM perangkat WHERE id = ?", (data["perangkat_id"],)).fetchone():
        raise ValueError("Perangkat tidak ditemukan")
    return data


def _render_form(insiden, form):
    return render_template(
        "insiden/form.html", insiden=insiden, form=form, ruangs=daftar_ruang(), perangkats=daftar_perangkat()
    )


@bp.route("/baru", methods=["GET", "POST"])
@bp.route("/<int:iid>/edit", methods=["GET", "POST"])
def form(iid=None):
    insiden = get_or_404("insiden", iid) if iid else None
    if request.method == "POST":
        try:
            data = _form_data()
        except ValueError as e:
            flash(str(e), "danger")
            return _render_form(insiden, request.form)
        db = get_db()
        cols = list(data)
        if insiden:
            db.execute(f"UPDATE insiden SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?", [data[k] for k in cols] + [iid])
            nomor = insiden["nomor"]
        else:
            cur = db.execute(
                f"INSERT INTO insiden ({', '.join(cols)}, pelapor_id) VALUES ({', '.join('?' * len(cols))}, ?)",
                [data[k] for k in cols] + [g.user["id"]],
            )
            iid = cur.lastrowid
            nomor = f"INC-{date.today().year}-{iid:04d}"
            db.execute("UPDATE insiden SET nomor = ? WHERE id = ?", (nomor, iid))
        audit("ubah" if insiden else "tambah", "insiden", f"{nomor} {data['judul']} [{data['status']}]")
        db.commit()
        flash(f"Insiden {nomor} disimpan", "success")
        return redirect(url_for("insiden.detail", iid=iid))
    initial = insiden or {
        "waktu_kejadian": now_local(),
        "status": "terbuka",
        "severity": "sedang",
        "ruang_id": request.args.get("ruang_id", type=int),
        "perangkat_id": request.args.get("perangkat_id", type=int),
        "kategori": request.args.get("kategori"),
        "judul": request.args.get("judul"),
        "deskripsi": request.args.get("deskripsi"),
    }
    return _render_form(insiden, initial)


@bp.route("/<int:iid>")
def detail(iid):
    row = get_db().execute(SELECT_INSIDEN + " WHERE i.id = ?", (iid,)).fetchone()
    if row is None:
        abort(404)
    return render_template("insiden/detail.html", i=row)


@bp.route("/<int:iid>/hapus", methods=["POST"])
@admin_required
def hapus(iid):
    insiden = get_or_404("insiden", iid)
    db = get_db()
    db.execute("DELETE FROM insiden WHERE id = ?", (iid,))
    audit("hapus", "insiden", f"{insiden['nomor']} {insiden['judul']}")
    db.commit()
    flash(f"Insiden {insiden['nomor']} dihapus", "success")
    return redirect(url_for("insiden.daftar"))
