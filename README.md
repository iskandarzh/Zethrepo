# Monitoring Pasien

Aplikasi web sederhana (Flask + SQLite) untuk:

- **Data pasien** – No. RM, nama, tanggal lahir, jenis kelamin, catatan (diagnosis/alergi).
- **Pengukuran** – tekanan darah (sistolik/diastolik, nadi) dan gula darah (sewaktu / puasa / 2 jam PP), lengkap dengan kategori otomatis (Normal, Hipertensi, Prediabetes, dll.) dan grafik tren.
- **Daftar obat** – nama obat, dosis + satuan, rute, frekuensi/aturan pakai, periode pemberian.
- **Jadwal pemberian obat** – buat jadwal otomatis berdasarkan rentang tanggal dan jam (mis. `08:00, 20:00`), lalu tandai *Diberikan* / *Dilewati*. Jadwal yang lewat waktu ditandai *Terlambat*.
- **Dashboard** – jadwal obat semua pasien per tanggal dan pengukuran terbaru.

## Menjalankan

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py            # http://localhost:5000
```

Database SQLite dibuat otomatis di `instance/pasien.db`. Atur `SECRET_KEY` dan `PORT` lewat environment variable bila perlu.

## Tes

```bash
python -m pytest -q
```

> Kategori tensi (AHA/ACC 2017) dan gula darah (ADA/PERKENI) hanya sebagai acuan; keputusan klinis tetap oleh tenaga kesehatan.
