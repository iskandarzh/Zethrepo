from datetime import date, timedelta

from flask import Blueprint, render_template

from .db import get_db
from .insiden import SELECT_INSIDEN, URUT_SEVERITY
from .patroli import temuan
from .util import now_local, today

bp = Blueprint("dashboard", __name__)


@bp.route("/")
def index():
    db = get_db()
    hari_ini = today()
    seminggu = (date.today() + timedelta(days=7)).isoformat()
    aktivitas_hari_ini = db.execute(
        """SELECT a.*, r.kode AS kode_ruang, k.kode AS kode_rak FROM aktivitas a
           LEFT JOIN ruang r ON r.id = a.ruang_id LEFT JOIN rak k ON k.id = a.rak_id
           WHERE a.status IN ('diajukan', 'disetujui', 'berlangsung', 'selesai')
             AND date(a.mulai_rencana) <= ? AND date(a.selesai_rencana) >= ?
           ORDER BY a.mulai_rencana""",
        (hari_ini, hari_ini),
    ).fetchall()
    akan_datang = db.execute(
        """SELECT a.*, r.kode AS kode_ruang FROM aktivitas a LEFT JOIN ruang r ON r.id = a.ruang_id
           WHERE a.status IN ('diajukan', 'disetujui') AND date(a.mulai_rencana) > ? AND date(a.mulai_rencana) <= ?
           ORDER BY a.mulai_rencana""",
        (hari_ini, seminggu),
    ).fetchall()
    menunggu = db.execute(
        """SELECT a.*, r.kode AS kode_ruang FROM aktivitas a LEFT JOIN ruang r ON r.id = a.ruang_id
           WHERE a.status = 'diajukan' ORDER BY a.mulai_rencana"""
    ).fetchall()
    tamu = db.execute(
        """SELECT k.*, r.kode AS kode_ruang FROM kunjungan k LEFT JOIN ruang r ON r.id = k.ruang_id
           WHERE k.keluar IS NULL AND k.masuk <= ? ORDER BY k.masuk""",
        (now_local(),),
    ).fetchall()
    insiden = db.execute(
        SELECT_INSIDEN + f" WHERE i.status != 'selesai' ORDER BY {URUT_SEVERITY}, i.waktu_kejadian"
    ).fetchall()
    kondisi = []
    for r in db.execute(
        """SELECT r.id AS rid, r.kode AS kode_ruang, r.nama AS nama_ruang, p.*,
                  COALESCE(p.batas_suhu_min, r.suhu_min) AS suhu_min, COALESCE(p.batas_suhu_max, r.suhu_max) AS suhu_max,
                  COALESCE(p.batas_rh_min, r.rh_min) AS rh_min, COALESCE(p.batas_rh_max, r.rh_max) AS rh_max
           FROM ruang r
           LEFT JOIN patroli p ON p.id = (SELECT id FROM patroli WHERE ruang_id = r.id ORDER BY waktu DESC, id DESC LIMIT 1)
           ORDER BY r.kode"""
    ):
        kondisi.append((r, temuan(r) if r["waktu"] else []))
    stats = {
        "aktivitas_hari_ini": len(aktivitas_hari_ini),
        "berlangsung": sum(1 for a in aktivitas_hari_ini if a["status"] == "berlangsung"),
        "menunggu": len(menunggu),
        "tamu": len(tamu),
        "insiden": len(insiden),
        "insiden_kritis": sum(1 for i in insiden if i["severity"] in ("kritis", "tinggi")),
    }
    return render_template(
        "dashboard.html", aktivitas_hari_ini=aktivitas_hari_ini, akan_datang=akan_datang, menunggu=menunggu,
        tamu=tamu, insiden=insiden, kondisi=kondisi, stats=stats,
    )
