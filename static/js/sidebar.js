// static/js/sidebar.js
// Membuka/menutup sidebar di layar sempit (di bawah 992 px). Di layar lebar sidebar selalu tampil, jadi skrip ini
// tidak melakukan apa pun. Sidebar ditutup lewat: klik tombol menu lagi, klik area gelap, tombol Esc, atau klik menu.
(function () {
    const sidebar = document.getElementById("sidebar");
    const overlay = document.getElementById("sidebar-overlay");
    const tombol = document.getElementById("btn-menu");
    if (!sidebar || !overlay || !tombol) return;

    function atur(buka) {
        sidebar.classList.toggle("open", buka);
        overlay.classList.toggle("show", buka);
        tombol.setAttribute("aria-expanded", String(buka));
        document.body.style.overflow = buka ? "hidden" : "";
    }

    tombol.addEventListener("click", () => atur(!sidebar.classList.contains("open")));
    overlay.addEventListener("click", () => atur(false));
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") atur(false); });
    sidebar.querySelectorAll("a").forEach((a) => a.addEventListener("click", () => atur(false)));

    // Bila jendela dilebarkan sampai sidebar tampil permanen, pastikan keadaan "terbuka" dibersihkan.
    window.matchMedia("(min-width: 992px)").addEventListener("change", (e) => { if (e.matches) atur(false); });
})();
