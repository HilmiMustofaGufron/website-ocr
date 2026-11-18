"""
core/
=====
Inti pembaca kode: murni algoritma (gambar masuk, kode keluar), TIDAK bergantung pada Flask atau database.
Dengan begitu bagian ini bisa diuji sendiri, dan hasilnya sama persis dengan pengujian di notebook.

  preprocessing.py  9 teknik pengolahan gambar + penilaian kualitas (IQA)   (disalin persis dari uji)
  orientation.py    deskew, putar gambar                                    (disalin persis dari uji)
  ocr.py            PaddleOCR (satu objek, dimuat sekali) dan penyaringan karakter
  validation.py     koreksi bacaan ke daftar kode valid (jarak edit berbobot)
  reader.py         mode cepat: putar 90 derajat, SATU kali baca, tanpa jalur cadangan
  detector.py       YOLO: deteksi lokasi kode, crop, pengecilan gambar
"""
