"""
core/detector.py
================
YOLO: mendeteksi lokasi kode pada foto, memotong (crop) areanya, dan memperkecil foto yang terlalu besar.

Pengaturan yang sama dengan pengujian 50 foto: IoU 0,7 (bawaan ultralytics), gambar diperkecil ke sisi terpanjang
1600 px sebelum diproses, dan crop = gabungan SEMUA kotak yang terdeteksi + padding 8 px.

Model YOLO dimuat SEKALI per berkas model (lazy singleton).
"""

import os

import cv2

PADDING_GABUNGAN = 8      # piksel di tiap sisi crop, supaya huruf yang mepet tidak terpotong
YOLO_IOU = 0.7            # NMS IoU; sama dengan bawaan ultralytics yang dipakai saat uji
YOLO_IMGSZ = 640

_models = {}  # {path_model: objek YOLO}


class ModelTidakDitemukan(FileNotFoundError):
    """Berkas model YOLO tidak ada di lokasi yang diharapkan."""


def get_yolo_model(path_model: str):
    """Mengembalikan objek YOLO untuk `path_model`, dimuat hanya sekali."""
    if path_model not in _models:
        if not os.path.isfile(path_model):
            raise ModelTidakDitemukan(
                f"Model YOLO tidak ditemukan: {path_model}. Letakkan berkas best_lokasi_new.pt di folder models_ai/."
            )
        from ultralytics import YOLO

        _models[path_model] = YOLO(path_model)
    return _models[path_model]


def perkecil_bila_besar(frame, maks_dimensi: int = 1600):
    """
    Memperkecil frame bila sisi terpanjangnya melebihi `maks_dimensi` (rasio aspek terjaga).
    Frame yang sudah kecil (mis. dari kamera) tidak diubah. Sama dengan kondisi pengujian.
    """
    h, w = frame.shape[:2]
    sisi_terpanjang = max(h, w)
    if sisi_terpanjang <= maks_dimensi:
        return frame
    skala = maks_dimensi / sisi_terpanjang
    return cv2.resize(frame, (int(w * skala), int(h * skala)), interpolation=cv2.INTER_AREA)


def detect_semua(frame, path_model: str, conf_threshold: float = 0.4, iou_threshold: float = YOLO_IOU,
                 imgsz: int = YOLO_IMGSZ):
    """
    Menjalankan deteksi YOLO pada satu frame; mengembalikan SEMUA kotak yang lolos ambang confidence,
    diurutkan dari confidence tertinggi.

    Returns:
        list[dict]: [{"bbox": (x1, y1, x2, y2), "confidence": float}, ...]; kosong bila tidak ada objek.
    """
    model = get_yolo_model(path_model)
    hasil = model.predict(frame, conf=conf_threshold, iou=iou_threshold, imgsz=imgsz, verbose=False)
    deteksi = []
    for box in hasil[0].boxes:
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        deteksi.append({"bbox": (x1, y1, x2, y2), "confidence": float(box.conf[0].item())})
    deteksi.sort(key=lambda d: d["confidence"], reverse=True)
    return deteksi


def crop_gabungan(frame, deteksi: list, padding: int = PADDING_GABUNGAN):
    """
    Memotong GABUNGAN (union) dari seluruh kotak yang terdeteksi, bukan hanya kotak terbaik: pada objek
    melengkung, teks yang satu kesatuan bisa terpecah jadi beberapa kotak oleh YOLO.

    Returns:
        tuple: (crop | None, bbox_gabungan | None)
    """
    if not deteksi:
        return None, None

    h, w = frame.shape[:2]
    x1 = max(0, min(d["bbox"][0] for d in deteksi) - padding)
    y1 = max(0, min(d["bbox"][1] for d in deteksi) - padding)
    x2 = min(w, max(d["bbox"][2] for d in deteksi) + padding)
    y2 = min(h, max(d["bbox"][3] for d in deteksi) + padding)

    crop = frame[y1:y2, x1:x2]
    if crop.size == 0:
        return None, (x1, y1, x2, y2)
    return crop, (x1, y1, x2, y2)


def gambar_kotak_deteksi(frame, deteksi: list):
    """
    Menggambar kotak hasil YOLO di atas frame (untuk halaman Monitoring dan Detail Scan). Kotak pertama
    (confidence tertinggi) oranye tebal, sisanya abu-abu tipis. Murni visualisasi.
    """
    vis = frame.copy()
    for i, d in enumerate(deteksi):
        x1, y1, x2, y2 = d["bbox"]
        warna = (255, 140, 0) if i == 0 else (160, 160, 160)
        tebal = 3 if i == 0 else 1
        cv2.rectangle(vis, (x1, y1), (x2, y2), warna, tebal)
        label = f"text_area {d['confidence']:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(vis, (x1, max(0, y1 - th - 8)), (x1 + tw + 4, y1), warna, -1)
        cv2.putText(vis, label, (x1 + 2, max(12, y1 - 4)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return vis
