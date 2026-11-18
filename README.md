# Gudang Scanner (versi baru)

Sistem pencatatan otomatis kode produk brake shoe: kamera atau foto, YOLOv8 menemukan lokasi kode, PaddleOCR membaca,
hasilnya dicocokkan ke Master Kode lalu dicatat. Aplikasi web Flask yang ditulis ulang dari nol dengan **mode cepat**
(satu kali baca, tanpa jalur cadangan).

## Menjalankan (Windows)

1. **Letakkan model YOLO** di folder `models_ai/` dengan nama `best_lokasi_new.pt` (berkas yang sama dengan proyek lama).
2. **Jalankan.** Pilih salah satu:
   - *Memakai lingkungan Python proyek lama* (paling cepat, tidak perlu memasang ulang PaddleOCR):
     `jalankan.bat "E:\TUGAS AKHIR PKL\warehouse_scanner\venv\Scripts\python.exe"`
   - *Lingkungan baru:* jalankan `siapkan.bat` sekali (butuh internet, memakan waktu), lalu `jalankan.bat`.
3. **Buka** http://127.0.0.1:5000 dan masuk. Saat pertama kali dijalankan, akun awal dibuat dengan password acak yang
   **dicetak sekali di terminal** dan disimpan di `instance/kredensial_awal.txt`. Ganti di halaman Settings, lalu hapus berkas itu.

Cek kesiapan komputer kapan saja: `python periksa_lingkungan.py`.

## Pertama kali dipakai
1. Buka **Master Kode** dan isi daftar kode valid (atau impor dari Excel dengan kolom `kode` dan `keterangan`).
   Tanpa daftar kode, semua hasil pindai ditolak (Dashboard memberi peringatan).
2. Buka **Monitoring**, panel **Uji dengan foto**: unggah satu foto untuk mencoba tanpa kamera.
3. Untuk kamera: isi indeks perangkat (0, 1, 2, dst. untuk webcam atau DroidCam USB), atau URL, lalu **Mulai kamera**.

## Memakai data lama (opsional)
Salin `instance/warehouse.db` dari proyek lama ke `instance/` di sini (aplikasi sedang mati). Yang terbawa: Master Kode,
riwayat, pengaturan, dan **akun lama (kata sandi tetap berlaku)**. Salin juga `static/uploads/` agar gambar riwayat tampil.
Catatan: `threshold_yolo` dari proyek lama (0,5) ikut terbawa; nilai yang diuji adalah 0,4, ubah di Settings bila ingin sama.

## Cara kerja pembaca (mode cepat)
YOLO memotong area kode, crop tegak diputar 90 derajat berlawanan arah jarum jam, satu preprocessing terbaik (menurut
penilaian kualitas gambar) dipakai, PaddleOCR membaca **satu kali**, lalu bacaan dikoreksi ke Master Kode (jarak edit
berbobot, batas 2,0). Bacaan yang tidak cocok ditandai **perlu verifikasi manual** dan TIDAK dicatat sebagai kode.

**Hasil pengujian** (50 foto berkunci jawaban, satu model lokasi, foto yang sama untuk semua alur):

| | Mode cepat |
|---|---|
| Benar | 28 dari 50 (56%) |
| Diterima tetapi salah | 1 |
| Ditolak (verifikasi manual) | 21 |
| Waktu rata-rata per foto | sekitar 5 detik (CPU Colab; di laptop bisa lebih lambat) |

**Keterbatasan yang diketahui, mohon dibaca:**
- Kode dengan **huruf bertumpuk vertikal** (AKL642, AKL609EEA, AKL608IEE) hampir tidak terbaca: 0 dari 20 pada mode ini.
  Semuanya ditolak ke verifikasi manual, tidak ada yang salah dicatat.
- Satu kesalahan terima: `AKL636EE` adalah awalan dari `AKL636EEA`, sehingga bacaan yang kehilangan huruf terakhir pada
  AKL636EEA dapat diterima sebagai AKL636EE.
- Hasil di atas dihitung pada foto, dengan keputusan sudut (putar 90 derajat) yang diambil dari foto yang sama (hasil
  cenderung sedikit optimis untuk foto baru). **Kamera langsung belum diuji dengan model asli.**
- Waktu ~5 detik per scan belum "instan"; mengganti ke model PaddleOCR yang lebih ringan atau memakai GPU belum diuji.

## Pengaturan
Semua opsional (lihat `.env.example`): `ADMIN_USERNAME`, `ADMIN_PASSWORD`, `HOST`, `PORT`, `MODEL_YOLO_PATH`,
`AMBANG_TERIMA_JARAK` (2,0), `MAX_DIMENSI_PROSES` (1600). Salin `.env.example` menjadi `.env` untuk mengubahnya.
Pengaturan operator (threshold YOLO, auto scan, interval, kamera) ada di halaman **Settings**.

## Struktur
```
app.py              pabrik aplikasi Flask (jalankan: python app.py)
config.py           konfigurasi
core/               inti pembaca kode: murni algoritma, tanpa Flask  (preprocessing.py dan orientation.py berasal dari uji)
services/           database, login, notifikasi, kamera, mesin status scan, alur pindai, ekspor
blueprints/         route: auth, dashboard, monitoring, camera, scan, history, master_kode, settings, export, notifications
templates/ static/  tampilan (Bootstrap dan font disertakan lokal: berjalan tanpa internet)
database/           skema SQLite
tests/              160 uji otomatis
buat_pengguna.py    buat pengguna / atur ulang password
periksa_lingkungan.py  cek kesiapan komputer
```

## Uji otomatis
`python -m unittest discover -s tests` (sekitar 1 menit). Uji memakai YOLO dan PaddleOCR **tiruan**, jadi membuktikan logika
aplikasi, bukan kualitas model. Lulus di OpenCV 4.10 dan 4.13.

## Bila ada masalah
| Gejala | Penyebab dan jalan keluar |
|---|---|
| Dashboard: "Model YOLO belum ada" | Letakkan `best_lokasi_new.pt` di `models_ai/`, jalankan ulang aplikasi |
| Pindai gagal, log menyebut `ConvertPirAttribute2RuntimeAttribute` | paddlepaddle >= 3.3.0; pasang `paddlepaddle==3.2.0` dan `paddleocr==3.3.0` |
| Lupa password | `python buat_pengguna.py <username>` (mengatur ulang password) |
| "Terlalu banyak percobaan gagal" | Tunggu 5 menit, atau jalankan ulang aplikasi (kunci disimpan di memori) |
| Kamera tidak terbuka | Coba indeks 0, 1, 2; pastikan aplikasi kamera lain tidak sedang memakainya |
| Port 5000 dipakai | Isi `PORT=5001` di `.env` |
| Rincian kegagalan | `logs/app.log` |

## Keamanan
Wajib login, kata sandi disimpan sebagai hash, perlindungan CSRF, akun dikunci 5 menit setelah 5 kali salah, dan header
keamanan dasar. Server bawaan Flask cukup untuk jaringan lokal gudang; **jangan dibuka langsung ke internet**.
Mode debug sengaja mati (debugger yang terbuka di jaringan berbahaya).

Aset pihak ketiga: Bootstrap (MIT) dan font Inter, JetBrains Mono, Space Grotesk (SIL OFL), lihat `static/vendor/LICENSES.txt`.
