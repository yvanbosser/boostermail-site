# Spécifications — Scoring Rédactionnel EasyMail

## Vue d'ensemble

Le scoring rédactionnel permet à EasyMail d'adapter automatiquement son comportement selon le niveau de l'utilisateur. Un avocat qui écrit parfaitement reçoit une imitation fidèle de son style. Un collaborateur comptable qui écrit de façon approximative reçoit des mails améliorés, structurés et sans faute.

Le scoring est **invisible** : jamais affiché, jamais mentionné. L'utilisateur voit juste que ses mails sont "comme lui" ou "meilleurs que lui" — et dans les deux cas, il envoie sans modifier.

---

## PHASE 1 — Scoring initial (onboarding)

### Quand
À l'onboarding, quand Claude analyse les 300 mails envoyés pour construire le style profile.

### Comment
Claude évalue **5 critères principaux**, chacun sur 20 points :

| Critère | 0-5 | 6-10 | 11-15 | 16-20 |
|---|---|---|---|---|
| **Orthographe / grammaire** | Fautes à chaque phrase | Fautes régulières | Fautes rares | Quasi parfait |
| **Vocabulaire** | Basique, répétitif | Correct, standard | Varié, précis | Riche, nuancé |
| **Syntaxe** | Phrases simples bancales | Phrases simples correctes | Phrases structurées | Syntaxe maîtrisée, fluide |
| **Structure** | Bloc de texte sans structure | Paragraphes basiques | Structure claire | Structure élégante, naturelle |
| **Personnalité** | Aucune personnalité | Quelques habitudes | Style identifiable | Style fort, unique |

**Score total : /100**

### 3 descripteurs complémentaires (hors scoring)

Ces descripteurs enrichissent la section B mais **n'impactent pas le score**. Ils décrivent le comportement rédactionnel, pas le niveau.

| Descripteur | Ce que Claude observe | Valeurs possibles |
|---|---|---|
| **Concision** | Longueur moyenne des mails, ratio information/mots | Très concis / Concis / Moyen / Détaillé / Très détaillé |
| **Adaptabilité** | Change-t-il de ton/registre selon le destinataire ? | Forte / Modérée / Faible / Non détectée |
| **Réactivité émotionnelle** | Comment réagit-il aux situations tendues ? | Froid / Mesuré / Expressif / Non détectée |

Chaque descripteur est **obligatoirement complété** lors de l'onboarding. Si rien n'est détecté dans les 300 mails, la valeur est "Non détectée". Les descripteurs s'enrichissent au fil de l'utilisation (voir ENRICHISSEMENT DU PROFIL).

### Où le score est stocké
En base de données, table `settings`, clé `writing_score`, valeur numérique (ex: `73`). Jamais affiché dans l'interface.

---

## PHASE 2 — Impact du scoring sur les sections A/B/C

### Les 10 niveaux

| Niveau | Score | Section A (paires) | Section B (règles) | Section C (mails représentatifs) |
|---|---|---|---|---|
| **N1** | 0-10 | Paires entièrement reformulées | Ton et registre uniquement. Instruction : "Rédiger un mail professionnel." | 5 mails reformulés |
| **N2** | 11-20 | Paires reformulées, intention conservée | + ouverture/clôture. "Structurer et corriger." | 5 mails reformulés |
| **N3** | 21-30 | Paires reformulées, ton conservé | + longueur habituelle. "Améliorer la forme." | 5 mails reformulés |
| **N4** | 31-40 | Quelques bonnes formulations gardées | + 2-3 formulations correctes citées | 5 mails légèrement améliorés |
| **N5** | 41-50 | Moitié verbatim, moitié reformulée | + 4-5 formulations citées | 5 mails mixtes |
| **N6** | 51-60 | Majorité verbatim, corrections ciblées | Style détaillé + 6-7 formulations | 5 mails quasi verbatim |
| **N7** | 61-70 | Quasi verbatim, fautes corrigées | Style riche + rythme décrit | 5 mails quasi verbatim |
| **N8** | 71-80 | Verbatim, corrections mineures | Style exhaustif + tics de langage | 5 mails verbatim |
| **N9** | 81-90 | 100% verbatim | Tout décrit. "Reproduire fidèlement." | 5 mails 100% verbatim |
| **N10** | 91-100 | 100% verbatim + imperfections volontaires | Tout décrit. "Le style prime sur les règles." | 5 mails 100% verbatim |

### Plancher de sortie : 70

Quel que soit le scoring de l'utilisateur, le niveau de sortie du mail ne descend jamais en dessous de 70/100. Ce plancher garantit un mail professionnel, structuré et sans faute pour tous les utilisateurs.

- Score 20 → niveau de sortie 70 (plancher)
- Score 50 → niveau de sortie 70 (plancher)
- Score 70 → niveau de sortie ~76
- Score 85 → niveau de sortie ~88
- Score 95 → niveau de sortie ~96

Au-dessus de 70, la progression est décroissante : EasyMail ajoute ~20% de l'écart restant vers 100. Plus le score est élevé, moins EasyMail modifie.

### Ce qui change entre les niveaux pour un même plancher

Un utilisateur à 20 et un utilisateur à 60 reçoivent tous les deux des mails à 70. La différence :

- **Score 20** : le mail est entièrement rédigé par EasyMail. Le ton de l'utilisateur est conservé, mais les formulations sont celles d'EasyMail. Le mail ne lui "ressemble" pas en forme, mais il est professionnel.
- **Score 60** : le mail intègre les formulations de l'utilisateur (les bonnes). Le ton ET certaines tournures lui ressemblent. Le mail est professionnel ET personnalisé.

Le scoring ne change pas le niveau de sortie (70 pour les deux). Il change le **dosage imitation/amélioration**.

---

## PHASE 3 — Évolution du score

### Quand
À chaque recalibrage (tous les 10 envois).

### Comment
La micro-analyse D2 (qui existe déjà) analyse chaque correction. Pour chaque mail corrigé par l'utilisateur, Claude compare la version proposée et la version envoyée et juge :

- **Amélioration de niveau** : l'utilisateur a enrichi le vocabulaire, affiné la syntaxe, restructuré un paragraphe → le score initial était trop bas
- **Ajustement de style** : l'utilisateur a changé l'ouverture, la clôture, le registre, la longueur → le score est bon, c'est une préférence → ne compte pas
- **Dégradation de niveau** : l'utilisateur a ajouté des fautes, cassé la syntaxe → score confirmé

### Ce qui déclenche un changement de score

Le score ne bouge **que** quand l'utilisateur corrige (modifie la proposition avant d'envoyer). Les envois directs (sans modification) ne sont pas interprétés — l'utilisateur peut être pressé, satisfait, ou indifférent. On ne sait pas.

Il faut un **pattern répété** : un seul signal ne suffit pas. Minimum 3 corrections dans la même direction sur les 10 derniers envois.

### Barème révisé

| Situation | Delta | Justification |
|---|---|---|
| 3 améliorations sur 10 corrections | +2 | Signal modéré, pourrait être ponctuel |
| 4 améliorations sur 10 corrections | +3 | Signal plus fiable |
| 5+ améliorations sur 10 corrections | +3 | Plafond — même 10/10 ne donne que +3 |
| 3 dégradations sur 10 corrections | -1 | Très prudent à la baisse |
| 4+ dégradations sur 10 corrections | -2 | Plafond bas |
| Moins de 3 dans une direction | 0 | Pas de pattern → pas de changement |
| Ajustements de style uniquement | 0 | Style, pas niveau |

### Pourquoi la descente est plus lente que la montée

Dégrader le score a plus d'impact que le monter. Un score qui descend rend les sections A/B plus "amélioratives" — les mails ressemblent moins à l'utilisateur. Il vaut mieux être prudent à la baisse pour ne pas créer de frustration.

### Score plafonné

- Minimum : 0
- Maximum : 100

### Quand les sections A/B/C changent-elles ?

Les sections A/B/C ne sont PAS re-rédigées à chaque changement de score. Elles ne changent que quand le score **franchit un seuil de niveau** (ex: N4→N5, soit de 40 à 51 avec hystérésis). Les petites variations du score (+2, -1) au sein d'un même niveau n'ont aucun impact sur les sections.

Cela évite que les sections oscillent à chaque recalibrage. L'utilisateur voit un style stable, qui ne change que quand un vrai changement de niveau est confirmé.

---

## PHASE 4 — Convergence

### Détection de la convergence

Le score a convergé quand il oscille dans une **zone de stabilité** : ±3 points sur 5 cycles consécutifs (50 envois).

Exemple :
- Cycle 1 : score 62
- Cycle 2 : score 64 (+2)
- Cycle 3 : score 63 (-1)
- Cycle 4 : score 65 (+2)
- Cycle 5 : score 64 (-1)

Variation totale : 3 points → convergé.

### Après convergence : Option C (seuil renforcé)

Le mécanisme ne change pas. Seul le seuil de déclenchement augmente :

| État | Seuil pour bouger le score |
|---|---|
| Avant convergence | 3 améliorations/dégradations sur 10 |
| Après convergence | 5 améliorations/dégradations sur 10 |

Les petites fluctuations sont ignorées. Seul un vrai changement de niveau (formation, nouveau poste, nouveau type de clients) déclenche un mouvement.

### Hystérésis aux frontières de niveau (±3 points)

Quand le score oscille autour d'une frontière de niveau (ex: 70, frontière N7/N8), les sections A/B ne changent que si le score s'éloigne franchement :

- Pour monter de N7 à N8 : il faut atteindre 73 (pas 71)
- Pour redescendre de N8 à N7 : il faut tomber à 67 (pas 69)

Cela empêche le "yoyo" des sections A/B quand le score oscille autour d'une frontière. Le ±3 est cohérent avec le barème révisé : un seul cycle à +3 ne suffit pas pour franchir.

### Pourquoi ±3 et pas ±2 ou ±4

- ±2 : un seul bon cycle (+3) suffirait pour franchir → yoyo possible
- ±3 : il faut minimum 2 cycles dans la même direction → stable
- ±4 : il faudrait 2 cycles à +3 (8 améliorations sur 20 envois) → excessivement conservateur

---

## ENRICHISSEMENT DU PROFIL (4 canaux)

### Principe

Le profil est "vivant". Il commence avec ce que l'onboarding trouve dans les 300 mails, puis s'enrichit continuellement avec chaque nouveau type de situation rencontré.

### Canal 1 — Section A (paires situationnelles)

**Quand** : chaque mail envoyé via EasyMail (avec ou sans correction)

**Comment** : après l'envoi, Claude vérifie si le type de situation est déjà couvert dans la section A. Si c'est un nouveau type (litige client, relance urgente, demande de devis...) non couvert, il est ajouté comme nouvelle paire au prochain recalibrage.

**Exemple** : le style profile a 15 paires (confirmation, planification, etc.) mais pas de paire "litige client". L'utilisateur traite son premier litige via EasyMail → cette situation est détectée comme nouvelle → ajoutée à la section A au recalibrage suivant.

### Canal 2 — Section B (règles de style + 3 descripteurs)

**Quand** : à chaque recalibrage (tous les 10 envois)

**Comment** : les corrections de l'utilisateur affinent les règles (ton, longueur, formulations) et enrichissent les 3 descripteurs complémentaires au fur et à mesure que de nouvelles situations sont rencontrées.

**Exemple** : "Réactivité émotionnelle : Non détectée" à l'onboarding. L'utilisateur traite un litige avec un ton ferme → le recalibrage détecte cette situation émotionnelle → la section B est mise à jour : "Réactivité émotionnelle : en situation de litige, ton ferme mais courtois."

### Canal 3 — Section C (mails représentatifs)

**Quand** : à chaque recalibrage

**Comment** : si un mail envoyé est meilleur ou plus représentatif que ceux de la section C, il peut les remplacer. Claude compare les 5 mails de la section C avec les 10 derniers mails envoyés et substitue si un nouveau mail couvre mieux un type de situation.

### Canal 4 — Le scoring

**Quand** : à chaque recalibrage

**Comment** : le score /100 évolue selon le barème de la Phase 3. Le score influence la densité de la section B et le traitement des paires en section A (verbatim vs reformulé). Voir Phase 3 pour le détail.

### Source commune

Les 4 canaux se nourrissent de la même source : chaque mail envoyé via EasyMail, qu'il soit corrigé ou non. Le profil devient de plus en plus précis et le scoring converge vers le bon niveau.

---

## RÉSUMÉ DU FLUX COMPLET

```
ONBOARDING (1 fois)
    └→ 300 mails analysés
    └→ Score /100 calculé (5 critères × 20)
    └→ 3 descripteurs complémentaires remplis
    └→ Niveau N1-N10 déterminé
    └→ Sections A/B/C rédigées selon le niveau
    └→ style_profile.txt créé

CHAQUE MAIL ENVOYÉ
    └→ Mail envoyé (avec ou sans correction)
    └→ Si correction : micro-analyse D2 (amélioration / style / dégradation)
    └→ Détection nouveau type de situation (canal 1)

RECALIBRAGE (tous les 10 envois)
    └→ Canal 1 : nouvelles paires ajoutées en section A
    └→ Canal 2 : section B affinée (règles + descripteurs)
    └→ Canal 3 : section C mise à jour si meilleur mail
    └→ Canal 4 : score ajusté (barème révisé)
    └→ Si franchissement de niveau (avec hystérésis ±3) : sections A/B/C re-rédigées
    └→ Vérification convergence (±3 sur 5 cycles)
    └→ Si convergé : seuil renforcé (5 au lieu de 3)
```

---

## RECALIBRAGE MANUEL (bouton "Recalibrer EasyMail")

Le recalibrage manuel (déclenché par l'utilisateur depuis la page Profil) applique l'**Option C enrichie** :

- **Score** : conservé tel quel — pas de recalcul. Le score ne bouge qu'au fil des recalibrages automatiques (tous les 10 envois, Phase 3).
- **Sections A/B/C** : re-rédigées intégralement en tenant compte des dernières corrections et des nouveaux types de situations détectés depuis le dernier recalibrage.
- **Pas d'exception** : le comportement est toujours le même, quel que soit l'état de la DB. Si la DB est vide (scénario développement uniquement), l'onboarding repart de zéro comme pour un nouvel utilisateur.

---

## INTERACTION SCORING × PROFIL CONTACT

Le scoring rédactionnel (global, /100) et le profil contact (par correspondant, bloc D) sont **deux axes orthogonaux** qui ne pilotent pas la même chose :

| | Scoring (global) | Profil contact (par correspondant) |
|---|---|---|
| **Ce qu'il contrôle** | La qualité d'écriture : orthographe, grammaire, syntaxe, structure, vocabulaire | La relation : registre (tu/vous), ton (formel/amical/ferme), humour, formules d'ouverture/clôture |
| **D'où il vient** | Analyse des 300 mails à l'onboarding, évolue avec les corrections | Analyse des échanges avec ce correspondant spécifique |
| **Ce qu'il fait** | Détermine si Claude imite tel quel (score haut) ou améliore (score bas) | Détermine comment Claude s'adresse à cette personne |
| **Dans le prompt** | Impact indirect : densité des sections A/B/C | Impact direct : bloc D injecté dans le prompt |

### Règle de priorité

Le profil contact prime sur le scoring pour le **ton et le registre**. Le scoring ne pilote que la **qualité rédactionnelle**.

### Exemple concret

Un collaborateur comptable (score 30, N3) qui tutoie son ami et utilise l'humour : le mail sort avec le tutoiement, le ton amical et les blagues (profil contact), mais avec une orthographe corrigée, des phrases bien construites et une structure claire (scoring N3). Le mail sort toujours au plancher qualité 70, quel que soit le score de l'utilisateur — mais le ton, le registre et l'humour du profil contact sont intégralement préservés.

### Impact code

Aucun code supplémentaire. Le scoring agit en amont (au recalibrage, sur les sections A/B/C). Le profil contact agit au moment de la génération (bloc D). Le bloc D est déjà en position 1 dans le prompt, donc il prime naturellement. Seule une ligne de clarification sera ajoutée dans le prompt : *"Le profil contact (bloc D) détermine le ton et le registre. Les sections A/B déterminent la qualité d'écriture."*

---

## TAILLE DU STYLE PROFILE

Un profil N10 (section B exhaustive) peut atteindre 15-20K chars (~5000 tokens). Non bloquant : le prompt total est déjà à 10-15K tokens, le surcoût est négligeable en coût et en latence.

## PREMIER MAIL APRÈS ONBOARDING

Dès l'onboarding, les sections A/B/C et le profil contact sont en place. Le premier mail généré est déjà personnalisé (ton, registre, formules). Pas de risque de mail générique.

## TRIGGER DE RECALIBRAGE UNIFIÉ

Le recalibrage se déclenche tous les 10 **envois** (au lieu de 10 corrections), mais uniquement s'il y a eu au moins **1 nouvelle correction** depuis le dernier recalibrage. Sans correction, le recalibrage est skippé — il n'y a rien de nouveau à apprendre.

**Avantage** : le système apprend plus vite (lots de ~4 corrections au lieu de 10), sans gaspillage quand l'utilisateur ne corrige pas. Le recalibrage relit toujours les 50 dernières corrections, donc la qualité n'est pas dégradée par les lots plus petits.

## CHANGEMENT DE NIVEAU DE L'UTILISATEUR

Si l'utilisateur progresse (formation, promotion, nouveau poste), le score monte organiquement via les recalibrages automatiques (+2/+3 par cycle). La progression est graduelle — un changement de poste ne change pas le niveau rédactionnel du jour au lendemain. Le recalibrage manuel ne recalcule pas le score, il ne fait qu'actualiser les sections A/B/C.

---

## IMPACT SUR LE CODE

### Fichiers à modifier

| Fichier | Modification |
|---|---|
| **app.py** | Prompt d'onboarding : ajouter instruction scoring + descripteurs. Recalibrage : ajouter canaux 1-4 + barème + convergence |
| **claude_ai.py** | Prompt d'onboarding : instructions scoring selon le niveau. Bloc D : aucun changement (le profil contact est indépendant du scoring) |
| **database.py** | Nouveau setting : `writing_score`. Optionnel : table pour historique des scores |
| **templates/** | Aucun changement (le scoring est invisible) |

### Ce qui ne change PAS

- Le prompt système (règles générales)
- Les profils contacts (indépendants du scoring)
- L'interface utilisateur (rien d'affiché)
- Le backend Flask (routes inchangées)
- L'envoi de mail (Outlook COM inchangé)

---

## VALIDATION — 16 cas wow testés

Le système a été validé sur 16 profils utilisateurs différents. Tous sont couverts :

| # | Profil | Score estimé | Wow attendu | Couvert |
|---|---|---|---|---|
| 1 | Avocat | 85 | "C'est exactement moi en 3 secondes" | ✅ |
| 2 | Collaborateur comptable | 35 | "Je n'aurais jamais aussi bien écrit" | ✅ |
| 3 | Artisan plombier | 25 | "Répondu en 10 secondes" | ✅ |
| 4 | Secrétaire cabinet | 50 | "50 mails traités dans la matinée" | ✅ |
| 5 | Notaire | 90 | "Le formalisme juridique est respecté" | ✅ |
| 6 | Patron PME | 60 | "Je peux déléguer mes mails" | ✅ |
| 7 | Commercial terrain | 40 | "Mes relances sont enfin pro" | ✅ |
| 8 | Médecin libéral | 70 | "Le vocabulaire médical est précis" | ✅ |
| 9 | Stagiaire | 15 | "Mon maître de stage est impressionné" | ✅ |
| 10 | DRH grand groupe | 75 | "Le ton diplomatique est respecté" | ✅ |
| 11 | Agent immobilier | 45 | "Mes réponses clients sont impeccables" | ✅ |
| 12 | Expert-comptable associé | 80 | "Mes clients ne voient pas la différence" | ✅ |
| 13 | Assistante bilingue | 65 | "Ça marche en français ET en anglais" | ⚠️ Risque : scoring mélange les langues. Pas bloquant V1, scoring par langue en V2 |
| 14 | Artisan couvreur (dicte ses mails) | 10 | "Enfin des mails que j'ose envoyer" | ✅ |
| 15 | Avocat pénaliste agressif | 88 | "Le ton ferme est reproduit" | ✅ (réactivité émotionnelle captée par descripteur) |
| 16 | Comptable junior timide | 40 | "J'ose enfin répondre aux clients difficiles" | ✅ |

### Risques identifiés et acceptés pour V1

- **Cas 13 (bilingue)** : le scoring est global, pas par langue. Un utilisateur qui écrit bien en français mais moins bien en anglais aura un score moyen qui ne reflète ni l'un ni l'autre. Solution V2 : scoring par langue.
- **Cas 15 (avocat agressif)** : si l'onboarding ne contient pas de mails de litige, la réactivité émotionnelle sera "Non détectée". L'enrichissement du profil (canal 2) corrigera au fur et à mesure.
