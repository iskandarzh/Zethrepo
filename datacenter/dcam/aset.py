import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for

from .const import STATUS_PERANGKAT
from .db import audit, get_db, get_or_404
from .util import admin_required, f_choice, f_float, f_int, f_str

bp = Blueprint("aset", __name__, url_prefix="/aset")


def daftar_ruang():
    return get_db().execute("SELECT * FROM ruang ORDER BY kode").fetchall()


def daftar_rak():
    return get_db().execute(
        "SELECT k.*, r.kode AS kode_ruang FROM rak k JOIN ruang r ON r.id = k.ruang_id ORDER BY r.kode, k.kode"
    ).fetchall()


def daftar_perangkat(termasuk=None):
    return get_db().execute(
        """SELECT d.id, d.nama, d.jenis, d.rak_id, k.kode AS kode_rak, r.kode AS kode_ruang
           FROM perangkat d LEFT JOIN rak k ON k.id = d.rak_id LEFT JOIN ruang r ON r.id = k.ruang_id
           WHERE d.status != 'decommissioned' OR d.id = ? ORDER BY d.nama""",
        (termasuk,),
    ).fetchall()


def hapus_aman(table, row_id, label):
    db = get_db()
    try:
        db.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
    except sqlite3.IntegrityError:
        db.rollback()
        flash(f"{label} tidak bisa dihapus karena masih dipakai oleh data lain", "danger")
        return False
    audit("hapus", table, label)
    db.commit()
    flash(f"{label} dihapus", "success")
    return True


# ---------- Ruang ----------
@bp.route("/")
def ruang_list():
    rows = get_db().execute(
        """SELECT r.*,
                  (SELECT COUNT(*) FROM rak WHERE ruang_id = r.id) AS jumlah_rak,
                  (SELECT COUNT(*) FROM perangkat d JOIN rak k ON k.id = d.rak_id WHERE k.ruang_id = r.id) AS jumlah_perangkat
           FROM ruang r ORDER BY r.kode"""
    ).fetchall()
    return render_template("aset/ruang_list.html", rows=rows)


def _ruang_form():
    data = {
        "kode": f_str("kode", "Kode ruang", True),
        "nama": f_str("nama", "Nama ruang", True),
        "lantai": f_str("lantai"),
        "suhu_min": f_float("suhu_min", "Suhu minimum"),
        "suhu_max": f_float("suhu_max", "Suhu maksimum"),
        "rh_min": f_float("rh_min", "Kelembaban minimum"),
        "rh_max": f_float("rh_max", "Kelembaban maksimum"),
        "keterangan": f_str("keterangan"),
    }
    for a, b, label in (("suhu_min", "suhu_max", "suhu"), ("rh_min", "rh_max", "kelembaban")):
        if data[a] is not None and data[b] is not None and data[a] >= data[b]:
            raise ValueError(f"Batas minimum {label} harus lebih kecil dari maksimum")
    return data


def _simpan(table, data, row_id=None):
    db = get_db()
    cols = list(data)
    if row_id is None:
        cur = db.execute(
            f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
            [data[k] for k in cols],
        )
        return cur.lastrowid
    db.execute(f"UPDATE {table} SET {', '.join(f'{k} = ?' for k in cols)} WHERE id = ?", [data[k] for k in cols] + [row_id])
    return row_id


@bp.route("/ruang/baru", methods=["GET", "POST"])
@bp.route("/ruang/<int:rid>/edit", methods=["GET", "POST"])
def ruang_form(rid=None):
    ruang = get_or_404("ruang", rid) if rid else None
    if request.method == "POST":
        try:
            data = _ruang_form()
            rid = _simpan("ruang", data, rid)
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("aset/ruang_form.html", ruang=ruang, form=request.form)
        except sqlite3.IntegrityError:
            flash("Kode ruang sudah dipakai", "danger")
            return render_template("aset/ruang_form.html", ruang=ruang, form=request.form)
        audit("ubah" if ruang else "tambah", "ruang", data["kode"])
        get_db().commit()
        flash("Ruang disimpan", "success")
        return redirect(url_for("aset.ruang_detail", rid=rid))
    return render_template("aset/ruang_form.html", ruang=ruang, form=ruang or {"suhu_min": 18, "suhu_max": 27, "rh_min": 40, "rh_max": 60})


@bp.route("/ruang/<int:rid>")
def ruang_detail(rid):
    db = get_db()
    ruang = get_or_404("ruang", rid)
    raks = db.execute(
        """SELECT k.*, COALESCE((SELECT SUM(tinggi_u) FROM perangkat WHERE rak_id = k.id AND posisi_u IS NOT NULL), 0) AS terpakai,
                  (SELECT COUNT(*) FROM perangkat WHERE rak_id = k.id) AS jumlah_perangkat
           FROM rak k WHERE k.ruang_id = ? ORDER BY k.kode""",
        (rid,),
    ).fetchall()
    tren = db.execute(
        "SELECT * FROM (SELECT waktu, suhu, kelembaban FROM patroli WHERE ruang_id = ? ORDER BY waktu DESC LIMIT 60) ORDER BY waktu",
        (rid,),
    ).fetchall()
    return render_template("aset/ruang_detail.html", ruang=ruang, raks=raks, tren=[dict(r) for r in tren])


@bp.route("/ruang/<int:rid>/hapus", methods=["POST"])
@admin_required
def ruang_hapus(rid):
    ruang = get_or_404("ruang", rid)
    if hapus_aman("ruang", rid, f"Ruang {ruang['kode']}"):
        return redirect(url_for("aset.ruang_list"))
    return redirect(url_for("aset.ruang_detail", rid=rid))


# ---------- Rak ----------
@bp.route("/rak/baru", methods=["GET", "POST"])
@bp.route("/rak/<int:kid>/edit", methods=["GET", "POST"])
def rak_form(kid=None):
    rak = get_or_404("rak", kid) if kid else None
    if request.method == "POST":
        try:
            data = {
                "ruang_id": f_int("ruang_id", "Ruang", True),
                "kode": f_str("kode", "Kode rak", True),
                "kapasitas_u": f_int("kapasitas_u", "Kapasitas", True, minimum=1),
                "keterangan": f_str("keterangan"),
            }
            if kid:
                tertinggi = get_db().execute(
                    "SELECT MAX(posisi_u + tinggi_u - 1) FROM perangkat WHERE rak_id = ? AND posisi_u IS NOT NULL", (kid,)
                ).fetchone()[0]
                if tertinggi and data["kapasitas_u"] < tertinggi:
                    raise ValueError(f"Kapasitas tidak boleh kurang dari {tertinggi}U (posisi perangkat tertinggi)")
            kid = _simpan("rak", data, kid)
        except ValueError as e:
            flash(str(e), "danger")
            return render_template("aset/rak_form.html", rak=rak, form=request.form, ruangs=daftar_ruang())
        except sqlite3.IntegrityError:
            flash("Kode rak sudah dipakai di ruang tersebut, atau ruang tidak valid", "danger")
            return render_template("aset/rak_form.html", rak=rak, form=request.form, ruangs=daftar_ruang())
        audit("ubah" if rak else "tambah", "rak", data["kode"])
        get_db().commit()
        flash("Rak disimpan", "success")
        return redirect(url_for("aset.rak_detail", kid=kid))
    form = rak or {"ruang_id": request.args.get("ruang_id", type=int), "kapasitas_u": 42}
    return render_template("aset/rak_form.html", rak=rak, form=form, ruangs=daftar_ruang())


def elevasi(rak, perangkat):
    """Baris rak dari U teratas ke bawah: (u, perangkat | 'lanjut' | None)."""
    puncak, terisi = {}, set()
    for p in perangkat:
        if p["posisi_u"]:
            atas = p["posisi_u"] + p["tinggi_u"] - 1
            puncak[atas] = p
            terisi.update(range(p["posisi_u"], atas + 1))
    baris = []
    for u in range(rak["kapasitas_u"], 0, -1):
        if u in puncak:
            baris.append((u, puncak[u]))
        elif u in terisi:
            baris.append((u, "lanjut"))
        else:
            baris.append((u, None))
    return baris


@bp.route("/rak/<int:kid>")
def rak_detail(kid):
    db = get_db()
    rak = db.execute(
        "SELECT k.*, r.kode AS kode_ruang, r.nama AS nama_ruang FROM rak k JOIN ruang r ON r.id = k.ruang_id WHERE k.id = ?",
        (kid,),
    ).fetchone()
    if rak is None:
        return render_template("error.html", kode=404, pesan="Rak tidak ditemukan."), 404
    perangkat = db.execute("SELECT * FROM perangkat WHERE rak_id = ? ORDER BY posisi_u DESC", (kid,)).fetchall()
    terpakai = sum(p["tinggi_u"] for p in perangkat if p["posisi_u"])
    return render_template(
        "aset/rak_detail.html", rak=rak, perangkat=perangkat, baris=elevasi(rak, perangkat), terpakai=terpakai
    )


@bp.route("/rak/<int:kid>/hapus", methods=["POST"])
@admin_required
def rak_hapus(kid):
    rak = get_or_404("rak", kid)
    if hapus_aman("rak", kid, f"Rak {rak['kode']}"):
        return redirect(url_for("aset.ruang_detail", rid=rak["ruang_id"]))
    return redirect(url_for("aset.rak_detail", kid=kid))


# ---------- Perangkat ----------
@bp.route("/perangkat")
def perangkat_list():
    q = request.args.get("q", "").strip()
    jenis = request.args.get("jenis", "")
    status = request.args.get("status", "")
    sql = """SELECT d.*, k.kode AS kode_rak, r.kode AS kode_ruang FROM perangkat d
             LEFT JOIN rak k ON k.id = d.rak_id LEFT JOIN ruang r ON r.id = k.ruang_id WHERE 1 = 1"""
    params = []
    if q:
        sql += " AND (d.nama LIKE ? OR d.serial LIKE ? OR d.merek LIKE ? OR d.model LIKE ? OR d.ip_mgmt LIKE ? OR d.pemilik LIKE ?)"
        params += [f"%{q}%"] * 6
    if jenis:
        sql += " AND d.jenis = ?"
        params.append(jenis)
    if status:
        sql += " AND d.status = ?"
        params.append(status)
    rows = get_db().execute(sql + " ORDER BY r.kode, k.kode, d.posisi_u DESC, d.nama LIMIT 1000", params).fetchall()
    return render_template("aset/perangkat_list.html", rows=rows, q=q, jenis=jenis, status=status)


def _perangkat_form(pid):
    data = {
        "nama": f_str("nama", "Nama perangkat", True),
        "jenis": f_str("jenis"),
        "merek": f_str("merek"),
        "model": f_str("model"),
        "serial": f_str("serial"),
        "rak_id": f_int("rak_id"),
        "posisi_u": f_int("posisi_u", "Posisi U", minimum=1),
        "tinggi_u": f_int("tinggi_u", "Tinggi", minimum=1) or 1,
        "ip_mgmt": f_str("ip_mgmt"),
        "pemilik": f_str("pemilik"),
        "status": f_choice("status", STATUS_PERANGKAT, "Status", "aktif"),
        "keterangan": f_str("keterangan"),
    }
    db = get_db()
    if data["posisi_u"] and not data["rak_id"]:
        raise ValueError("Pilih rak jika mengisi posisi U")
    if data["rak_id"]:
        rak = db.execute("SELECT * FROM rak WHERE id = ?", (data["rak_id"],)).fetchone()
        if rak is None:
            raise ValueError("Rak tidak ditemukan")
        if data["posisi_u"]:
            atas = data["posisi_u"] + data["tinggi_u"] - 1
            if atas > rak["kapasitas_u"]:
                raise ValueError(f"Posisi melebihi kapasitas rak ({rak['kapasitas_u']}U)")
            tabrakan = db.execute(
                """SELECT nama, posisi_u, tinggi_u FROM perangkat
                   WHERE rak_id = ? AND id != ? AND posisi_u IS NOT NULL AND posisi_u <= ? AND posisi_u + tinggi_u - 1 >= ?""",
                (data["rak_id"], pid or 0, atas, data["posisi_u"]),
            ).fetchone()
            if tabrakan:
                raise ValueError(
                    f"Posisi U{data['posisi_u']}-U{atas} bertabrakan dengan {tabrakan['nama']} "
                    f"(U{tabrakan['posisi_u']}-U{tabrakan['posisi_u'] + tabrakan['tinggi_u'] - 1})"
                )
    return data


@bp.route("/perangkat/baru", methods=["GET", "POST"])
@bp.route("/perangkat/<int:pid>/edit", methods=["GET", "POST"])
def perangkat_form(pid=None):
    perangkat = get_or_404("perangkat", pid) if pid else None
    if request.method == "POST":
        try:
            data = _perangkat_form(pid)
            pid = _simpan("perangkat", data, pid)
        except ValueError as e:
            flash(str(e), "danger")
            return render_template(
                "aset/perangkat_form.html", perangkat=perangkat, form=request.form, raks=daftar_rak()
            )
        audit("ubah" if perangkat else "tambah", "perangkat", data["nama"])
        get_db().commit()
        flash("Perangkat disimpan", "success")
        return redirect(url_for("aset.perangkat_detail", pid=pid))
    form = perangkat or {
        "rak_id": request.args.get("rak_id", type=int),
        "posisi_u": request.args.get("posisi_u", type=int),
        "tinggi_u": 1,
        "status": "aktif",
    }
    return render_template("aset/perangkat_form.html", perangkat=perangkat, form=form, raks=daftar_rak())


@bp.route("/perangkat/<int:pid>")
def perangkat_detail(pid):
    db = get_db()
    perangkat = db.execute(
        """SELECT d.*, k.kode AS kode_rak, r.kode AS kode_ruang, r.id AS ruang_id FROM perangkat d
           LEFT JOIN rak k ON k.id = d.rak_id LEFT JOIN ruang r ON r.id = k.ruang_id WHERE d.id = ?""",
        (pid,),
    ).fetchone()
    if perangkat is None:
        return render_template("error.html", kode=404, pesan="Perangkat tidak ditemukan."), 404
    aktivitas = db.execute(
        "SELECT * FROM aktivitas WHERE perangkat_id = ? ORDER BY mulai_rencana DESC LIMIT 50", (pid,)
    ).fetchall()
    insiden = db.execute(
        "SELECT * FROM insiden WHERE perangkat_id = ? ORDER BY waktu_kejadian DESC LIMIT 50", (pid,)
    ).fetchall()
    return render_template("aset/perangkat_detail.html", p=perangkat, aktivitas=aktivitas, insiden=insiden)


@bp.route("/perangkat/<int:pid>/hapus", methods=["POST"])
@admin_required
def perangkat_hapus(pid):
    perangkat = get_or_404("perangkat", pid)
    if hapus_aman("perangkat", pid, f"Perangkat {perangkat['nama']}"):
        return redirect(url_for("aset.perangkat_list"))
    return redirect(url_for("aset.perangkat_detail", pid=pid))

