"""
services/export.py
==================
Membuat berkas ekspor riwayat scan: PDF (ReportLab) dan Excel (pandas + openpyxl). Filter yang diterima SAMA dengan
filter di halaman History (tanggal, kode, status).

Berkas hasil disimpan sementara di static/exports dan otomatis dibersihkan bila sudah lebih dari 24 jam.
"""

import os
import time
import uuid
from datetime import datetime

from flask import current_app

from services import database

BATAS_BARIS = 10_000
UMUR_MAKS_DETIK = 24 * 3600


def _bersihkan_berkas_lama(folder: str) -> None:
    sekarang = time.time()
    for nama in os.listdir(folder):
        p = os.path.join(folder, nama)
        if nama.startswith("laporan_scan_") and os.path.isfile(p) and sekarang - os.path.getmtime(p) > UMUR_MAKS_DETIK:
            try:
                os.remove(p)
            except OSError:
                pass


def _siapkan_folder() -> str:
    folder = current_app.config["EXPORT_FOLDER"]
    os.makedirs(folder, exist_ok=True)
    _bersihkan_berkas_lama(folder)
    return folder


def _teks_bacaan(r: dict) -> str:
    """Bacaan OCR untuk laporan: '-' bila tidak ada OCR atau data lama, '(tidak ada teks)' bila OCR tidak membaca apa pun."""
    if r.get("teks_terbaca") is None:
        return "-"
    return r["teks_terbaca"] or "(tidak ada teks)"


def _ambil_data(filters: dict = None) -> list:
    filters = filters or {}
    if any(filters.values()):
        return database.search_scan_history(filters, limit=BATAS_BARIS)
    return database.get_scan_history(limit=BATAS_BARIS)


def generate_pdf(filters: dict = None) -> str:
    """Membuat PDF laporan (judul, tanggal cetak, tabel, nomor halaman). Returns: path berkas."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    folder = _siapkan_folder()
    path = os.path.join(folder, f"laporan_scan_{uuid.uuid4().hex[:8]}.pdf")
    data = _ambil_data(filters)
    styles = getSampleStyleSheet()

    def header_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 9)
        canvas.drawString(2 * cm, landscape(A4)[1] - 1.2 * cm, "Sistem Pencatatan Otomatis Barang Gudang")
        canvas.setFont("Helvetica", 8)
        canvas.drawRightString(landscape(A4)[0] - 2 * cm, landscape(A4)[1] - 1.2 * cm,
                               datetime.now().strftime("Dicetak: %d-%m-%Y %H:%M"))
        canvas.drawCentredString(landscape(A4)[0] / 2, 1 * cm, f"Halaman {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(path, pagesize=landscape(A4), topMargin=2 * cm, bottomMargin=1.8 * cm,
                            leftMargin=2 * cm, rightMargin=2 * cm)
    story = [Paragraph("Laporan Riwayat Pemindaian Kode Produk", styles["Title"]), Spacer(1, 4)]
    if filters and any(filters.values()):
        story.append(Paragraph("Filter diterapkan: " + ", ".join(f"{k}: {v}" for k, v in filters.items() if v), styles["Normal"]))
    story.append(Paragraph(f"Total data: {len(data)} entri", styles["Normal"]))
    story.append(Spacer(1, 12))

    rows = [["Tanggal", "Jam", "Kode", "Bacaan OCR", "Status", "Conf. YOLO", "Conf. OCR", "Waktu (s)"]]
    for r in data:
        rows.append([r["tanggal"], r["jam"], r["kode"] or "-", _teks_bacaan(r), r["status"],
                     f"{r['confidence_yolo'] * 100:.1f}%", f"{r['confidence_ocr'] * 100:.1f}%",
                     f"{r['processing_time']:.3f}"])
    if len(rows) == 1:
        story.append(Paragraph("Tidak ada data untuk ditampilkan.", styles["Normal"]))
    else:
        tabel = Table(rows, repeatRows=1)
        tabel.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0A2351")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D3DBE9")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EDF1F8")]),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(tabel)
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return path


def generate_excel(filters: dict = None) -> str:
    """Membuat Excel (.xlsx): header tebal, lebar kolom otomatis, baris judul dibekukan. Returns: path berkas."""
    import pandas as pd
    from openpyxl.styles import Alignment, Font, PatternFill

    folder = _siapkan_folder()
    path = os.path.join(folder, f"laporan_scan_{uuid.uuid4().hex[:8]}.xlsx")
    data = _ambil_data(filters)

    kolom = ["tanggal", "jam", "kode", "teks_terbaca", "status", "confidence_yolo", "confidence_ocr", "processing_time",
             "waktu_yolo", "waktu_ocr", "alasan_keputusan"]
    label = ["Tanggal", "Jam", "Kode", "Bacaan OCR", "Status", "Confidence YOLO", "Confidence OCR", "Processing Time (s)",
             "Waktu YOLO (s)", "Waktu OCR (s)", "Alasan Keputusan"]
    df = pd.DataFrame(data)
    if not df.empty:
        df["teks_terbaca"] = [_teks_bacaan(r) for r in data]
    df = pd.DataFrame(columns=kolom) if df.empty else df[kolom]
    df.columns = label

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Riwayat Scan")
        ws = writer.sheets["Riwayat Scan"]
        isi = PatternFill(start_color="0A2351", end_color="0A2351", fill_type="solid")
        huruf = Font(name="Arial", bold=True, color="FFFFFF")
        for sel in ws[1]:
            sel.fill, sel.font = isi, huruf
            sel.alignment = Alignment(horizontal="center", vertical="center")
        for kolom_sel in ws.columns:
            panjang = max((len(str(c.value)) for c in kolom_sel if c.value is not None), default=10)
            ws.column_dimensions[kolom_sel[0].column_letter].width = min(panjang + 4, 45)
        ws.freeze_panes = "A2"
    return path
