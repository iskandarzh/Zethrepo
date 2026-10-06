from datetime import date

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .aset import daftar_perangkat, daftar_rak, daftar_ruang
from .const import JENIS_AKTIVITAS, RISIKO, STATUS_AKTIVITAS, STATUS_AKTIVITAS_AKTIF, TRANSISI_AKTIVITAS
from .db import audit, get_db, get_or_404
from .util import admin_required, arg_date, f_choice, f_datetime, f_int, f_str, is_admin, now_local

bp = Blueprint("aktivitas", __name__, url_prefix="/aktivitas")

SELECT_AKTIVITAS = """
SELECT a.*, r.kode AS kode_ruang, r.nama AS nama_ruang, k.kode AS kode_rak,
       d.nama AS nama_perangkat, u1.nama AS nama_pengaju, u1.username AS pengaju,
       u2.nama AS nama_penyetuju, u2.username AS penyetuju
FROM aktivitas a
LEFT JOIN ruang r ON r.id = a.ruang_id
LEFT JOIN rak k ON k.id = a.rak_id
LEFT JOIN perangkat d ON d.id = a.perangkat_id
LEFT JOIN pengguna u1 ON u1.id = a.diajukan_oleh
LEFT JOIN pengguna u2 ON u2.id = a.disetujui_oleh
"""


def get_aktivitas(aid):
    row = get_db().execute(SELECT_AKTIVITAS + " WHERE a.id = ?", (aid,)).fetchone()
    if row is None:
        abort(404)
    return row


def cari_bentrok(ruang_id, rak_id, mulai, selesai, kecuali=None):
    """Aktivitas aktif lain yang waktunya tumpang tindih di rak yang sama (atau ruang yang sama bila rak kosong)."""
    if not ruang_id and not rak_id:
        return []
    return get_db().execute(
        """SELECT id, nomor, judul, mulai_rencana, selesai_rencana, status FROM aktivitas
           WHERE status IN ('diajukan', 'disetujui', 'berlangsung') AND id != :kecuali
             AND mulai_rencana < :selesai AND selesai_rencana > :mulai
             AND (rak_id = :rak OR ((rak_id IS NULL OR :rak IS NULL) AND ruang_id = :ruang))
           ORDER BY mulai_rencana""",
        {"kecuali": kecuali or 0, "mulai": mulai, "selesai": selesai, "rak": rak_id, "ruang": ruang_id},
    ).fetchall()


def tambah_log(aid, isi, jenis="catatan"):
    get_db().execute(
        "INSERT INTO aktivitas_log (aktivitas_id, waktu, pengguna_id, jenis, isi) VALUES (?, ?, ?, ?, ?)",
        (aid, now_local(), g.user["id"], jenis, isi),
    )


def _form_data():
    data = {
        "judul": f_str("judul", "Judul", True),
        "jenis": f_choice("jenis", JENIS_AKTIVITAS, "Jenis aktivitas"),
        "deskripsi": f_str("deskripsi"),
        "ruang_id": f_int("ruang_id"),
        "rak_id": f_int("rak_id"),
        "perangkat_id": f_int("perangkat_id"),
        "mulai_rencana": f_datetime("mulai_rencana", "Rencana mulai", True),
        "selesai_rencana": f_datetime("selesai_rencana", "Rencana selesai", True),
        "pic": f_str("pic", "PIC", True),
        "vendor": f_str("vendor"),
        "risiko": f_choice("risiko", RISIKO, "Tingkat risiko", "rendah"),
        "dampak_layanan": f_str("dampak_layanan"),
        "rencana_rollback": f_str("rencana_rollback"),
    }
    if data["selesai_rencana"] <= data["mulai_rencana"]:
        raise ValueError("Rencana selesai harus setelah rencana mulai")
    if data["risiko"] == "tinggi" and not data["rencana_rollback"]:
        raise ValueError("Aktivitas berisiko tinggi wajib mengisi rencana rollback")
    db = get_db()
    if data["perangkat_id"]:
        perangkat = db.execute("SELECT rak_id FROM perangkat WHERE id = ?", (data["perangkat_id"],)).fetchone()
        if perangkat is None:
            raise ValueError("Perangkat tidak ditemukan")
        if not data["rak_id"]:
            data["rak_id"] = perangkat["rak_id"]
    if data["rak_id"]:
        rak = db.execute("SELECT ruang_id FROM rak WHERE id = ?", (data["rak_id"],)).fetchone()
        if rak is None:
            raise ValueError("Rak tidak ditemukan")
        data["ruang_id"] = rak["ruang_id"]
    if data["ruang_id"] and not db.execute("SELECT 1 FROM ruang WHERE id = ?", (data["ruang_id"],)).fetchone():
        raise ValueError("Ruang tidak ditemukan")
    return data


def _render_form(aktivitas, form):
    return render_template(
        "aktivitas/form.html", aktivitas=aktivitas, form=form,
        ruangs=daftar_ruang(), raks=daftar_rak(), perangkats=daftar_perangkat(),
    )


def _peringatan_bentrok(data, aid):
    bentrok = cari_bentrok(data["ruang_id"], data["rak_id"], data["mulai_rencana"], data["selesai_rencana"], aid)
    if bentrok:
        daftar = ", ".join(f"{b['nomor']} ({b['judul']})" for b in bentrok)
        flash(f"Perhatian: jadwal bentrok dengan aktivitas lain di lokasi yang sama: {daftar}", "warning")


@bp.route("/")
def daftar():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    jenis = request.args.get("jenis", "")
    dari = arg_date("dari")
    sampai = arg_date("sampai")
    sql = SELECT_AKTIVITAS + " WHERE 1 = 1"
    params = []
    if q:
        sql += " AND (a.judul LIKE ? OR a.nomor LIKE ? OR a.pic LIKE ? OR a.vendor LIKE ?)"
        params += [f"%{q}%"] * 4
    if status == "aktif":
        sql += f" AND a.status IN ({', '.join('?' * len(STATUS_AKTIVITAS_AKTIF))})"
        params += list(STATUS_AKTIVITAS_AKTIF)
    elif status in STATUS_AKTIVITAS:
        sql += " AND a.status = ?"
        params.append(status)
    if jenis:
        sql += " AND a.jenis = ?"
        params.append(jenis)
    if dari:
        sql += " AND date(a.selesai_rencana) >= ?"
        params.append(dari)
    if sampai:
        sql += " AND date(a.mulai_rencana) <= ?"
        params.append(sampai)
    rows = get_db().execute(sql + " ORDER BY a.mulai_rencana DESC LIMIT 500", params).fetchall()
    return render_template(
        "aktivitas/list.html", rows=rows, q=q, status=status, jenis=jenis, dari=dari or "", sampai=sampai or ""
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
        cur = db.execute(
            f"INSERT INTO aktivitas ({', '.join(cols)}, status, diajukan_oleh) VALUES ({', '.join('?' * len(cols))}, 'diajukan', ?)",
            [data[k] for k in cols] + [g.user["id"]],
        )
        aid = cur.lastrowid
        nomor = f"WO-{date.today().year}-{aid:04d}"
        db.execute("UPDATE aktivitas SET nomor = ? WHERE id = ?", (nomor, aid))
        tambah_log(aid, "Aktivitas diajukan", "status")
        audit("tambah", "aktivitas", f"{nomor} {data['judul']}")
        db.commit()
        flash(f"Aktivitas {nomor} diajukan", "success")
        _peringatan_bentrok(data, aid)
        return redirect(url_for("aktivitas.detail", aid=aid))
    form = {
        "rak_id": request.args.get("rak_id", type=int),
        "perangkat_id": request.args.get("perangkat_id", type=int),
        "ruang_id": request.args.get("ruang_id", type=int),
        "risiko": "rendah",
        "pic": (g.user["nama"] or g.user["username"]),
    }
    return _render_form(None, form)


def boleh_edit(aktivitas):
    if aktivitas["status"] == "diajukan":
        return True
    return is_admin() and aktivitas["status"] in STATUS_AKTIVITAS_AKTIF


@bp.route("/<int:aid>/edit", methods=["GET", "POST"])
def edit(aid):
    aktivitas = get_or_404("aktivitas", aid)
    if not boleh_edit(aktivitas):
        flash("Aktivitas dengan status ini tidak bisa diubah", "danger")
        return redirect(url_for("aktivitas.detail", aid=aid))
    if request.method == "POST":
        try:
            data = _form_data()
        except ValueError as e:
            flash(str(e), "danger")
            return _render_form(aktivitas, request.form)
        db = get_db()
        db.execute(
            f"UPDATE aktivitas SET {', '.join(f'{k} = ?' for k in data)} WHERE id = ?",
            [data[k] for k in data] + [aid],
        )
        tambah_log(aid, "Detail aktivitas diperbarui", "status")
        audit("ubah", "aktivitas", aktivitas["nomor"])
        db.commit()
        flash("Aktivitas diperbarui", "success")
        _peringatan_bentrok(data, aid)
        return redirect(url_for("aktivitas.detail", aid=aid))
    return _render_form(aktivitas, aktivitas)


@bp.route("/<int:aid>")
def detail(aid):
    db = get_db()
    aktivitas = get_aktivitas(aid)
    logs = db.execute(
        """SELECT l.*, p.username, p.nama FROM aktivitas_log l LEFT JOIN pengguna p ON p.id = l.pengguna_id
           WHERE l.aktivitas_id = ? ORDER BY l.waktu DESC, l.id DESC""",
        (aid,),
    ).fetchall()
    tamu = db.execute("SELECT * FROM kunjungan WHERE aktivitas_id = ? ORDER BY masuk", (aid,)).fetchall()
    bentrok = []
    if aktivitas["status"] in STATUS_AKTIVITAS_AKTIF:
        bentrok = cari_bentrok(
            aktivitas["ruang_id"], aktivitas["rak_id"], aktivitas["mulai_rencana"], aktivitas["selesai_rencana"], aid
        )
    transisi = [t for t in TRANSISI_AKTIVITAS.get(aktivitas["status"], []) if is_admin() or not t[2]]
    return render_template(
        "aktivitas/detail.html", a=aktivitas, logs=logs, tamu=tamu, bentrok=bentrok,
        transisi=transisi, boleh_edit=boleh_edit(aktivitas),
    )


@bp.route("/<int:aid>/status", methods=["POST"])
def ubah_status(aid):
    aktivitas = get_or_404("aktivitas", aid)
    tujuan = request.form.get("status", "")
    opsi = {t[0]: t for t in TRANSISI_AKTIVITAS.get(aktivitas["status"], [])}
    if tujuan not in opsi:
        flash("Perubahan status tidak valid", "danger")
        return redirect(url_for("aktivitas.detail", aid=aid))
    if opsi[tujuan][2] and not is_admin():
        abort(403)
    catatan = request.form.get("catatan", "").strip()
    if tujuan in ("ditolak", "batal") and not catatan:
        flash("Alasan wajib diisi untuk menolak/membatalkan aktivitas", "danger")
        return redirect(url_for("aktivitas.detail", aid=aid))
    sekarang = now_local()
    sets = {"status": tujuan}
    if tujuan in ("disetujui", "ditolak"):
        sets.update(disetujui_oleh=g.user["id"], waktu_persetujuan=sekarang)
    elif tujuan == "berlangsung":
        sets["mulai_aktual"] = sekarang
    elif tujuan == "selesai":
        sets["selesai_aktual"] = sekarang
    db = get_db()
    db.execute(
        f"UPDATE aktivitas SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", list(sets.values()) + [aid]
    )
    isi = f"Status: {STATUS_AKTIVITAS[aktivitas['status']][0]} → {STATUS_AKTIVITAS[tujuan][0]}"
    if catatan:
        isi += f" — {catatan}"
    tambah_log(aid, isi, "status")
    audit("status", "aktivitas", f"{aktivitas['nomor']}: {tujuan}")
    db.commit()
    flash(f"Status aktivitas: {STATUS_AKTIVITAS[tujuan][0]}", "success")
    return redirect(url_for("aktivitas.detail", aid=aid))


@bp.route("/<int:aid>/catatan", methods=["POST"])
def tambah_catatan(aid):
    get_or_404("aktivitas", aid)
    isi = request.form.get("isi", "").strip()
    if not isi:
        flash("Catatan tidak boleh kosong", "danger")
    else:
        tambah_log(aid, isi)
        get_db().commit()
        flash("Catatan ditambahkan", "success")
    return redirect(url_for("aktivitas.detail", aid=aid) + "#timeline")


@bp.route("/<int:aid>/hapus", methods=["POST"])
@admin_required
def hapus(aid):
    aktivitas = get_or_404("aktivitas", aid)
    db = get_db()
    db.execute("DELETE FROM aktivitas WHERE id = ?", (aid,))
    audit("hapus", "aktivitas", f"{aktivitas['nomor']} {aktivitas['judul']}")
    db.commit()
    flash(f"Aktivitas {aktivitas['nomor']} dihapus", "success")
    return redirect(url_for("aktivitas.daftar"))


@bp.route("/<int:aid>/cetak")
def cetak(aid):
    db = get_db()
    tamu = db.execute("SELECT * FROM kunjungan WHERE aktivitas_id = ? ORDER BY masuk", (aid,)).fetchall()
    return render_template("aktivitas/cetak.html", a=get_aktivitas(aid), tamu=tamu)
