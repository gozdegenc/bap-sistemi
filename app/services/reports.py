"""
Rapor motoru: PDF ve Excel çıktısı üretir.
Türkçe karakter desteği için sistem TTF fontu kullanılır.
"""
import io
import os
from datetime import datetime
from collections import defaultdict
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.models import Project, Output, User, OutputType, OutputStatus


# ── Font yönetimi ────────────────────────────────────────────────────────────

def _find_unicode_font() -> Optional[str]:
    """Sistemde Türkçe destekli TTF font arar."""
    candidates = [
        # Windows
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        # Linux (Docker)
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _register_font():
    """
    Türkçe destekli font kaydeder; bulamazsa None döner
    ve çağıran kod Helvetica'ya düşer.
    Döner: (normal_font_name, bold_font_name)
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    path = _find_unicode_font()
    if not path:
        return "Helvetica", "Helvetica-Bold"

    base = os.path.splitext(path)[0]
    # Bold varyantını da dene
    bold_candidates = [
        base + "b.ttf", base + "bd.ttf", base + "-Bold.ttf",
        base + "Bold.ttf",
        path.replace(".ttf", "b.ttf").replace(".ttf", "bd.ttf"),
    ]
    bold_path = next((p for p in bold_candidates if os.path.exists(p)), None)

    try:
        pdfmetrics.registerFont(TTFont("TRFont", path))
        if bold_path:
            pdfmetrics.registerFont(TTFont("TRFontBold", bold_path))
            return "TRFont", "TRFontBold"
        return "TRFont", "TRFont"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


# ── Veri toplama ─────────────────────────────────────────────────────────────

def _get_report_data(db: Session, year: Optional[int] = None) -> dict:
    query = db.query(Output).join(Project)
    if year:
        query = query.filter(Project.application_year == year)
    outputs = query.filter(Output.status == OutputStatus.onaylandi).all()

    by_type: dict = defaultdict(int)
    by_faculty: dict = defaultdict(int)
    by_department: dict = defaultdict(int)

    for o in outputs:
        by_type[o.output_type.value] += 1
        pi = o.project.principal_investigator
        fac = (pi.faculty or "Belirtilmemiş") if pi else "Belirtilmemiş"
        dep = (pi.department or o.project.department or "Belirtilmemiş") if pi else (o.project.department or "Belirtilmemiş")
        by_faculty[fac] += 1
        by_department[dep] += 1

    proj_q = db.query(Project).filter(Project.is_active == True)
    if year:
        proj_q = proj_q.filter(Project.application_year == year)
    total_projects = proj_q.count()

    return {
        "outputs": outputs,
        "by_type": dict(by_type),
        "by_faculty": dict(by_faculty),
        "by_department": dict(by_department),
        "total_outputs": len(outputs),
        "projects_with_output": len(set(o.project_id for o in outputs)),
        "total_projects": total_projects,
        "year": year,
    }


# ── PDF Raporu ────────────────────────────────────────────────────────────────

def generate_pdf_report(db: Session, year: Optional[int] = None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable, PageBreak, KeepTogether,
    )

    fn, fnb = _register_font()
    data = _get_report_data(db, year)
    buf = io.BytesIO()
    W, H = A4
    _ns = str(id(buf))  # her çağrıda benzersiz stil adları için

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2*cm, rightMargin=2*cm,
        topMargin=2*cm, bottomMargin=2.5*cm,
        title=f"BAP Çıktı Raporu {data['year'] or 'Tüm Yıllar'}",
        author="BAP Koordinasyon Birimi",
    )

    # ── Stiller ──
    C_BLUE  = colors.HexColor("#1A365D")
    C_BLUE2 = colors.HexColor("#2B6CB0")
    C_GRAY  = colors.HexColor("#4A5568")
    C_LGRAY = colors.HexColor("#F7FAFC")
    C_LINE  = colors.HexColor("#CBD5E0")
    C_PURPLE= colors.HexColor("#6B21A8")

    def style(name, **kw):
        kw.pop("parent", None)
        kw.setdefault("fontName", fn)
        kw.setdefault("fontSize", 10)
        kw.setdefault("leading", 15)
        return ParagraphStyle(f"{name}_{_ns}", **kw)

    s_title    = style("T",  fontName=fnb, fontSize=20, textColor=C_BLUE,  spaceAfter=4)
    s_subtitle = style("ST", fontSize=11,  textColor=C_GRAY,  spaceAfter=18)
    s_h2       = style("H2", fontName=fnb, fontSize=13, textColor=C_BLUE,  spaceBefore=18, spaceAfter=8)
    s_h3       = style("H3", fontName=fnb, fontSize=11, textColor=C_BLUE2, spaceBefore=12, spaceAfter=4)
    s_body     = style("B",  fontSize=10,  leading=15)
    s_small    = style("S",  fontSize=8.5, textColor=C_GRAY, leading=13)
    s_footer   = style("F",  fontSize=8,   textColor=C_GRAY)
    s_label    = style("L",  fontName=fnb, fontSize=9, textColor=C_GRAY)

    def cell_style(data_rows, col_widths, header_color=C_BLUE2):
        t = Table(data_rows, colWidths=col_widths, repeatRows=1)
        n = len(data_rows)
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0),  header_color),
            ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",    (0, 0), (-1, 0),  fnb),
            ("FONTNAME",    (0, 1), (-1, -1), fn),
            ("FONTSIZE",    (0, 0), (-1, -1), 9),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_LGRAY]),
            ("BOX",         (0, 0), (-1, -1), 0.4, C_LINE),
            ("INNERGRID",   (0, 0), (-1, -1), 0.4, C_LINE),
            ("TOPPADDING",  (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",(0,0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING",(0, 0), (-1, -1), 6),
            ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    story = []

    # ── Kapak ──
    story.append(Paragraph("BAP Proje Çıktıları Raporu", s_title))
    story.append(Paragraph(
        f"{str(data['year']) + ' Başvuru Yılı' if data['year'] else 'Tüm Yıllar'}  ·  Bilimsel Araştırma Projeleri Koordinasyon Birimi",
        s_subtitle,
    ))
    story.append(HRFlowable(width="100%", thickness=1.5, color=C_BLUE2))
    story.append(Spacer(1, 16))

    # ── Genel Özet ──
    story.append(Paragraph("Genel Özet", s_h2))
    summary_rows = [
        ["Gösterge", "Değer"],
        ["Toplam Onaylı Çıktı", str(data["total_outputs"])],
        ["Çıktısı Olan Proje Sayısı", str(data["projects_with_output"])],
        ["Toplam Aktif Proje", str(data["total_projects"])],
        ["Çıktısı Olmayan Proje", str(data["total_projects"] - data["projects_with_output"])],
    ]
    story.append(cell_style(summary_rows, [11*cm, 4*cm]))
    story.append(Spacer(1, 16))

    # ── Türe Göre Dağılım ──
    if data["by_type"]:
        story.append(Paragraph("Çıktı Türü Dağılımı", s_h2))
        type_rows = [["Çıktı Türü", "Adet", "Oran (%)"]]
        for otype, cnt in sorted(data["by_type"].items(), key=lambda x: -x[1]):
            pct = f"{cnt / data['total_outputs'] * 100:.1f}" if data["total_outputs"] else "0"
            type_rows.append([otype, str(cnt), pct])
        story.append(cell_style(type_rows, [9.5*cm, 2.5*cm, 3*cm]))
        story.append(Spacer(1, 16))

    # ── Fakülteye Göre Dağılım ──
    if data["by_faculty"] and len(data["by_faculty"]) > 1:
        story.append(Paragraph("Fakülteye Göre Dağılım", s_h2))
        fac_rows = [["Fakülte", "Çıktı Sayısı", "Oran (%)"]]
        for fac, cnt in sorted(data["by_faculty"].items(), key=lambda x: -x[1]):
            pct = f"{cnt / data['total_outputs'] * 100:.1f}" if data["total_outputs"] else "0"
            fac_rows.append([fac, str(cnt), pct])
        story.append(cell_style(fac_rows, [9.5*cm, 2.5*cm, 3*cm]))
        story.append(Spacer(1, 16))

    # ── Bölüme Göre Dağılım ──
    if data["by_department"] and len(data["by_department"]) > 1:
        story.append(Paragraph("Bölüme Göre Dağılım", s_h2))
        dep_rows = [["Bölüm", "Çıktı Sayısı", "Oran (%)"]]
        for dep, cnt in sorted(data["by_department"].items(), key=lambda x: -x[1]):
            pct = f"{cnt / data['total_outputs'] * 100:.1f}" if data["total_outputs"] else "0"
            dep_rows.append([dep, str(cnt), pct])
        story.append(cell_style(dep_rows, [9.5*cm, 2.5*cm, 3*cm]))
        story.append(Spacer(1, 16))

    # ── Detaylı Çıktı Listesi ──
    story.append(PageBreak())
    story.append(Paragraph("Onaylı Çıktıların Detaylı Listesi", s_h2))

    s_cell = style("cell8", fontSize=8, fontName=fn)  # tablo hücre stili (bir kez tanımla)

    projects = db.query(Project).filter(Project.is_active == True).order_by(Project.project_code).all()
    for project in projects:
        approved = [o for o in project.outputs if o.status == OutputStatus.onaylandi]
        if not approved:
            continue

        pi = project.principal_investigator
        pi_info = f"{pi.full_name}" if pi else "—"
        if pi and pi.faculty:
            pi_info += f" · {pi.faculty}"
        if pi and pi.department:
            pi_info += f" / {pi.department}"
        dep_info = project.department or (pi.department if pi else "") or ""

        block = []
        block.append(Paragraph(
            f"<b>{project.project_code}</b>  {project.title}",
            s_h3,
        ))
        block.append(Paragraph(
            f"Yürütücü: {pi_info}" + (f"  |  Bölüm: {dep_info}" if dep_info and dep_info not in pi_info else ""),
            s_small,
        ))
        block.append(Spacer(1, 4))

        out_rows = [["Tür", "Başlık", "Yazar(lar)", "Yayıncı / Dergi", "Tarih", "DOI/ISBN"]]
        for o in approved:
            out_rows.append([
                Paragraph(o.output_type.value, s_cell),
                Paragraph(o.title or "—", s_cell),
                Paragraph(o.authors or "—", s_cell),
                Paragraph(o.publisher_venue or "—", s_cell),
                Paragraph(o.publication_date or "—", s_cell),
                Paragraph(o.identifier or "—", s_cell),
            ])
        t = Table(out_rows, colWidths=[2.5*cm, 4.5*cm, 3*cm, 3*cm, 1.8*cm, 2.2*cm], repeatRows=1)
        t.setStyle(TableStyle([
            ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#EBF8FF")),
            ("FONTNAME",    (0, 0), (-1, 0),  fnb),
            ("FONTNAME",    (0, 1), (-1, -1), fn),
            ("FONTSIZE",    (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_LGRAY]),
            ("BOX",         (0, 0), (-1, -1), 0.4, C_LINE),
            ("INNERGRID",   (0, 0), (-1, -1), 0.3, C_LINE),
            ("TOPPADDING",  (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ]))
        block.append(t)
        block.append(Spacer(1, 12))
        story.append(KeepTogether(block))

    # ── Alt bilgi ──
    story.append(HRFlowable(width="100%", thickness=0.5, color=C_LINE))
    story.append(Paragraph(
        f"Bu rapor {datetime.now().strftime('%d.%m.%Y %H:%M')} tarihinde "
        "BAP Çıktı Yönetim Sistemi tarafından otomatik oluşturulmuştur.",
        s_footer,
    ))

    doc.build(story)
    buf.seek(0)
    return buf.read()


# ── Excel Raporu ──────────────────────────────────────────────────────────────

def generate_excel_report(db: Session, year: Optional[int] = None) -> bytes:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
    from openpyxl.utils import get_column_letter

    data = _get_report_data(db, year)
    wb = openpyxl.Workbook()

    H_FILL  = PatternFill("solid", fgColor="1A365D")
    H2_FILL = PatternFill("solid", fgColor="2B6CB0")
    H_FONT  = Font(color="FFFFFF", bold=True, size=11)
    TITLE_FONT = Font(bold=True, size=14, color="1A365D")
    BOLD = Font(bold=True)
    CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
    LEFT   = Alignment(horizontal="left",  vertical="top",    wrap_text=True)
    thin   = Side(style="thin", color="CBD5E0")
    BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)

    def header_row(ws, row, cols):
        for c, val in enumerate(cols, 1):
            cell = ws.cell(row=row, column=c, value=val)
            cell.font = H2_FILL and Font(color="FFFFFF", bold=True, size=10)
            cell.fill = H2_FILL
            cell.alignment = CENTER
            cell.border = BORDER

    def data_cell(ws, row, col, val, align=LEFT):
        cell = ws.cell(row=row, column=col, value=val)
        cell.alignment = align
        cell.border = BORDER
        return cell

    # ══════════════════════════════════════════════
    # SAYFA 1 — Özet
    # ══════════════════════════════════════════════
    ws1 = wb.active
    assert ws1 is not None
    ws1.title = "Özet"
    ws1.row_dimensions[1].height = 30

    ws1.merge_cells("A1:E1")
    ws1["A1"] = f"BAP Proje Çıktıları — {str(data['year']) + ' Başvuru Yılı' if data['year'] else 'Tüm Yıllar'} Raporu"
    ws1["A1"].font = TITLE_FONT
    ws1["A1"].alignment = Alignment(horizontal="center", vertical="center")

    ws1["A3"] = "Genel İstatistikler"
    ws1["A3"].font = BOLD
    stats_rows = [
        ("Toplam Onaylı Çıktı",         data["total_outputs"]),
        ("Çıktısı Olan Proje Sayısı",    data["projects_with_output"]),
        ("Toplam Aktif Proje",           data["total_projects"]),
        ("Çıktısı Olmayan Proje",        data["total_projects"] - data["projects_with_output"]),
    ]
    for i, (label, val) in enumerate(stats_rows, start=4):
        ws1[f"A{i}"] = label
        ws1[f"B{i}"] = val
        ws1[f"B{i}"].font = Font(bold=True, size=12)

    # Tür dağılımı
    r = 9
    ws1[f"A{r}"] = "Çıktı Türü Dağılımı"
    ws1[f"A{r}"].font = BOLD
    r += 1
    header_row(ws1, r, ["Çıktı Türü", "Adet", "Oran (%)"])
    r += 1
    for otype, cnt in sorted(data["by_type"].items(), key=lambda x: -x[1]):
        pct = round(cnt / data["total_outputs"] * 100, 1) if data["total_outputs"] else 0
        data_cell(ws1, r, 1, otype)
        data_cell(ws1, r, 2, cnt, CENTER)
        data_cell(ws1, r, 3, pct, CENTER)
        r += 1

    # Fakülte dağılımı
    r += 1
    ws1[f"A{r}"] = "Fakülte Dağılımı"
    ws1[f"A{r}"].font = BOLD
    r += 1
    header_row(ws1, r, ["Fakülte", "Çıktı Sayısı", "Oran (%)"])
    r += 1
    for fac, cnt in sorted(data["by_faculty"].items(), key=lambda x: -x[1]):
        pct = round(cnt / data["total_outputs"] * 100, 1) if data["total_outputs"] else 0
        data_cell(ws1, r, 1, fac)
        data_cell(ws1, r, 2, cnt, CENTER)
        data_cell(ws1, r, 3, pct, CENTER)
        r += 1

    # Bölüm dağılımı
    r += 1
    ws1[f"A{r}"] = "Bölüm Dağılımı"
    ws1[f"A{r}"].font = BOLD
    r += 1
    header_row(ws1, r, ["Bölüm", "Çıktı Sayısı", "Oran (%)"])
    r += 1
    for dep, cnt in sorted(data["by_department"].items(), key=lambda x: -x[1]):
        pct = round(cnt / data["total_outputs"] * 100, 1) if data["total_outputs"] else 0
        data_cell(ws1, r, 1, dep)
        data_cell(ws1, r, 2, cnt, CENTER)
        data_cell(ws1, r, 3, pct, CENTER)
        r += 1

    ws1.column_dimensions["A"].width = 35
    ws1.column_dimensions["B"].width = 18
    ws1.column_dimensions["C"].width = 12

    # ══════════════════════════════════════════════
    # SAYFA 2 — Tüm Çıktılar (Detay)
    # ══════════════════════════════════════════════
    ws2 = wb.create_sheet("Tüm Çıktılar")
    ws2.freeze_panes = "A2"
    cols2 = [
        "Proje Kodu", "Proje Başlığı", "Bölüm (Proje)",
        "Yürütücü", "Fakülte", "Bölüm (Yürütücü)",
        "Çıktı Türü", "Çıktı Başlığı",
        "Yazar(lar)", "Yayın Tarihi",
        "DOI / ISBN / Patent No", "Yayıncı / Dergi / Konferans",
        "BAP Atıf Notu", "Projeyle İlişki Notu",
        "Eklenme Tarihi",
    ]
    header_row(ws2, 1, cols2)

    for ri, o in enumerate(data["outputs"], start=2):
        pi = o.project.principal_investigator
        data_cell(ws2, ri,  1, o.project.project_code, CENTER)
        data_cell(ws2, ri,  2, o.project.title)
        data_cell(ws2, ri,  3, o.project.department or "—")
        data_cell(ws2, ri,  4, pi.full_name if pi else "—")
        data_cell(ws2, ri,  5, (pi.faculty or "—") if pi else "—")
        data_cell(ws2, ri,  6, (pi.department or "—") if pi else "—")
        data_cell(ws2, ri,  7, o.output_type.value, CENTER)
        data_cell(ws2, ri,  8, o.title)
        data_cell(ws2, ri,  9, o.authors or "—")
        data_cell(ws2, ri, 10, o.publication_date or "—", CENTER)
        data_cell(ws2, ri, 11, o.identifier or "—")
        data_cell(ws2, ri, 12, o.publisher_venue or "—")
        data_cell(ws2, ri, 13, o.acknowledgement_note or "—")
        data_cell(ws2, ri, 14, o.relation_note or "—")
        data_cell(ws2, ri, 15, o.created_at.strftime("%d.%m.%Y"), CENTER)

    col_widths2 = [14, 30, 20, 22, 20, 20, 18, 35, 28, 14, 22, 28, 30, 30, 14]
    for i, w in enumerate(col_widths2, 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.row_dimensions[1].height = 32

    # ══════════════════════════════════════════════
    # SAYFA 3 — Proje Bazlı Özet
    # ══════════════════════════════════════════════
    ws3 = wb.create_sheet("Proje Bazlı")
    ws3.freeze_panes = "A2"
    cols3 = [
        "Proje Kodu", "Proje Başlığı", "Proje Türü", "Bölüm",
        "Yürütücü", "Fakülte", "Bütçe (₺)",
        "Kabul / Başlangıç Tarihi", "Bitiş Tarihi",
        "Toplam Çıktı", "Makale/Yayın", "Bildiri", "Patent",
        "Diğer Çıktılar",
    ]
    header_row(ws3, 1, cols3)

    projects = db.query(Project).filter(Project.is_active == True).order_by(Project.project_code).all()
    for ri, proj in enumerate(projects, start=2):
        approved = [o for o in proj.outputs if o.status == OutputStatus.onaylandi]
        type_counts: dict = defaultdict(int)
        for o in approved:
            type_counts[o.output_type.value] += 1

        pi = proj.principal_investigator
        other = sum(v for k, v in type_counts.items()
                    if k not in ("Makale/Yayın", "Bildiri", "Patent"))

        start_str = proj.start_date.strftime("%d.%m.%Y") if proj.start_date else "—"
        end_str   = proj.end_date.strftime("%d.%m.%Y")   if proj.end_date   else "—"

        data_cell(ws3, ri,  1, proj.project_code, CENTER)
        data_cell(ws3, ri,  2, proj.title)
        data_cell(ws3, ri,  3, proj.project_type or "—")
        data_cell(ws3, ri,  4, proj.department or (pi.department if pi else "") or "—")
        data_cell(ws3, ri,  5, pi.full_name if pi else "—")
        data_cell(ws3, ri,  6, (pi.faculty or "—") if pi else "—")
        budget_cell = data_cell(ws3, ri, 7, proj.budget or 0, CENTER)
        if proj.budget:
            budget_cell.number_format = '#,##0.00'
        data_cell(ws3, ri,  8, start_str, CENTER)
        data_cell(ws3, ri,  9, end_str,   CENTER)
        data_cell(ws3, ri, 10, len(approved), CENTER)
        data_cell(ws3, ri, 11, type_counts.get("Makale/Yayın", 0), CENTER)
        data_cell(ws3, ri, 12, type_counts.get("Bildiri", 0), CENTER)
        data_cell(ws3, ri, 13, type_counts.get("Patent", 0), CENTER)
        data_cell(ws3, ri, 14, other, CENTER)

    col_widths3 = [14, 32, 16, 20, 22, 20, 14, 18, 15, 12, 14, 12, 12, 14]
    for i, w in enumerate(col_widths3, 1):
        ws3.column_dimensions[get_column_letter(i)].width = w
    ws3.row_dimensions[1].height = 32

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()
