import re

from conftest import login_as


def lokasi(client):
    client.post("/aset/ruang/baru", data={"kode": "SR-01", "nama": "Server Room 1", "suhu_min": "18", "suhu_max": "27", "rh_min": "40", "rh_max": "60"})
    client.post("/aset/rak/baru", data={"ruang_id": "1", "kode": "A01", "kapasitas_u": "42"})


def aktivitas(client, **extra):
    data = {"judul": "Instalasi server ERP", "jenis": "Instalasi Perangkat", "rak_id": "1", "mulai_rencana": "2026-10-06T09:00",
            "selesai_rencana": "2026-10-06T12:00", "pic": "Budi", "vendor": "PT Vendor", "risiko": "sedang"}
    data.update(extra)
    return client.post("/aktivitas/baru", data=data)


def test_setup_dan_login(app, anon):
    assert anon.get("/").headers["Location"].endswith("/setup")
    anon.post("/setup", data={"username": "admin", "password": "rahasia123", "konfirmasi": "rahasia123"})
    c = app.test_client()
    assert "/login" in c.get("/aktivitas/").headers["Location"]
    assert c.post("/login", data={"username": "admin", "password": "salah"}).status_code == 401
    assert c.post("/login", data={"username": "admin", "password": "rahasia123"}).status_code == 302
    assert c.get("/").status_code == 200


def test_csrf(tmp_path):
    from dcam import create_app

    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "x.db"), "SECRET_KEY": "x"})
    c = app.test_client()
    assert c.post("/setup", data={"username": "a", "password": "rahasia123", "konfirmasi": "rahasia123"}).status_code == 400


def test_alur_aktivitas(admin, operator):
    lokasi(admin)
    r = aktivitas(operator)
    assert r.status_code == 302
    aid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    html = operator.get(f"/aktivitas/{aid}").get_data(as_text=True)
    assert "WO-" in html and "Diajukan" in html and "SR-01 / A01" in html

    # operator tidak boleh menyetujui
    assert operator.post(f"/aktivitas/{aid}/status", data={"status": "disetujui"}).status_code == 403
    # transisi tidak valid
    admin.post(f"/aktivitas/{aid}/status", data={"status": "selesai"})
    assert "Diajukan" in admin.get(f"/aktivitas/{aid}").get_data(as_text=True)

    admin.post(f"/aktivitas/{aid}/status", data={"status": "disetujui", "catatan": "OK"})
    # setelah disetujui, operator tidak bisa ubah
    r = operator.get(f"/aktivitas/{aid}/edit", follow_redirects=True)
    assert "tidak bisa diubah" in r.get_data(as_text=True)

    operator.post(f"/aktivitas/{aid}/status", data={"status": "berlangsung"})
    operator.post(f"/aktivitas/{aid}/catatan", data={"isi": "Rack mounting selesai"})
    operator.post(f"/aktivitas/{aid}/status", data={"status": "selesai"})
    html = admin.get(f"/aktivitas/{aid}").get_data(as_text=True)
    assert "Selesai" in html and "Rack mounting selesai" in html and "Disetujui → Berlangsung" in html
    assert "Instalasi server ERP" in admin.get(f"/aktivitas/{aid}/cetak").get_data(as_text=True)


def test_validasi_dan_bentrok(admin):
    lokasi(admin)
    r = aktivitas(admin, selesai_rencana="2026-10-06T08:00")
    assert "harus setelah" in r.get_data(as_text=True)
    r = aktivitas(admin, risiko="tinggi")
    assert "rollback" in r.get_data(as_text=True)
    aktivitas(admin)
    r = aktivitas(admin, judul="Cabling", mulai_rencana="2026-10-06T11:00", selesai_rencana="2026-10-06T13:00")
    html = admin.get(r.headers["Location"]).get_data(as_text=True)
    assert "bentrok" in html
    # tolak wajib alasan
    admin.post("/aktivitas/2/status", data={"status": "ditolak"})
    assert "Diajukan" in admin.get("/aktivitas/2").get_data(as_text=True)
    admin.post("/aktivitas/2/status", data={"status": "ditolak", "catatan": "Bentrok"})
    assert "Ditolak" in admin.get("/aktivitas/2").get_data(as_text=True)


def test_kunjungan(admin):
    lokasi(admin)
    r = admin.post("/kunjungan/baru", data={"nama": "Andi", "perusahaan": "PT Vendor", "tujuan": "Instalasi", "ruang_id": "1", "masuk": "2026-10-06T08:00"})
    assert r.status_code == 302
    html = admin.get("/").get_data(as_text=True)
    assert "Andi" in html
    admin.post("/kunjungan/1/keluar", data={"next": "//evil.com"})
    html = admin.get("/kunjungan/?q=Andi").get_data(as_text=True)
    assert "Check-out</button>" not in html
    r = admin.post("/kunjungan/baru", data={"nama": "X", "tujuan": "Y", "masuk": "2026-10-06T08:00", "keluar": "2026-10-06T07:00"})
    assert "tidak boleh sebelum" in r.get_data(as_text=True)


def test_rak_dan_perangkat(admin):
    lokasi(admin)
    r = admin.post("/aset/perangkat/baru", data={"nama": "srv-erp-01", "jenis": "Server", "rak_id": "1", "posisi_u": "10", "tinggi_u": "2", "status": "aktif"})
    assert r.status_code == 302
    r = admin.post("/aset/perangkat/baru", data={"nama": "srv-x", "rak_id": "1", "posisi_u": "11", "tinggi_u": "1", "status": "aktif"})
    assert "bertabrakan" in r.get_data(as_text=True)
    r = admin.post("/aset/perangkat/baru", data={"nama": "srv-y", "rak_id": "1", "posisi_u": "42", "tinggi_u": "2", "status": "aktif"})
    assert "melebihi" in r.get_data(as_text=True)
    html = admin.get("/aset/rak/1").get_data(as_text=True)
    assert 'rowspan="2"' in html and "srv-erp-01" in html and "2/42U" in html
    r = admin.post("/aset/rak/1/edit", data={"ruang_id": "1", "kode": "A01", "kapasitas_u": "5"})
    assert "tidak boleh kurang" in r.get_data(as_text=True)
    # ruang yang masih punya rak tidak bisa dihapus
    r = admin.post("/aset/ruang/1/hapus", follow_redirects=True)
    assert "masih dipakai" in r.get_data(as_text=True)
    # aktivitas dari perangkat otomatis isi rak/ruang
    aktivitas(admin, rak_id="", perangkat_id="1")
    assert "SR-01 / A01" in admin.get("/aktivitas/1").get_data(as_text=True)


def test_patroli_temuan(admin):
    lokasi(admin)
    r = admin.post("/patroli/baru", data={"ruang_id": "1", "waktu": "2026-10-06T08:00", "suhu": "29.5", "kelembaban": "55", "ups": "gangguan"}, follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Suhu 29.5°C &gt; batas 27°C" in html and "UPS: gangguan" in html
    html = admin.get("/").get_data(as_text=True)
    assert "2 temuan" in html
    r = admin.post("/patroli/baru", data={"ruang_id": "1", "waktu": "2026-10-06T10:00", "suhu": "22", "kelembaban": "50"}, follow_redirects=True)
    assert "semua kondisi normal" in r.get_data(as_text=True)
    assert "Normal" in admin.get("/").get_data(as_text=True)


def test_insiden(admin):
    r = admin.post("/insiden/baru", data={"judul": "CRAC 2 mati", "kategori": "Pendingin", "severity": "kritis", "waktu_kejadian": "2026-10-06T07:00", "status": "terbuka"})
    assert r.status_code == 302
    assert "CRAC 2 mati" in admin.get("/").get_data(as_text=True)
    r = admin.post("/insiden/1/edit", data={"judul": "CRAC 2 mati", "kategori": "Pendingin", "severity": "kritis", "waktu_kejadian": "2026-10-06T07:00", "status": "selesai"})
    assert "Isi penanganan" in r.get_data(as_text=True)
    admin.post("/insiden/1/edit", data={"judul": "CRAC 2 mati", "kategori": "Pendingin", "severity": "kritis", "waktu_kejadian": "2026-10-06T07:00", "status": "selesai", "penanganan": "Ganti kompresor"})
    html = admin.get("/insiden/1").get_data(as_text=True)
    assert "INC-" in html and "Selesai" in html
    assert "Tidak ada insiden terbuka" in admin.get("/").get_data(as_text=True)


def test_laporan_dan_csv(admin):
    lokasi(admin)
    aktivitas(admin, judul="=HYPERLINK(1)")
    html = admin.get("/laporan/?dari=2026-10-01&sampai=2026-10-31").get_data(as_text=True)
    assert "Instalasi Perangkat" in html
    r = admin.get("/laporan/aktivitas.csv?dari=2026-10-01&sampai=2026-10-31")
    body = r.get_data(as_text=True)
    assert r.mimetype == "text/csv" and "nomor;judul" in body and "'=HYPERLINK(1)" in body
    assert admin.get("/laporan/xxx.csv").status_code == 404


def test_peran(admin, operator, viewer):
    lokasi(admin)
    aktivitas(admin)
    assert viewer.get("/aktivitas/1").status_code == 200
    assert aktivitas(viewer).status_code == 403
    assert viewer.post("/akun/password", data={"password_lama": "x"}).status_code == 200
    assert operator.get("/pengguna").status_code == 403
    assert operator.post("/aktivitas/1/hapus").status_code == 403
    assert admin.post("/aktivitas/1/hapus").status_code == 302
    assert admin.get("/audit").status_code == 200


def test_pengguna_nonaktif(app, admin):
    c = login_as(app, admin, "op2", "operator")
    uid = int(re.search(r"/pengguna/(\d+)/edit", admin.get("/pengguna").get_data(as_text=True).split("op2")[1]).group(1))
    admin.post(f"/pengguna/{uid}/edit", data={"nama": "", "peran": "operator"})
    assert "/login" in c.get("/").headers["Location"]
    r = admin.post("/pengguna/1/edit", data={"peran": "viewer", "aktif": "1"})
    assert "akun sendiri" in r.get_data(as_text=True)


def test_halaman_render(admin):
    lokasi(admin)
    for url in ["/", "/aktivitas/", "/aktivitas/baru", "/kunjungan/", "/kunjungan/baru", "/patroli/", "/patroli/baru",
                "/insiden/", "/insiden/baru", "/aset/", "/aset/ruang/1", "/aset/rak/1", "/aset/perangkat",
                "/aset/perangkat/baru", "/laporan/", "/pengguna", "/akun/password", "/audit"]:
        assert admin.get(url).status_code == 200, url
    assert admin.get("/aset/rak/99").status_code == 404
