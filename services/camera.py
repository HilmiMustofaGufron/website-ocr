"""
services/camera.py
==================
Koneksi video ke kamera (HP via DroidCam/USB, atau webcam USB). Generik: DroidCam maupun webcam asli sama-sama
muncul sebagai perangkat video biasa, jadi cv2.VideoCapture() membaca keduanya dengan kode yang sama. `source`
juga bisa berupa URL (mis. RTSP) atau berkas video (berguna untuk pengujian).

Pembacaan frame dijalankan di THREAD TERPISAH karena cv2.VideoCapture.read() bersifat blocking. Thread itu terus
menyimpan frame terbaru ke variabel bersama (dilindungi lock), dan route cukup memanggil get_latest_frame().

Bila koneksi terputus saat membaca frame, callback `on_terputus` (bila diberikan) dipanggil SEKALI dari thread itu.
"""

import threading
import time

import cv2

_capture = None
_thread_baca = None
_frame_terbaru = None
_lock = threading.Lock()
_berhenti = threading.Event()
_status = {"aktif": False, "sumber": None, "fps": 0.0, "pesan_error": None}


def start_stream(source=0, on_terputus=None, loop_berkas: bool = False) -> bool:
    """
    Membuka kamera dan mulai membaca frame di thread terpisah.

    Args:
        source: int (indeks perangkat), URL (str), atau path berkas video.
        on_terputus: callable tanpa argumen, dipanggil sekali bila koneksi terputus.
        loop_berkas: bila source berkas video, ulang dari awal saat habis (untuk pengujian).
    Returns:
        bool: True bila kamera berhasil dibuka.
    """
    global _capture, _thread_baca

    if _status["aktif"] or _capture is not None:
        stop_stream()   # hentikan koneksi lama dulu

    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        cap.release()
        _status.update({"aktif": False, "sumber": source, "fps": 0.0,
                        "pesan_error": f"Tidak bisa membuka kamera source={source}"})
        return False

    _capture = cap
    _berhenti.clear()
    _status.update({"aktif": True, "sumber": source, "fps": 0.0, "pesan_error": None})
    _thread_baca = threading.Thread(target=_loop_baca_frame, args=(cap, on_terputus, loop_berkas), daemon=True)
    _thread_baca.start()
    return True


def stop_stream() -> None:
    """Menghentikan thread pembaca dan melepas kamera."""
    global _capture, _frame_terbaru, _thread_baca

    _berhenti.set()
    if _thread_baca is not None:
        _thread_baca.join(timeout=3.0)
        _thread_baca = None
    if _capture is not None:
        _capture.release()
        _capture = None
    with _lock:
        _frame_terbaru = None
    _status.update({"aktif": False, "fps": 0.0})


def _loop_baca_frame(cap, on_terputus, loop_berkas) -> None:
    global _frame_terbaru
    jumlah, waktu_mulai = 0, time.time()
    while not _berhenti.is_set():
        ok, frame = cap.read()
        if not ok and loop_berkas:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
        if not ok:
            if not _berhenti.is_set():   # terputus sendiri, bukan karena dihentikan operator
                _status.update({"aktif": False, "pesan_error": "Koneksi kamera terputus saat membaca frame."})
                if on_terputus is not None:
                    try:
                        on_terputus()
                    except Exception:
                        pass
            break
        with _lock:
            _frame_terbaru = frame
        jumlah += 1
        selisih = time.time() - waktu_mulai
        if selisih >= 1.0:
            _status["fps"] = round(jumlah / selisih, 1)
            jumlah, waktu_mulai = 0, time.time()
        time.sleep(0.005)   # beri kesempatan thread lain (khususnya untuk berkas video yang dibaca sangat cepat)


def get_latest_frame():
    """SALINAN frame terbaru, atau None bila kamera belum aktif / belum ada frame."""
    with _lock:
        return None if _frame_terbaru is None else _frame_terbaru.copy()


def get_camera_status() -> dict:
    return dict(_status)
