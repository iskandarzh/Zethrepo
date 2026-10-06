PERAN = {
    "admin": "Admin",
    "operator": "Operator",
    "viewer": "Viewer (hanya lihat)",
}

JENIS_AKTIVITAS = [
    "Instalasi Perangkat",
    "Maintenance Preventif",
    "Maintenance Korektif",
    "Troubleshooting",
    "Decommission",
    "Relokasi Perangkat",
    "Penarikan Kabel",
    "Upgrade / Patching",
    "Inspeksi / Audit",
    "Lainnya",
]

STATUS_AKTIVITAS = {
    "diajukan": ("Diajukan", "warning"),
    "disetujui": ("Disetujui", "primary"),
    "berlangsung": ("Berlangsung", "info"),
    "selesai": ("Selesai", "success"),
    "ditolak": ("Ditolak", "danger"),
    "batal": ("Batal", "secondary"),
}
STATUS_AKTIVITAS_AKTIF = ("diajukan", "disetujui", "berlangsung")

# status asal -> [(status tujuan, label tombol, hanya admin, kelas tombol, ikon)]
TRANSISI_AKTIVITAS = {
    "diajukan": [
        ("disetujui", "Setujui", True, "success", "check2-circle"),
        ("ditolak", "Tolak", True, "danger", "x-circle"),
        ("batal", "Batalkan", False, "outline-secondary", "slash-circle"),
    ],
    "disetujui": [
        ("berlangsung", "Mulai Pekerjaan", False, "info", "play-circle"),
        ("batal", "Batalkan", False, "outline-secondary", "slash-circle"),
    ],
    "berlangsung": [
        ("selesai", "Selesai", False, "success", "flag"),
    ],
}

RISIKO = {
    "rendah": ("Rendah", "success"),
    "sedang": ("Sedang", "warning"),
    "tinggi": ("Tinggi", "danger"),
}

KONDISI = {
    "normal": ("Normal", "success"),
    "perhatian": ("Perhatian", "warning"),
    "gangguan": ("Gangguan", "danger"),
}

FASILITAS = [
    ("ups", "UPS"),
    ("genset", "Genset"),
    ("pendingin", "Pendingin (CRAC/PAC)"),
    ("kebakaran", "Sistem Pemadam Kebakaran"),
    ("keamanan", "Keamanan & CCTV"),
    ("kebersihan", "Kebersihan"),
]

KATEGORI_INSIDEN = [
    "Listrik",
    "Pendingin",
    "Jaringan",
    "Server / Storage",
    "Keamanan Fisik",
    "Kebakaran / Asap",
    "Kebocoran Air",
    "Lainnya",
]

SEVERITY = {
    "kritis": ("Kritis", "dark"),
    "tinggi": ("Tinggi", "danger"),
    "sedang": ("Sedang", "warning"),
    "rendah": ("Rendah", "info"),
}

STATUS_INSIDEN = {
    "terbuka": ("Terbuka", "danger"),
    "ditangani": ("Ditangani", "warning"),
    "selesai": ("Selesai", "success"),
}

JENIS_PERANGKAT = [
    "Server",
    "Storage",
    "Switch",
    "Router",
    "Firewall",
    "Load Balancer",
    "Patch Panel",
    "PDU",
    "UPS",
    "KVM",
    "Lainnya",
]

STATUS_PERANGKAT = {
    "aktif": ("Aktif", "success"),
    "standby": ("Standby", "info"),
    "rusak": ("Rusak", "danger"),
    "decommissioned": ("Decommissioned", "secondary"),
}
