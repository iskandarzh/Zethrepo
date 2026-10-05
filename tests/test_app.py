import pytest

from app import create_app, kategori_gula, kategori_tensi


@pytest.fixture
def client(tmp_path):
    app = create_app({"TESTING": True, "DATABASE": str(tmp_path / "test.db")})
    return app.test_client()


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
