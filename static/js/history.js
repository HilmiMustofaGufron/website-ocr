/**
 * static/js/history.js
 * ====================
 * Tabel riwayat scan: filter (tanggal, kode, status) lewat /history/search, hapus lewat DELETE /history/<id>,
 * modal detail dengan gambar, dan paginasi di sisi browser (data sudah diambil lengkap, dipotong per halaman).
 * Semua teks dari data di-escape (esc) sebelum masuk ke HTML. Data baris disimpan di memori (Map), bukan di
 * atribut HTML.
 */

const tabelBody = document.getElementById("tabel-body");
const alertBox = document.getElementById("alert-box");
const jumlahRiwayat = document.getElementById("jumlah-riwayat");
const paginationControls = document.getElementById("pagination-controls");
const modal = document.getElementById("modal-detail");
const modalContent = document.getElementById("modal-content");

const PER_HALAMAN = 10;
let semuaData = [];
let halamanAktif = 1;

function tampilkanAlert(pesan, jenis) {
    alertBox.textContent = pesan;
    alertBox.className = "alert-inline show " + jenis;
    setTimeout(() => alertBox.classList.remove("show"), 4000);
}

function kelasStatus(status) {
    if (status === "VALID") return "valid";
    if (status === "INVALID") return "invalid";
    return "not-found";
}

// Bacaan OCR apa adanya. null = tidak ada OCR (mis. YOLO tidak menemukan objek) atau data lama yang bacaannya tidak dicatat;
// "" = OCR berjalan tetapi tidak ada teks yang terbaca.
function teksBacaan(r) {
    if (r.teks_terbaca === null || r.teks_terbaca === undefined) return "-";
    return r.teks_terbaca === "" ? "(tidak ada teks)" : r.teks_terbaca;
}

function persen(nilai) {
    return nilai === null || nilai === undefined ? "-" : (nilai * 100).toFixed(1) + "%";
}

function buatBarisHTML(r) {
    return `
        <tr data-id="${esc(r.id)}">
            <td class="mono">${esc(r.tanggal)}</td>
            <td class="mono">${esc(r.jam)}</td>
            <td class="mono">${esc(r.kode) || "-"}</td>
            <td class="mono">${esc(teksBacaan(r))}</td>
            <td><span class="status-badge ${kelasStatus(r.status)}">${esc(r.status)}</span></td>
            <td class="mono">${persen(r.confidence_yolo)}</td>
            <td class="mono">${persen(r.confidence_ocr)}</td>
            <td class="mono">${esc(r.processing_time)}s</td>
            <td>
                <button class="btn-icon btn-detail">Detail</button>
                <button class="btn-icon danger btn-hapus">Hapus</button>
            </td>
        </tr>`;
}

function renderHalaman() {
    const totalHalaman = Math.max(1, Math.ceil(semuaData.length / PER_HALAMAN));
    halamanAktif = Math.min(halamanAktif, totalHalaman);
    const mulai = (halamanAktif - 1) * PER_HALAMAN;
    const potongan = semuaData.slice(mulai, mulai + PER_HALAMAN);

    tabelBody.innerHTML = potongan.length
        ? potongan.map(buatBarisHTML).join("")
        : '<tr class="empty-row"><td colspan="9">Tidak ada data untuk ditampilkan.</td></tr>';

    const dariKe = semuaData.length ? `${mulai + 1}-${Math.min(mulai + PER_HALAMAN, semuaData.length)}` : "0";
    jumlahRiwayat.textContent = `Menampilkan ${dariKe} dari ${semuaData.length} data`;
    renderPagination(totalHalaman);
}

function renderPagination(totalHalaman) {
    let html = `<button class="page-btn" id="pg-prev" ${halamanAktif === 1 ? "disabled" : ""}>&lsaquo;</button>`;
    for (let i = 1; i <= totalHalaman; i++) {
        html += `<button class="page-btn ${i === halamanAktif ? "active" : ""}" data-page="${i}">${i}</button>`;
    }
    html += `<button class="page-btn" id="pg-next" ${halamanAktif === totalHalaman ? "disabled" : ""}>&rsaquo;</button>`;
    paginationControls.innerHTML = html;

    paginationControls.querySelectorAll("[data-page]").forEach((btn) => {
        btn.addEventListener("click", () => { halamanAktif = parseInt(btn.dataset.page, 10); renderHalaman(); });
    });
    const prev = document.getElementById("pg-prev");
    const next = document.getElementById("pg-next");
    if (prev) prev.addEventListener("click", () => { halamanAktif--; renderHalaman(); });
    if (next) next.addEventListener("click", () => { halamanAktif++; renderHalaman(); });
}

function ambilQueryFilterAktif() {
    const params = new URLSearchParams();
    const tanggal = document.getElementById("filter-tanggal").value;
    const kode = document.getElementById("filter-kode").value.trim();
    const status = document.getElementById("filter-status").value;
    if (tanggal) params.set("tanggal", tanggal);
    if (kode) params.set("kode", kode);
    if (status) params.set("status", status);
    return params.toString();
}

function terapkanFilter() {
    fetch("/history/search?" + ambilQueryFilterAktif())
        .then((r) => r.json())
        .then((data) => { semuaData = Array.isArray(data) ? data : []; halamanAktif = 1; renderHalaman(); })
        .catch(() => tampilkanAlert("Gagal memuat data.", "error"));
}

function debounce(fn, ms) {
    let t;
    return (...args) => { clearTimeout(t); t = setTimeout(() => fn(...args), ms); };
}

document.getElementById("filter-tanggal").addEventListener("change", terapkanFilter);
document.getElementById("filter-kode").addEventListener("input", debounce(terapkanFilter, 400));
document.getElementById("filter-status").addEventListener("change", terapkanFilter);
document.getElementById("btn-reset-filter").addEventListener("click", () => {
    document.getElementById("filter-tanggal").value = "";
    document.getElementById("filter-kode").value = "";
    document.getElementById("filter-status").value = "";
    terapkanFilter();
});
document.getElementById("btn-export-pdf").addEventListener("click", (e) => {
    e.preventDefault();
    window.location.href = "/export/pdf?" + ambilQueryFilterAktif();
});
document.getElementById("btn-export-excel").addEventListener("click", (e) => {
    e.preventDefault();
    window.location.href = "/export/excel?" + ambilQueryFilterAktif();
});

function bukaModalDetail(r) {
    // path gambar berasal dari server, tetapi tetap di-escape; hanya path di bawah static/uploads yang dipakai.
    // Data lama dari proyek sebelumnya bisa memakai garis miring terbalik (gaya Windows): dinormalkan dulu.
    const gambar = (label, pathMentah) => {
        const path = pathMentah ? String(pathMentah).replace(/\\/g, "/") : "";
        return /^static\/uploads\/[A-Za-z0-9_.-]+$/.test(path)
            ? `<div class="mb-2"><div class="stat-label">${esc(label)}</div><img src="/${esc(path)}" alt="${esc(label)}"></div>`
            : "";
    };
    const baris = (k, v) => `<div class="readout-row"><span class="k">${esc(k)}</span><span class="v">${v}</span></div>`;

    modalContent.innerHTML = `
        <div class="row g-3">
            <div class="col-md-6">${gambar("Gambar asli", r.path_gambar)}</div>
            <div class="col-md-6">
                ${gambar("Deteksi YOLO", r.path_deteksi)}
                ${gambar("Hasil crop", r.path_crop)}
            </div>
        </div>
        ${baris("Kode", esc(r.kode) || "-")}
        ${baris("Bacaan OCR (apa adanya)", esc(teksBacaan(r)))}
        ${r.jarak_koreksi !== null && r.jarak_koreksi !== undefined ? baris("Jarak bacaan ke kode terdekat", esc(Number(r.jarak_koreksi).toFixed(1))) : ""}
        ${baris("Status", `<span class="status-badge ${kelasStatus(r.status)}">${esc(r.status)}</span>`)}
        ${baris("Confidence YOLO", persen(r.confidence_yolo))}
        ${baris("Confidence OCR", persen(r.confidence_ocr))}
        ${baris("Waktu YOLO", esc(r.waktu_yolo ?? "-") + "s")}
        ${baris("Waktu OCR", esc(r.waktu_ocr ?? "-") + "s")}
        ${r.waktu_recovery ? baris("Waktu jalur cadangan (data lama)", esc(r.waktu_recovery) + "s") : ""}
        ${baris("Total processing time", esc(r.processing_time) + "s")}
        ${baris("Alasan keputusan", esc(r.alasan_keputusan) || "-")}
    `;
    modal.classList.add("open");
}

tabelBody.addEventListener("click", (e) => {
    const tr = e.target.closest("tr");
    if (!tr || !tr.dataset.id) return;
    const id = parseInt(tr.dataset.id, 10);

    if (e.target.classList.contains("btn-hapus")) {
        if (!confirm("Hapus riwayat ini?")) return;
        fetchProtected(`/history/${id}`, { method: "DELETE" })
            .then(async (r) => {
                const data = await r.json();
                if (!r.ok) throw new Error(data.error || "Gagal menghapus");
                semuaData = semuaData.filter((x) => x.id !== id);
                renderHalaman();
                tampilkanAlert("Riwayat dihapus.", "success");
            })
            .catch((err) => tampilkanAlert(err.message, "error"));
    }
    if (e.target.classList.contains("btn-detail")) {
        const r = semuaData.find((x) => x.id === id);
        if (r) bukaModalDetail(r);
    }
});

document.getElementById("btn-tutup-modal").addEventListener("click", () => modal.classList.remove("open"));
modal.addEventListener("click", (e) => { if (e.target === modal) modal.classList.remove("open"); });

terapkanFilter();
