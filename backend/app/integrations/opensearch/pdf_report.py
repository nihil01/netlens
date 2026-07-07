from __future__ import annotations

import io
import logging
import os
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

from app.utils.timezone import to_baku, now_baku
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    Image,
    PageBreak,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Font registration -- use a TTF font that supports Azerbaijani characters
# (ş, ç, ı, ü, ö, ğ, etc.).  The built-in Helvetica does NOT include them.
# ---------------------------------------------------------------------------
AZERBAIJANI_FONT = "Helvetica"  # fallback if nothing found
AZERBAIJANI_FONT_BOLD = "Helvetica-Bold"

_FONT_CANDIDATES = [
    # macOS system fonts (Arial covers Turkish / Azerbaijani well)
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    # Linux common locations
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
]


def _register_font() -> None:
    """Try to register a TTF font that supports Azerbaijani characters."""
    global AZERBAIJANI_FONT, AZERBAIJANI_FONT_BOLD

    for candidate in _FONT_CANDIDATES:
        if os.path.isfile(candidate):
            try:
                face_name = os.path.splitext(os.path.basename(candidate))[0]
                pdfmetrics.registerFont(TTFont(face_name, candidate))
                logger.debug("Registered font %s from %s", face_name, candidate)
            except Exception:
                logger.warning("Failed to register font %s", candidate, exc_info=True)

    # Resolve the actual registered names
    registered = pdfmetrics.getRegisteredFontNames()

    # Try preferred fonts (Arial family first, then DejaVu)
    for regular, bold in [
        ("Arial", "Arial Bold"),
        ("DejaVuSans", "DejaVuSans-Bold"),
    ]:
        if regular in registered:
            AZERBAIJANI_FONT = regular
            AZERBAIJANI_FONT_BOLD = bold if bold in registered else regular
            return

    # If neither was registered, fall back to Helvetica (best effort)
    logger.warning(
        "No TTF font supporting Azerbaijani characters was found. "
        "Some characters may not render correctly in the PDF."
    )


_register_font()


# --- Colors ---
PRIMARY = colors.HexColor("#1e40af")  # blue-800
SECONDARY = colors.HexColor("#3b82f6")  # blue-500
ACCENT = colors.HexColor("#059669")  # emerald-600
DARK = colors.HexColor("#111827")  # gray-900
GRAY = colors.HexColor("#6b7280")  # gray-500
LIGHT_BG = colors.HexColor("#f9fafb")  # gray-50
HEADER_BG = colors.HexColor("#1e3a5f")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "Title2", parent=base["Title"],
            fontSize=22, textColor=PRIMARY, spaceAfter=6, alignment=1,
            fontName=AZERBAIJANI_FONT_BOLD,
        ),
        "subtitle": ParagraphStyle(
            "Subtitle2", parent=base["Normal"],
            fontSize=12, textColor=GRAY, spaceAfter=20, alignment=1,
            fontName=AZERBAIJANI_FONT,
        ),
        "section": ParagraphStyle(
            "Section2", parent=base["Heading2"],
            fontSize=14, textColor=PRIMARY, spaceBefore=16, spaceAfter=8,
            fontName=AZERBAIJANI_FONT_BOLD,
        ),
        "body": ParagraphStyle(
            "Body2", parent=base["Normal"],
            fontSize=9, textColor=DARK, spaceAfter=4,
            fontName=AZERBAIJANI_FONT,
        ),
        "small": ParagraphStyle(
            "Small2", parent=base["Normal"],
            fontSize=7, textColor=GRAY,
            fontName=AZERBAIJANI_FONT,
        ),
        "footer": ParagraphStyle(
            "Footer2", parent=base["Normal"],
            fontSize=7, textColor=GRAY, alignment=1,
            fontName=AZERBAIJANI_FONT,
        ),
    }


def _make_table(headers: list[str], rows: list[list[Any]], max_rows: int = 50) -> Table:
    data = [headers] + rows[:max_rows]
    t = Table(data, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), AZERBAIJANI_FONT_BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 8),
        ("FONTNAME", (0, 1), (-1, -1), AZERBAIJANI_FONT),
        ("FONTSIZE", (0, 1), (-1, -1), 7),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e5e7eb")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT_BG]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]
    t.setStyle(TableStyle(style))
    return t


def build_pdf_report(
    ip: str,
    full_data: dict[str, Any],
    logo_path: str | None = None,
) -> io.BytesIO:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
    )

    s = _styles()
    elements: list[Any] = []

    # --- Cover ---
    elements.append(Spacer(1, 2 * cm))

    if logo_path:
        try:
            img = Image(logo_path, width=5 * cm, height=5 * cm)
            img.hAlign = "CENTER"
            elements.append(img)
            elements.append(Spacer(1, 1 * cm))
        except Exception:
            pass

    elements.append(Paragraph("Şəbəkə Auditi", s["title"]))
    elements.append(Paragraph("Şəbəkə fəaliyyəti hesabatı", s["subtitle"]))

    # Summary box - convert to Baku time
    start_raw = full_data.get("start", "")
    end_raw = full_data.get("end", "")
    start_str = to_baku(start_raw)[:10] if start_raw else "—"
    end_str = to_baku(end_raw)[:10] if end_raw else "—"
    total_hits = full_data.get("total_hits", 0)
    domain_count = full_data.get("domains", {}).get("total", 0)
    port_count = len(full_data.get("ports", []))
    user_count = len(full_data.get("users", []))

    summary_data = [
        ["IP ünvanı", ip],
        ["Dövr", f"{start_str} — {end_str}"],
        ["Ümumi hadisələr", f"{total_hits:,}"],
        ["Unikal domenlər", f"{domain_count:,}"],
        ["Unikal portlar", f"{port_count:,}"],
        ["İstifadəçilər", f"{user_count:,}"],
    ]
    summary_table = Table(summary_data, colWidths=[5 * cm, 10 * cm])
    summary_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), AZERBAIJANI_FONT_BOLD),
        ("FONTNAME", (1, 0), (1, -1), AZERBAIJANI_FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), GRAY),
        ("TEXTCOLOR", (1, 0), (1, -1), DARK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, -1), (-1, -1), 1, colors.HexColor("#e5e7eb")),
    ]))
    elements.append(summary_table)
    elements.append(PageBreak())

    # --- Domains ---
    elements.append(Paragraph("DOMENLƏR VƏ TƏTİBIKLƏR", s["section"]))
    elements.append(Paragraph(
        "Bu bölmədə IP ünvanının ziyaret etdiyi domenlər və istifadə olunan tətbiqlər göstərilir.",
        s["body"],
    ))
    domains = full_data.get("domains", {}).get("buckets", [])
    if domains:
        domain_rows = []
        for i, b in enumerate(domains[:50], 1):
            key = b.get("key", {})
            first_seen = to_baku(b.get("first_seen", {}).get("value_as_string", ""))[:16]
            last_seen = to_baku(b.get("last_seen", {}).get("value_as_string", ""))[:16]
            domain_rows.append([
                str(i),
                key.get("domain", "—"),
                key.get("application", "—"),
                f"{b.get('doc_count', 0):,}",
                first_seen,
                last_seen,
            ])
        elements.append(_make_table(
            ["#", "Domen", "Tətbiq", "Say", "İlk", "Son"],
            domain_rows,
        ))
    else:
        elements.append(Paragraph("Domen məlumatı tapılmadı.", s["body"]))

    elements.append(PageBreak())

    # --- ASN Info ---
    asn_info = full_data.get("asn_info", {})
    if asn_info.get("asn"):
        elements.append(Paragraph("ASN MƏLUMATI", s["section"]))
        asn_rows = [
            ["IP ünvanı", ip],
            ["ASN", f"AS{asn_info['asn']}"],
            ["Təşkilat", asn_info.get("asn_org", "—")],
            ["Vendor", asn_info.get("vendor", "—")],
            ["Kateqoriya", asn_info.get("category", "—")],
        ]
        asn_table = Table(asn_rows, colWidths=[5 * cm, 10 * cm])
        asn_table.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (0, -1), AZERBAIJANI_FONT_BOLD),
            ("FONTNAME", (1, 0), (1, -1), AZERBAIJANI_FONT),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("TEXTCOLOR", (0, 0), (0, -1), GRAY),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elements.append(asn_table)
        elements.append(Spacer(1, 12))

    # --- Top IPs ---
    elements.append(Paragraph("ƏSAS IP ÜNVANLARI", s["section"]))
    ips_data = full_data.get("ips", {})

    for label, key in [
        ("Mənbə kimi (source)", "as_source"),
        ("Təyinat kimi (destination)", "as_destination"),
        ("Başladıcı kimi (initiator)", "as_initiator"),
        ("Cavabdeh kimi (responder)", "as_responder"),
    ]:
        items = ips_data.get(key, [])
        if items:
            elements.append(Paragraph(f"<b>{label}</b>", s["body"]))
            ip_rows = []
            for i, item in enumerate(items[:30], 1):
                asn_val = item.get("asn")
                org_val = item.get("asn_org", "—") or "—"
                vendor_val = item.get("vendor", "—") or "—"
                country_val = item.get("country_name") or item.get("country") or "—"
                ip_rows.append([
                    str(i),
                    item["key"],
                    f"AS{asn_val}" if asn_val else "—",
                    org_val[:25],
                    vendor_val[:15],
                    country_val[:20],
                    f"{item['doc_count']:,}",
                ])
            elements.append(_make_table(["#", "IP", "ASN", "Təşkilat", "Vendor", "Ölkə", "Say"], ip_rows))
            elements.append(Spacer(1, 8))

    elements.append(PageBreak())

    # --- Ports ---
    elements.append(Paragraph("ƏSAS PORTLAR", s["section"]))
    ports = full_data.get("ports", [])
    if ports:
        port_rows = [[str(i + 1), p["key"], f"{p['doc_count']:,}"] for i, p in enumerate(ports[:40])]
        elements.append(_make_table(["#", "Port", "Say"], port_rows))
    else:
        elements.append(Paragraph("Port məlumatı tapılmadı.", s["body"]))

    # --- Protocols ---
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("PROTOKOLLAR", s["section"]))
    protocols = full_data.get("protocols", [])
    if protocols:
        proto_rows = [[p["key"], f"{p['doc_count']:,}"] for p in protocols[:20]]
        elements.append(_make_table(["Protokol", "Say"], proto_rows))

    # --- Actions ---
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("ƏMƏLİYYATLAR (ACTION)", s["section"]))
    actions = full_data.get("actions", [])
    if actions:
        action_rows = [[a["key"], f"{a['doc_count']:,}"] for a in actions[:20]]
        elements.append(_make_table(["Əməliyyat", "Say"], action_rows))

    # --- Users ---
    elements.append(Spacer(1, 12))
    elements.append(Paragraph("İSTİFADƏÇİLƏR", s["section"]))
    users = full_data.get("users", [])
    if users:
        user_rows = [[u["key"], f"{u['doc_count']:,}"] for u in users[:30]]
        elements.append(_make_table(["İstifadəçi", "Say"], user_rows))
    else:
        elements.append(Paragraph("İstifadəçi məlumatı tapılmadı.", s["body"]))

    # --- Footer ---
    elements.append(Spacer(1, 2 * cm))
    elements.append(Paragraph(
        f"NetLens Şəbəkə Auditi — {ip} — {start_str} — {end_str}",
        s["footer"],
    ))

    doc.build(elements)
    buf.seek(0)
    return buf
