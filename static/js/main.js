// static/js/main.js
// Logika global di semua halaman:
// 1. fetchProtected(): fetch yang otomatis membawa token CSRF (wajib untuk POST/PUT/PATCH/DELETE).
// 2. Pembungkus fetch global: permintaan yang mengubah data ke situs ini otomatis membawa token CSRF, dan
//    jawaban 401 (sesi berakhir) langsung mengarahkan ke halaman login. Dengan begitu semua berkas JS lain
//    cukup memakai fetch() biasa dan tetap aman.

function getCsrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : "";
}

const _fetchAsli = window.fetch.bind(window);

function _sameOrigin(url) {
    try {
        return new URL(url, window.location.href).origin === window.location.origin;
    } catch (e) {
        return false;
    }
}

window.fetch = function (input, init) {
    init = init || {};
    const url = typeof input === "string" ? input : input.url;
    const metode = (init.method || (typeof input !== "string" && input.method) || "GET").toUpperCase();
    if (_sameOrigin(url) && metode !== "GET" && metode !== "HEAD") {
        init.headers = new Headers(init.headers || {});
        if (!init.headers.has("X-CSRF-Token")) init.headers.set("X-CSRF-Token", getCsrfToken());
    }
    return _fetchAsli(input, init).then((resp) => {
        if (resp.status === 401 && _sameOrigin(url) && !window.location.pathname.startsWith("/login")) {
            window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
        }
        return resp;
    });
};

function fetchProtected(url, options = {}) {
    return fetch(url, options);
}

// Meng-escape teks sebelum dimasukkan ke innerHTML (mencegah penyuntikan HTML/JavaScript lewat data).
function esc(nilai) {
    if (nilai === null || nilai === undefined) return "";
    return String(nilai)
        .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
