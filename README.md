# Monitoring Pasien

Aplikasi web sederhana (Flask + SQLite) untuk:

- **Data pasien** – No. RM, nama, tanggal lahir, jenis kelamin, catatan (diagnosis/alergi).
- **Pengukuran** – tekanan darah (sistolik/diastolik, nadi) dan gula darah (sewaktu / puasa / 2 jam PP), lengkap dengan kategori otomatis (Normal, Hipertensi, Prediabetes, dll.) dan grafik tren.
- **Daftar obat** – nama obat, dosis + satuan, rute, frekuensi/aturan pakai, periode pemberian.
- **Jadwal pemberian obat** – buat jadwal otomatis berdasarkan rentang tanggal dan jam (mis. `08:00, 20:00`), lalu tandai *Diberikan* / *Dilewati*. Jadwal yang lewat waktu ditandai *Terlambat*.
- **Dashboard** – jadwal obat semua pasien per tanggal dan pengukuran terbaru.
- **Login** – semua halaman wajib login (username/password, password di-hash). Kelola pengguna & ganti password lewat menu akun.

## Menjalankan

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python app.py            # http://localhost:5000
```

Database SQLite dibuat otomatis di `instance/pasien.db`. Atur `PORT` lewat environment variable bila perlu.

## Login

- Saat pertama dibuka (belum ada pengguna), aplikasi menampilkan halaman **Buat Akun Admin**.
- Pengguna lain ditambahkan lewat menu akun → **Kelola Pengguna**.
- Lupa password / buat pengguna dari terminal:

  ```bash
  flask --app app set-password <username>
  ```

- `SECRET_KEY` dibuat acak otomatis dan disimpan di `instance/secret_key` (atau set lewat env `SECRET_KEY`). Jika dijalankan di belakang HTTPS, set `SESSION_COOKIE_SECURE=1`.

## Tes

```bash
python -m pytest -q
```

> Kategori tensi (AHA/ACC 2017) dan gula darah (ADA/PERKENI) hanya sebagai acuan; keputusan klinis tetap oleh tenaga kesehatan.

## Aplikasi lain di repo ini

- [`datacenter/`](datacenter/README.md) – **Datacenter Activity Management** (work order, kunjungan, patroli suhu/kelembaban, insiden, aset rak, laporan). Berjalan terpisah di port 5001.
