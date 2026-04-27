# Prompt — Prochaine session BoosterMail V2

> **À copier-coller en début de session** pour démarrer efficacement.
> **Contexte** : prend la suite de la session 25/04/2026 (Phase 1+2+3 + garde-fou drafts).

---

## Prompt à copier-coller

```
Bonjour Claude. On reprend BoosterMail V2.

Hier (25/04) on a fait 15 commits centrés sur la fiabilisation du flux BG → click :
- Phase 1 : étiquetage canonique IMID strict via _canonical_mid()
- Phase 2 : filtre unifié Smart Speculative (1 filtre = 5 plats)
- Phase 3 : 3 portes API séparées (échéance / classement mail / classement PJ)
- Garde-fou anti-pollution drafts + 11 autres fixes

V2 N'A PAS encore été redémarré pour activer ces changements.

AVANT TOUT : lis dans cet ordre :
1. NOUVELLE_SESSION_V3.md (guide de démarrage à jour)
2. docs/sessions/BILAN_SESSION_20260425.md (bilan complet d'hier)
3. audit/INVARIANTS.md (invariants techniques P1-P14)
4. audit/PLAYBOOK.md (kit audit — réflexe pour tout diagnostic)

Puis on enchaîne :

ÉTAPE 1 — VALIDATION DU RESTART V2 (priorité absolue, mode nocode)
- Demande-moi de redémarrer V2 si pas déjà fait
- Lis V2_stderr.log : vérifie [reply_cache] 36 entrée(s) restaurée(s) au boot
- Demande-moi de tester les 4 mails de référence : Ombeline Guérin,
  Vincent Hubert, Vincent Lecou, Christelle MENDES
- Si MISS persiste sur instant_reply → diagnostic logs en mode nocode
  AVANT toute correction de code

ÉTAPE 2 — BUGS UI IDENTIFIÉS HIER NON TRAITÉS
Si Étape 1 OK, attaquer dans l'ordre :
1. Interlignes apparaissent puis disparaissent dans le dialog
2. Signature dupliquée ou mal placée
3. Graph 400 sur extract_attachments (frontend envoie IMID, Graph veut Entry ID)

Méthode : analyse → implémentation → contrôle → test, phase par phase
(comme hier). Si test négatif → correction → retest → recontrol jusqu'à
positif. Pas de phase suivante avant validation.

RAPPEL DES RÈGLES :
- "nocode" = on ne code pas, on se pose, on réfléchit, on creuse
  (lecture/audit/analyse seulement, pas d'Edit/Write sur le code)
- Kit audit (audit/PLAYBOOK.md + audit/INVARIANTS.md +
  audit/ANOMALIES_RECURRENTES.md) consulté en RÉFLEXE quand un bug
  est non-trivial, AVANT de toucher le code
- Worktree de travail : claude/unruffled-pascal-ba42f3
- Production = C:/EasyMail/V2/ (à synchroniser après chaque commit worktree)

C'est parti. Commence par lire les 4 docs ci-dessus, puis demande-moi
si V2 a été redémarré.
```

---

## Axes à creuser dans cette session

### 🔴 Axe 1 — Validation Phase 1+2+3 sur tests réels (priorité absolue)

**Question principale** : les drafts pré-rédigés sont-ils maintenant trouvés au clic utilisateur ?

**Méthode** :
1. Restart V2 → premières lignes de log
2. Tests manuels sur les 4 mails de référence
3. Inspection logs en cas de MISS persistant : chercher `[instant_reply] HIT` vs `[instant_reply] MISS reason='...'`
4. Si HIT systématique → ✅ Phase 1+2+3 validées
5. Si MISS persiste → analyse en mode nocode (kit audit)

**Documents à consulter en cas de souci** :
- `audit/INVARIANTS.md` — invariant I-DATA-11 (clé canonique IMID)
- `audit/ANOMALIES_RECURRENTES.md` — Pattern #14 (clés cache mixtes)
- `audit/rapports/2026-04-23_audit_coherence_cles_cache.md` — précédent passage sur le sujet

### 🟠 Axe 2 — Bug interlignes (si Axe 1 OK)

**Symptôme** : dans le dialog, après affichage de la réponse Claude, les interlignes apparaissent puis disparaissent (rendu HTML qui clignote).

**Hypothèses** :
- `_normalize_reply_to_html()` produit des `<br>` qui sont ensuite collapsés
- Le streaming `editor.insertAdjacentText('beforeend', chunk)` ne gère pas bien les newlines
- Le path cache hit (`editor.innerHTML = res.text`) écrase le contenu streamé

**Documents à consulter** :
- `V2/dialog.js` lignes 1500-1600 (instant_reply consumer)
- `V2/dialog.js` lignes 1740-1840 (streaming consumer)
- `V2/app_plugin.py` chercher `_normalize_reply_to_html`

### 🟠 Axe 3 — Bug signature

**Symptôme** : signature dupliquée ou mal placée dans la réponse générée.

**Hypothèses** :
- Claude inclut une signature dans sa génération + `instant_reply` en ajoute une → doublon
- `_should_append_signature(closing, user_name)` ne détecte pas le pattern `Cdlt yvan` qui contient déjà le prénom
- Différence entre path streaming (qui n'ajoute rien) vs path cache (qui ajoute via `html_parts.append(user_name)`)

**Documents à consulter** :
- `V2/app_plugin.py` chercher `_should_append_signature` et `instant_reply` step 2 (ligne ~6770-6786)
- Comparer avec proto pour la logique d'origine

### 🟠 Axe 4 — Graph 400 sur extract_attachments

**Symptôme** : `GET /me/messages/<imid>/attachments` → `400 Id is malformed`.

**Cause** : Graph API veut un Entry ID (format `AQMkAD...`), pas un IMID (format `<...@domain>`). Le frontend envoie l'IMID (correct côté nous), mais Graph ne sait pas le résoudre directement.

**Solution probable** : avant l'appel `graph.get_attachments(message_id)`, résoudre l'IMID en Entry ID :
- Helper `_db.get_email_by_internet_id(imid)` (déjà ajouté Phase 1) retourne le row email_cache
- Récupérer `entry_id` depuis ce row
- Appeler `graph.get_attachments(entry_id)`

**Sites à modifier** :
- `V2/app_plugin.py` ligne ~5414 (`api_extract_attachments`)
- Possiblement d'autres endpoints qui appellent `graph.*` avec un IMID

### 🟢 Axe 5 (bonus, si tout va bien) — 22 manques V2 vs proto

4 traités hier (R/S/H, email_cache, suggestions multiples, Smart Speculative coverage). 18 restants — voir `docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md` pour la priorisation.

Candidats P0 restants :
- Templates fixes + appris (45 fixes du proto)
- Pipeline contexte A/B/C optimisé
- Contexte C par mots-clés
- Réfutation Claude inline

---

## Documents à consulter (liste non exhaustive)

### Lecture obligatoire en début de session
1. **`NOUVELLE_SESSION_V3.md`** — guide de démarrage à jour
2. **`docs/sessions/BILAN_SESSION_20260425.md`** — bilan détaillé d'hier
3. **`CLAUDE.md`** — règles absolues (section 25/04 ajoutée)
4. **`audit/INVARIANTS.md`** — invariants techniques P1-P14

### Selon le sujet investigué

| Si le sujet est… | Lire en priorité |
|---|---|
| Étiquetage cache / lookup MISS | `audit/INVARIANTS.md` (I-DATA-11), `audit/rapports/2026-04-23_audit_coherence_cles_cache.md` |
| Smart Speculative filtres | `audit/INVARIANTS.md` (P11 list vs str), `V2/app_plugin.py:_should_speculate` |
| Drafts BG / `_reply_cache` | `audit/ANOMALIES_RECURRENTES.md` (Pattern #14), `V2/app_plugin.py:_start_speculative` |
| Templates / réponses rapides | `docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md`, `V2/templates_mail.py` |
| Contexte A/B/C | `docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md` (section 7), `V2/app_plugin.py:_run_prefetch` |
| Profils contacts | `docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md` (section 13) |
| Office.js / dialog | `V2/dialog.js`, `V2/autorunshared.js`, `docs/v2_specs/SPEC_PHASE2_DIALOG.md` |
| Graph API | `V2/outlook_graph.py`, `docs/v2_specs/SPEC_PHASE2_GRAPH.md` |
| Companion (COM proxy) | `companion/companion.py`, `docs/v2_specs/SPEC_PHASE2_COMPANION.md` |

### Logs à consulter en cas de bug
- `C:/EasyMail/V2_stderr.log` — log principal V2 (Flask + Python)
- `C:/EasyMail/addin_debug.log` — log Office.js depuis le bouton BoosterMail
- `C:/EasyMail/boostermail.log` — log superviseur
- `C:/EasyMail/popup_pyqt.log` — log popup PyQt

### DB à inspecter
- `C:/EasyMail/V2/boostermail.db` — DB V2 (séparée du proto)
- Tables clés : `mail_summaries`, `mail_classement_cache`, `mail_pj_classement_cache`, `mail_echeance_cache`, `email_cache` (avec colonne `internet_message_id` ajoutée Phase 1)
- Fichiers JSON : `drafts_v2.json` (36 drafts au 25/04 19h), `prefetch_cache_v2.json`

---

## Récap commits du worktree (ordre chronologique 25/04)

```
fc8f7f7 P9+P10 — warmup_cache coverage + perpetual-retry + F1=30j
4f1ca87 P1+P2+P3 — coverage draft-first + Claude fallback classement/PJ + top-3
bbf1300 déclenche preview dès que le draft est prêt
ce906a3 self-mail guard classement + normalisation dest_folder PJ
d7da818 cache partagé arborescence Outlook (évite 429 Graph)
9be80ac C-bis tier2 perpetual-retry + Néant UI + INVARIANTS P11-P13
a825fd9 email_cache + index internet_message_id (Pattern #14)
5563c6e Gap #4 : detect_importance proto → V2 (R/S/H + contacts sensibles)
713a535 3 améliorations post-stabilisation BG (R/S/H + email_cache + streaming)
7d76446 circular reference dans suggest_folder()
cdbd39e P14 guard anti-écrasement drafts valides par 'filtered'
04c372e Phase 1 — Étiquetage canonique strict via _canonical_mid()
3d8cdab Phase 2 — Filtre unifié Smart Speculative (1 filtre = 5 décisions)
a21c213 Phase 3 — 3 portes séparées (échéance + classement + classement PJ)
3be6cbb fix: garde-fou anti-pollution drafts (refus Claude détectés à l'écriture)
```

---

## Format de message attendu côté Claude

Au démarrage de la prochaine session, Claude doit :
1. **Confirmer** la lecture des 4 docs en début de session
2. **Demander** si V2 a été redémarré
3. **Lire** les premières lignes de `V2_stderr.log` après confirmation
4. **Proposer** le test des 4 mails (Ombeline / Vincent x2 / Christelle)
5. **Diagnostiquer** en mode nocode si problème, **avant** toute action de code

NE PAS commencer à coder sans validation utilisateur après diagnostic.
