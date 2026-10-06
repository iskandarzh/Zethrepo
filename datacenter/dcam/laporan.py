import csv
import io
from datetime import date

from flask import Blueprint, Response, abort, render_template

from .const import FASILITAS
from .db import get_db
from .patroli import SELECT_PATROLI, temuan
from .util import arg_date

bp = Blueprint("laporan", __name__, url_prefix="/laporan")


def periode():
    awal_bulan = date.today().replace(day=1).isoformat()
    dari = arg_date("dari", awal_bulan)
    sampai = arg_date("sampai", date.today().isoformat())
    if dari > sampai:
        dari, sampai = sampai, dari
    return dari, sampai


def hitung(sql, params):
    return get_db().execute(sql, params).fetchall()


@bp.route("/")
def index():
    dari, sampai = periode()
    p = (dari, sampai)
    akt = "FROM aktivitas WHERE date(mulai_rencana) BETWEEN ? AND ?"
    data = {
        "aktivitas_status": hitung(f"SELECT status AS k, COUNT(*) AS n {akt} GROUP BY status ORDER BY n DESC", p),
        "aktivitas_jenis": hitung(f"SELECT jenis AS k, COUNT(*) AS n {akt} GROUP BY jenis ORDER BY n DESC", p),
        "aktivitas_total": hitung(f"SELECT COUNT(*) AS n {akt}", p)[0]["n"],
        "tepat_waktu": hitung(
            f"SELECT COUNT(*) AS n {akt} AND status = 'selesai' AND selesai_aktual <= selesai_rencana", p
        )[0]["n"],
        "selesai": hitung(f"SELECT COUNT(*) AS n {akt} AND status = 'selesai'", p)[0]["n"],
        "kunjungan_total": hitung("SELECT COUNT(*) AS n FROM kunjungan WHERE date(masuk) BETWEEN ? AND ?", p)[0]["n"],
        "kunjungan_perusahaan": hitung(
            """SELECT COALESCE(perusahaan, '(tanpa perusahaan)') AS k, COUNT(*) AS n FROM kunjungan
               WHERE date(masuk) BETWEEN ? AND ? GROUP BY k ORDER BY n DESC LIMIT 10""",
            p,
        ),
        "insiden_severity": hitung(
            "SELECT severity AS k, COUNT(*) AS n FROM insiden WHERE date(waktu_kejadian) BETWEEN ? AND ? GROUP BY severity",
            p,
        ),
        "insiden_kategori": hitung(
            """SELECT kategori AS k, COUNT(*) AS n FROM insiden WHERE date(waktu_kejadian) BETWEEN ? AND ?
               GROUP BY kategori ORDER BY n DESC""",
            p,
        ),
        "insiden_total": hitung("SELECT COUNT(*) AS n FROM insiden WHERE date(waktu_kejadian) BETWEEN ? AND ?", p)[0]["n"],
    }
    patroli = hitung(SELECT_PATROLI + " WHERE date(p.waktu) BETWEEN ? AND ?", p)
    data["patroli_total"] = len(patroli)
    data["patroli_temuan"] = sum(1 for r in patroli if temuan(r))
    ruang = {}
    for r in patroli:
        s = ruang.setdefault(r["kode_ruang"], {"suhu": [], "rh": []})
        if r["suhu"] is not None:
            s["suhu"].append(r["suhu"])
        if r["kelembaban"] is not None:
            s["rh"].append(r["kelembaban"])
    data["lingkungan"] = sorted(ruang.items())
    return render_template("laporan/index.html", dari=dari, sampai=sampai, d=data)


def aman_csv(value):
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


EKSPOR = {
    "aktivitas": (
        """SELECT a.nomor, a.judul, a.jenis, a.status, r.kode AS ruang, k.kode AS rak, d.nama AS perangkat,
                  a.mulai_rencana, a.selesai_rencana, a.mulai_aktual, a.selesai_aktual, a.pic, a.vendor, a.risiko,
                  a.dampak_layanan, u.username AS diajukan_oleh, v.username AS disetujui_oleh, a.deskripsi
           FROM aktivitas a LEFT JOIN ruang r ON r.id = a.ruang_id LEFT JOIN rak k ON k.id = a.rak_id
           LEFT JOIN perangkat d ON d.id = a.perangkat_id LEFT JOIN pengguna u ON u.id = a.diajukan_oleh
           LEFT JOIN pengguna v ON v.id = a.disetujui_oleh
           WHERE date(a.mulai_rencana) BETWEEN ? AND ? ORDER BY a.mulai_rencana"""
    ),
    "kunjungan": (
        """SELECT k.nama, k.perusahaan, k.no_identitas, k.telepon, k.tujuan, r.kode AS ruang, a.nomor AS aktivitas,
                  k.pendamping, k.kartu_akses, k.masuk, k.keluar, k.catatan
           FROM kunjungan k LEFT JOIN ruang r ON r.id = k.ruang_id LEFT JOIN aktivitas a ON a.id = k.aktivitas_id
           WHERE date(k.masuk) BETWEEN ? AND ? ORDER BY k.masuk"""
    ),
    "patroli": (
        f"""SELECT p.waktu, r.kode AS ruang, p.suhu, p.kelembaban, {', '.join('p.' + k for k, _ in FASILITAS)},
                   p.catatan, u.username AS petugas
            FROM patroli p JOIN ruang r ON r.id = p.ruang_id LEFT JOIN pengguna u ON u.id = p.petugas_id
            WHERE date(p.waktu) BETWEEN ? AND ? ORDER BY p.waktu"""
    ),
    "insiden": (
        """SELECT i.nomor, i.judul, i.kategori, i.severity, i.status, r.kode AS ruang, d.nama AS perangkat,
                  i.waktu_kejadian, i.waktu_selesai, i.deskripsi, i.penanganan, u.username AS pelapor
           FROM insiden i LEFT JOIN ruang r ON r.id = i.ruang_id LEFT JOIN perangkat d ON d.id = i.perangkat_id
           LEFT JOIN pengguna u ON u.id = i.pelapor_id
           WHERE date(i.waktu_kejadian) BETWEEN ? AND ? ORDER BY i.waktu_kejadian"""
    ),
}


@bp.route("/<jenis>.csv")
def ekspor(jenis):
    if jenis not in EKSPOR:
        abort(404)
    dari, sampai = periode()
    cur = get_db().execute(EKSPOR[jenis], (dari, sampai))
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([col[0] for col in cur.description])
    for row in cur:
        writer.writerow([aman_csv(v) for v in row])
    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{jenis}_{dari}_{sampai}.csv"'},
    )
