/**
 * static/js/monitoring.js
 * =======================
 * Logika polling halaman Monitoring:
 * 1. Frame kamera langsung (img src disegarkan berkala dengan penangkal cache).
 * 2. Memicu /scan/live berkala (bila auto scan aktif). Mesin status di backend (services/scan_state.py)
 *    yang memutuskan kapan pembacaan kode sungguhan dijalankan; JavaScript hanya memicu "cek frame ini".
 *    Satu permintaan pada satu waktu: bila pembacaan sedang berjalan (bisa beberapa detik di CPU), pemicu
 *    berikutnya dilewati supaya permintaan tidak menumpuk.
 * 3. Memperbarui panel status (beacon dan hasil scan terakhir).
 * 4. Panel "Uji dengan foto": memindai foto yang diunggah tanpa memerlukan kamera.
 */

let pollingHandle = null;
let cameraAktif = false;
let sedangScan = false;

const el = {
    frame: document.getElementById("live-frame"),
    placeholder: document.getElementById("camera-placeholder"),
    wrap: document.getElementById("camera-wrap"),
    beaconDot: document.getElementById("beacon-dot"),
    beaconLabel: document.getElementById("beacon-label"),
    fps: document.getElementById("camera-fps"),
    inputSource: document.getElementById("input-source"),
    btnStart: document.getElementById("btn-start-camera"),
    btnStop: document.getElementById("btn-stop-camera"),
    rKode: document.getElementById("r-kode"),
    rTeks: document.getElementById("r-teks"),
    rStatus: document.getElementById("r-status"),
    rConfYolo: document.getElementById("r-conf-yolo"),
    rConfOcr: document.getElementById("r-conf-ocr"),
    rProcTime: document.getElementById("r-proc-time"),
    inputFoto: document.getElementById("input-foto"),
    btnUjiFoto: document.getElementById("btn-uji-foto"),
    hasilUjiFoto: document.getElementById("uji-foto-hasil"),
};

function setBeacon(state) {
    const peta = {
        IDLE: { cls: "state-idle", label: "IDLE" },
        OBJECT_DETECTED: { cls: "state-detected", label: "OBJEK TERDETEKSI" },
        SCANNING: { cls: "state-scanning", label: "MEMINDAI..." },
        SUDAH_DISCAN: { cls: "state-done", label: "SELESAI DISCAN" },
        ERROR: { cls: "state-error", label: "ERROR" },
    };
    const info = peta[state] || peta.IDLE;
    el.beaconDot.className = "beacon-dot " + info.cls;
    el.beaconLabel.textContent = info.label;
    el.wrap.classList.toggle("scanning", state === "SCANNING");
}

function tampilkanHasilScan(hasil) {
    if (!hasil) return;
    el.rKode.textContent = hasil.kode || "-";
    // Bacaan OCR apa adanya, juga saat ditolak (supaya operator tahu apa yang sebenarnya terbaca).
    el.rTeks.textContent = (hasil.teks_terbaca === null || hasil.teks_terbaca === undefined) ? "-"
        : (hasil.teks_terbaca === "" ? "(tidak ada teks)" : hasil.teks_terbaca);
    const statusKelas = { VALID: "valid", INVALID: "invalid", NOT_FOUND: "not-found" };
    const kelas = statusKelas[hasil.status] || "not-found";
    el.rStatus.innerHTML = `<span class="status-badge ${kelas}">${esc(hasil.status || "-")}</span>`;
    el.rConfYolo.textContent = hasil.confidence_yolo != null ? (hasil.confidence_yolo * 100).toFixed(1) + "%" : "-";
    el.rConfOcr.textContent = hasil.confidence_ocr != null ? (hasil.confidence_ocr * 100).toFixed(1) + "%" : "-";
    el.rProcTime.textContent = hasil.processing_time != null ? hasil.processing_time.toFixed(3) + "s" : "-";
}

function refreshFrame() {
    if (!cameraAktif) return;
    el.frame.src = "/camera/frame?t=" + Date.now();
}

function cekStatusKamera() {
    fetch("/camera/status")
        .then((r) => r.json())
        .then((data) => {
            cameraAktif = data.aktif;
            el.fps.textContent = data.fps || "0";
            el.frame.style.display = cameraAktif ? "block" : "none";
            el.placeholder.style.display = cameraAktif ? "none" : "block";
            if (!cameraAktif && data.pesan_error) {
                el.placeholder.innerHTML = esc(data.pesan_error) + '<br>Tekan "Mulai kamera" untuk mencoba lagi.';
            }
        })
        .catch(() => { });
}

function jalankanScanLive() {
    if (sedangScan) return;     // pembacaan sebelumnya belum selesai
    sedangScan = true;
    fetch("/scan/live", { method: "POST" })
        .then((r) => r.json())
        .then((data) => {
            if (data.error) { if (cameraAktif) setBeacon("ERROR"); return; }
            if (data.status === "auto_scan_off") return;
            if (data.state) setBeacon(data.state);
            if (data.scan_dipicu && data.hasil) tampilkanHasilScan(data.hasil);
        })
        .catch(() => { })
        .finally(() => { sedangScan = false; });
}

function ambilStatusScanTerakhir() {
    fetch("/scan/status")
        .then((r) => r.json())
        .then((data) => {
            if (data.state) setBeacon(data.state);
            if (data.hasil_scan_terakhir) tampilkanHasilScan(data.hasil_scan_terakhir);
        })
        .catch(() => { });
}

function mulaiPolling() {
    if (pollingHandle) clearInterval(pollingHandle);
    pollingHandle = setInterval(() => {
        cekStatusKamera();
        refreshFrame();
        if (AUTO_SCAN_AKTIF && cameraAktif) jalankanScanLive();
    }, INTERVAL_SCAN_MS);
}

el.btnStart.addEventListener("click", () => {
    const sumber = (el.inputSource.value || "0").trim();
    const source = /^\d+$/.test(sumber) ? parseInt(sumber, 10) : sumber;   // angka = indeks perangkat, selain itu URL/berkas
    fetch("/camera/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source }),
    })
        .then((r) => r.json())
        .then((data) => {
            if (data.status === "error") el.placeholder.innerHTML = esc(data.pesan_error || "Kamera gagal dibuka.");
            cekStatusKamera();
        });
});

el.btnStop.addEventListener("click", () => {
    fetch("/camera/stop", { method: "POST" }).then(() => { cekStatusKamera(); setBeacon("IDLE"); });
});

el.btnUjiFoto.addEventListener("click", () => {
    const berkas = el.inputFoto.files[0];
    if (!berkas) { el.hasilUjiFoto.textContent = "Pilih foto dulu."; return; }
    const form = new FormData();
    form.append("file", berkas);
    el.btnUjiFoto.disabled = true;
    el.hasilUjiFoto.textContent = "Memproses (beberapa detik)...";
    fetch("/scan/image", { method: "POST", body: form })
        .then(async (r) => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || "Pindai gagal");
            tampilkanHasilScan(data);
            el.hasilUjiFoto.textContent = `Selesai: ${data.status}${data.kode ? " | " + data.kode : ""} | ${data.processing_time}s`;
        })
        .catch((err) => { el.hasilUjiFoto.textContent = "Gagal: " + err.message; })
        .finally(() => { el.btnUjiFoto.disabled = false; });
});

document.addEventListener("DOMContentLoaded", () => {
    cekStatusKamera();
    ambilStatusScanTerakhir();
    mulaiPolling();
});
