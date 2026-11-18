"""
core/validation.py
==================
Mencocokkan bacaan OCR ke daftar kode produk valid (jarak edit berbobot).

Algoritmanya sama dengan yang dipakai pada pengujian. Yang berbeda dari versi lama hanya dua hal:
1. Fungsi ini MURNI: daftar kode diberikan sebagai argumen (diambil dari database oleh lapisan di atasnya).
2. Ambang penerimaan bawaan 2,0 (bukan 4,0), berdasarkan pengujian 50 foto berkunci jawaban: ambang 4,0 tidak
   menambah satu pun bacaan benar, tetapi menaikkan kode yang diterima tapi salah dari 1 menjadi 4.
"""

# Nilai bawaan; nilai yang dipakai aplikasi diatur lewat config (AMBANG_TERIMA_JARAK).
AMBANG_TERIMA_JARAK = 2.0

# Karakter yang sering tertukar karena kepotong/blur. Penggantian antar pasangan ini lebih murah.
PASANGAN_MIRIP = {
    frozenset({"B", "R"}): 0.3,
    frozenset({"D", "0"}): 0.3,
    frozenset({"1", "T"}): 0.3,
    frozenset({"E", "F"}): 0.3,
}
BIAYA_SUBSTITUSI_NORMAL = 1.0

PENANDA_GAGAL = ("[TIDAK TERBACA]", "[PERLU VERIFIKASI MANUAL]")


def _biaya_substitusi(a, b):
    if a == b:
        return 0.0
    return PASANGAN_MIRIP.get(frozenset({a, b}), BIAYA_SUBSTITUSI_NORMAL)


def edit_distance_berbobot(a: str, b: str) -> float:
    """Edit distance biasa, tetapi penggantian di PASANGAN_MIRIP berbiaya 0,3. Hapus/sisip berbiaya 1."""
    n, m = len(a), len(b)
    dp = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            biaya_sub = _biaya_substitusi(a[i - 1], b[j - 1])
            dp[i][j] = min(
                dp[i - 1][j] + 1,             # hapus
                dp[i][j - 1] + 1,             # sisip
                dp[i - 1][j - 1] + biaya_sub,  # ganti / cocok
            )
    return dp[n][m]


def koreksi_ke_kode_valid(teks: str, daftar_kode, ambang_terima: float = AMBANG_TERIMA_JARAK):
    """
    Mencocokkan bacaan OCR ke kode valid terdekat.

    - Bacaan yang SUDAH persis sama dengan salah satu kode valid langsung diterima.
    - Selain itu dicari kode dengan jarak berbobot terkecil; diterima hanya bila jarak <= ambang_terima.

    Returns:
        tuple: (teks_terkoreksi: str, jarak_koreksi: float | None, yakin: bool)
    """
    if not teks or teks == "[TIDAK TERBACA]":
        return teks, None, False

    daftar_kode = list(daftar_kode)
    if teks in daftar_kode:
        return teks, 0.0, True
    if not daftar_kode:
        return teks, None, False

    jarak_terbaik, kode_terbaik = None, None
    for kode in daftar_kode:
        jarak = edit_distance_berbobot(teks, kode)
        if jarak_terbaik is None or jarak < jarak_terbaik:
            jarak_terbaik, kode_terbaik = jarak, kode

    if jarak_terbaik <= ambang_terima:
        return kode_terbaik, jarak_terbaik, True
    return teks, jarak_terbaik, False


def status_kode(kode: str, daftar_kode, ambang_terima: float = AMBANG_TERIMA_JARAK) -> str:
    """Status tunggal untuk disimpan: 'VALID' | 'INVALID' | 'NOT_FOUND'."""
    if not kode or kode in PENANDA_GAGAL:
        return "NOT_FOUND"
    _, _, yakin = koreksi_ke_kode_valid(kode, daftar_kode, ambang_terima)
    return "VALID" if yakin else "INVALID"
