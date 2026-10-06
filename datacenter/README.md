# Datacenter Activity Management

Aplikasi web (Flask + SQLite) untuk mengelola aktivitas operasional data center:

- **Dashboard** – aktivitas hari ini, pengajuan yang menunggu persetujuan, tamu yang masih di dalam DC, kondisi tiap ruang dari patroli terakhir, insiden terbuka, dan jadwal 7 hari ke depan.
- **Aktivitas / Work Order** – instalasi, maintenance, decommission, troubleshooting, cabling, dll. Lokasi (ruang / rak / perangkat), jadwal, PIC, vendor, tingkat risiko, dampak layanan, rencana rollback (wajib untuk risiko tinggi).
  Alur status: *Diajukan → Disetujui / Ditolak → Berlangsung → Selesai* (atau *Batal*). Persetujuan hanya oleh admin. Timeline catatan progres, peringatan **jadwal bentrok** di rak/ruang yang sama, dan **Formulir Izin Kerja** siap cetak.
- **Kunjungan / Akses** – buku tamu check-in / check-out (identitas, perusahaan, area, pendamping, kartu akses), bisa dikaitkan ke aktivitas.
- **Patroli & Monitoring** – catat suhu, kelembaban, kondisi UPS, genset, pendingin, pemadam kebakaran, keamanan, kebersihan. Pembacaan di luar batas ruang / kondisi gangguan otomatis ditandai dan bisa langsung dibuat insiden.
- **Insiden** – kategori, severity, ruang & perangkat terdampak, penanganan / root cause, durasi.
- **Aset** – ruang (dengan batas suhu & kelembaban), rak dengan **elevasi rak** & pemakaian U, perangkat (merek, model, serial, posisi U, IP management) beserta riwayat aktivitas & insidennya.
- **Laporan** – ringkasan per periode dan export CSV (aktivitas, kunjungan, patroli, insiden; pemisah `;` agar langsung terbuka di Excel lokal Indonesia).
- **Pengguna & peran** – *Admin* (semua akses, persetujuan, hapus data, kelola pengguna, log audit), *Operator* (mencatat & memproses), *Viewer* (hanya lihat). Semua perubahan tercatat di **Log Audit**.

## Menjalankan

```bash
cd datacenter
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py            # http://localhost:5001
```

- Database SQLite dibuat otomatis di `datacenter/instance/datacenter.db`.
- Environment variable opsional: `PORT` (default 5001), `HOST` (default 0.0.0.0), `NAMA_DC` (nama yang tampil di header, mis. `NAMA_DC="DC Jakarta"`), `SECRET_KEY`, `SESSION_COOKIE_SECURE=1` bila di belakang HTTPS.

## Login

- Saat pertama dibuka, aplikasi menampilkan halaman **Buat Akun Admin**.
- Pengguna lain ditambahkan lewat menu akun → **Kelola Pengguna**.
- Lupa password / buat admin dari terminal:

  ```bash
  cd datacenter
  flask --app run set-password <username>
  ```

## Tes

```bash
cd datacenter
python -m pytest -q
```
