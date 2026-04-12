# Spécifications — Templates Intelligents EasyMail

## Principe

Un seul bouton "Générer". EasyMail détecte automatiquement si un template correspond. Si oui, affichage instantané (0 appel IA). Si non, appel IA classique.

L'utilisateur ne sait pas que les templates existent. Il voit juste que parfois la réponse arrive instantanément.

Si le template ne convient pas, l'utilisateur tape une instruction dans la barre Modifier → l'IA prend le relais.

---

## Flux 1 — Réponse à un mail reçu

```
Utilisateur clique "Générer"
        ↓
Analyse du mail reçu (heuristique, <50ms)
        ↓
    Template trouvé ?
      /         \
    OUI          NON
     ↓            ↓
Template affiché   Appel IA
(instantané)      (2-3 secondes)
     ↓            ↓
  L'utilisateur voit la réponse
```

### Critères de détection (mail reçu)

Les 3 critères combinés :
- Longueur du mail reçu < 200 caractères
- 0 point d'interrogation
- Contient des mots-clés simples : "reçu", "noté", "merci", "confirme", "ok", "parfait", "bonne journée"

---

## Flux 2 — Nouveau mail (pas une réponse)

```
Utilisateur clique "Nouveau mail"
        ↓
Remplit : À, Objet, Brief
        ↓
Clique "Générer"
        ↓
Analyse du brief (heuristique, <50ms)
        ↓
    Template trouvé ?
      /         \
    OUI          NON
     ↓            ↓
Template affiché   Appel IA
(instantané)      (2-3 secondes)
     ↓            ↓
  L'utilisateur voit le mail
```

### Mots-clés brief → template

| Brief | Template |
|---|---|
| "relance" | #31 |
| "relance douce" | #32 |
| "rdv" ou "rendez-vous" | #33 |
| "créneaux" ou "dispo" | #34 |
| "urgent" | #35 |
| "refus" | #29 |
| "pj oubliée" | #37 |
| "félicitations" | #40 |
| "voeux" | #41 |
| "excuses" ou "retard" | #42 |
| "pour info" | #25 |
| "ton avis" | #27 |
| Brief long ou complexe | Pas de template → appel IA |

---

## Adaptation tu/vous

Chaque template existe en 2 versions. Le code choisit selon le profil contact (bloc D).
L'ouverture et la clôture viennent du profil contact.

Assemblage final (100% code, 0% IA) :
```
[Ouverture du profil contact]
[Template corps adapté tu/vous]
[Clôture du profil contact]
[Signature utilisateur]
```

---

## 45 Templates

### Accusés de réception (5)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 1 | Document reçu | Bien reçu, merci. Je prends connaissance du document et reviens vers vous rapidement. | Bien reçu, merci. Je prends connaissance du document et te reviens rapidement. |
| 2 | Facture reçue | Bien reçu, merci. Je prends connaissance du document et reviens vers vous rapidement. | Bien reçu, merci. Je prends connaissance du document et te reviens rapidement. |
| 3 | Planning reçu | Bien noté, merci pour le planning. | Bien noté, merci pour le planning. |
| 4 | Information simple | C'est bien noté, merci pour l'information. | C'est bien noté, merci pour l'info. |
| 5 | Compte-rendu | Bien reçu, merci pour ce compte-rendu. | Bien reçu, merci pour le CR. |

### Confirmations (4)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 6 | RDV confirmé | Parfait, c'est bien noté. À [DATE] à [HEURE]. | Parfait, c'est noté. À [DATE] à [HEURE]. |
| 7 | Confirmation de réception | Skip — pas de réponse | Skip |
| 8 | Accord validé | Parfait, merci pour la confirmation. | Parfait, merci pour la confirmation. |
| 9 | Bonne exécution | Parfait, merci pour votre retour. | Parfait, merci pour ton retour. |

### Remerciements (3)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 10 | Merci retour rapide | Avec plaisir. N'hésitez pas si besoin. | Avec plaisir, n'hésite pas. |
| 11 | Merci aide | Avec plaisir, c'est normal. | Avec plaisir, c'est normal. |
| 12 | Merci bonne journée | Skip — pas de réponse | Skip |

### Transmissions (3)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 13 | Envoi document | Je vous prie de bien vouloir trouver ci-joint le document demandé. | Tu trouveras ci-joint le document demandé. |
| 14 | Envoi coordonnées | Vous trouverez ci-dessous les coordonnées de [À COMPLÉTER]. | Tu trouveras ci-dessous les coordonnées de [À COMPLÉTER]. |
| 15 | Réception transfert | Merci pour la transmission, c'est bien noté. | Merci pour la transmission, c'est bien noté. |

### Reports / Mises en attente (3)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 16 | Relance non traitée | Bien noté, je reviens vers vous dès que possible sur ce point. | Bien noté, je te reviens dès que possible sur ce point. |
| 17 | Demande MAJ | Le dossier est en cours de traitement, je vous tiens informé dès sa mise à jour effectuée. | Le dossier est en cours, je te tiens informé dès que c'est à jour. |
| 18 | Question vérification | Je vérifie ce point et reviens vers vous rapidement. | Je vérifie ce point et te reviens rapidement. |

### Acceptations (3)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 19 | Créneau proposé | C'est noté, [CRÉNEAU À CONFIRMER] me convient. | C'est noté, [CRÉNEAU À CONFIRMER] me va. |
| 20 | Invitation | Merci pour l'invitation, je prends note. | Merci pour l'invitation, je prends note. |
| 21 | Proposition commerciale | Merci pour votre proposition que je vais étudier. Je reviendrai vers vous si besoin. | Merci pour ta proposition que je vais regarder. Je te reviens si besoin. |

### Clôtures — Skip (3)

| # | Type | Action |
|---|---|---|
| 22 | "OK c'est bon" | Skip |
| 23 | "Bonne journée/week-end" | Skip |
| 24 | "À bientôt/À lundi" | Skip |

### Forwards (3)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 25 | Forward info | Pour information. | Pour info. |
| 26 | Forward action | Merci de prendre en charge ce point. | Merci de prendre en charge ce point. |
| 27 | Forward avis | Quel est votre avis sur ce point ? | Quel est ton avis sur ce point ? |

### Refus (3)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 28 | Refus créneau | Je ne suis malheureusement pas disponible sur ce créneau. Auriez-vous d'autres disponibilités ? | Je ne suis malheureusement pas dispo sur ce créneau. Tu aurais d'autres dispos ? |
| 29 | Refus demande | Je ne suis pas en mesure de donner suite à votre demande. | Je ne suis pas en mesure de donner suite à cette demande. |
| 30 | Refus commercial | Merci pour votre proposition, mais cela ne correspond pas à notre besoin actuel. | Merci pour ta proposition, mais ça ne correspond pas à notre besoin actuel. |

### Relances (2)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 31 | Relance client | Je me permets de revenir vers vous concernant mon précédent message. Avez-vous pu en prendre connaissance ? | Je me permets de revenir vers toi concernant mon précédent message. As-tu pu en prendre connaissance ? |
| 32 | Relance douce | Sauf erreur de ma part, je n'ai pas eu de retour sur ce point. | Sauf erreur de ma part, je n'ai pas eu de retour sur ce point. |

### Propositions (2)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 33 | Proposer RDV | Seriez-vous disponible pour un échange à ce sujet ? | Serais-tu disponible pour un échange sur ce sujet ? |
| 34 | Proposer créneaux | Je peux vous proposer les créneaux suivants : [À COMPLÉTER]. | Je peux te proposer les créneaux suivants : [À COMPLÉTER]. |

### Urgences (2)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 35 | Urgence soft | Pouvez-vous me confirmer ce point rapidement ? | Peux-tu me confirmer ce point rapidement ? |
| 36 | Urgence pro | Ce point étant prioritaire, je vous remercie de votre retour rapide. | Ce point étant prioritaire, merci de ton retour rapide. |

### Divers (9)

| # | Type | Vouvoiement | Tutoiement |
|---|---|---|---|
| 37 | PJ oubliée | Je vous prie de bien vouloir trouver en pièce jointe le document mentionné dans mon précédent message. | Tu trouveras en PJ le document mentionné dans mon précédent message. |
| 38 | Demande interne | — | Peux-tu regarder ce point et me faire un retour ? |
| 39 | Assignation | Merci de prendre ce sujet en charge. | Merci de prendre ce sujet en charge. |
| 40 | Félicitations | Toutes mes félicitations, c'est une excellente nouvelle. | Félicitations, c'est top ! |
| 41 | Voeux | Je vous adresse mes meilleurs voeux pour cette nouvelle année. | Bonne année à toi ! |
| 42 | Excuses/délai | Je vous prie de m'excuser pour ce délai de réponse. | Désolé pour le délai. |
| 43 | Demande de délai | Serait-il possible d'avoir davantage de temps sur ce point ? | Serait-il possible d'avoir davantage de temps sur ce point ? |
| 44 | Réponse partielle | Je vous réponds sur les premiers points, je reviens vers vous pour le reste. | Je te réponds sur les premiers points, je reviens vers toi pour le reste. |
| 45 | Mise en copie | Je mets [NOM] en copie pour suivi. | Je mets [NOM] en copie pour suivi. |

---

## TEMPLATES APPRIS (auto-générés par l'IA)

### Principe

Les 45 templates fixes sont des templates de DÉMARRAGE. Après quelques semaines d'utilisation, EasyMail apprend les patterns de l'utilisateur et crée ses propres templates — personnalisés, dans le style de l'utilisateur, adaptés à son métier.

### Flux d'apprentissage

```
Mail de facture reçu → utilisateur répond "Bien reçu, je prends connaissance..."
2ème mail de facture → utilisateur répond "Bien reçu, je reviens vers vous..."
3ème mail de facture → utilisateur répond "Bien reçu, merci pour l'envoi..."
        ↓
EasyMail détecte : 3 réponses similaires au même type de mail
        ↓
1 appel IA (one-shot) : "Extrais le template commun avec placeholders"
        ↓
Template appris créé et stocké en DB
        ↓
4ème mail de facture → template appris proposé instantanément (0 appel IA)
```

### Seuil de détection

- **3 répétitions** : template créé (statut "candidat")
- **5 répétitions** : template confirmé (statut "validé")
- Un template candidat est proposé mais avec moins de priorité qu'un template validé

### Détection du pattern (heuristique, 0 IA)

Les critères pour détecter que 3 mails sont "du même type" :
- Longueur du mail reçu similaire (±50%)
- Longueur de la réponse similaire (±50%)
- Au moins 2 mots-clés en commun dans le mail reçu
- Même nombre de paragraphes dans la réponse
- Ouverture et clôture identiques

### Création du template (1 appel IA, one-shot)

Quand le pattern est détecté à 3 occurrences, 1 seul appel IA :
"Voici 3 réponses que l'utilisateur a envoyées à des mails similaires. Extrais le template commun avec des placeholders [OBJET], [REFERENCE], [DATE], etc. Retourne le template en version vouvoiement ET tutoiement."

Coût : 1 appel (~$0.006), jamais répété pour ce pattern.

### Stockage

```sql
CREATE TABLE IF NOT EXISTS learned_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern_keywords TEXT,
    pattern_type TEXT,
    template_vouvoiement TEXT,
    template_tutoiement TEXT,
    source_corrections TEXT,
    usage_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'candidate',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    validated_at TEXT
)
```

### Priorité de matching

Quand l'utilisateur clique "Générer" :
1. Chercher dans les **templates appris validés** (status='validated') → match ?
2. Sinon, chercher dans les **templates appris candidats** (status='candidate') → match ?
3. Sinon, chercher dans les **45 templates fixes** → match ?
4. Sinon → **appel IA**

Les templates appris ont PRIORITÉ sur les templates fixes car ils sont personnalisés au style de l'utilisateur.

### Évolution dans le temps

- Semaine 1 : 45 templates fixes couvrent ~20% des mails
- Semaine 2-3 : premiers templates appris créés → couverture monte à ~30%
- Mois 2+ : templates appris matures → couverture potentielle **40-60%** des mails

### Remplacement des templates fixes

Si un template appris couvre le même cas qu'un template fixe, le template appris remplace le fixe (il est dans le style de l'utilisateur, pas générique).

---

## Économie estimée

### Semaine 1 (templates fixes seuls)
- Type A (détection auto mails reçus) : ~6 appels IA économisés/jour = -$0.036/jour
- Type B (brief simple nouveau mail) : ~2-3 appels économisés/jour = -$0.015/jour
- Total : **-$0.051/jour = ~$1.12/mois**

### Mois 2+ (templates fixes + appris)
- Couverture estimée 40-60% des mails
- ~12-18 appels IA économisés/jour = -$0.072-$0.108/jour
- Total : **-$0.072-$0.108/jour = ~$1.58-$2.38/mois**

---

## Impact code

- Ajouter une fonction `_detect_template(mail_content, brief)` dans app.py
- Avant l'appel IA dans `generate_reply_stream()`, vérifier si un template matche (appris → fixe → IA)
- Si oui, retourner le template assemblé (ouverture + corps + clôture + signature)
- Si non, continuer vers l'appel IA classique
- Ajouter une fonction `_detect_pattern()` appelée après chaque envoi pour détecter les patterns récurrents
- Ajouter une fonction `_create_learned_template()` qui appelle l'IA une seule fois pour extraire le template commun
- Nouvelle table `learned_templates` en DB
