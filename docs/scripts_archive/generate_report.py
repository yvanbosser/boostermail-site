"""Génère le rapport de présentation EasyMail."""
from docx import Document
from docx.shared import Inches, Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
import os

doc = Document()

# ─── Styles ───────────────────────────────────────────────
style = doc.styles['Normal']
style.font.name = 'Calibri'
style.font.size = Pt(11)
style.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
style.paragraph_format.space_after = Pt(6)
style.paragraph_format.line_spacing = 1.3

for level, size, color in [(1, 22, (0x1a, 0x1a, 0x2e)), (2, 16, (0x00, 0x78, 0xd4)), (3, 13, (0x33, 0x33, 0x33))]:
    h = doc.styles[f'Heading {level}']
    h.font.name = 'Calibri'
    h.font.size = Pt(size)
    h.font.color.rgb = RGBColor(*color)
    h.font.bold = True
    h.paragraph_format.space_before = Pt(18 if level == 1 else 12)
    h.paragraph_format.space_after = Pt(8)

# ─── Page de couverture ───────────────────────────────────
for _ in range(6):
    doc.add_paragraph('')

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('EasyMail')
run.font.size = Pt(42)
run.font.color.rgb = RGBColor(0x00, 0x78, 0xd4)
run.bold = True

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run("L'assistant email intelligent")
run.font.size = Pt(18)
run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)

doc.add_paragraph('')

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Outlook + Claude AI')
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x00, 0x78, 0xd4)

for _ in range(6):
    doc.add_paragraph('')

p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('Mars 2026')
run.font.size = Pt(12)
run.font.color.rgb = RGBColor(0x99, 0x99, 0x99)

doc.add_page_break()

# ─── Sommaire ─────────────────────────────────────────────
doc.add_heading('Sommaire', level=1)

toc_items = [
    ('1.', "Qu'est-ce qu'EasyMail ?"),
    ('2.', "Le probleme que l'on resout"),
    ('3.', 'Fonctionnalites cles'),
    ('4.', 'EasyMail vs Copilot Outlook'),
    ('5.', 'EasyMail vs gestion email classique'),
    ('6.', 'Architecture technique'),
    ('7.', 'Roadmap'),
]
for num, title in toc_items:
    p = doc.add_paragraph()
    run = p.add_run(f'{num}  {title}')
    run.font.size = Pt(12)
    run.font.color.rgb = RGBColor(0x33, 0x33, 0x33)

doc.add_page_break()

# ─── 1. Qu'est-ce qu'EasyMail ? ──────────────────────────
doc.add_heading("1. Qu'est-ce qu'EasyMail ?", level=1)

doc.add_paragraph(
    "EasyMail est un assistant email personnel qui se connecte directement "
    "a votre boite Outlook et utilise l'intelligence artificielle (Claude, par Anthropic) "
    "pour generer des reponses et des emails dans VOTRE style redactionnel."
)

doc.add_paragraph(
    "Contrairement aux outils generiques, EasyMail apprend votre facon d'ecrire "
    "en analysant vos 100 derniers mails envoyes. Il reproduit vos formules de politesse, "
    "votre ton, votre niveau de formalite et vos habitudes de communication."
)

doc.add_heading('Les 3 piliers', level=2)

pillars = [
    ("Personnalisation totale", "L'IA ecrit comme vous, pas comme un robot. Votre style, vos formules, votre ton."),
    ("Contexte intelligent", "EasyMail recherche dans votre historique de correspondance pour comprendre le contexte de chaque echange."),
    ("Simplicite d'utilisation", "Interface web epuree, accessible depuis n'importe quel navigateur sur votre reseau local."),
]
for title, desc in pillars:
    p = doc.add_paragraph()
    run = p.add_run(f'{title} : ')
    run.bold = True
    run.font.color.rgb = RGBColor(0x00, 0x78, 0xd4)
    p.add_run(desc)

doc.add_page_break()

# ─── 2. Le probleme ──────────────────────────────────────
doc.add_heading("2. Le probleme que l'on resout", level=1)

doc.add_paragraph(
    "Un professionnel passe en moyenne 2h30 par jour a gerer ses emails. "
    "La majorite de ce temps est consacre a la redaction, pas a la prise de decision."
)

doc.add_heading("Ce que l'on observe au quotidien", level=2)

problems = [
    "Repondre a un email prend 5 a 15 minutes quand le sujet est technique ou sensible",
    "On relit 3 fois avant d'envoyer pour s'assurer du ton",
    "On cherche manuellement dans l'historique pour retrouver un contexte",
    "Les brouillons generiques de Copilot sonnent faux et necessitent une reecriture complete",
    "Les pieces jointes sont ignorees par les outils IA standards",
]
for prob in problems:
    p = doc.add_paragraph(prob, style='List Bullet')

doc.add_heading("Ce qu'EasyMail change", level=2)

doc.add_paragraph(
    "EasyMail reduit le temps de traitement d'un email de 10 minutes a 30 secondes. "
    "L'utilisateur passe du role de redacteur a celui de validateur : "
    "il relit, ajuste si necessaire, et envoie."
)

doc.add_page_break()

# ─── 3. Fonctionnalites cles ─────────────────────────────
doc.add_heading('3. Fonctionnalites cles', level=1)

features = [
    ("Boite de reception intelligente",
     "Affichage de tous vos mails avec indicateur de pieces jointes, "
     "suppression directe (corbeille), et actualisation automatique."),

    ("Generation de reponses IA",
     "Un clic sur 'Generer' produit une reponse dans votre style. "
     "3 niveaux d'importance (Rapide / Standard / Haute) controlent la profondeur "
     "de recherche dans l'historique."),

    ("Analyse de votre style redactionnel",
     "Au premier lancement, EasyMail analyse vos 100 derniers mails envoyes "
     "pour creer un profil de style unique : formules de politesse, niveau de "
     "formalite, tournures recurrentes, signature."),

    ("Recherche contextuelle par mot-cle",
     "Saisissez un mot-cle (nom de dossier, societe, sujet) et EasyMail "
     "retrouve automatiquement les echanges pertinents pour enrichir la reponse."),

    ("Gestion avancee des pieces jointes",
     "Affichage sous la date (3 visibles + menu deroulant), telechargement direct, "
     "analyse du contenu des PJ par l'IA pour des reponses plus precises, "
     "selection granulaire des PJ a inclure lors d'un transfert (cases a cocher)."),

    ("Modification iterative",
     "Barre 'Modifier' pour affiner la reponse generee par instruction naturelle "
     "(ex: 'ton plus ferme', 'raccourcir', 'ajouter une relance'). "
     "Bouton retour pour annuler chaque modification."),

    ("Historique des versions",
     "Bouton 'Autre proposition' pour regenerer. Fleche retour pour revenir "
     "a une version precedente. Empilement illimite."),

    ("Repondre / Repondre a tous / Transferer",
     "Gestion complete des modes de reponse avec pre-remplissage intelligent "
     "des destinataires, sujet, et pieces jointes."),

    ("Nouveau mail",
     "Composition de mails originaux avec le meme moteur IA, "
     "les memes outils de modification, et la meme qualite de style."),

    ("Editeur riche",
     "Barre d'outils avec police, taille, gras, italique, listes, "
     "pieces jointes, et mise en forme professionnelle."),

    ("Carnet de correspondants",
     "Base de contacts enrichie automatiquement a partir de vos echanges. "
     "Chaque fiche affiche le ton, le registre, les formules d'ouverture/cloture, "
     "et l'organisation du contact. Bouton 'Modifier' pour corriger manuellement "
     "toute information."),
]

for title, desc in features:
    doc.add_heading(title, level=2)
    doc.add_paragraph(desc)

doc.add_page_break()

# ─── 4. EasyMail vs Copilot ──────────────────────────────
doc.add_heading('4. EasyMail vs Copilot dans Outlook', level=1)

doc.add_paragraph(
    "Copilot dans Outlook (Microsoft 365) est un outil generique. "
    "EasyMail est un assistant personnel. Voici les differences concretes :"
)

# Tableau comparatif
table = doc.add_table(rows=1, cols=3)
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.style = 'Light Grid Accent 1'

# En-tete
for i, text in enumerate(['Critere', 'Copilot Outlook', 'EasyMail']):
    cell = table.rows[0].cells[i]
    cell.text = text
    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in paragraph.runs:
            run.bold = True
            run.font.size = Pt(10)

comparisons = [
    ("Style de redaction", "Generique, ton Microsoft", "Votre style personnel appris"),
    ("Apprentissage", "Aucun", "Analyse de 100 mails envoyes"),
    ("Contexte historique", "Limte au fil de discussion", "Recherche dans tout l'historique par mot-cle"),
    ("Pieces jointes", "Non analysees", "Analyse du contenu pour enrichir la reponse"),
    ("Modification iterative", "Regeneration complete", "Instructions naturelles + undo"),
    ("Versioning", "Non", "Pile de versions avec retour arriere"),
    ("Correspondants", "Carnet Outlook basique", "Base enrichie automatiquement"),
    ("Prix", "30 EUR/mois/utilisateur", "Cout API Claude uniquement (~5 EUR/mois)"),
    ("Confidentialite", "Donnees Microsoft Cloud", "Traitement local + API Anthropic"),
    ("Personnalisation", "Aucune", "Profil de style, importance, brief"),
]

for critere, copilot, easymail in comparisons:
    row = table.add_row()
    row.cells[0].text = critere
    row.cells[1].text = copilot
    row.cells[2].text = easymail
    for cell in row.cells:
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.size = Pt(9)

doc.add_paragraph('')
p = doc.add_paragraph()
run = p.add_run('Verdict : ')
run.bold = True
run.font.color.rgb = RGBColor(0x00, 0x78, 0xd4)
p.add_run(
    "Copilot est un assistant generique qui ecrit comme Microsoft. "
    "EasyMail est VOTRE assistant qui ecrit comme VOUS."
)

doc.add_page_break()

# ─── 5. EasyMail vs gestion classique ────────────────────
doc.add_heading('5. EasyMail vs gestion email classique', level=1)

doc.add_paragraph(
    "Comparons le workflow quotidien d'un professionnel qui gere "
    "ses emails de maniere traditionnelle vs avec EasyMail :"
)

doc.add_heading("Scenario : repondre a un email complexe", level=2)

# Tableau workflow
table2 = doc.add_table(rows=1, cols=3)
table2.alignment = WD_TABLE_ALIGNMENT.CENTER
table2.style = 'Light Grid Accent 1'

for i, text in enumerate(['Etape', 'Sans EasyMail', 'Avec EasyMail']):
    cell = table2.rows[0].cells[i]
    cell.text = text
    for paragraph in cell.paragraphs:
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in paragraph.runs:
            run.bold = True
            run.font.size = Pt(10)

workflow = [
    ("Lire le mail", "2 min", "2 min"),
    ("Chercher le contexte", "5-10 min (recherche manuelle)", "0 min (automatique)"),
    ("Lire les PJ", "3-5 min", "0 min (analyse IA)"),
    ("Rediger la reponse", "5-15 min", "0 min (generation IA)"),
    ("Relire et ajuster", "2-3 min", "1 min (modifier par instruction)"),
    ("Envoyer", "30 sec", "30 sec"),
    ("TOTAL", "17-35 minutes", "3-4 minutes"),
]

for etape, sans, avec in workflow:
    row = table2.add_row()
    row.cells[0].text = etape
    row.cells[1].text = sans
    row.cells[2].text = avec
    for cell in row.cells:
        for paragraph in cell.paragraphs:
            for run in paragraph.runs:
                run.font.size = Pt(9)
    if etape == "TOTAL":
        for cell in row.cells:
            for paragraph in cell.paragraphs:
                for run in paragraph.runs:
                    run.bold = True

doc.add_paragraph('')
p = doc.add_paragraph()
run = p.add_run('Gain de temps : ')
run.bold = True
run.font.color.rgb = RGBColor(0x10, 0x7c, 0x10)
p.add_run(
    "Sur 30 emails/jour, EasyMail fait economiser 1h30 a 3h de travail quotidien. "
    "Soit 7 a 15 heures par semaine."
)

doc.add_page_break()

# ─── 6. Architecture technique ───────────────────────────
doc.add_heading('6. Architecture technique', level=1)

doc.add_paragraph(
    "EasyMail est une application web locale qui tourne sur votre poste."
)

components = [
    ("Frontend", "Interface web HTML/CSS/JS, style Outlook moderne, accessible via navigateur (localhost:5050)"),
    ("Backend", "Serveur Flask (Python) qui orchestre la communication entre Outlook et Claude"),
    ("Outlook COM", "Connexion directe a Outlook desktop via l'API COM Windows pour lire/envoyer les mails"),
    ("Claude API", "Modele Claude (Anthropic) pour la generation de texte, l'analyse de style et l'analyse de PJ"),
    ("Base locale", "SQLite pour le profil de style, les correspondants, et les parametres utilisateur"),
]

for title, desc in components:
    p = doc.add_paragraph()
    run = p.add_run(f'{title} : ')
    run.bold = True
    run.font.color.rgb = RGBColor(0x00, 0x78, 0xd4)
    p.add_run(desc)

doc.add_heading('Securite et confidentialite', level=2)

security = [
    "Aucune donnee stockee dans le cloud (hors appels API Claude)",
    "Les emails restent dans Outlook, jamais copies sur un serveur externe",
    "Le profil de style est stocke localement sur votre machine",
    "L'application tourne en local (localhost), non accessible de l'exterieur",
]
for item in security:
    doc.add_paragraph(item, style='List Bullet')

doc.add_page_break()

# ─── 7. Roadmap ──────────────────────────────────────────
doc.add_heading('7. Prochaines evolutions', level=1)

roadmap = [
    ("Court terme", [
        "Acces a l'agenda Outlook : lorsqu'un RDV est propose (envoye ou recu), "
        "EasyMail consulte automatiquement votre calendrier pour verifier vos disponibilites "
        "et suggere une reponse adaptee (creneaux libres, conflit, contre-proposition)",
        "Rappels automatiques des echeances : detection intelligente des dates limites, "
        "delais et engagements mentionnes dans vos mails (envoyes et recus). "
        "Notification proactive avant expiration",
        "Classement automatique des emails dans Outlook : organisation intelligente "
        "de vos mails dans les dossiers Outlook en fonction du sujet, du correspondant "
        "et de la priorite detectee par l'IA",
        "Mode multi-comptes (plusieurs boites Outlook)",
    ]),
    ("Moyen terme", [
        "Base de donnees de reponses metier : integration d'une base documentaire "
        "(type Compta Sante) pour alimenter l'IA avec des reponses types, "
        "des procedures et des references specifiques a votre domaine d'activite",
        "Gestion des brouillons",
        "Traduction automatique des mails recus",
        "Templates de reponse personnalises",
    ]),
    ("Long terme", [
        "Application desktop autonome (sans navigateur)",
        "Version mobile (iOS/Android)",
        "Mode equipe (partage de style entre collaborateurs)",
        "Integration CRM",
    ]),
]

for period, items in roadmap:
    doc.add_heading(period, level=2)
    for item in items:
        doc.add_paragraph(item, style='List Bullet')

# ─── Footer ──────────────────────────────────────────────
doc.add_paragraph('')
doc.add_paragraph('')
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
run = p.add_run('EasyMail — Vos mails, votre style, en 30 secondes.')
run.font.size = Pt(14)
run.font.color.rgb = RGBColor(0x00, 0x78, 0xd4)
run.bold = True
run.italic = True

# ─── Sauvegarde ──────────────────────────────────────────
output = r'C:\Users\yvanb\OneDrive\Desktop\.claude\easymail\EasyMail_Presentation_v2.docx'
doc.save(output)
print(f"Rapport sauvegarde : {output}")
