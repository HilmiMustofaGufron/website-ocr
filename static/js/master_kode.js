/**
 * static/js/master_kode.js
 * ===========================
 * CRUD Master Kode: tambah, edit (inline prompt sederhana), hapus, search,
 * import Excel. Semua lewat fetch ke endpoint yang sudah ada di
 * blueprints/master_kode/routes.py.
 */

const alertBox = document.getElementById("alert-box");
const tabelBody = document.getElementById("tabel-body");
const inputSearch = document.getElementById("input-search");
const jumlahKode = document.getElementById("jumlah-kode");

function tampilkanAlert(pesan, jenis) {
    alertBox.textContent = pesan;
    alertBox.className = "alert-inline show " + jenis;
    setTimeout(() => alertBox.classList.remove("show"), 4000);
}

/**
 * Meng-escape karakter HTML berbahaya (&, <, >, ", ') sebelum dimasukkan
 * ke innerHTML/insertAdjacentHTML. WAJIB dipakai untuk SEMUA data yang
 * berasal dari input operator (kode, keterangan) -- tanpa ini, operator
 * bisa menyuntikkan HTML/JavaScript berbahaya lewat kolom "Keterangan"
 * (stored XSS) yang akan tereksekusi di browser siapa pun yang membuka
 * halaman ini setelahnya.
 */
function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function updateJumlah() {
    const jumlah = tabelBody.querySelectorAll("tr:not(.empty-row)").length;
    jumlahKode.textContent = jumlah + " kode terdaftar";
}

function buatBarisHTML(item) {
    const kode = escapeHtml(item.kode);
    const ket = escapeHtml(item.keterangan);
    const tanggal = escapeHtml(item.created_at || "");
    return `
        <tr data-id="${item.id}" data-kode="${kode}" data-keterangan="${ket}">
            <td class="mono">${kode}</td>
            <td>${ket || "-"}</td>
            <td class="mono">${tanggal}</td>
            <td>
                <button class="btn-icon btn-edit">Edit</button>
                <button class="btn-icon danger btn-hapus">Hapus</button>
            </td>
        </tr>`;
}

document.getElementById("form-tambah").addEventListener("submit", (e) => {
    e.preventDefault();
    const kode = document.getElementById("input-kode").value.trim().toUpperCase();
    const keterangan = document.getElementById("input-keterangan").value.trim();
    if (!kode) return;

    fetchProtected("/master-kode/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kode, keterangan }),
    })
        .then(async (r) => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || "Gagal menambah kode");
            document.querySelector(".empty-row")?.remove();
            tabelBody.insertAdjacentHTML("afterbegin", buatBarisHTML(data));
            document.getElementById("input-kode").value = "";
            document.getElementById("input-keterangan").value = "";
            updateJumlah();
            tampilkanAlert("Kode " + data.kode + " berhasil ditambahkan.", "success");
        })
        .catch((err) => tampilkanAlert(err.message, "error"));
});

tabelBody.addEventListener("click", (e) => {
    const tr = e.target.closest("tr");
    if (!tr || !tr.dataset.id) return;
    const id = tr.dataset.id;

    if (e.target.classList.contains("btn-hapus")) {
        if (!confirm("Hapus kode " + tr.dataset.kode + "?")) return;
        fetchProtected(`/master-kode/${id}`, { method: "DELETE" })
            .then(async (r) => {
                const data = await r.json();
                if (!r.ok) throw new Error(data.error || "Gagal menghapus");
                tr.remove();
                updateJumlah();
                tampilkanAlert("Kode dihapus.", "success");
            })
            .catch((err) => tampilkanAlert(err.message, "error"));
    }

    if (e.target.classList.contains("btn-edit")) {
        const kodeLama = tr.dataset.kode;
        const ketLama = tr.dataset.keterangan;
        const kodeBaru = prompt("Edit kode:", kodeLama);
        if (kodeBaru === null) return;
        const ketBaru = prompt("Edit keterangan:", ketLama);

        fetchProtected(`/master-kode/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ kode: kodeBaru.trim().toUpperCase(), keterangan: ketBaru }),
        })
            .then(async (r) => {
                const data = await r.json();
                if (!r.ok) throw new Error(data.error || "Gagal mengubah");
                tr.outerHTML = buatBarisHTML(data);
                tampilkanAlert("Kode berhasil diubah.", "success");
            })
            .catch((err) => tampilkanAlert(err.message, "error"));
    }
});

inputSearch.addEventListener("input", () => {
    const q = inputSearch.value.trim().toLowerCase();
    tabelBody.querySelectorAll("tr:not(.empty-row)").forEach((tr) => {
        const kode = tr.dataset.kode.toLowerCase();
        const ket = (tr.dataset.keterangan || "").toLowerCase();
        tr.style.display = (kode.includes(q) || ket.includes(q)) ? "" : "none";
    });
});

document.getElementById("input-import").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("file", file);

    tampilkanAlert("Mengimpor file Excel...", "success");
    fetchProtected("/master-kode/import", { method: "POST", body: formData })
        .then(async (r) => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || "Gagal import");
            tampilkanAlert(
                `Import selesai: ${data.berhasil} berhasil, ${data.dilewati} dilewati (duplikat), ${data.gagal} gagal.`,
                data.gagal > 0 ? "error" : "success"
            );
            setTimeout(() => location.reload(), 1500);
        })
        .catch((err) => tampilkanAlert(err.message, "error"))
        .finally(() => { e.target.value = ""; });
});

updateJumlah();
