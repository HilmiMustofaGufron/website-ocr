# -*- coding: utf-8 -*-
"""
periksa_lingkungan.py -- memeriksa apakah komputer ini siap menjalankan aplikasi. Hanya membaca, tidak mengubah apa pun.

    python periksa_lingkungan.py

Menampilkan versi pustaka penting, keberadaan model YOLO, dan apakah folder data bisa ditulisi.
"""

import importlib
import os
import sys
import warnings

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE)

DIHARAPKAN = {
    "flask": "3.0", "cv2": "4.10", "numpy": "2.", "ultralytics": "8.3", "paddle": "3.2", "paddleocr": "3.3",
    "pandas": "2.2", "openpyxl": "3.1", "reportlab": "4.2",
}
masalah = 0

print(f"Python {sys.version.split()[0]}")
for nama, awalan in DIHARAPKAN.items():
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            modul = importlib.import_module(nama)
            versi = getattr(modul, "__version__", "?")
        catatan = "" if str(versi).startswith(awalan) else f"   <- diharapkan {awalan}.x (boleh beda, tetapi hasil uji berlaku untuk versi ini)"
        print(f"  [ada    ] {nama:12s} {versi}{catatan}")
    except Exception as exc:
        masalah += 1
        print(f"  [TIDAK ADA] {nama:12s} {type(exc).__name__}: pasang dengan  pip install -r requirements.txt")

model = os.environ.get("MODEL_YOLO_PATH", os.path.join(BASE, "models_ai", "best_lokasi_new.pt"))
if os.path.isfile(model):
    print(f"  [ada    ] model YOLO  {model} ({os.path.getsize(model) / 1e6:.1f} MB)")
else:
    masalah += 1
    print(f"  [TIDAK ADA] model YOLO  {model}  (letakkan best_lokasi_new.pt di folder models_ai/)")

for folder in ("instance", "logs", os.path.join("static", "uploads"), os.path.join("static", "exports")):
    p = os.path.join(BASE, folder)
    os.makedirs(p, exist_ok=True)
    uji = os.path.join(p, ".uji_tulis")
    try:
        open(uji, "w").close()
        os.remove(uji)
        print(f"  [bisa ditulis] {folder}")
    except OSError as exc:
        masalah += 1
        print(f"  [TIDAK BISA DITULIS] {folder}: {exc}")

print()
print("HASIL:", "siap dijalankan." if masalah == 0 else f"ada {masalah} hal yang perlu diperbaiki (lihat baris bertanda TIDAK).")
sys.exit(1 if masalah else 0)
