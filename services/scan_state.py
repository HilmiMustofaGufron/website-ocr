"""
services/scan_state.py
======================
Mesin status untuk mode pindai otomatis (kamera langsung). Menjawab dua masalah nyata:
1. Satu objek jangan di-scan berkali-kali saat masih diam di bawah kamera.
2. Objek yang baru masuk frame jangan langsung di-scan sebelum stabil.

IDLE -> OBJECT_DETECTED -> SCANNING -> SUDAH_DISCAN -> (objek diangkat) -> IDLE

YOLO saja (murah) dipakai untuk mendeteksi ada/tidaknya objek. Pembacaan kode (mahal) dipanggil SEKALI saat
objek sudah stabil. Setelah itu tidak ada scan baru sampai objek diangkat (YOLO tidak mendeteksi apa pun selama
beberapa frame berturut-turut).
"""

import threading

IDLE = "IDLE"
OBJECT_DETECTED = "OBJECT_DETECTED"
SCANNING = "SCANNING"
SUDAH_DISCAN = "SUDAH_DISCAN"


class ScanStateMachine:
    def __init__(self, frame_stabil_diperlukan: int = 3, frame_kosong_diperlukan: int = 5):
        self.state = IDLE
        self.frame_stabil_diperlukan = frame_stabil_diperlukan
        self.frame_kosong_diperlukan = frame_kosong_diperlukan
        self._hitung_terdeteksi = 0
        self._hitung_kosong = 0
        self.hasil_scan_terakhir = None
        self._lock = threading.Lock()   # satu permintaan /scan/live diproses pada satu waktu

    def reset(self) -> None:
        with self._lock:
            self.state = IDLE
            self._hitung_terdeteksi = 0
            self._hitung_kosong = 0
            self.hasil_scan_terakhir = None

    def process_frame(self, frame, ada_objek_fn, scan_fn) -> dict:
        """
        Memproses satu frame sesuai status saat ini.

        Args:
            ada_objek_fn: callable(frame) -> bool, apakah ada objek.
            scan_fn: callable(frame) -> dict hasil scan; dipanggil sekali saat objek stabil.
        Returns:
            dict: state (setelah frame ini), scan_dipicu (bool), hasil (dict | None)
        """
        with self._lock:
            ada_objek = ada_objek_fn(frame)

            if self.state == IDLE:
                if ada_objek:
                    self._hitung_terdeteksi += 1
                    self.state = OBJECT_DETECTED
                return {"state": self.state, "scan_dipicu": False, "hasil": None}

            if self.state == OBJECT_DETECTED:
                if not ada_objek:
                    # Objek hilang sebelum stabil -> anggap noise, kembali IDLE.
                    self._hitung_terdeteksi = 0
                    self.state = IDLE
                    return {"state": self.state, "scan_dipicu": False, "hasil": None}
                self._hitung_terdeteksi += 1
                if self._hitung_terdeteksi >= self.frame_stabil_diperlukan:
                    self.state = SCANNING
                    try:
                        hasil = scan_fn(frame)
                    except Exception:
                        self.state = IDLE            # gagal: jangan macet di SCANNING
                        self._hitung_terdeteksi = 0
                        raise
                    self.hasil_scan_terakhir = hasil
                    self.state = SUDAH_DISCAN
                    self._hitung_kosong = 0
                    return {"state": self.state, "scan_dipicu": True, "hasil": hasil}
                return {"state": self.state, "scan_dipicu": False, "hasil": None}

            if self.state == SUDAH_DISCAN:
                if ada_objek:
                    self._hitung_kosong = 0     # objek masih di situ, tidak scan ulang
                else:
                    self._hitung_kosong += 1
                    if self._hitung_kosong >= self.frame_kosong_diperlukan:
                        self.state = IDLE       # objek sudah diangkat: siap untuk objek berikutnya
                        self._hitung_terdeteksi = 0
                        self._hitung_kosong = 0
                return {"state": self.state, "scan_dipicu": False, "hasil": None}

            return {"state": self.state, "scan_dipicu": False, "hasil": None}

    def status(self) -> dict:
        return {"state": self.state, "hasil_scan_terakhir": self.hasil_scan_terakhir}


# Satu instance dipakai bersama oleh route scan dan kamera (satu kamera aktif).
state_machine_aktif = ScanStateMachine()
