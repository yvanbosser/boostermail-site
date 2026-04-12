# Recherche exhaustive — Portage moteur IA (Phase 2 ter)

*Produit le 11/04/2026 — Session de recherche (nocode)*

---

## REVELATION MAJEURE : les routes ne sont PAS des squelettes

Le `TODO_SESSION_SUIVANTE.md` dit que les routes `/generate_reply`, `/refine_reply`, `/send_reply` sont des squelettes. **C'est faux.** L'analyse du code montre :

| Route | Lignes | Etat reel |
|-------|--------|-----------|
| `/generate_reply` | 1436-1695 | **ENTIEREMENT implementee** — contexte A+B+C, prompt builder, pre-injection greeting/closing, SSE streaming |
| `/refine_reply` | 1698-1777 | **ENTIEREMENT implementee** — prompt refine, profil contact, SSE streaming |
| `/send_reply` | 1784-1843 | **ENTIEREMENT implementee** — envoi Graph API (reply, reply_all, forward, new), signature marketing |
| `/api/post_send` | 2100-2201 | **IMPLEMENTEE** — sauvegarde threads, metrics, apprentissage diff propose/envoye |

**Le moteur tourne.** Il ne tourne pas "a vide" — il est branche. La question est : **qu'est-ce qui MANQUE par rapport au proto ?**

---

## ECARTS REELS entre V1 et proto

### Ecart 1 — Le prefetch cache est gaspille (CRITIQUE)

**Constat** : `_run_prefetch()` (lignes 690-805) lance 3 threads paralleles pour collecter A+B+C et stocke dans `_prefetch_cache`. Mais `/generate_reply` (lignes 1477-1574) **ignore completement ce cache** et refait les memes requetes Graph inline.

**Impact** : chaque generation fait des appels Graph redondants (~200ms gaspilles si le prefetch a deja tourne).

**Solutions** :

| # | Solution | Principe | Risques | Pertinence |
|---|----------|----------|---------|------------|
| **S1** | Consommer le prefetch cache dans generate_reply | Avant de fetch inline, verifier si `_prefetch_cache[cache_key]` existe et est recent. Si oui, utiliser. Sinon, fetch inline comme aujourd'hui. | Risque de cache stale (mail change entre prefetch et generation). Mitigation : TTL de 60s sur le cache. | **#1 — RECOMMANDEE** |
| **S2** | Supprimer le prefetch et ne garder que le fetch inline | Simplifier le code. Le fetch inline fonctionne deja. | Perd le gain de performance du prefetch parallele (le proto fait ~200ms grace au prefetch vs ~800ms inline). Pas de speculation possible sans prefetch. | #3 — Solution de repli si S1 pose probleme |
| **S3** | Rendre le prefetch obligatoire et supprimer le fetch inline | generate_reply attend que le prefetch soit termine (polling ou event). | Risque de blocage si le prefetch echoue ou est lent. L'utilisateur attend plus longtemps. Complexifie la gestion d'erreur. | #2 — Plus propre mais plus risquee |

**Risques communs** :
- Le cache_key est base sur `message_id` OU `from_email:subject` — un meme mail peut avoir des cles differentes selon le contexte d'appel
- Le prefetch ne charge pas les corrections D2 ni le profil contact — generate_reply devra toujours les charger separement

---

### Ecart 2 — Pas de Block F (echeances dans le prompt) (MOYEN)

**Constat** : Le proto injecte un Bloc F quand le correspondant a des echeances actives. La V1 ne le fait pas — `/generate_reply` n'appelle jamais `get_echeances()` pendant la construction du prompt.

**Impact** : L'IA ne mentionne pas les echeances en cours dans ses reponses. Un mail qui dit "je vous envoie le document lundi" ne sera pas connecte a une echeance existante.

**Solutions** :

| # | Solution | Principe | Risques | Pertinence |
|---|----------|----------|---------|------------|
| **S1** | Ajouter un appel DB dans generate_reply | Avant `_build_prompt()`, appeler `_db.get_echeances(correspondant=from_email, statut='active')`. Formater en Bloc F. Passer dans le prompt. | Requete DB rapide (~1ms), risque quasi nul. Mais il faut que `_build_prompt()` accepte un parametre `echeances` — a verifier si c'est le cas. | **#1 — RECOMMANDEE** |
| **S2** | Integrer les echeances dans le prefetch | Le prefetch charge aussi les echeances et les stocke dans le cache. generate_reply les recupere du cache. | Plus complexe, couple prefetch et echeances. Benefice marginal (la requete DB est instantanee). | #2 — Over-engineering |

**Point d'attention** : `_build_prompt()` dans claude_ai.py n'a PAS de parametre `echeances` dans sa signature actuelle. Le Bloc F est probablement assemble dans `app.py` (proto) AVANT l'appel a `_build_prompt()`. A verifier en lisant app.py — mais on NE MODIFIE PAS claude_ai.py. Solution : assembler le Bloc F dans app_plugin.py et l'ajouter au prompt apres `_build_prompt()`.

**Alternative** : `_build_prompt()` accepte `learning_priorities` (Bloc E) — on pourrait passer les echeances comme partie du Bloc E. Mais c'est un detournement semantique. Mieux vaut ajouter le bloc F en post-build.

---

### Ecart 3 — Pas de generation speculative (MAJEUR pour UX)

**Constat** : Le proto lance la generation speculative des que le prefetch A+B est termine, AVANT que l'utilisateur clique "Generer". Resultat : bouton actif en <=4s. La V1 a un commentaire `# TODO (futur)` a la ligne 799-800 et `speculative_ready` est hardcode a `False`.

**Impact** : L'utilisateur attend 3-8s apres avoir clique "Generer" au lieu de 0-2s.

**Solutions** :

| # | Solution | Principe | Risques | Pertinence |
|---|----------|----------|---------|------------|
| **S1** | Speculation post-prefetch avec buffer SSE | Apres prefetch A+B+C termine, lancer `generate_reply_stream()` avec importance=S (defaut) et brief="" (vide). Stocker les chunks dans un buffer. Quand l'utilisateur clique Generer : si buffer rempli, renvoyer le buffer instantanement ; si importance/brief differents du speculatif, ignorer le buffer et generer normalement. | - Cout API double si l'utilisateur change l'importance ou ajoute un brief (le speculatif est jete). - Complexite de synchronisation buffer/generation live. - Le proto a ce probleme et l'accepte. | **#1 — RECOMMANDEE** (c'est ce que fait le proto) |
| **S2** | Speculation legere (prefetch seulement, pas de generation) | Ne pas generer a l'avance, mais s'assurer que A+B+C sont prets. Quand l'utilisateur clique, le fetch inline est instantane (cache hit). Gain : ~200ms au lieu de ~800ms. | Ne donne pas le "wow effect" du proto (reponse instantanee). Mais c'est beaucoup plus simple. Pas de cout API gaspille. | **#2 — BON COMPROMIS** |
| **S3** | Speculation avec SSE push vers le dialog | Generer speculativement ET pousser les chunks via SSE (`speculative_chunk` event). Le dialog affiche la reponse en temps reel AVANT le clic utilisateur. | Tres complexe cote frontend. dialog.js doit gerer un etat "reponse pre-remplie". Risque de confusion UX si la reponse change apres le clic. Le proto NE fait PAS ca (il buffer cote serveur). | #3 — Trop complexe, pas recommandee |

**Risques communs** :
- La speculation sans brief genere une reponse "neutre" — si l'utilisateur avait un brief precis, la reponse speculative est inutile
- Le proto gere le "0-chunks fallback" : si la speculation n'a rien produit, generation normale. La V1 devra aussi gerer ce cas.
- La speculation consomme des tokens API meme si l'utilisateur ne clique jamais Generer

**Prerequis** : Ecart 1 (prefetch cache) doit etre resolu AVANT de travailler sur la speculation.

---

### Ecart 4 — Post-envoi incomplet (MOYEN)

**Constat** : `/api/post_send` sauvegarde les donnees (threads, metrics, corrections) mais il manque :
- Pas de recalibrage automatique (proto : tous les 10/20/50 envois)
- Pas de re-analyse profil contact (proto : tous les 3 mails)
- Pas de calcul scoring EasyMail
- Pas de milestones gamification

**Impact** : Le systeme n'apprend pas au fil du temps. Le score ne bouge jamais. Les profils contacts deviennent obsoletes.

**Solutions** :

| # | Solution | Principe | Risques | Pertinence |
|---|----------|----------|---------|------------|
| **S1** | Ajouter les 3 automatismes dans /api/post_send | Apres la sauvegarde existante (lignes 2137-2196), ajouter : 1) Compter les corrections, si multiple de 10 → recalibrer. 2) Compter les mails au contact, si multiple de 3 → re-analyser. 3) Calculer le scoring. Le tout en daemon threads (non bloquant). | Route post_send devient plus lourde. Mais c'est deja un POST asynchrone (le dialog n'attend pas le resultat des threads). | **#1 — RECOMMANDEE** |
| **S2** | Creer des routes separees pollees par le dialog | Comme pour echeances/classification, creer `/api/recalibrage/post_send` et `/api/contact_reanalysis/post_send`. Le dialog les appelle separement. | Plus de requetes HTTP. Plus complexe cote dialog.js. Le proto fait tout en daemon threads cote serveur. | #2 — Over-engineering |
| **S3** | Cron job periodique au lieu de post-envoi | Un thread planifie verifie toutes les 10 minutes s'il y a des recalibrages a faire. | Decouple du flux d'envoi. Peut rater des recalibrages si le backend redemarre. Plus complexe a debugger. | #3 — Pas recommandee |

**Detail du recalibrage** :
- Lire `_db.count_corrections()` (ou equivalent)
- Si count % 10 == 0 ET count > 0 : lancer le recalibrage via `builder.analyze_style()` ou equivalent
- Le recalibrage modifie `style_profile.txt` et appelle `builder.reload_style(new_level)`
- Attention : le proto utilise `analyze_style.py` (fichier separe) pour l'analyse initiale. Pour le recalibrage, il utilise probablement une logique simplifiee dans app.py.

**Detail re-analyse contact** :
- Apres sauvegarde dans threads, compter les mails recents avec ce contact
- Si count depuis derniere analyse >= 3 : lancer `builder.analyze_contact_profile()`
- Sauvegarder le nouveau profil en DB

---

### Ecart 5 — Pas d'auto-detection importance cote serveur (MINEUR)

**Constat** : Le dialog.js fait l'auto-detection (regex sur le sujet : litige, bail, notaire, etc.). Mais le serveur ne verifie pas — il fait confiance au frontend.

**Impact** : Si le dialog ne detecte pas (bug JS, mode standalone), l'importance n'est pas ajustee.

**Solutions** :

| # | Solution | Principe | Risques | Pertinence |
|---|----------|----------|---------|------------|
| **S1** | Garder la detection frontend uniquement | Le dialog.js le fait deja. Le serveur fait confiance. | Si le frontend a un bug, pas de filet de securite. Mais c'est simple et ca marche. | **#1 — RECOMMANDEE** (KISS) |
| **S2** | Double detection (frontend + serveur) | Le serveur re-verifie et peut upgrader R→H si detection positive. Ne downgrade jamais (respecte le choix utilisateur). | Code duplique. Risque de desynchronisation des listes de mots-cles. | #2 — Pour plus tard |

---

### Ecart 6 — PJ pas attachees dans /send_reply (MINEUR)

**Constat** : `/send_reply` envoie le mail via Graph API mais ne passe pas les PJ. Les methodes Graph (`send_forward`, etc.) supportent les PJ mais le JSON du dialog n'inclut pas les donnees PJ.

**Impact** : En mode forward, les PJ originales ne sont pas re-attachees automatiquement. L'utilisateur doit le faire manuellement.

**Solutions** :

| # | Solution | Principe | Risques | Pertinence |
|---|----------|----------|---------|------------|
| **S1** | Passer les `fwd_pj_indices` dans /send_reply | Le dialog envoie deja `fwd_pj_indices` dans `/generate_reply`. Ajouter le meme champ dans `/send_reply`. Le serveur recupere les PJ via Graph et les attache. | Les PJ peuvent etre volumineuses. Le re-download + re-attach peut etre lent. | **#1 — RECOMMANDEE** |
| **S2** | Utiliser le Graph "forward" natif | Graph API a un endpoint `POST /messages/{id}/forward` qui re-attache automatiquement les PJ. | Moins de controle sur le body (Graph ajoute le mail original en dessous). Peut casser le formatage. | #2 — A tester |
| **S3** | Reporter a plus tard | L'utilisateur attache manuellement. | Mauvaise UX mais pas bloquant pour le lancement. | #3 — Acceptable court terme |

---

### Ecart 7 — Bug _setStatus() non defini dans dialog.js (MINEUR)

**Constat** : `_setStatus()` est appelee aux lignes 815 et 923 de dialog.js mais n'est JAMAIS definie. Provoque un `ReferenceError` quand le serveur retourne un HTTP non-200 pour `/generate_reply` ou `/refine_reply`.

**Impact** : Si la generation echoue (erreur API, timeout), le dialog crash silencieusement au lieu d'afficher un message d'erreur.

**Solution** : Definir `_setStatus(msg)` ou remplacer par `_updateStatus(msg)` (qui existe probablement). A verifier.

---

### Ecart 8 — Speculative check dans dialog.js est un squelette (MINEUR)

**Constat** : `_checkSpeculativeCache()` (ligne 1797) appelle `GET /api/prefetch_status` et verifie `speculative_ready`, mais il y a un `TODO` — la reponse speculative n'est jamais chargee ni affichee meme si elle existe.

**Impact** : Meme si on implemente la speculation cote serveur (Ecart 3), le dialog ne l'utilise pas encore.

**Solution** : Quand `speculative_ready === true`, fetch le buffer speculatif et l'injecter dans l'editeur. A faire APRES que le serveur soit pret.

---

### Ecart 9 — Onboarding style analysis non termine (MOYEN)

**Constat** : `/api/setup/onboarding` (lignes 2260-2337) recupere 300 mails envoyes via Graph+Companion et les indexe dans la table `threads`. Mais il ne lance PAS l'analyse de style via Claude. Le code s'arrete a l'indexation.

**Impact** : L'onboarding ne genere pas le `style_profile.txt` ni le score initial. Sans style profile, le prompt WOW tourne avec un profil par defaut generique.

**Solutions** :

| # | Solution | Principe | Risques | Pertinence |
|---|----------|----------|---------|------------|
| **S1** | Appeler analyze_style() apres l'indexation | Apres avoir indexe les 300 mails, selectionner 80-100 mails divers, appeler `builder.analyze_style()` (ou logique equivalente), ecrire `style_profile.txt`, calculer le score initial. | L'analyse prend 2-3 min (plusieurs appels Claude). Doit etre en thread daemon. Le dialog/popup doit poller la progression. | **#1 — RECOMMANDEE** |
| **S2** | Reutiliser analyze_style.py du proto | Importer et appeler directement `analyze_style.py`. Le fichier existe deja dans la racine. | Couplage avec le proto (le fichier est dans la zone "intouchable"). Mais c'est en LECTURE SEULE, donc acceptable. | #2 — Plus simple mais couplage |
| **S3** | Onboarding simplifie (pas d'analyse style) | Ne pas faire d'analyse. Utiliser un profil par defaut. Le systeme apprend via les corrections au fil du temps. | Mauvaise qualite des premieres reponses. Le "wow effect" au premier usage disparait. | #3 — Pas recommandee |

---

### Ecart 10 — Templates email non utilises (MINEUR)

**Constat** : `templates_mail.py` est importe (ligne 160 de app_plugin.py) mais `detect_template()` et `assemble_template()` ne sont jamais appeles.

**Impact** : Les 45 templates (confirmation RDV, relance facture, etc.) ne sont pas utilises. L'IA genere tout from scratch.

**Solutions** :

| # | Solution | Principe | Risques | Pertinence |
|---|----------|----------|---------|------------|
| **S1** | Reporter a plus tard | Les templates sont un bonus, pas une necessite. L'IA genere tres bien sans. | Pas d'impact immediat. | **#1 — RECOMMANDEE** (priorite basse) |
| **S2** | Integrer la detection dans generate_reply | Avant generation, detecter si le mail correspond a un template. Si oui, assembler le template et le passer comme brief implicite. | Risque de faux positifs (detection incorrecte du type de mail). Complexifie le flux. | #2 — Pour Phase 3 |

---

## HIERARCHIE DES ECARTS PAR PRIORITE

| Priorite | Ecart | Impact | Effort | Recommandation |
|----------|-------|--------|--------|----------------|
| **P0** | Ecart 7 — Bug _setStatus() | Crash sur erreur | 5 min | Corriger immediatement |
| **P1** | Ecart 1 — Prefetch cache gaspille | Performance | 1-2h | Connecter le cache a generate_reply |
| **P2** | Ecart 4 — Post-envoi incomplet | Apprentissage | 3-4h | Ajouter recalibrage + re-analyse contact |
| **P3** | Ecart 2 — Pas de Bloc F | Qualite reponses | 30 min | Ajouter echeances dans le prompt |
| **P4** | Ecart 9 — Onboarding incomplet | Premier usage | 2-3h | Completer l'analyse de style |
| **P5** | Ecart 3 — Pas de speculation | UX (temps attente) | 4-6h | Implementer apres P1 resolu |
| **P6** | Ecart 6 — PJ non attachees | UX forward | 1-2h | Passer les indices PJ dans send |
| **P7** | Ecart 8 — Dialog speculatif | UX | 1h | Apres P5 |
| **P8** | Ecart 5 — Auto-detection serveur | Securite | 30 min | Garder frontend seul pour l'instant |
| **P9** | Ecart 10 — Templates | Bonus | 2-3h | Reporter |

---

## CONTRAT D'INTERFACE FRONTEND ↔ BACKEND (verifie)

### Routes SANS prefixe /api/ (attention)

| Route | Methode | Prefixe |
|-------|---------|---------|
| `/generate_reply` | POST | PAS de /api/ |
| `/refine_reply` | POST | PAS de /api/ |
| `/send_reply` | POST | PAS de /api/ |

Toutes les autres routes utilisent `/api/`.

### Format SSE attendu par dialog.js

```
data: {"chunk": "texte"}\n\n
data: {"done": true}\n\n
data: {"error": "message"}\n\n
```

- PAS de champ `event:` (pas de named events)
- Le frontend lit via `response.body.getReader()` + `TextDecoder`, split sur `\n`, filtre `data: `
- Les chunks sont du texte brut (PAS du HTML) — le frontend convertit en `<p>` apres la fin du stream

### Donnees envoyees par dialog.js pour /generate_reply

```json
{
  "message_id": "<messageId>",
  "brief": "<brief utilisateur>",
  "importance": "R"|"S"|"H",
  "mode": "reply"|"reply_all"|"forward"|"new",
  "to": "<destinataire>",
  "subject": "<sujet>",
  "from_email": "<email expediteur>",
  "from_name": "<nom expediteur>",
  "body": "<corps du mail recu>",
  "pj_context": "<texte extrait des PJ>",
  "fwd_pj_indices": [0, 1, ...] | undefined
}
```

### Boutons qui appellent /generate_reply (PAS /refine_reply)

- "Plus court" → change importance -1 puis regenere
- "Plus travaille" → change importance +1 puis regenere
- "Essayer une autre reponse" → push version, regenere

Seule la saisie libre dans `refineInput` appelle `/refine_reply`.

---

## QUESTIONS OUVERTES (a verifier avant de coder)

### Q1 — Le prefetch cache a-t-il le bon format pour generate_reply ?

Le prefetch stocke `context_a`, `context_b`, `context_c` dans `_prefetch_cache[key]`. Mais generate_reply attend des listes de mails (avec from_name, subject, body, date, direction). **A verifier** : est-ce que le format du cache correspond a ce que `_build_prompt()` attend ?

### Q2 — Comment app.py (proto) assemble le Bloc F ?

`_build_prompt()` dans claude_ai.py n'a pas de parametre `echeances`. Le proto assemble probablement le Bloc F dans app.py avant d'appeler `_build_prompt()`. **A verifier** en lisant app.py (LECTURE SEULE) pour comprendre ou et comment le Bloc F est injecte.

### Q3 — Comment le proto gere la speculation ?

La speculation est dans app.py, pas dans claude_ai.py. Il faut lire app.py pour comprendre :
- Quand la speculation demarre (apres prefetch A+B ou A+B+C ?)
- Quel importance/brief est utilise par defaut
- Comment le buffer est stocke et consomme
- Comment le fallback 0-chunks fonctionne

### Q4 — Comment le proto fait le recalibrage ?

Le recalibrage est mentionne dans les specs mais le code est dans app.py. Il faut verifier :
- Quand le compteur de corrections atteint 10/20/50
- Quel appel Claude est fait (analyze_style avec les 50 dernieres corrections ?)
- Comment style_profile.txt est reecrit
- Comment le score/level est mis a jour

### Q5 — Est-ce que /generate_reply fonctionne vraiment end-to-end ?

Le code est implemente mais a-t-il ete **teste** ? Possible qu'il y ait des bugs non detectes :
- Le Graph API retourne-t-il les donnees au bon format pour `_build_prompt()` ?
- Les corrections D2 sont-elles correctement chargees ?
- Le SSE streaming arrive-t-il correctement dans dialog.js ?
- La pre-injection greeting/closing fonctionne-t-elle ?

**Recommandation** : le PREMIER test a faire est d'ouvrir un mail dans New Outlook, cliquer le bouton BoosterMail, et tester la generation. Si ca marche, on sait que le moteur est branche et on se concentre sur les ecarts. Si ca ne marche pas, on debug avant tout.

---

## PLAN D'ACTION RECOMMANDE (a valider avec Yvan)

### Etape 0 — Test E2E (15 min)
Tester la generation sur New Outlook tel quel. Determiner si le moteur fonctionne deja.

### Etape 1 — Fix critique (5 min)
Corriger le bug `_setStatus()` dans dialog.js.

### Etape 2 — Lire app.py pour les questions ouvertes (30 min, nocode)
Repondre a Q2, Q3, Q4 en lisant le proto. NE PAS MODIFIER.

### Etape 3 — Connecter le prefetch cache (1-2h)
Solution S1 de l'Ecart 1 : verifier le cache avant le fetch inline.

### Etape 4 — Ajouter Bloc F echeances (30 min)
Solution S1 de l'Ecart 2 : requete DB + injection post-build.

### Etape 5 — Completer le post-envoi (3-4h)
Solution S1 de l'Ecart 4 : recalibrage + re-analyse contact en daemon threads.

### Etape 6 — Speculation (4-6h)
Solution S1 ou S2 de l'Ecart 3, selon le temps disponible.

### Etape 7 — Onboarding (2-3h)
Solution S1 de l'Ecart 9 : completer l'analyse de style.

---

## RESUME

Le moteur IA est **beaucoup plus avance** que ce que le TODO suggerait. Les routes principales sont implementees et fonctionnelles. Le travail restant est :
1. **Connecter les pieces** (prefetch → generate, echeances → prompt)
2. **Completer l'apprentissage** (recalibrage, re-analyse contact)
3. **Optimiser l'UX** (speculation, templates)
4. **Tester end-to-end** (le plus urgent)

Ce n'est plus un "portage de moteur" — c'est une **finalisation et optimisation** d'un moteur deja en place.
