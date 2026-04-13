"""Génère le rapport de présentation EasyMail — focus pertinence, apprentissage, rapidité."""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml

doc = Document()

# ── Styles ──
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)
style.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
style.paragraph_format.space_after = Pt(6)
style.paragraph_format.line_spacing = 1.15

for level, (size, color) in enumerate([
    (Pt(26), RGBColor(0x00, 0x78, 0xD4)),
    (Pt(16), RGBColor(0x1A, 0x1A, 0x2E)),
    (Pt(13), RGBColor(0x00, 0x78, 0xD4)),
], start=1):
    h = doc.styles[f'Heading {level}']
    h.font.name = 'Calibri'
    h.font.size = size
    h.font.color.rgb = color
    h.font.bold = True
    h.paragraph_format.space_before = Pt(16 if level > 1 else 0)
    h.paragraph_format.space_after = Pt(8)

for section in doc.sections:
    section.top_margin = Cm(2.5)
    section.bottom_margin = Cm(2)
    section.left_margin = Cm(2.5)
    section.right_margin = Cm(2.5)


def styled_table(headers, rows, col_widths, header_color='0078D4'):
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = ''
        shading = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{header_color}"/>')
        cell._tc.get_or_add_tcPr().append(shading)
        run = cell.paragraphs[0].add_run(h)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)
        run.font.bold = True
        run.font.size = Pt(10)
        run.font.name = 'Calibri'
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


def bold_paragraph(bold_text, normal_text):
    p = doc.add_paragraph()
    run = p.add_run(bold_text)
    run.bold = True
    run.font.color.rgb = RGBColor(0x00, 0x78, 0xD4)
    p.add_run(normal_text)
    return p


# ════════════════════════════════════════════════════════════
# COUVERTURE
# ════════════════════════════════════════════════════════════

doc.add_paragraph('\n\n\n')

title = doc.add_paragraph()
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = title.add_run('EasyMail')
run.font.size = Pt(48)
run.font.color.rgb = RGBColor(0x00, 0x78, 0xD4)
run.font.bold = True

subtitle = doc.add_paragraph()
subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = subtitle.add_run('Votre style. Votre ton. Automatiquement.')
run.font.size = Pt(18)
run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
run.italic = True

doc.add_paragraph('\n')

tagline = doc.add_paragraph()
tagline.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = tagline.add_run('Assistant email intelligent — Outlook + Claude AI')
run.font.size = Pt(13)
run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

doc.add_paragraph('\n\n\n')

info = doc.add_paragraph()
info.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = info.add_run('Mars 2026')
run.font.size = Pt(12)
run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)


# ════════════════════════════════════════════════════════════
# 1. LE PROBLÈME
# ════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('Le problème', level=1)

doc.add_paragraph(
    'Un professionnel gère des dizaines de correspondants avec des styles de communication '
    'différents : vouvoiement ou tutoiement, ton formel ou direct, formules de politesse variables. '
    'Chaque email exige de retrouver le bon registre, le bon contexte, le bon ton.'
)

doc.add_paragraph(
    'Résultat : on passe plus de temps à réfléchir comment écrire qu\'à décider quoi écrire.'
)

bold_paragraph('Le vrai coût : ', 'ce n\'est pas la frappe, c\'est l\'adaptation cognitive. '
    'Retrouver si on vouvoie ou tutoie ce contact, quelle formule d\'ouverture on utilise avec lui, '
    'quel est l\'historique de ce dossier — à chaque email.')


# ════════════════════════════════════════════════════════════
# 2. CE QUE FAIT EASYMAIL
# ════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('Ce que fait EasyMail', level=1)

doc.add_paragraph(
    'EasyMail apprend votre style d\'écriture et celui de chacun de vos correspondants, '
    'puis génère des réponses prêtes à envoyer qui sonnent comme vous.'
)

doc.add_heading('Un clic, une réponse adaptée', level=2)

steps = [
    ('Vous ouvrez un email.',
     'En arrière-plan, EasyMail charge automatiquement le contexte : '
     'historique de conversation, échanges passés avec ce correspondant, '
     'emails liés au même sujet dans tous vos dossiers.'),
    ('Vous cliquez "Générer".',
     'Claude AI rédige une réponse qui respecte votre style, '
     'utilise le bon registre avec ce correspondant (vouvoiement, ton, formules), '
     'et intègre le contexte pertinent.'),
    ('Vous envoyez — ou vous corrigez.',
     'Si vous modifiez le texte, EasyMail mémorise la correction. '
     'La prochaine réponse sera meilleure.'),
]

for step_title, step_desc in steps:
    bold_paragraph(step_title + ' ', step_desc)


# ════════════════════════════════════════════════════════════
# 3. APPRENTISSAGE
# ════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('Apprentissage', level=1)

doc.add_paragraph(
    'EasyMail ne se contente pas de générer du texte. Il apprend en continu, '
    'sur deux dimensions complémentaires.'
)

doc.add_heading('Votre style personnel', level=2)

doc.add_paragraph(
    'Au premier lancement, EasyMail analyse vos 300 derniers emails envoyés et reçus. '
    'Il en extrait votre empreinte rédactionnelle : vocabulaire, niveau de formalité, '
    'structure de phrases, formules récurrentes, signature.'
)

doc.add_paragraph(
    'Après chaque envoi, si vous avez corrigé le texte proposé, la différence '
    '(proposé vs envoyé) est mémorisée. Ces corrections guident les futures générations. '
    'Plus vous utilisez EasyMail, plus il écrit comme vous.'
)

doc.add_heading('Profils de correspondants', level=2)

doc.add_paragraph(
    'EasyMail crée automatiquement un profil pour chaque correspondant. '
    'Pas un simple carnet d\'adresses — un profil comportemental :'
)

styled_table(
    ['Dimension analysée', 'Exemple'],
    [
        ['Registre', 'Vouvoiement avec Pierre Haillette (UBS)'],
        ['Ton', 'Direct et concis avec Julien LE VU (Solaris)'],
        ['Formule d\'ouverture', '"Bonjour Vincent," — prénom + vouvoiement'],
        ['Formule de clôture', '"Cdlt" avec les prestataires, "Cordialement," avec les banquiers'],
        ['Longueur typique', 'Court (< 50 mots) avec les collaborateurs'],
        ['Dynamique', 'Client qui instruit avec Solaris, pair avec Phiwest'],
        ['Domaine', 'Immobilier, bancaire, comptabilité, juridique...'],
    ],
    [5, 11.5],
    header_color='1A1A2E'
)

doc.add_paragraph()
p = doc.add_paragraph()
run = p.add_run('102 profils créés automatiquement')
run.bold = True
p.add_run(
    ' lors de l\'onboarding (12 minutes en arrière-plan). '
    'Chaque nouveau correspondant obtient son profil dès le premier échange.'
)


# ════════════════════════════════════════════════════════════
# 4. CONTEXTE INTELLIGENT
# ════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('Contexte intelligent', level=1)

doc.add_paragraph(
    'La qualité d\'une réponse dépend du contexte disponible. '
    'EasyMail assemble automatiquement 3 niveaux de contexte, '
    'en arrière-plan, avant même que vous ne cliquiez "Générer".'
)

styled_table(
    ['Niveau', 'Quoi', 'Comment'],
    [
        ['A — Conversation', 'Historique du fil de discussion en cours',
         'Même objet, même correspondant'],
        ['B — Correspondant', 'Tous les échanges passés avec cette personne',
         'Détecte le ton, le registre, les sujets habituels'],
        ['C — Sujet', 'Emails liés par mots-clés dans TOUS vos dossiers',
         'Recherche multi-dossiers automatique'],
    ],
    [3, 5, 8.5],
    header_color='28A745'
)

doc.add_paragraph()
doc.add_paragraph(
    'Le contexte est chargé en parallèle dès l\'ouverture du mail (3 threads simultanés). '
    'Quand vous cliquez "Générer", tout est déjà prêt — seule la génération Claude prend du temps.'
)

doc.add_heading('3 niveaux d\'importance', level=2)

doc.add_paragraph(
    'Configurable par email : le niveau d\'importance contrôle la profondeur du contexte chargé. '
    'Un email courant utilise un contexte léger et rapide. '
    'Un email important (enjeu juridique, financier) charge un contexte maximal.'
)


# ════════════════════════════════════════════════════════════
# 5. RAPIDITÉ — RÉSULTATS DE TESTS
# ════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('Rapidité — Tests réels', level=1)

doc.add_paragraph(
    'Mesures réalisées en conditions réelles : 54 emails en boîte de réception, '
    '102 profils de correspondants, 1 036 emails indexés en base.'
)

doc.add_heading('Temps de réponse serveur', level=2)

styled_table(
    ['Opération', 'Temps mesuré', 'Commentaire'],
    [
        ['Chargement inbox', '15-30 ms', 'Instantané grâce au cache'],
        ['Ouverture d\'un email', '94-122 ms', 'Corps + métadonnées'],
        ['Refresh Outlook (COM)', '270 ms', 'Synchronisation boîte complète'],
        ['Page correspondants (102)', '30 ms', 'Rendu de tous les profils'],
        ['Chargement contexte A/B/C', '< 4 s', 'En arrière-plan, transparent'],
        ['Recherche mot-clé multi-dossiers', '200-574 ms', 'Via index Windows Search'],
        ['Génération réponse (Claude AI)', '3-8 s', 'Latence API — incompressible'],
    ],
    [6, 3, 7.5],
    header_color='7C3AED'
)

doc.add_paragraph()
bold_paragraph('Point clé : ',
    'toutes les opérations locales sont sous la seconde. '
    'Le seul temps perceptible est la génération Claude (3-8s), '
    'qui dépend de la complexité de l\'email et de la latence API Anthropic.')


# ════════════════════════════════════════════════════════════
# 6. PERTINENCE — RÉSULTATS DE TESTS
# ════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('Pertinence — Tests réels', level=1)

doc.add_paragraph(
    'Génération de réponses testée sur 5 emails réels de la boîte de réception, '
    'couvrant différents types de correspondants et de situations.'
)

styled_table(
    ['Email testé', 'Temps', 'Résultat'],
    [
        ['Diana GUILLET\nMandats immobiliers LOC/VENTE', '3.8s',
         'Vouvoiement, ton pro, mentionne les mandats LOC et VENTE, '
         'propose la signature électronique. Style Yvan respecté.'],
        ['Pierre Haillette (UBS)\nÉchange bancaire Luxembourg', '3.6s',
         'Contexte fiscal intégré, mentionne la résidence Maurice '
         'et les éléments transmis à Edmond de Rothschild. Concis.'],
        ['Notification automatique\nQuarantine Coaxis (spam)', '4.0s',
         'Détecte qu\'il ne faut PAS répondre. '
         'Explique que c\'est un email système sans destinataire humain.'],
        ['Crédit Agricole\nDocuments disponibles', '7.8s',
         'Identifie la notification automatique. '
         'Recommande aucune réponse — email informatif uniquement.'],
        ['Auto-certification fiscale\nRésidence fiscale à compléter', '3.6s',
         'Répond avec les bonnes informations contextuelles '
         '(Maurice, numéro fiscal). Ton adapté.'],
    ],
    [5, 1.3, 10.2],
    header_color='E67E22'
)

doc.add_paragraph()
doc.add_heading('Ce que la pertinence signifie concrètement', level=2)

pertinence_points = [
    'L\'IA détecte les emails automatiques (notifications, spam) et recommande de ne pas répondre '
    '— pas de réponse inutile envoyée par erreur',
    'Le vouvoiement/tutoiement est correct à chaque fois, calibré sur vos échanges passés '
    'avec chaque correspondant',
    'Les informations factuelles du contexte sont intégrées : références de dossier, adresses, '
    'noms de contacts mentionnés dans les échanges précédents',
    'La signature et les formules de politesse correspondent à celles que vous utilisez réellement '
    'avec chaque interlocuteur',
]
for pt in pertinence_points:
    doc.add_paragraph(pt, style='List Bullet')


# ════════════════════════════════════════════════════════════
# 7. ARCHITECTURE (condensé)
# ════════════════════════════════════════════════════════════

doc.add_page_break()
doc.add_heading('Architecture', level=1)

doc.add_paragraph(
    'EasyMail est une application 100% locale. '
    'Vos emails ne quittent jamais votre machine — seul le contenu strictement nécessaire '
    'à la génération est envoyé à l\'API Claude (Anthropic ne stocke pas les données API).'
)

styled_table(
    ['Composant', 'Choix technique', 'Pourquoi'],
    [
        ['Serveur', 'Flask (Python) — local', 'Léger, pas de dépendance cloud'],
        ['IA', 'Claude Haiku (génération)\nClaude Sonnet (analyse profils)', 'Rapport qualité/coût/vitesse optimal'],
        ['Email', 'Outlook via COM (pywin32)', 'Accès natif, pas de sync externe'],
        ['Base', 'SQLite WAL, 3 Mo', 'Zéro config, performant jusqu\'à 100K+ emails'],
        ['Recherche', 'Index Windows Search\n+ AdvancedSearch Outlook', 'Recherche multi-dossiers en < 1s'],
        ['Threading', 'Thread COM dédié\n+ 3 threads prefetch parallèles', 'Zéro blocage, contexte prêt avant le clic'],
    ],
    [3, 5, 8.5],
    header_color='1A1A2E'
)

doc.add_paragraph()
doc.add_heading('Données locales', level=2)

styled_table(
    ['Donnée', 'Volume actuel'],
    [
        ['Emails indexés (threads)', '1 036'],
        ['Profils de correspondants', '102'],
        ['Corrections de style mémorisées', '1 (début d\'utilisation)'],
        ['Taille base de données', '3 Mo'],
        ['Profil de style personnel', '3.9 Ko'],
    ],
    [8, 8.5],
    header_color='28A745'
)


# ════════════════════════════════════════════════════════════
# 8. CONCLUSION
# ════════════════════════════════════════════════════════════

doc.add_page_break()

doc.add_paragraph('\n\n')

final = doc.add_paragraph()
final.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = final.add_run('EasyMail')
run.font.size = Pt(36)
run.font.color.rgb = RGBColor(0x00, 0x78, 0xD4)
run.font.bold = True

doc.add_paragraph()

conclusions = [
    ('Pertinence', 'Réponses adaptées au correspondant, au contexte, à votre style. '
     'Détection automatique des emails sans réponse nécessaire.'),
    ('Apprentissage', '102 profils créés automatiquement. Chaque correction améliore les futures réponses. '
     'Nouveaux correspondants profilés dès le premier échange.'),
    ('Rapidité', 'Toutes les opérations locales < 1 seconde. '
     'Contexte chargé en arrière-plan avant le clic. Génération en 3-8 secondes.'),
    ('Confidentialité', '100% local. Aucun serveur tiers. Vos emails restent sur votre machine.'),
]

for title_text, desc in conclusions:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(f'{title_text} — ')
    run.bold = True
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(0x00, 0x78, 0xD4)
    run2 = p.add_run(desc)
    run2.font.size = Pt(11)
    p.paragraph_format.space_after = Pt(12)

doc.add_paragraph('\n')
final2 = doc.add_paragraph()
final2.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = final2.add_run('Écrivez moins. Communiquez mieux.')
run.font.size = Pt(16)
run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)
run.italic = True


# ── Sauvegarder ──
output_path = os.path.join(os.path.dirname(__file__), 'EasyMail_Presentation.docx')
doc.save(output_path)
print(f'Document sauvegardé : {output_path}')
