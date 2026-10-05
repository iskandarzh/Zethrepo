import pytest

from app import create_app, kategori_gula, kategori_tensi


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "CSRF_ENABLED": False, "DATABASE": str(tmp_path / "test.db")})


@pytest.fixture
def anon(app):
    return app.test_client()


@pytest.fixture
def client(app):
    c = app.test_client()
    r = c.post("/setup", data={"username": "admin", "password": "rahasia123", "konfirmasi": "rahasia123"})
    assert r.status_code == 302
    return c


def test_kategori():
    assert kategori_tensi(115, 75)[0] == "Normal"
    assert kategori_tensi(125, 75)[0] == "Meningkat"
    assert kategori_tensi(135, 85)[0] == "Hipertensi Tahap 1"
    assert kategori_tensi(150, 95)[0] == "Hipertensi Tahap 2"
    assert kategori_tensi(190, 100)[0] == "Krisis Hipertensi"
    assert kategori_gula(90, "puasa")[0] == "Normal"
    assert kategori_gula(110, "puasa")[0] == "Prediabetes"
    assert kategori_gula(130, "puasa")[0] == "Diabetes"
    assert kategori_gula(130, "sewaktu")[0] == "Normal"
    assert kategori_gula(250, "sewaktu")[0] == "Diabetes"
    assert kategori_gula(60, "sewaktu")[0] == "Hipoglikemia"


def test_alur_lengkap(client):
    r = client.post("/pasien/baru", data={"nama": "Budi Santoso", "no_rm": "RM001", "jenis_kelamin": "L"})
    assert r.status_code == 302
    pid = int(r.headers["Location"].rstrip("/").split("/")[-1])

    r = client.post(f"/pasien/{pid}/pengukuran/baru", data={
        "waktu": "2026-10-05T08:00", "sistolik": "150", "diastolik": "95", "nadi": "88",
        "gula_darah": "180", "jenis_gula": "sewaktu",
    })
    assert r.status_code == 302

    r = client.post(f"/pasien/{pid}/obat/baru", data={
        "nama": "Amlodipine", "dosis": "5", "satuan": "mg", "rute": "Oral", "frekuensi": "1x sehari",
        "tanggal_mulai": "2026-10-05", "tanggal_selesai": "2026-10-07",
    })
    assert r.status_code == 302
    oid = int(r.headers["Location"].split("/")[-3])

    r = client.post(f"/obat/{oid}/jadwal/baru", data={
        "tanggal_mulai": "2026-10-05", "tanggal_selesai": "2026-10-07", "jam": "08:00, 20:00",
    }, follow_redirects=True)
    assert "6 jadwal pemberian Amlodipine dibuat" in r.get_data(as_text=True)

    # duplicate generation is skipped
    r = client.post(f"/obat/{oid}/jadwal/baru", data={
        "tanggal_mulai": "2026-10-05", "tanggal_selesai": "2026-10-05", "jam": "08:00",
    }, follow_redirects=True)
    assert "0 jadwal pemberian" in r.get_data(as_text=True)

    html = client.get(f"/pasien/{pid}").get_data(as_text=True)
    assert "150/95" in html and "Hipertensi Tahap 2" in html
    assert "Amlodipine" in html and "5 mg" in html

    r = client.post("/jadwal/1/status", data={"status": "diberikan", "next": "//evil.com"})
    assert r.headers["Location"].startswith("/pasien/")
    html = client.get("/?tanggal=2026-10-05").get_data(as_text=True)
    assert "Budi Santoso" in html and "Diberikan" in html


def test_validasi(client):
    client.post("/pasien/baru", data={"nama": "Ani"})
    r = client.post("/pasien/1/pengukuran/baru", data={"waktu": "2026-10-05T08:00"})
    assert "Isi minimal tensi atau gula darah" in r.get_data(as_text=True)
    r = client.post("/pasien/1/pengukuran/baru", data={"waktu": "2026-10-05T08:00", "sistolik": "120"})
    assert "Isi sistolik dan diastolik sekaligus" in r.get_data(as_text=True)
    r = client.post("/pasien/baru", data={"nama": ""})
    assert "Nama pasien wajib diisi" in r.get_data(as_text=True)


def test_edit_pasien_nama_kosong(client):
    client.post("/pasien/baru", data={"nama": "Ani"})
    r = client.post("/pasien/1/edit", data={"nama": "   "})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "Nama pasien wajib diisi" in html and 'href="/pasien/1"' in html


def test_obat_tanggal_terbalik_saat_tambah(client):
    client.post("/pasien/baru", data={"nama": "Ani"})
    r = client.post("/pasien/1/obat/baru", data={
        "nama": "Metformin", "dosis": "500", "tanggal_mulai": "2026-10-10", "tanggal_selesai": "2026-10-05",
    })
    assert "Tanggal selesai tidak boleh sebelum tanggal mulai" in r.get_data(as_text=True)


def test_setup_lalu_login(anon):
    assert anon.get("/").headers["Location"].endswith("/setup")
    r = anon.post("/setup", data={"username": "admin", "password": "pendek", "konfirmasi": "pendek"})
    assert "Password minimal 8 karakter" in r.get_data(as_text=True)
    anon.post("/setup", data={"username": "admin", "password": "rahasia123", "konfirmasi": "rahasia123"})
    assert anon.get("/").status_code == 200
    anon.post("/logout")
    assert "/login" in anon.get("/pasien").headers["Location"]
    # setup is closed once a user exists
    assert anon.get("/setup").headers["Location"].endswith("/login")
    r = anon.post("/login", data={"username": "admin", "password": "salah"})
    assert r.status_code == 401
    r = anon.post("/login?next=/pasien", data={"username": "ADMIN", "password": "rahasia123"})
    assert r.headers["Location"] == "/pasien"


def test_kelola_pengguna_dan_ganti_password(client, app):
    client.post("/pengguna", data={"username": "perawat", "password": "perawat123", "konfirmasi": "perawat123"})
    r = client.post("/pengguna", data={"username": "perawat", "password": "perawat123", "konfirmasi": "perawat123"})
    assert "sudah dipakai" in r.get_data(as_text=True)
    r = client.post("/akun/password", data={"password_lama": "salah", "password": "baru12345", "konfirmasi": "baru12345"})
    assert "Password lama salah" in r.get_data(as_text=True)
    client.post("/akun/password", data={"password_lama": "rahasia123", "password": "baru12345", "konfirmasi": "baru12345"})
    client.post("/logout")
    other = app.test_client()
    assert other.post("/login", data={"username": "admin", "password": "baru12345"}).status_code == 302
    r = other.post("/pengguna/1/hapus", follow_redirects=True)
    assert "Tidak bisa menghapus akun sendiri" in r.get_data(as_text=True)


def test_csrf(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "csrf.db")})
    c = app.test_client()
    assert c.post("/setup", data={"username": "a", "password": "rahasia123", "konfirmasi": "rahasia123"}).status_code == 400
    html = c.get("/setup").get_data(as_text=True)
    token = html.split('name="csrf_token" value="')[1].split('"')[0]
    r = c.post("/setup", data={"csrf_token": token, "username": "a", "password": "rahasia123", "konfirmasi": "rahasia123"})
    assert r.status_code == 302


def test_cli_set_password(app):
    runner = app.test_cli_runner()
    r = runner.invoke(args=["set-password", "admin"], input="rahasia123\nrahasia123\n")
    assert "dibuat" in r.output
    c = app.test_client()
    assert c.post("/login", data={"username": "admin", "password": "rahasia123"}).status_code == 302
