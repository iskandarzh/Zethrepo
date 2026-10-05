import os
import sqlite3
from datetime import date, datetime, timedelta

from flask import Flask, abort, flash, g, redirect, render_template, request, url_for

SCHEMA = """
CREATE TABLE IF NOT EXISTS pasien (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    no_rm TEXT,
    nama TEXT NOT NULL,
    tanggal_lahir TEXT,
    jenis_kelamin TEXT,
    catatan TEXT,
    dibuat TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS pengukuran (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pasien_id INTEGER NOT NULL REFERENCES pasien(id) ON DELETE CASCADE,
    waktu TEXT NOT NULL,
    sistolik INTEGER,
    diastolik INTEGER,
    nadi INTEGER,
    gula_darah INTEGER,
    jenis_gula TEXT,
    catatan TEXT
);

CREATE TABLE IF NOT EXISTS obat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pasien_id INTEGER NOT NULL REFERENCES pasien(id) ON DELETE CASCADE,
    nama TEXT NOT NULL,
    dosis TEXT NOT NULL,
    satuan TEXT,
    rute TEXT,
    frekuensi TEXT,
    tanggal_mulai TEXT,
    tanggal_selesai TEXT,
    keterangan TEXT
);

CREATE TABLE IF NOT EXISTS jadwal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obat_id INTEGER NOT NULL REFERENCES obat(id) ON DELETE CASCADE,
    waktu TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'terjadwal',
    waktu_diberikan TEXT,
    catatan TEXT
);
"""

JENIS_GULA = {
    "sewaktu": "Sewaktu (GDS)",
    "puasa": "Puasa (GDP)",
    "2jam_pp": "2 Jam Post Prandial",
}
RUTE = ["Oral", "Injeksi IV", "Injeksi IM", "Injeksi SC", "Topikal", "Inhalasi", "Sublingual", "Lainnya"]
STATUS_JADWAL = {"terjadwal": "Terjadwal", "diberikan": "Diberikan", "dilewati": "Dilewati"}


def kategori_tensi(sis, dia):
    """Klasifikasi tekanan darah (acuan AHA/ACC 2017)."""
    if sis is None or dia is None:
        return None
    if sis > 180 or dia > 120:
        return ("Krisis Hipertensi", "dark")
    if sis >= 140 or dia >= 90:
        return ("Hipertensi Tahap 2", "danger")
    if sis >= 130 or dia >= 80:
        return ("Hipertensi Tahap 1", "warning")
    if sis >= 120:
        return ("Meningkat", "info")
    if sis < 90 or dia < 60:
        return ("Hipotensi", "primary")
    return ("Normal", "success")


def kategori_gula(nilai, jenis):
    """Klasifikasi gula darah (mg/dL, acuan ADA/PERKENI)."""
    if nilai is None:
        return None
    if nilai < 70:
        return ("Hipoglikemia", "primary")
    if jenis == "puasa":
        if nilai < 100:
            return ("Normal", "success")
        if nilai < 126:
            return ("Prediabetes", "warning")
        return ("Diabetes", "danger")
    if nilai < 140:
        return ("Normal", "success")
    if nilai < 200:
        return ("Prediabetes", "warning")
    return ("Diabetes", "danger")


def parse_int(value):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"'{value}' bukan angka yang valid")


def safe_next(value, fallback):
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return fallback


def now_local():
    return datetime.now().strftime("%Y-%m-%dT%H:%M")


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-ganti-di-produksi"),
        DATABASE=os.path.join(app.instance_path, "pasien.db"),
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"])
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    with app.app_context():
        get_db().executescript(SCHEMA)

    app.jinja_env.globals.update(
        kategori_tensi=kategori_tensi,
        kategori_gula=kategori_gula,
        JENIS_GULA=JENIS_GULA,
        RUTE=RUTE,
        STATUS_JADWAL=STATUS_JADWAL,
    )

    @app.template_filter("tgl")
    def format_tgl(value):
        if not value:
            return "-"
        try:
            if "T" in value or " " in value:
                return datetime.fromisoformat(value.replace(" ", "T")).strftime("%d-%m-%Y %H:%M")
            return datetime.fromisoformat(value).strftime("%d-%m-%Y")
        except ValueError:
            return value

    @app.template_filter("jam")
    def format_jam(value):
        try:
            return datetime.fromisoformat(value).strftime("%H:%M")
        except (TypeError, ValueError):
            return value

    @app.template_filter("umur")
    def umur(tanggal_lahir):
        if not tanggal_lahir:
            return "-"
        try:
            lahir = date.fromisoformat(tanggal_lahir)
        except ValueError:
            return "-"
        today = date.today()
        return today.year - lahir.year - ((today.month, today.day) < (lahir.month, lahir.day))

    def get_pasien(pasien_id):
        row = get_db().execute("SELECT * FROM pasien WHERE id = ?", (pasien_id,)).fetchone()
        if row is None:
            abort(404)
        return row

    def get_obat(obat_id):
        row = get_db().execute("SELECT * FROM obat WHERE id = ?", (obat_id,)).fetchone()
        if row is None:
            abort(404)
        return row

    # ---------- Dashboard ----------
    @app.route("/")
    def dashboard():
        db = get_db()
        tanggal = request.args.get("tanggal") or date.today().isoformat()
        jadwal = db.execute(
            """
            SELECT j.*, o.nama AS nama_obat, o.dosis, o.satuan, o.rute,
                   p.id AS pasien_id, p.nama AS nama_pasien, p.no_rm
            FROM jadwal j
            JOIN obat o ON o.id = j.obat_id
            JOIN pasien p ON p.id = o.pasien_id
            WHERE date(j.waktu) = ?
            ORDER BY j.waktu, p.nama
            """,
            (tanggal,),
        ).fetchall()
        pengukuran = db.execute(
            """
            SELECT m.*, p.nama AS nama_pasien FROM pengukuran m
            JOIN pasien p ON p.id = m.pasien_id
            ORDER BY m.waktu DESC LIMIT 10
            """
        ).fetchall()
        stats = {
            "pasien": db.execute("SELECT COUNT(*) FROM pasien").fetchone()[0],
            "jadwal": len(jadwal),
            "diberikan": sum(1 for j in jadwal if j["status"] == "diberikan"),
            "terlambat": sum(1 for j in jadwal if j["status"] == "terjadwal" and j["waktu"] < now_local()),
        }
        return render_template(
            "dashboard.html", jadwal=jadwal, pengukuran=pengukuran, stats=stats,
            tanggal=tanggal, sekarang=now_local(),
        )

    # ---------- Pasien ----------
    @app.route("/pasien")
    def pasien_list():
        q = request.args.get("q", "").strip()
        sql = """
            SELECT p.*,
              (SELECT COUNT(*) FROM obat o WHERE o.pasien_id = p.id) AS jumlah_obat,
              (SELECT MAX(waktu) FROM pengukuran m WHERE m.pasien_id = p.id) AS terakhir_ukur
            FROM pasien p
        """
        params = ()
        if q:
            sql += " WHERE p.nama LIKE ? OR p.no_rm LIKE ?"
            params = (f"%{q}%", f"%{q}%")
        sql += " ORDER BY p.nama"
        return render_template("pasien_list.html", pasien=get_db().execute(sql, params).fetchall(), q=q)

    def _pasien_form_data():
        data = {k: request.form.get(k, "").strip() for k in ("no_rm", "nama", "tanggal_lahir", "jenis_kelamin", "catatan")}
        if not data["nama"]:
            raise ValueError("Nama pasien wajib diisi")
        return data

    @app.route("/pasien/baru", methods=["GET", "POST"])
    def pasien_baru():
        if request.method == "POST":
            try:
                d = _pasien_form_data()
            except ValueError as e:
                flash(str(e), "danger")
                return render_template("pasien_form.html", pasien=request.form)
            db = get_db()
            cur = db.execute(
                "INSERT INTO pasien (no_rm, nama, tanggal_lahir, jenis_kelamin, catatan) VALUES (?, ?, ?, ?, ?)",
                (d["no_rm"], d["nama"], d["tanggal_lahir"], d["jenis_kelamin"], d["catatan"]),
            )
            db.commit()
            flash("Pasien berhasil ditambahkan", "success")
            return redirect(url_for("pasien_detail", pasien_id=cur.lastrowid))
        return render_template("pasien_form.html", pasien={})

    @app.route("/pasien/<int:pasien_id>/edit", methods=["GET", "POST"])
    def pasien_edit(pasien_id):
        pasien = get_pasien(pasien_id)
        if request.method == "POST":
            try:
                d = _pasien_form_data()
            except ValueError as e:
                flash(str(e), "danger")
                return render_template("pasien_form.html", pasien=request.form, edit=True)
            db = get_db()
            db.execute(
                "UPDATE pasien SET no_rm=?, nama=?, tanggal_lahir=?, jenis_kelamin=?, catatan=? WHERE id=?",
                (d["no_rm"], d["nama"], d["tanggal_lahir"], d["jenis_kelamin"], d["catatan"], pasien_id),
            )
            db.commit()
            flash("Data pasien diperbarui", "success")
            return redirect(url_for("pasien_detail", pasien_id=pasien_id))
        return render_template("pasien_form.html", pasien=pasien, edit=True)

    @app.route("/pasien/<int:pasien_id>/hapus", methods=["POST"])
    def pasien_hapus(pasien_id):
        get_pasien(pasien_id)
        db = get_db()
        db.execute("DELETE FROM pasien WHERE id = ?", (pasien_id,))
        db.commit()
        flash("Pasien dihapus", "success")
        return redirect(url_for("pasien_list"))

    @app.route("/pasien/<int:pasien_id>")
    def pasien_detail(pasien_id):
        pasien = get_pasien(pasien_id)
        db = get_db()
        pengukuran = db.execute(
            "SELECT * FROM pengukuran WHERE pasien_id = ? ORDER BY waktu DESC", (pasien_id,)
        ).fetchall()
        obat = db.execute(
            "SELECT * FROM obat WHERE pasien_id = ? ORDER BY nama", (pasien_id,)
        ).fetchall()
        jadwal = db.execute(
            """
            SELECT j.*, o.nama AS nama_obat, o.dosis, o.satuan, o.rute FROM jadwal j
            JOIN obat o ON o.id = j.obat_id
            WHERE o.pasien_id = ? ORDER BY j.waktu
            """,
            (pasien_id,),
        ).fetchall()
        grafik = list(reversed(pengukuran))
        return render_template(
            "pasien_detail.html", pasien=pasien, pengukuran=pengukuran, obat=obat,
            jadwal=jadwal, sekarang=now_local(), hari_ini=date.today().isoformat(),
            grafik={
                "label": [m["waktu"].replace("T", " ") for m in grafik],
                "sistolik": [m["sistolik"] for m in grafik],
                "diastolik": [m["diastolik"] for m in grafik],
                "gula": [m["gula_darah"] for m in grafik],
            },
            tab=request.args.get("tab", "pengukuran"),
        )

    # ---------- Pengukuran ----------
    def _pengukuran_form_data():
        d = {
            "waktu": request.form.get("waktu", "").strip(),
            "sistolik": parse_int(request.form.get("sistolik")),
            "diastolik": parse_int(request.form.get("diastolik")),
            "nadi": parse_int(request.form.get("nadi")),
            "gula_darah": parse_int(request.form.get("gula_darah")),
            "jenis_gula": request.form.get("jenis_gula") or None,
            "catatan": request.form.get("catatan", "").strip(),
        }
        if not d["waktu"]:
            raise ValueError("Waktu pengukuran wajib diisi")
        if (d["sistolik"] is None) != (d["diastolik"] is None):
            raise ValueError("Isi sistolik dan diastolik sekaligus")
        if d["sistolik"] is None and d["gula_darah"] is None:
            raise ValueError("Isi minimal tensi atau gula darah")
        if d["sistolik"] is not None and not (40 <= d["sistolik"] <= 300 and 20 <= d["diastolik"] <= 200):
            raise ValueError("Nilai tensi di luar rentang wajar")
        if d["gula_darah"] is not None:
            if not 10 <= d["gula_darah"] <= 1000:
                raise ValueError("Nilai gula darah di luar rentang wajar (10-1000 mg/dL)")
            d["jenis_gula"] = d["jenis_gula"] or "sewaktu"
        else:
            d["jenis_gula"] = None
        return d

    @app.route("/pasien/<int:pasien_id>/pengukuran/baru", methods=["GET", "POST"])
    def pengukuran_baru(pasien_id):
        pasien = get_pasien(pasien_id)
        if request.method == "POST":
            try:
                d = _pengukuran_form_data()
            except ValueError as e:
                flash(str(e), "danger")
                return render_template("pengukuran_form.html", pasien=pasien, m=request.form)
            db = get_db()
            db.execute(
                """INSERT INTO pengukuran (pasien_id, waktu, sistolik, diastolik, nadi, gula_darah, jenis_gula, catatan)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (pasien_id, d["waktu"], d["sistolik"], d["diastolik"], d["nadi"], d["gula_darah"], d["jenis_gula"], d["catatan"]),
            )
            db.commit()
            flash("Pengukuran tersimpan", "success")
            return redirect(url_for("pasien_detail", pasien_id=pasien_id, tab="pengukuran"))
        return render_template("pengukuran_form.html", pasien=pasien, m={"waktu": now_local()})

    @app.route("/pengukuran/<int:mid>/edit", methods=["GET", "POST"])
    def pengukuran_edit(mid):
        db = get_db()
        m = db.execute("SELECT * FROM pengukuran WHERE id = ?", (mid,)).fetchone()
        if m is None:
            abort(404)
        pasien = get_pasien(m["pasien_id"])
        if request.method == "POST":
            try:
                d = _pengukuran_form_data()
            except ValueError as e:
                flash(str(e), "danger")
                return render_template("pengukuran_form.html", pasien=pasien, m=request.form, edit=True)
            db.execute(
                """UPDATE pengukuran SET waktu=?, sistolik=?, diastolik=?, nadi=?, gula_darah=?, jenis_gula=?, catatan=?
                   WHERE id=?""",
                (d["waktu"], d["sistolik"], d["diastolik"], d["nadi"], d["gula_darah"], d["jenis_gula"], d["catatan"], mid),
            )
            db.commit()
            flash("Pengukuran diperbarui", "success")
            return redirect(url_for("pasien_detail", pasien_id=pasien["id"], tab="pengukuran"))
        return render_template("pengukuran_form.html", pasien=pasien, m=m, edit=True)

    @app.route("/pengukuran/<int:mid>/hapus", methods=["POST"])
    def pengukuran_hapus(mid):
        db = get_db()
        m = db.execute("SELECT * FROM pengukuran WHERE id = ?", (mid,)).fetchone()
        if m is None:
            abort(404)
        db.execute("DELETE FROM pengukuran WHERE id = ?", (mid,))
        db.commit()
        flash("Pengukuran dihapus", "success")
        return redirect(url_for("pasien_detail", pasien_id=m["pasien_id"], tab="pengukuran"))

    # ---------- Obat ----------
    OBAT_FIELDS = ("nama", "dosis", "satuan", "rute", "frekuensi", "tanggal_mulai", "tanggal_selesai", "keterangan")

    def _obat_form_data():
        d = {k: request.form.get(k, "").strip() for k in OBAT_FIELDS}
        if not d["nama"] or not d["dosis"]:
            raise ValueError("Nama obat dan dosis wajib diisi")
        if d["tanggal_mulai"] and d["tanggal_selesai"] and d["tanggal_selesai"] < d["tanggal_mulai"]:
            raise ValueError("Tanggal selesai tidak boleh sebelum tanggal mulai")
        return d

    @app.route("/pasien/<int:pasien_id>/obat/baru", methods=["GET", "POST"])
    def obat_baru(pasien_id):
        pasien = get_pasien(pasien_id)
        if request.method == "POST":
            try:
                d = _obat_form_data()
            except ValueError as e:
                flash(str(e), "danger")
                return render_template("obat_form.html", pasien=pasien, o=request.form)
            db = get_db()
            cur = db.execute(
                f"INSERT INTO obat (pasien_id, {', '.join(OBAT_FIELDS)}) VALUES (?{', ?' * len(OBAT_FIELDS)})",
                (pasien_id, *[d[k] for k in OBAT_FIELDS]),
            )
            db.commit()
            flash("Obat ditambahkan. Silakan buat jadwal pemberiannya.", "success")
            return redirect(url_for("jadwal_baru", obat_id=cur.lastrowid))
        return render_template("obat_form.html", pasien=pasien, o={"tanggal_mulai": date.today().isoformat(), "rute": "Oral"})

    @app.route("/obat/<int:obat_id>/edit", methods=["GET", "POST"])
    def obat_edit(obat_id):
        o = get_obat(obat_id)
        pasien = get_pasien(o["pasien_id"])
        if request.method == "POST":
            try:
                d = _obat_form_data()
            except ValueError as e:
                flash(str(e), "danger")
                return render_template("obat_form.html", pasien=pasien, o=request.form, edit=True)
            db = get_db()
            db.execute(
                f"UPDATE obat SET {', '.join(f'{k}=?' for k in OBAT_FIELDS)} WHERE id=?",
                (*[d[k] for k in OBAT_FIELDS], obat_id),
            )
            db.commit()
            flash("Data obat diperbarui", "success")
            return redirect(url_for("pasien_detail", pasien_id=pasien["id"], tab="obat"))
        return render_template("obat_form.html", pasien=pasien, o=o, edit=True)

    @app.route("/obat/<int:obat_id>/hapus", methods=["POST"])
    def obat_hapus(obat_id):
        o = get_obat(obat_id)
        db = get_db()
        db.execute("DELETE FROM obat WHERE id = ?", (obat_id,))
        db.commit()
        flash("Obat beserta jadwalnya dihapus", "success")
        return redirect(url_for("pasien_detail", pasien_id=o["pasien_id"], tab="obat"))

    # ---------- Jadwal ----------
    @app.route("/obat/<int:obat_id>/jadwal/baru", methods=["GET", "POST"])
    def jadwal_baru(obat_id):
        o = get_obat(obat_id)
        pasien = get_pasien(o["pasien_id"])
        default = {
            "tanggal_mulai": o["tanggal_mulai"] or date.today().isoformat(),
            "tanggal_selesai": o["tanggal_selesai"] or o["tanggal_mulai"] or date.today().isoformat(),
            "jam": "08:00, 20:00",
        }
        if request.method == "POST":
            form = request.form
            try:
                mulai = date.fromisoformat(form.get("tanggal_mulai", ""))
                selesai = date.fromisoformat(form.get("tanggal_selesai", ""))
            except ValueError:
                flash("Tanggal mulai dan selesai wajib diisi", "danger")
                return render_template("jadwal_form.html", pasien=pasien, o=o, j=form)
            jam_list = []
            for part in form.get("jam", "").replace(";", ",").split(","):
                part = part.strip()
                if not part:
                    continue
                try:
                    jam_list.append(datetime.strptime(part, "%H:%M").strftime("%H:%M"))
                except ValueError:
                    flash(f"Format jam '{part}' tidak valid, gunakan HH:MM", "danger")
                    return render_template("jadwal_form.html", pasien=pasien, o=o, j=form)
            if not jam_list:
                flash("Isi minimal satu jam pemberian", "danger")
                return render_template("jadwal_form.html", pasien=pasien, o=o, j=form)
            if selesai < mulai:
                flash("Tanggal selesai tidak boleh sebelum tanggal mulai", "danger")
                return render_template("jadwal_form.html", pasien=pasien, o=o, j=form)
            if (selesai - mulai).days > 366:
                flash("Rentang jadwal maksimal 1 tahun", "danger")
                return render_template("jadwal_form.html", pasien=pasien, o=o, j=form)
            db = get_db()
            jumlah = 0
            hari = mulai
            while hari <= selesai:
                for jam in sorted(set(jam_list)):
                    waktu = f"{hari.isoformat()}T{jam}"
                    exists = db.execute(
                        "SELECT 1 FROM jadwal WHERE obat_id = ? AND waktu = ?", (obat_id, waktu)
                    ).fetchone()
                    if not exists:
                        db.execute(
                            "INSERT INTO jadwal (obat_id, waktu, catatan) VALUES (?, ?, ?)",
                            (obat_id, waktu, form.get("catatan", "").strip()),
                        )
                        jumlah += 1
                hari += timedelta(days=1)
            db.commit()
            flash(f"{jumlah} jadwal pemberian {o['nama']} dibuat", "success")
            return redirect(url_for("pasien_detail", pasien_id=pasien["id"], tab="jadwal"))
        return render_template("jadwal_form.html", pasien=pasien, o=o, j=default)

    @app.route("/jadwal/<int:jid>/status", methods=["POST"])
    def jadwal_status(jid):
        db = get_db()
        j = db.execute(
            "SELECT j.*, o.pasien_id FROM jadwal j JOIN obat o ON o.id = j.obat_id WHERE j.id = ?", (jid,)
        ).fetchone()
        if j is None:
            abort(404)
        status = request.form.get("status")
        if status not in STATUS_JADWAL:
            abort(400)
        waktu_diberikan = now_local() if status == "diberikan" else None
        db.execute(
            "UPDATE jadwal SET status = ?, waktu_diberikan = ? WHERE id = ?", (status, waktu_diberikan, jid)
        )
        db.commit()
        flash(f"Status jadwal diubah menjadi {STATUS_JADWAL[status]}", "success")
        return redirect(safe_next(request.form.get("next"), url_for("pasien_detail", pasien_id=j["pasien_id"], tab="jadwal")))

    @app.route("/jadwal/<int:jid>/hapus", methods=["POST"])
    def jadwal_hapus(jid):
        db = get_db()
        j = db.execute(
            "SELECT j.*, o.pasien_id FROM jadwal j JOIN obat o ON o.id = j.obat_id WHERE j.id = ?", (jid,)
        ).fetchone()
        if j is None:
            abort(404)
        db.execute("DELETE FROM jadwal WHERE id = ?", (jid,))
        db.commit()
        flash("Jadwal dihapus", "success")
        return redirect(safe_next(request.form.get("next"), url_for("pasien_detail", pasien_id=j["pasien_id"], tab="jadwal")))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
