"""
Génération du rapport d'analyse concurrentielle EasyMail
"""
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn, nsdecls
from docx.oxml import parse_xml
import os

# ── Couleurs ──
BLEU_FONCE = RGBColor(0x1B, 0x3A, 0x5C)
BLEU_MOYEN = RGBColor(0x2E, 0x75, 0xB6)
BLEU_CLAIR = RGBColor(0xD6, 0xE4, 0xF0)
GRIS_CLAIR = RGBColor(0xF2, 0xF2, 0xF2)
BLANC = RGBColor(0xFF, 0xFF, 0xFF)
NOIR = RGBColor(0x00, 0x00, 0x00)
VERT = RGBColor(0x27, 0xAE, 0x60)
ROUGE = RGBColor(0xE7, 0x4C, 0x3C)
ORANGE = RGBColor(0xF3, 0x9C, 0x12)
JAUNE_FONCE = RGBColor(0xF1, 0xC4, 0x0F)
GRIS_TEXTE = RGBColor(0x33, 0x33, 0x33)

doc = Document()

# ── Styles de base ──
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)
style.font.color.rgb = GRIS_TEXTE
style.paragraph_format.space_after = Pt(6)
style.paragraph_format.line_spacing = 1.15

for level, size, color in [('Heading 1', 22, BLEU_FONCE), ('Heading 2', 16, BLEU_MOYEN), ('Heading 3', 13, BLEU_MOYEN)]:
    h = doc.styles[level]
    h.font.name = 'Calibri'
    h.font.size = Pt(size)
    h.font.color.rgb = color
    h.font.bold = True
    h.paragraph_format.space_before = Pt(18 if level == 'Heading 1' else 12)
    h.paragraph_format.space_after = Pt(8)

# ── Marges ──
for section in doc.sections:
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)


def set_cell_shading(cell, color_hex):
    """Applique un fond de couleur à une cellule"""
    shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{color_hex}" w:val="clear"/>')
    cell._tc.get_or_add_tcPr().append(shading)


def set_cell_border(cell, **kwargs):
    """Applique des bordures fines à une cellule"""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    tcBorders = parse_xml(f'<w:tcBorders {nsdecls("w")}>'
        '<w:top w:val="single" w:sz="4" w:space="0" w:color="D0D0D0"/>'
        '<w:left w:val="single" w:sz="4" w:space="0" w:color="D0D0D0"/>'
        '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="D0D0D0"/>'
        '<w:right w:val="single" w:sz="4" w:space="0" w:color="D0D0D0"/>'
        '</w:tcBorders>')
    tcPr.append(tcBorders)


def format_cell(cell, text, bold=False, color=GRIS_TEXTE, size=10, align=WD_ALIGN_PARAGRAPH.LEFT, font_color=None):
    """Formate le contenu d'une cellule"""
    cell.text = ""
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(3)
    run = p.add_run(text)
    run.font.name = 'Calibri'
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = font_color if font_color else color


def add_styled_table(headers, rows, col_widths=None, header_color="1B3A5C"):
    """Crée un tableau stylé avec en-têtes colorés et alternance de lignes"""
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    # En-têtes
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        set_cell_shading(cell, header_color)
        set_cell_border(cell)
        format_cell(cell, header, bold=True, font_color=BLANC, size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
        if col_widths:
            cell.width = Cm(col_widths[i])

    # Lignes de données
    for r_idx, row_data in enumerate(rows):
        for c_idx, value in enumerate(row_data):
            cell = table.rows[r_idx + 1].cells[c_idx]
            bg = "F2F2F2" if r_idx % 2 == 0 else "FFFFFF"
            set_cell_shading(cell, bg)
            set_cell_border(cell)
            # Gestion des icônes de couleur
            fc = None
            if isinstance(value, str):
                if value.startswith("OK "):
                    fc = VERT
                elif value.startswith("NON "):
                    fc = ROUGE
            format_cell(cell, value, size=9.5, font_color=fc)
            if col_widths:
                cell.width = Cm(col_widths[c_idx])

    doc.add_paragraph()  # espacement
    return table


def add_bullet(text, bold_prefix="", level=0):
    """Ajoute un point à puce"""
    p = doc.add_paragraph(style='List Bullet')
    if bold_prefix:
        run_b = p.add_run(bold_prefix)
        run_b.bold = True
        run_b.font.name = 'Calibri'
        run_b.font.size = Pt(11)
        run_b.font.color.rgb = GRIS_TEXTE
        run = p.add_run(text)
        run.font.name = 'Calibri'
        run.font.size = Pt(11)
        run.font.color.rgb = GRIS_TEXTE
    else:
        p.runs[0].font.name = 'Calibri' if p.runs else None
        if not bold_prefix and not p.runs:
            run = p.add_run(text)
            run.font.name = 'Calibri'
            run.font.size = Pt(11)
            run.font.color.rgb = GRIS_TEXTE
    return p


def add_separator():
    """Ajoute une ligne de séparation subtile"""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(6)
    pPr = p._p.get_or_add_pPr()
    pBdr = parse_xml(
        f'<w:pBdr {nsdecls("w")}>'
        '<w:bottom w:val="single" w:sz="6" w:space="1" w:color="2E75B6"/>'
        '</w:pBdr>'
    )
    pPr.append(pBdr)


# ═══════════════════════════════════════════════════════════════
# PAGE DE GARDE
# ═══════════════════════════════════════════════════════════════

# Espaces avant le titre
for _ in range(6):
    doc.add_paragraph()

# Ligne décorative supérieure
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("━" * 50)
run.font.color.rgb = BLEU_MOYEN
run.font.size = Pt(14)

# Titre principal
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(20)
p.paragraph_format.space_after = Pt(6)
run = p.add_run("ANALYSE CONCURRENTIELLE")
run.font.name = 'Calibri'
run.font.size = Pt(32)
run.font.color.rgb = BLEU_FONCE
run.font.bold = True

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(20)
run = p.add_run("EasyMail")
run.font.name = 'Calibri'
run.font.size = Pt(40)
run.font.color.rgb = BLEU_MOYEN
run.font.bold = True

# Ligne décorative inférieure
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("━" * 50)
run.font.color.rgb = BLEU_MOYEN
run.font.size = Pt(14)

# Sous-titre
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(30)
p.paragraph_format.space_after = Pt(6)
run = p.add_run("Positionnement stratégique sur le marché\ndes assistants email IA")
run.font.name = 'Calibri'
run.font.size = Pt(16)
run.font.color.rgb = GRIS_TEXTE
run.font.italic = True

# Date
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(40)
run = p.add_run("Mars 2026")
run.font.name = 'Calibri'
run.font.size = Pt(14)
run.font.color.rgb = BLEU_FONCE
run.font.bold = True

# Mention confidentiel
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(60)
run = p.add_run("CONFIDENTIEL")
run.font.name = 'Calibri'
run.font.size = Pt(11)
run.font.color.rgb = ROUGE
run.font.bold = True
run.font.all_caps = True

# ═══════════════════════════════════════════════════════════════
# SAUT DE PAGE — TABLE DES MATIERES
# ═══════════════════════════════════════════════════════════════

doc.add_page_break()

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.LEFT
p.paragraph_format.space_after = Pt(20)
run = p.add_run("TABLE DES MATIÈRES")
run.font.name = 'Calibri'
run.font.size = Pt(22)
run.font.color.rgb = BLEU_FONCE
run.font.bold = True

add_separator()

toc_items = [
    ("1.", "Synthèse exécutive", 0),
    ("2.", "Panorama du marché", 0),
    ("   2.1", "Les géants technologiques", 1),
    ("   2.2", "Les startups spécialisées", 1),
    ("   2.3", "Les outils d'outreach / cold email", 1),
    ("3.", "Tableau comparatif des concurrents", 0),
    ("4.", "Les forces uniques d'EasyMail", 0),
    ("5.", "Faiblesses à combler", 0),
    ("6.", "Stratégie recommandée", 0),
    ("   6.1", "Phase 1 — L'effet wow", 1),
    ("   6.2", "Phase 2 — Auto-drafts proactifs", 1),
    ("   6.3", "Phase 3 — Triage & briefing", 1),
    ("7.", "Positionnement tarifaire recommandé", 0),
    ("8.", "Conclusion", 0),
]

for num, title, level in toc_items:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(2)
    indent = Cm(1) if level == 1 else Cm(0)
    p.paragraph_format.left_indent = indent
    run = p.add_run(f"{num}  {title}")
    run.font.name = 'Calibri'
    run.font.size = Pt(12 if level == 0 else 11)
    run.font.color.rgb = BLEU_FONCE if level == 0 else BLEU_MOYEN
    run.font.bold = (level == 0)

# ═══════════════════════════════════════════════════════════════
# 1. SYNTHESE EXECUTIVE
# ═══════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('1. Synthèse exécutive', level=1)
add_separator()

p = doc.add_paragraph()
run = p.add_run(
    "Le marché des assistants email IA pèse environ 2 milliards de dollars en 2025, "
    "avec une croissance annuelle de 10 à 21%, et une projection à 5,5 milliards de dollars "
    "d'ici 2030. Ce secteur en pleine effervescence attire aussi bien les géants technologiques "
    "(Microsoft, Google, Apple) que des startups innovantes à forte croissance."
)
run.font.name = 'Calibri'
run.font.size = Pt(11)

p = doc.add_paragraph()
run = p.add_run(
    "Ce rapport analyse en profondeur les principaux concurrents, identifie les forces uniques "
    "d'EasyMail sur ce marché, et propose une feuille de route stratégique pour maximiser "
    "l'avantage compétitif de la solution."
)
run.font.name = 'Calibri'
run.font.size = Pt(11)

# Encadré chiffres clés
doc.add_paragraph()
table = doc.add_table(rows=1, cols=3)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
for i, (label, value) in enumerate([
    ("Marché 2025", "~2 Mrd $"),
    ("Croissance/an", "10-21%"),
    ("Projection 2030", "5,5 Mrd $"),
]):
    cell = table.rows[0].cells[i]
    set_cell_shading(cell, "1B3A5C")
    cell.width = Cm(5)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(value)
    run.font.name = 'Calibri'
    run.font.size = Pt(18)
    run.font.color.rgb = BLANC
    run.font.bold = True
    p2 = cell.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p2.paragraph_format.space_after = Pt(8)
    run2 = p2.add_run(label)
    run2.font.name = 'Calibri'
    run2.font.size = Pt(9)
    run2.font.color.rgb = BLEU_CLAIR

doc.add_paragraph()

# ═══════════════════════════════════════════════════════════════
# 2. PANORAMA DU MARCHE
# ═══════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('2. Panorama du marché', level=1)
add_separator()

# 2.1 Géants
doc.add_heading('2.1  Les géants technologiques', level=2)

giants = [
    ("Microsoft Copilot", "21-30$/mois", "430M+ utilisateurs Microsoft 365",
     "Intégration native Outlook, rédaction et résumé IA",
     "Générique, pas de personnalisation par contact, coût additionnel"),
    ("Google Gemini", "Gratuit / inclus", "3 milliards d'utilisateurs Gmail",
     "Triage intelligent inbox, auto-drafts, recherche conversationnelle",
     "Uniquement Gmail, données utilisateur exploitées, pas de profil contact"),
    ("Apple Intelligence", "Gratuit", "Tous les iPhone 15 Pro+",
     "Traitement on-device, forte confidentialité, résumés intelligents",
     "Fonctionnalités email très limitées, écosystème fermé Apple"),
]

for name, price, users, force, faiblesse in giants:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    run = p.add_run(f"{name}")
    run.font.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = BLEU_FONCE
    run.font.name = 'Calibri'

    for label, val in [("Prix : ", price), ("Utilisateurs : ", users)]:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.5)
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        r1 = p.add_run(label)
        r1.font.bold = True
        r1.font.size = Pt(10)
        r1.font.color.rgb = GRIS_TEXTE
        r1.font.name = 'Calibri'
        r2 = p.add_run(val)
        r2.font.size = Pt(10)
        r2.font.color.rgb = GRIS_TEXTE
        r2.font.name = 'Calibri'

    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(1)
    r1 = p.add_run("Force : ")
    r1.font.bold = True
    r1.font.size = Pt(10)
    r1.font.color.rgb = VERT
    r1.font.name = 'Calibri'
    r2 = p.add_run(force)
    r2.font.size = Pt(10)
    r2.font.color.rgb = GRIS_TEXTE
    r2.font.name = 'Calibri'

    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(6)
    r1 = p.add_run("Faiblesse : ")
    r1.font.bold = True
    r1.font.size = Pt(10)
    r1.font.color.rgb = ROUGE
    r1.font.name = 'Calibri'
    r2 = p.add_run(faiblesse)
    r2.font.size = Pt(10)
    r2.font.color.rgb = GRIS_TEXTE
    r2.font.name = 'Calibri'


# 2.2 Startups
doc.add_heading('2.2  Les startups spécialisées', level=2)

startups = [
    ("Superhuman", "30-40$/mois", "~70 000 utilisateurs", "118M$ levés (valorisé 825M$)",
     "Auto-drafts + adaptation au style de rédaction",
     "Cher, pas de profil persistant par contact"),
    ("Shortwave", "0-9$/mois", "N/A", "9M$ levés",
     "Ghostwriter + recherche IA dans les emails",
     "Uniquement Gmail"),
    ("MailMaestro (ex-Flowrite)", "~15$/mois", "N/A", "1,3M$ levés",
     "Multi-LLM, add-in Outlook natif",
     "Pas d'apprentissage continu, fonctionnalités basiques"),
    ("Lindy AI", "49$/mois+", "N/A", "49,9M$ levés",
     "Agents IA no-code, automatisation avancée",
     "Complexe à configurer, pas spécialisé email"),
]

for name, price, users, funding, force, faiblesse in startups:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    run = p.add_run(f"{name}")
    run.font.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = BLEU_FONCE
    run.font.name = 'Calibri'

    for label, val in [("Prix : ", price), ("Financement : ", funding)]:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.5)
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        r1 = p.add_run(label)
        r1.font.bold = True
        r1.font.size = Pt(10)
        r1.font.color.rgb = GRIS_TEXTE
        r1.font.name = 'Calibri'
        r2 = p.add_run(val)
        r2.font.size = Pt(10)
        r2.font.color.rgb = GRIS_TEXTE
        r2.font.name = 'Calibri'

    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(1)
    r1 = p.add_run("Force : ")
    r1.font.bold = True
    r1.font.size = Pt(10)
    r1.font.color.rgb = VERT
    r1.font.name = 'Calibri'
    r2 = p.add_run(force)
    r2.font.size = Pt(10)
    r2.font.color.rgb = GRIS_TEXTE
    r2.font.name = 'Calibri'

    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(6)
    r1 = p.add_run("Faiblesse : ")
    r1.font.bold = True
    r1.font.size = Pt(10)
    r1.font.color.rgb = ROUGE
    r1.font.name = 'Calibri'
    r2 = p.add_run(faiblesse)
    r2.font.size = Pt(10)
    r2.font.color.rgb = GRIS_TEXTE
    r2.font.name = 'Calibri'


# 2.3 Outreach
doc.add_heading("2.3  Les outils d'outreach / cold email", level=2)

outreach = [
    ("Instantly AI", "30-358$/mois", "Bootstrapped, ~80M$ ARR",
     "Envoi massif optimisé, warm-up automatique",
     "Cold email uniquement, pas adapté à l'email quotidien"),
    ("Lemlist (FR)", "59-99$/mois", "Bootstrapped, 40M$ ARR",
     "Séquences multicanal, entreprise française",
     "Outreach uniquement, pas adapté à l'email quotidien"),
]

for name, price, funding, force, faiblesse in outreach:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    run = p.add_run(f"{name}")
    run.font.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = BLEU_FONCE
    run.font.name = 'Calibri'

    for label, val in [("Prix : ", price), ("Financement : ", funding)]:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.5)
        p.paragraph_format.space_before = Pt(1)
        p.paragraph_format.space_after = Pt(1)
        r1 = p.add_run(label)
        r1.font.bold = True
        r1.font.size = Pt(10)
        r1.font.color.rgb = GRIS_TEXTE
        r1.font.name = 'Calibri'
        r2 = p.add_run(val)
        r2.font.size = Pt(10)
        r2.font.color.rgb = GRIS_TEXTE
        r2.font.name = 'Calibri'

    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(1)
    r1 = p.add_run("Force : ")
    r1.font.bold = True
    r1.font.size = Pt(10)
    r1.font.color.rgb = VERT
    r1.font.name = 'Calibri'
    r2 = p.add_run(force)
    r2.font.size = Pt(10)
    r2.font.color.rgb = GRIS_TEXTE
    r2.font.name = 'Calibri'

    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Cm(0.5)
    p.paragraph_format.space_before = Pt(1)
    p.paragraph_format.space_after = Pt(6)
    r1 = p.add_run("Faiblesse : ")
    r1.font.bold = True
    r1.font.size = Pt(10)
    r1.font.color.rgb = ROUGE
    r1.font.name = 'Calibri'
    r2 = p.add_run(faiblesse)
    r2.font.size = Pt(10)
    r2.font.color.rgb = GRIS_TEXTE
    r2.font.name = 'Calibri'


# ═══════════════════════════════════════════════════════════════
# 3. TABLEAU COMPARATIF
# ═══════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('3. Tableau comparatif des concurrents', level=1)
add_separator()

p = doc.add_paragraph()
run = p.add_run("Vue d'ensemble des principaux acteurs du marché des assistants email IA :")
run.font.name = 'Calibri'
run.font.size = Pt(11)
run.font.italic = True
doc.add_paragraph()

headers_comp = ["Concurrent", "Prix", "Utilisateurs", "Financement", "Force principale"]
rows_comp = [
    ["Microsoft Copilot", "21-30$/mois", "430M+ M365", "N/A (Microsoft)", "Intégration native Outlook"],
    ["Google Gemini", "Gratuit/inclus", "3 Mrd Gmail", "N/A (Google)", "Triage inbox + auto-drafts"],
    ["Apple Intelligence", "Gratuit", "iPhone 15 Pro+", "N/A (Apple)", "On-device, vie privée"],
    ["Superhuman", "30-40$/mois", "~70 000", "118M$ (val. 825M$)", "Auto-drafts + style adapté"],
    ["Shortwave", "0-9$/mois", "N/A", "9M$", "Ghostwriter + recherche IA"],
    ["MailMaestro", "~15$/mois", "N/A", "1,3M$", "Multi-LLM, Outlook add-in"],
    ["Instantly AI", "30-358$/mois", "N/A", "Bootstrap ~80M$ ARR", "Cold email optimisé"],
    ["Lemlist", "59-99$/mois", "N/A", "Bootstrap 40M$ ARR", "Français, multicanal"],
    ["Lindy AI", "49$/mois+", "N/A", "49,9M$", "Agents IA no-code"],
]

add_styled_table(headers_comp, rows_comp, col_widths=[3.2, 2.5, 2.5, 3.5, 4.3])


# ═══════════════════════════════════════════════════════════════
# 4. FORCES UNIQUES D'EASYMAIL
# ═══════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading("4. Les forces uniques d'EasyMail", level=1)
add_separator()

p = doc.add_paragraph()
run = p.add_run(
    "EasyMail se distingue par des avantages compétitifs qu'aucun concurrent "
    "ne combine actuellement. Ces différenciateurs constituent le coeur de la proposition de valeur."
)
run.font.name = 'Calibri'
run.font.size = Pt(11)
doc.add_paragraph()

headers_forces = ["Fonctionnalité", "EasyMail", "Concurrents"]
rows_forces = [
    ["Profils par contact", "OUI - Profil D persistant par correspondant", "NON - Aucun (Superhuman adapte mais sans profil persistant)"],
    ["Apprentissage par corrections", "OUI - Feedback loop + recalibrage automatique", "NON - Aucun concurrent"],
    ["Exécution 100% locale", "OUI - COM Outlook, zéro cloud", "NON - Tous sont cloud"],
    ["Détection d'échéances", "OUI - Scan IA + relance automatique", "NON - Seul Alfred fait vaguement"],
    ["Base connaissances métier", "OUI - Planifié (bloc K)", "NON - Aucun concurrent"],
]

table = doc.add_table(rows=1 + len(rows_forces), cols=3)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.autofit = False
col_w = [4, 5.5, 6.5]

# En-têtes
for i, h in enumerate(headers_forces):
    cell = table.rows[0].cells[i]
    set_cell_shading(cell, "1B3A5C")
    set_cell_border(cell)
    format_cell(cell, h, bold=True, font_color=BLANC, size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
    cell.width = Cm(col_w[i])

# Données
for r_idx, row_data in enumerate(rows_forces):
    for c_idx, value in enumerate(row_data):
        cell = table.rows[r_idx + 1].cells[c_idx]
        bg = "F2F2F2" if r_idx % 2 == 0 else "FFFFFF"
        set_cell_shading(cell, bg)
        set_cell_border(cell)
        cell.width = Cm(col_w[c_idx])

        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(3)
        p.paragraph_format.space_after = Pt(3)

        if c_idx == 0:
            # Nom de la fonctionnalité
            run = p.add_run(value)
            run.font.name = 'Calibri'
            run.font.size = Pt(9.5)
            run.font.bold = True
            run.font.color.rgb = GRIS_TEXTE
        elif value.startswith("OUI"):
            run = p.add_run("  ")  # checkmark space
            run.font.size = Pt(9.5)
            run = p.add_run(value.replace("OUI - ", ""))
            run.font.name = 'Calibri'
            run.font.size = Pt(9.5)
            run.font.color.rgb = VERT
        elif value.startswith("NON"):
            run = p.add_run(value.replace("NON - ", ""))
            run.font.name = 'Calibri'
            run.font.size = Pt(9.5)
            run.font.color.rgb = ROUGE

doc.add_paragraph()

# Message clé encadré
p = doc.add_paragraph()
p.paragraph_format.space_before = Pt(12)
p.paragraph_format.space_after = Pt(12)
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run(
    "EasyMail est le SEUL assistant email IA combinant profils persistants, "
    "apprentissage par corrections et exécution 100% locale."
)
run.font.name = 'Calibri'
run.font.size = Pt(12)
run.font.color.rgb = BLEU_FONCE
run.font.bold = True
run.font.italic = True


# ═══════════════════════════════════════════════════════════════
# 5. FAIBLESSES A COMBLER
# ═══════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('5. Faiblesses à combler', level=1)
add_separator()

p = doc.add_paragraph()
run = p.add_run(
    "Malgré des fondamentaux solides, EasyMail doit combler certaines lacunes fonctionnelles "
    "pour rester compétitif face aux solutions établies."
)
run.font.name = 'Calibri'
run.font.size = Pt(11)
doc.add_paragraph()

headers_weak = ["Priorité", "Fonctionnalité manquante", "Référence marché"]
rows_weak = [
    ["CRITIQUE", "Auto-drafts proactifs (réponse prête avant le clic)", "Superhuman, Fyxer, Alfred"],
    ["CRITIQUE", "Triage intelligent inbox (urgence / importance)", "SaneBox, Superhuman, Shortwave"],
    ["IMPORTANT", "Briefing matinal quotidien", "Alfred, Google CC"],
    ["IMPORTANT", "Intégration calendrier (créneaux réels)", "Shortwave, Alfred, Notion Mail"],
    ["IMPORTANT", "Suivi des relances automatique", "Mailbutler, SaneBox"],
    ["SOUHAITABLE", "Support Gmail", "Quasi tous les concurrents"],
    ["SOUHAITABLE", "Version mobile", "Quasi tous les concurrents"],
]

table = doc.add_table(rows=1 + len(rows_weak), cols=3)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.autofit = False
col_w = [3, 6.5, 5]

# En-têtes
for i, h in enumerate(headers_weak):
    cell = table.rows[0].cells[i]
    set_cell_shading(cell, "1B3A5C")
    set_cell_border(cell)
    format_cell(cell, h, bold=True, font_color=BLANC, size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
    cell.width = Cm(col_w[i])

# Données
priority_colors = {
    "CRITIQUE": ("E74C3C", BLANC),
    "IMPORTANT": ("F39C12", BLANC),
    "SOUHAITABLE": ("F1C40F", GRIS_TEXTE),
}

for r_idx, row_data in enumerate(rows_weak):
    for c_idx, value in enumerate(row_data):
        cell = table.rows[r_idx + 1].cells[c_idx]
        cell.width = Cm(col_w[c_idx])
        set_cell_border(cell)

        if c_idx == 0:
            bg, fc = priority_colors.get(value, ("F2F2F2", GRIS_TEXTE))
            set_cell_shading(cell, bg)
            format_cell(cell, value, bold=True, font_color=fc, size=9, align=WD_ALIGN_PARAGRAPH.CENTER)
        else:
            bg = "F2F2F2" if r_idx % 2 == 0 else "FFFFFF"
            set_cell_shading(cell, bg)
            format_cell(cell, value, size=9.5)

doc.add_paragraph()


# ═══════════════════════════════════════════════════════════════
# 6. STRATEGIE RECOMMANDEE
# ═══════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('6. Stratégie recommandée', level=1)
add_separator()

p = doc.add_paragraph()
run = p.add_run(
    "La stratégie de développement d'EasyMail s'articule en trois phases progressives, "
    "chacune construisant sur la précédente pour maximiser l'impact et la rétention utilisateur."
)
run.font.name = 'Calibri'
run.font.size = Pt(11)

# Phase 1
doc.add_paragraph()
doc.add_heading("6.1  Phase 1 — L'effet wow (immédiat)", level=2)

# Encadré Phase 1
table = doc.add_table(rows=1, cols=1)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
cell = table.rows[0].cells[0]
set_cell_shading(cell, "E8F4E8")
cell.width = Cm(15)

p = cell.paragraphs[0]
p.paragraph_format.space_before = Pt(10)
p.paragraph_format.space_after = Pt(10)
run = p.add_run("OBJECTIF : ")
run.font.bold = True
run.font.size = Pt(11)
run.font.color.rgb = VERT
run.font.name = 'Calibri'
run = p.add_run("Qualité des réponses portée à 70%+ d'envoi direct sans modification")
run.font.size = Pt(11)
run.font.color.rgb = GRIS_TEXTE
run.font.name = 'Calibri'

p = doc.add_paragraph()
run = p.add_run(
    "C'est LE différenciateur fondamental. EasyMail doit produire des emails que l'utilisateur "
    "envoie tels quels, sans retouche. C'est la base sur laquelle tout le reste se construit. "
    "Un taux de 70% d'envoi direct transforme l'outil d'un assistant en un véritable collaborateur."
)
run.font.name = 'Calibri'
run.font.size = Pt(11)

# Phase 2
doc.add_paragraph()
doc.add_heading('6.2  Phase 2 — Auto-drafts proactifs (court terme)', level=2)

table = doc.add_table(rows=1, cols=1)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
cell = table.rows[0].cells[0]
set_cell_shading(cell, "E8ECF4")
cell.width = Cm(15)

p = cell.paragraphs[0]
p.paragraph_format.space_before = Pt(10)
p.paragraph_format.space_after = Pt(10)
run = p.add_run("OBJECTIF : ")
run.font.bold = True
run.font.size = Pt(11)
run.font.color.rgb = BLEU_MOYEN
run.font.name = 'Calibri'
run = p.add_run("La réponse est DÉJÀ prête quand l'utilisateur ouvre un email")
run.font.size = Pt(11)
run.font.color.rgb = GRIS_TEXTE
run.font.name = 'Calibri'

p = doc.add_paragraph()
run = p.add_run(
    "La spéculation streaming existe déjà dans l'architecture d'EasyMail. Il suffit de l'étendre "
    "pour que le brouillon soit visible avant même de cliquer sur 'Répondre'. "
    "C'est la fonctionnalité phare de Superhuman — EasyMail peut faire mieux grâce aux profils "
    "persistants qui permettent une personnalisation impossible chez les concurrents."
)
run.font.name = 'Calibri'
run.font.size = Pt(11)

# Phase 3
doc.add_paragraph()
doc.add_heading('6.3  Phase 3 — Triage & briefing (moyen terme)', level=2)

table = doc.add_table(rows=1, cols=1)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
cell = table.rows[0].cells[0]
set_cell_shading(cell, "FEF3E2")
cell.width = Cm(15)

p = cell.paragraphs[0]
p.paragraph_format.space_before = Pt(10)
p.paragraph_format.space_after = Pt(10)
run = p.add_run("OBJECTIF : ")
run.font.bold = True
run.font.size = Pt(11)
run.font.color.rgb = ORANGE
run.font.name = 'Calibri'
run = p.add_run("Classer l'inbox par priorité et fournir un résumé matinal actionnable")
run.font.size = Pt(11)
run.font.color.rgb = GRIS_TEXTE
run.font.name = 'Calibri'

p = doc.add_paragraph()
run = p.add_run(
    "Classification automatique : urgent / important / informatif / spam. "
    "Résumé matinal des actions en attente avec suggestions de réponse. "
    "Cette fonctionnalité transforme EasyMail d'un outil réactif en un véritable assistant "
    "proactif qui anticipe les besoins de l'utilisateur."
)
run.font.name = 'Calibri'
run.font.size = Pt(11)


# ═══════════════════════════════════════════════════════════════
# 7. POSITIONNEMENT TARIFAIRE
# ═══════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('7. Positionnement tarifaire recommandé', level=1)
add_separator()

p = doc.add_paragraph()
run = p.add_run(
    "Le positionnement tarifaire doit refléter la valeur unique de la solution "
    "tout en restant accessible par rapport aux alternatives du marché."
)
run.font.name = 'Calibri'
run.font.size = Pt(11)
doc.add_paragraph()

# Tableau pricing
table = doc.add_table(rows=3, cols=3)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.autofit = False
col_w_pricing = [4, 4, 7]

# En-tête
for i, h in enumerate(["Formule", "Prix mensuel", "Justification"]):
    cell = table.rows[0].cells[i]
    set_cell_shading(cell, "1B3A5C")
    set_cell_border(cell)
    format_cell(cell, h, bold=True, font_color=BLANC, size=10, align=WD_ALIGN_PARAGRAPH.CENTER)
    cell.width = Cm(col_w_pricing[i])

pricing_data = [
    ["Individuel", "15 - 30 EUR/mois", "Accès complet, profils contacts, apprentissage continu"],
    ["Professionnel", "30 - 50 EUR/mois", "Multi-comptes, base connaissances métier, support prioritaire"],
]

for r_idx, row_data in enumerate(pricing_data):
    for c_idx, value in enumerate(row_data):
        cell = table.rows[r_idx + 1].cells[c_idx]
        bg = "F2F2F2" if r_idx % 2 == 0 else "FFFFFF"
        set_cell_shading(cell, bg)
        set_cell_border(cell)
        cell.width = Cm(col_w_pricing[c_idx])
        bold = (c_idx == 1)
        format_cell(cell, value, bold=bold, size=10)

doc.add_paragraph()

p = doc.add_paragraph()
run = p.add_run("Justification du premium : ")
run.font.bold = True
run.font.size = Pt(11)
run.font.color.rgb = BLEU_FONCE
run.font.name = 'Calibri'
run = p.add_run(
    "la confidentialité locale (zéro données cloud) combinée à l'apprentissage continu "
    "et aux profils persistants par contact justifient un tarif supérieur aux 9-15 EUR "
    "des plugins email IA basiques."
)
run.font.size = Pt(11)
run.font.color.rgb = GRIS_TEXTE
run.font.name = 'Calibri'


# ═══════════════════════════════════════════════════════════════
# 8. CONCLUSION
# ═══════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('8. Conclusion', level=1)
add_separator()

p = doc.add_paragraph()
run = p.add_run(
    "EasyMail occupe une position unique et défendable sur le marché des assistants email IA "
    "grâce à trois avantages compétitifs qu'aucun concurrent ne combine :"
)
run.font.name = 'Calibri'
run.font.size = Pt(11)

conclusions = [
    ("Les profils persistants par contact", " — chaque correspondant a un profil enrichi au fil des échanges, "
     "permettant une personnalisation impossible chez les concurrents."),
    ("L'apprentissage par corrections", " — chaque modification de l'utilisateur améliore les futures suggestions, "
     "créant un cercle vertueux unique sur le marché."),
    ("L'exécution 100% locale", " — aucune donnée ne transite par le cloud, garantissant une confidentialité "
     "totale dans un marché où c'est un différenciateur croissant."),
]

for bold_part, normal_part in conclusions:
    p = doc.add_paragraph(style='List Bullet')
    run = p.add_run(bold_part)
    run.font.bold = True
    run.font.size = Pt(11)
    run.font.color.rgb = BLEU_FONCE
    run.font.name = 'Calibri'
    run = p.add_run(normal_part)
    run.font.size = Pt(11)
    run.font.color.rgb = GRIS_TEXTE
    run.font.name = 'Calibri'

doc.add_paragraph()

# Message final encadré
table = doc.add_table(rows=1, cols=1)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
cell = table.rows[0].cells[0]
set_cell_shading(cell, "1B3A5C")
cell.width = Cm(15)

p = cell.paragraphs[0]
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(15)
p.paragraph_format.space_after = Pt(15)
run = p.add_run(
    "La priorité absolue est de transformer cette architecture supérieure\n"
    "en qualité de réponse perceptible — l'effet wow —\n"
    "avant d'étendre les fonctionnalités vers les auto-drafts et le triage intelligent."
)
run.font.name = 'Calibri'
run.font.size = Pt(13)
run.font.color.rgb = BLANC
run.font.bold = True
run.font.italic = True


# ═══════════════════════════════════════════════════════════════
# EN-TETES ET PIEDS DE PAGE
# ═══════════════════════════════════════════════════════════════

for section in doc.sections:
    # En-tête
    header = section.header
    header.is_linked_to_previous = False
    p = header.paragraphs[0] if header.paragraphs else header.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run("EasyMail — Analyse Concurrentielle | Mars 2026")
    run.font.name = 'Calibri'
    run.font.size = Pt(8)
    run.font.color.rgb = BLEU_MOYEN
    run.font.italic = True

    # Pied de page
    footer = section.footer
    footer.is_linked_to_previous = False
    p = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("CONFIDENTIEL")
    run.font.name = 'Calibri'
    run.font.size = Pt(8)
    run.font.color.rgb = ROUGE
    run.font.bold = True


# ── Sauvegarde ──
output_path = r"C:\Users\yvanb\OneDrive\Desktop\.claude\EasyMail\Analyse_Concurrentielle_EasyMail.docx"
doc.save(output_path)
print(f"Rapport généré : {output_path}")
