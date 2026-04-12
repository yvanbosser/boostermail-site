"""
EasyMail — Analyse de style one-shot
Lit 80 mails envoyes depuis Outlook, les envoie a Claude pour analyse,
et sauvegarde le profil de style dans style_profile.txt.
"""
import json
import pythoncom
from outlook_com import OutlookClient
import anthropic

with open("config.json") as f:
    config = json.load(f)

client = anthropic.Anthropic(api_key=config["ANTHROPIC_API_KEY"])

print("[style] Connexion a Outlook...", flush=True)
outlook = OutlookClient()

print("[style] Lecture de 80 mails envoyes...", flush=True)
sent = outlook.get_sent_emails(limit=80)
print(f"[style] {len(sent)} mails lus", flush=True)

if len(sent) < 10:
    print("[style] ERREUR : pas assez de mails envoyes pour analyser le style")
    exit(1)

# Construire le corpus pour Claude
corpus_lines = []
for i, m in enumerate(sent, 1):
    corpus_lines.append(f"--- Mail {i} ---")
    corpus_lines.append(f"A: {m['to']}")
    corpus_lines.append(f"Objet: {m['subject']}")
    corpus_lines.append(f"Date: {m['date']}")
    corpus_lines.append(m['body'][:2000])  # Tronquer les mails tres longs
    corpus_lines.append("")

corpus = "\n".join(corpus_lines)

ANALYSIS_PROMPT = """Analyse ces mails envoyes par un utilisateur et extrais son profil de style redactionnel.

Sois TRES precis et concret. Donne des exemples reels tires des mails.

Structure ton analyse ainsi :

## 1. Formules d'ouverture
Liste les formules d'ouverture utilisees avec leur frequence (ex: "Bonjour Vincent," = 15 fois)

## 2. Formules de cloture
Liste les formules de cloture (ex: "Bien cordialement" = 12 fois, "Cordialement" = 8 fois)

## 3. Signature
Comment signe-t-il ? (prenom seul, prenom + nom, avec titre, etc.)

## 4. Tutoiement vs vouvoiement
Pourcentage approximatif. Avec quels types d'interlocuteurs tutoie-t-il ?

## 5. Longueur typique
Nombre de phrases moyen, longueur des paragraphes

## 6. Structure des mails
Schema recurrent (ex: salutation, remerciement, corps, demande, cloture)

## 7. Formulations recurrentes
Les expressions qu'il utilise souvent (minimum 5 exemples avec citations exactes)

## 8. Ton general
Direct/diplomatique, formel/informel, factuel/emotionnel

## 9. Particularites
Tout ce qui est distinctif : ponctuation, abreviations, mots-cles, habitudes

## 10. Exemples de mails representatifs
Cite 3 mails courts qui representent bien son style (copie quasi-exacte)

IMPORTANT : Base-toi UNIQUEMENT sur les mails fournis. Ne generise pas, sois factuel."""

print("[style] Envoi a Claude pour analyse (cela peut prendre 30s)...", flush=True)

response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4000,
    messages=[{
        "role": "user",
        "content": f"{ANALYSIS_PROMPT}\n\n# CORPUS DE {len(sent)} MAILS ENVOYES :\n\n{corpus}"
    }]
)

profile = ""
for block in response.content:
    if block.type == "text":
        profile = block.text.strip()

if not profile:
    print("[style] ERREUR : Claude n'a pas retourne de profil")
    exit(1)

with open("style_profile.txt", "w", encoding="utf-8") as f:
    f.write(profile)

print(f"\n[style] Profil sauvegarde dans style_profile.txt ({len(profile)} chars)")
print("[style] Termine !")
