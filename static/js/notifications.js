/**
 * static/js/notifications.js
 * =============================
 * Dropdown notifikasi di bell icon topbar. Polling berkala (30 detik) +
 * saat pertama halaman dibuka. Klik notifikasi -> tandai dibaca.
 */

const btnNotif = document.getElementById("btn-notif");
const notifDropdown = document.getElementById("notif-dropdown");
const notifDot = document.getElementById("notif-dot");
const notifList = document.getElementById("notif-list");
const btnReadAll = document.getElementById("btn-notif-read-all");

const LABEL_TIPE = {
    scan_tidak_dikenali: "Scan Tidak Dikenali",
    kamera_terputus: "Kamera Terputus",
    import_selesai: "Import Selesai",
};

function waktuRelatif(iso) {
    const diffMs = Date.now() - new Date(iso.replace(" ", "T")).getTime();
    const menit = Math.floor(diffMs / 60000);
    if (menit < 1) return "baru saja";
    if (menit < 60) return `${menit} menit lalu`;
    const jam = Math.floor(menit / 60);
    if (jam < 24) return `${jam} jam lalu`;
    return `${Math.floor(jam / 24)} hari lalu`;
}

function renderNotif(data) {
    const list = data.notifikasi || [];
    notifDot.style.display = data.jumlah_belum_dibaca > 0 ? "block" : "none";

    if (!list.length) {
        notifList.innerHTML = '<div class="notif-empty">Belum ada notifikasi.</div>';
        return;
    }

    notifList.innerHTML = list.map((n) => `
        <div class="notif-item ${n.dibaca ? 'read' : ''}" data-id="${n.id}">
            <span class="dot"></span>
            <div class="body">
                <span class="tipe-badge ${esc(n.tipe)}">${esc(LABEL_TIPE[n.tipe] || n.tipe)}</span>
                <div class="msg">${esc(n.pesan)}</div>
                <div class="meta">${esc(waktuRelatif(n.created_at))}</div>
            </div>
        </div>
    `).join("");
}

function muatNotifikasi() {
    fetch("/notifications/")
        .then((r) => r.json())
        .then(renderNotif)
        .catch(() => {});
}

btnNotif.addEventListener("click", (e) => {
    e.stopPropagation();
    notifDropdown.classList.toggle("open");
    if (notifDropdown.classList.contains("open")) muatNotifikasi();
});

document.addEventListener("click", (e) => {
    if (!notifDropdown.contains(e.target) && !btnNotif.contains(e.target)) {
        notifDropdown.classList.remove("open");
    }
});

notifList.addEventListener("click", (e) => {
    const item = e.target.closest(".notif-item");
    if (!item || item.classList.contains("read")) return;
    const id = item.dataset.id;
    fetchProtected(`/notifications/${id}/read`, { method: "POST" })
        .then(() => { item.classList.add("read"); muatNotifikasi(); })
        .catch(() => {});
});

btnReadAll.addEventListener("click", () => {
    fetchProtected("/notifications/read-all", { method: "POST" })
        .then(() => muatNotifikasi())
        .catch(() => {});
});

document.addEventListener("DOMContentLoaded", () => {
    muatNotifikasi();
    setInterval(muatNotifikasi, 30000);
});
