/**
 * static/js/settings.js
 * =====================
 * Halaman Settings: simpan pengaturan operator (POST /settings/) dan ganti akun (POST /account).
 */

const alertBox = document.getElementById("alert-box");
const rangeYolo = document.getElementById("input-threshold-yolo");
const labelYolo = document.getElementById("label-threshold-yolo");
const formSettings = document.getElementById("form-settings");

function tampilkanAlert(el, pesan, jenis) {
    el.textContent = pesan;
    el.className = "alert-inline show " + jenis;
    setTimeout(() => el.classList.remove("show"), 4000);
}

rangeYolo.addEventListener("input", () => { labelYolo.textContent = rangeYolo.value; });

formSettings.addEventListener("submit", (e) => {
    e.preventDefault();
    const payload = {
        threshold_yolo: parseFloat(rangeYolo.value),
        auto_scan: document.getElementById("input-auto-scan").checked,
        interval_scan: parseInt(document.getElementById("input-interval").value, 10),
        kamera_aktif: document.getElementById("input-kamera").value.trim(),
    };
    fetchProtected("/settings/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    })
        .then(async (r) => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || "Gagal menyimpan pengaturan");
            tampilkanAlert(alertBox, "Pengaturan disimpan. Berlaku untuk scan berikutnya.", "success");
        })
        .catch((err) => tampilkanAlert(alertBox, err.message, "error"));
});

const formAccount = document.getElementById("form-account");
formAccount.addEventListener("submit", (e) => {
    e.preventDefault();
    const alertAccount = document.getElementById("alert-account");
    const payload = new URLSearchParams({
        username_baru: document.getElementById("input-username-baru").value.trim(),
        password_baru: document.getElementById("input-password-baru").value,
        konfirmasi_password: document.getElementById("input-konfirmasi-password").value,
        password_sekarang: document.getElementById("input-password-sekarang").value,
    });
    fetchProtected("/account", { method: "POST", body: payload })
        .then(async (r) => {
            const data = await r.json();
            if (!r.ok) throw new Error(data.error || "Gagal menyimpan akun");
            tampilkanAlert(alertAccount, "Akun berhasil diperbarui.", "success");
            ["input-password-baru", "input-konfirmasi-password", "input-password-sekarang"].forEach((id) => {
                document.getElementById(id).value = "";
            });
        })
        .catch((err) => tampilkanAlert(alertAccount, err.message, "error"));
});
