import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS pengguna (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nama TEXT,
    peran TEXT NOT NULL DEFAULT 'operator',
    aktif INTEGER NOT NULL DEFAULT 1,
    password_hash TEXT NOT NULL,
    dibuat TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS ruang (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kode TEXT NOT NULL UNIQUE COLLATE NOCASE,
    nama TEXT NOT NULL,
    lantai TEXT,
    suhu_min REAL DEFAULT 18,
    suhu_max REAL DEFAULT 27,
    rh_min REAL DEFAULT 40,
    rh_max REAL DEFAULT 60,
    keterangan TEXT
);

CREATE TABLE IF NOT EXISTS rak (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ruang_id INTEGER NOT NULL REFERENCES ruang(id),
    kode TEXT NOT NULL,
    kapasitas_u INTEGER NOT NULL DEFAULT 42,
    keterangan TEXT,
    UNIQUE (ruang_id, kode)
);

CREATE TABLE IF NOT EXISTS perangkat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    jenis TEXT,
    merek TEXT,
    model TEXT,
    serial TEXT,
    rak_id INTEGER REFERENCES rak(id) ON DELETE SET NULL,
    posisi_u INTEGER,
    tinggi_u INTEGER NOT NULL DEFAULT 1,
    ip_mgmt TEXT,
    pemilik TEXT,
    status TEXT NOT NULL DEFAULT 'aktif',
    keterangan TEXT
);

CREATE TABLE IF NOT EXISTS aktivitas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomor TEXT,
    judul TEXT NOT NULL,
    jenis TEXT NOT NULL,
    deskripsi TEXT,
    ruang_id INTEGER REFERENCES ruang(id) ON DELETE SET NULL,
    rak_id INTEGER REFERENCES rak(id) ON DELETE SET NULL,
    perangkat_id INTEGER REFERENCES perangkat(id) ON DELETE SET NULL,
    mulai_rencana TEXT NOT NULL,
    selesai_rencana TEXT NOT NULL,
    mulai_aktual TEXT,
    selesai_aktual TEXT,
    pic TEXT NOT NULL,
    vendor TEXT,
    risiko TEXT NOT NULL DEFAULT 'rendah',
    dampak_layanan TEXT,
    rencana_rollback TEXT,
    status TEXT NOT NULL DEFAULT 'diajukan',
    diajukan_oleh INTEGER REFERENCES pengguna(id) ON DELETE SET NULL,
    disetujui_oleh INTEGER REFERENCES pengguna(id) ON DELETE SET NULL,
    waktu_persetujuan TEXT,
    dibuat TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS aktivitas_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    aktivitas_id INTEGER NOT NULL REFERENCES aktivitas(id) ON DELETE CASCADE,
    waktu TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M', 'now', 'localtime')),
    pengguna_id INTEGER REFERENCES pengguna(id) ON DELETE SET NULL,
    jenis TEXT NOT NULL DEFAULT 'catatan',
    isi TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kunjungan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nama TEXT NOT NULL,
    perusahaan TEXT,
    no_identitas TEXT,
    telepon TEXT,
    tujuan TEXT NOT NULL,
    ruang_id INTEGER REFERENCES ruang(id) ON DELETE SET NULL,
    aktivitas_id INTEGER REFERENCES aktivitas(id) ON DELETE SET NULL,
    pendamping TEXT,
    kartu_akses TEXT,
    masuk TEXT NOT NULL,
    keluar TEXT,
    catatan TEXT,
    dicatat_oleh INTEGER REFERENCES pengguna(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS patroli (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    waktu TEXT NOT NULL,
    ruang_id INTEGER NOT NULL REFERENCES ruang(id),
    suhu REAL,
    kelembaban REAL,
    ups TEXT NOT NULL DEFAULT 'normal',
    genset TEXT NOT NULL DEFAULT 'normal',
    pendingin TEXT NOT NULL DEFAULT 'normal',
    kebakaran TEXT NOT NULL DEFAULT 'normal',
    keamanan TEXT NOT NULL DEFAULT 'normal',
    kebersihan TEXT NOT NULL DEFAULT 'normal',
    catatan TEXT,
    petugas_id INTEGER REFERENCES pengguna(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS insiden (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nomor TEXT,
    judul TEXT NOT NULL,
    kategori TEXT NOT NULL,
    severity TEXT NOT NULL,
    ruang_id INTEGER REFERENCES ruang(id) ON DELETE SET NULL,
    perangkat_id INTEGER REFERENCES perangkat(id) ON DELETE SET NULL,
    waktu_kejadian TEXT NOT NULL,
    deskripsi TEXT,
    penanganan TEXT,
    status TEXT NOT NULL DEFAULT 'terbuka',
    waktu_selesai TEXT,
    pelapor_id INTEGER REFERENCES pengguna(id) ON DELETE SET NULL,
    dibuat TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    waktu TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
    pengguna_id INTEGER REFERENCES pengguna(id) ON DELETE SET NULL,
    aksi TEXT NOT NULL,
    objek TEXT NOT NULL,
    detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_aktivitas_mulai ON aktivitas(mulai_rencana);
CREATE INDEX IF NOT EXISTS idx_kunjungan_masuk ON kunjungan(masuk);
CREATE INDEX IF NOT EXISTS idx_patroli_ruang_waktu ON patroli(ruang_id, waktu);
CREATE INDEX IF NOT EXISTS idx_insiden_waktu ON insiden(waktu_kejadian);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_app(app):
    app.teardown_appcontext(close_db)
    with app.app_context():
        get_db().executescript(SCHEMA)


def audit(aksi, objek, detail=""):
    """Catat aksi pengguna; commit dilakukan oleh pemanggil."""
    user = g.get("user")
    get_db().execute(
        "INSERT INTO audit (pengguna_id, aksi, objek, detail) VALUES (?, ?, ?, ?)",
        (user["id"] if user else None, aksi, objek, detail),
    )


def get_or_404(table, row_id):
    from flask import abort

    row = get_db().execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        abort(404)
    return row
