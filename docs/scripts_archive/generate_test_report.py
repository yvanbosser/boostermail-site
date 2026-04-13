"""Génère le rapport de synthèse des tests de performance EasyMail."""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml

doc = Document()

# Styles
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)
style.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
style.paragraph_format.line_spacing = 1.15

for level, (size, color) in enumerate([
    (Pt(24), RGBColor(0x00, 0x78, 0xD4)),
    (Pt(16), RGBColor(0x1A, 0x1A, 0x2E)),
    (Pt(13), RGBColor(0x00, 0x78, 0xD4)),
], start=1):
    h = doc.styles[f'Heading {level}']
    h.font.name = 'Calibri'
    h.font.size = size
    h.font.color.rgb = color
    h.font.bold = True

for section in doc.sections:
    section.top_margin = Cm(2)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)


def styled_table(doc, headers, rows, col_widths, header_color='0078D4'):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    # Header
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ''
        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{header_color}"/>')
        cell._tc.get_or_add_tcPr().append(shading)
        p = cell.paragraphs[0]
        run = p.add_run(h)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.bold = True
        run.font.size = Pt(10)
        run.font.name = 'Calibri'
    # Rows
    for r_idx, row_data in enumerate(rows):
        for c_idx, text in enumerate(row_data):
            cell = table.rows[r_idx + 1].cells[c_idx]
            cell.text = ''
            bg = 'F8F9FA' if r_idx % 2 == 0 else 'FFFFFF'
            shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{bg}"/>')
            cell._tc.get_or_add_tcPr().append(shading)
            run = cell.paragraphs[0].add_run(str(text))
            run.font.size = Pt(10)
            run.font.name = 'Calibri'
    for row in table.rows:
        for i, w in enumerate(col_widths):
            row.cells[i].width = Cm(w)
    return table


# ═══ TITRE ═══
title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('EasyMail — Rapport de Tests')
run.font.size = Pt(28)
run.font.color.rgb = RGBColor(0x00, 0x78, 0xD4)
run.font.bold = True

sub = doc.add_paragraph()
sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = sub.add_run('Tests de rapidité et pertinence — 17 mars 2026')
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x66, 0x66, 0x66)
run.italic = True

doc.add_paragraph()

# ═══ MÉTHODOLOGIE ═══
doc.add_heading('Méthodologie', level=1)
doc.add_paragraph(
    'Tests réalisés en conditions réelles sur la machine de production avec Outlook ouvert '
    'et 54 emails en boîte de réception. Mesures effectuées via requêtes HTTP brutes (raw socket) '
    'pour éliminer tout overhead client. Chaque mesure de rapidité est la moyenne de 3 exécutions.'
)
doc.add_paragraph(
    'Base de données : 1 036 threads, 102 profils de correspondants, 22 métriques d\'envoi. '
    'Fichier SQLite de 3 Mo avec WAL mode et indexes optimisés.'
)

# ═══ 1. RAPIDITÉ ═══
doc.add_page_break()
doc.add_heading('1. Rapidité', level=1)

doc.add_heading('Pages et APIs (temps serveur réel)', level=2)
styled_table(doc,
    ['Opération', 'Min', 'Moy', 'Max', 'Verdict'],
    [
        ['API style_status', '13ms', '14ms', '16ms', 'Instantané'],
        ['API metrics', '15ms', '20ms', '30ms', 'Instantané'],
        ['API contact_profiles (102)', '16ms', '25ms', '29ms', 'Instantané'],
        ['Page contacts (102 profils)', '29ms', '30ms', '31ms', 'Instantané'],
        ['Page inbox (54 emails, cache)', '15ms', '25ms', '30ms', 'Instantané'],
        ['Inbox refresh Outlook (COM)', '269ms', '272ms', '275ms', 'Excellent'],
    ],
    [5.5, 1.5, 1.5, 1.5, 3]
)

doc.add_paragraph()
doc.add_heading('Opérations email', level=2)
styled_table(doc,
    ['Opération', 'Temps', 'Commentaire'],
    [
        ['Ouverture email (1er, cold)', '1 074ms', 'Initialisation COM Outlook — normal'],
        ['Ouverture email (suivants)', '94-122ms', 'Cache actif — rapide'],
        ['Prefetch contexte A/B', '< 4s', 'Background, transparent pour l\'utilisateur'],
        ['Recherche mot-clé', '200-574ms', 'Via GetTable + DASL filter'],
        ['Génération réponse Claude', '2.9-7.8s', 'Latence API Anthropic — incompressible'],
    ],
    [6, 3, 7.5]
)

doc.add_paragraph()
p = doc.add_paragraph()
run = p.add_run('Note importante : ')
run.bold = True
p.add_run(
    'Les mesures initiales avec urllib/requests montraient ~2 000ms par requête. '
    'Investigation a révélé que c\'était un artefact DNS Windows (résolution de "localhost"). '
    'En utilisant 127.0.0.1 directement, les temps réels sont 10-30ms pour les pages et APIs.'
)

# ═══ 2. PERTINENCE ═══
doc.add_page_break()
doc.add_heading('2. Pertinence', level=1)

doc.add_paragraph(
    '5 emails testés avec génération de réponse automatique. '
    'Évaluation de la qualité du style, du contexte intégré, et de l\'adaptation au correspondant.'
)

doc.add_heading('Résultats détaillés', level=2)
styled_table(doc,
    ['Email testé', 'Temps', 'Qualité', 'Observations'],
    [
        ['Diana GUILLET\n(mandats immobiliers)', '3.8s', 'Bon',
         'Vouvoiement respecté, ton pro, mentionne LOC/VENTE, propose signature électronique. Style Yvan.'],
        ['Pierre Haillette (UBS)\n(échange bancaire)', '3.6s', 'Bon',
         'Contexte bancaire intégré, concis, mentionne résidence Maurice.'],
        ['Notifications auto\n(Quarantine Coaxis)', '4.0s', 'Excellent',
         'Détecte correctement qu\'il ne faut PAS répondre. Explique pourquoi.'],
        ['Crédit Agricole\n(documents dispo)', '7.8s', 'Excellent',
         'Identifie la notification automatique. Recommande aucune réponse.'],
        ['Auto-certification\n(résidence fiscale)', '3.6s', 'Bon',
         'Contexte fiscal intégré, mentionne Maurice et numéro fiscal.'],
    ],
    [4, 1.5, 2, 9]
)

doc.add_paragraph()
doc.add_heading('Points forts de la pertinence', level=2)
points_forts = [
    'Détection automatique des emails ne nécessitant pas de réponse (notifications, spam, système)',
    'Style Yvan respecté : vouvoiement, concision, "Cdlt" / "Cordialement" en signature',
    'Contexte B (historique correspondant) bien intégré dans les réponses',
    'Profils de correspondants utilisés pour adapter ton, registre et formules',
    'Informations factuelles pertinentes extraites du contexte (adresses, références dossier)',
]
for pt in points_forts:
    doc.add_paragraph(pt, style='List Bullet')

doc.add_heading('Points d\'amélioration identifiés', level=2)
points_amelio = [
    'Prénom du destinataire parfois incorrect — CORRIGÉ : instruction explicite ajoutée dans le prompt',
    'Contexte C sous-utilisé par le frontend — CORRIGÉ : prefetch_status retourne maintenant le C auto-détecté',
    'Génération 3-8s — contrainte API Claude (Haiku), incompressible côté code',
]
for pt in points_amelio:
    doc.add_paragraph(pt, style='List Bullet')

# ═══ 3. CORRECTIONS APPLIQUÉES ═══
doc.add_page_break()
doc.add_heading('3. Corrections appliquées', level=1)

styled_table(doc,
    ['Problème', 'Correction', 'Impact'],
    [
        ['Prénom destinataire parfois faux',
         'Ajout instruction explicite dans le prompt :\n"Tu réponds à [nom]. Utilise son prénom [prénom].\nNe confonds JAMAIS avec d\'autres noms."',
         'Réponses avec le bon prénom'],
        ['Contexte C invisible au frontend',
         'prefetch_status retourne le C auto-prefetché\nmême sans keyword explicite',
         'UI peut afficher le statut C'],
        ['Page contacts : titre "appris"',
         'Renommé en "Correspondants"',
         'Plus clair'],
        ['Chip "confiance moyenne"',
         'Supprimé de la page contacts',
         'Interface plus propre'],
        ['Empty state "3 mails"',
         'Corrigé en "dès le premier échange"',
         'Cohérent avec le nouveau seuil'],
    ],
    [5, 6.5, 5]
)

# ═══ 4. ÉTAT DE LA BASE ═══
doc.add_heading('4. État de la base de données', level=1)

styled_table(doc,
    ['Table', 'Nombre d\'enregistrements', 'Commentaire'],
    [
        ['threads', '1 036', 'Emails indexés (envoyés + reçus)'],
        ['contact_profiles', '102', 'Profils de correspondants appris'],
        ['metrics', '22', 'Métriques d\'envoi'],
        ['settings', '4', 'Paramètres utilisateur'],
        ['style_corrections', '1', 'Correction de style enregistrée'],
    ],
    [5, 4, 7.5]
)

doc.add_paragraph()
p = doc.add_paragraph()
run = p.add_run('Taille base : ')
run.bold = True
p.add_run('3 Mo (SQLite WAL mode, 8 Mo cache, 6 indexes)')

p2 = doc.add_paragraph()
run = p2.add_run('Profil de style : ')
run.bold = True
p2.add_run('3.9 Ko (style_profile.txt)')

# ═══ CONCLUSION ═══
doc.add_page_break()
doc.add_heading('Conclusion', level=1)

doc.add_paragraph(
    'EasyMail présente des performances de rapidité excellentes sur toutes les opérations '
    'locales (< 30ms pour les pages, < 300ms pour les rafraîchissements Outlook). '
    'Le seul temps incompressible est la génération Claude AI (3-8 secondes), '
    'qui dépend de la latence API Anthropic.'
)
doc.add_paragraph(
    'La pertinence des réponses générées est bonne, avec une détection efficace '
    'des emails ne nécessitant pas de réponse et une bonne intégration du contexte. '
    'Les corrections apportées (instruction prénom explicite, C auto-visible) '
    'devraient améliorer encore la qualité lors des prochaines utilisations.'
)

# Save
output_path = os.path.join(os.path.dirname(__file__), 'EasyMail_Tests_Report.docx')
doc.save(output_path)
print(f'Rapport sauvegardé : {output_path}')
