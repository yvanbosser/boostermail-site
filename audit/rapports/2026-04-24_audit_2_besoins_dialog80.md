# Audit #2 — Besoins de données pour la complétude du dialog 80%

> **Date** : 24/04/2026
> **Type** : Audit structurel thématique — inventaire des besoins d'affichage
> **Périmètre** : `V2/dialog.html` + `V2/dialog.js` + endpoints consommés
> **Objectif** : recenser EXHAUSTIVEMENT ce que le dialog 80% doit afficher pour être « complet et instantané », afin de pouvoir ensuite mapper chaque besoin avec une source BG (cache / DB / generation BG)
> **Méthode** : Kit d'audit `C:/EasyMail/audit/` — Playbook workflow thématique, checklist Flux B/C/I/J, lecture code factuelle, aucune proposition de fix (audit de BESOINS, pas de solutions)

---

## 1. Résumé exécutif

Le dialog 80% consomme **~15 endpoints distincts** pour peupler **~35 zones d'affichage** réparties en 4 blocs (header, panneau gauche mail+résumé, panneau droit éditeur, popups post-envoi). L'ouverture idéale « instantanée » est conçue autour d'**un bundle unifié** (`/api/dialog_init`) qui agrège body + résumé + profil contact, complété par des fetches indépendants (contacts pour autocomplete, status, draft, instant_reply, template match, échéances). Le flux réel marque 8 repères perf (T0–T7), dont 6 sont bloquants pour la sensation « complet » : T2 header, T3 body, T4_first_point résumé, T5_first_chunk réponse, T6 tags contact, T7 PJ. Les échéances et la suggestion de classement ne sont pas bloquants pour « ouvert » — ils sont pré-calculés en BG et apparaissent si disponibles, sinon se peuplent en post-envoi. La granularité actuelle distingue précisément :

- **Données P0 (complétude requise)** : from_name, from_email, subject, body HTML, résumé (points+actions), profil contact (register+confidence), liste PJ, réponse pré-générée ou template
- **Données P1 (valeur ajoutée)** : badge source réponse, greeting/closing contact, drafts, échéances détectées
- **Données P2 (post-envoi / conditionnel)** : suggestion classement mail, suggestion classement PJ, smart_paperclip

Toutes les données **P0** ont un chemin de cache explicite dans `email_cache`, `mail_summaries`, `contact_profiles`, `_reply_cache`, `learned_templates` DB — l'ouverture instantanée est donc théoriquement servie par DB/RAM pour les mails pré-chauffés.

---

## 2. Baseline smoke_test

```
Smoke test : 38 PASS / 0 FAIL / 1 SKIP
- I-DATA-09 : V2 started <5min, cache not yet persisted (non bloquant)
[OK] Tous les invariants valides. Exit 0.
```

Baseline propre. Aucune anomalie invariant. V2 lancé récemment donc `prefetch_cache_v2.json` pas encore écrit — normal.

---

## 3. Inventaire complet des besoins d'affichage du dialog 80%

Tableau exhaustif (35 besoins recensés). Zones référencées `dialog.html:Lxxx`, handlers `dialog.js:Lxxx`.

### 3.A — Header (bandeau bleu, toujours visible)

| # | Zone UI (DOM id) | Donnée | Priorité | Source actuelle | Endpoint API | Format attendu | Blocant pour "ouvert" ? | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | `headerReplyLabel` (`dialog.html:L53`) | Libellé mode + nom/sujet ("Repondre a X", "Transferer — sujet") | P0 | URL params `fromName/from`, `subject`, `mode` (`dialog.js:L26-30`) | — (URL) | string | OUI | Rendu dans `_updateHeader()` `dialog.js:L416`, marque T2 |
| 2 | `tagRegister` (`dialog.html:L54`) | Registre du contact (tu/vous/formel) | P1 | `contact_profiles.register` (DB) | `/api/contact_profile/<email>` ou bundle `dialog_init.contact_profile` (`dialog.js:L438, L900`) | string | non-blocant | Rendu via `_applyContactProfile()` `dialog.js:L964`, marque T6 |
| 3 | `tagConfidence` (`dialog.html:L55`) | Niveau de confiance contact (0-100%) | P1 | `contact_profiles.confidence` | idem #2 | int | non-blocant | idem #2 |
| 4 | `headerStatus` (`dialog.html:L57`) | Status transitoire ("Generation en cours...", "Reponse prete 3.2s", "Erreur serveur") | P0 | État interne + messages d'erreur fetch | — (local) | string | non-blocant | Utilisé ~30 fois pour signaler avancement |
| 5 | Boutons header (`btnNavProfil/Contacts/Echeances/Close`) (`dialog.html:L59-63`) | URLs vers popup.html extension | P0 | `_backendUrl + /plugin/popup.html?view=…` | — | href | OUI (cliquables) | Doivent être actifs dès le load |

### 3.B — Panneau gauche — Onglet « Résumé »

| # | Zone UI | Donnée | Priorité | Source actuelle | Endpoint API | Format | Blocant ? | Notes |
|---|---|---|---|---|---|---|---|---|
| 6 | `resumeFrom` (`dialog.html:L86`) | "Nom — email@domain" expéditeur | P0 | URL params | — | string | OUI | Rendu dans `_loadMailBody()` `dialog.js:L810` |
| 7 | `resumeSubject` (`dialog.html:L87`) | Sujet du mail reçu | P0 | URL param `subject` | — | string | OUI | idem |
| 8 | `resumePoints` (`dialog.html:L88`) | Liste des points clés du mail (résumé IA) | P0 | `mail_summaries.points` DB (Haiku warmup bulk + piggyback) | `/api/mail_summary?wait=2` OU bundle `dialog_init.summary.points` OU SSE `/api/mail_summary_stream` (`dialog.js:L893, L3115, L3162`) | `string[]` | OUI (complétude) | Si cache MISS : streaming progressif. Marque T4_summary_first_point / T4_summary_done |
| 9 | `resumeActions` / `resumeActionsList` (`dialog.html:L92-94`) | Liste des actions attendues | P0 | `mail_summaries.actions` DB | idem #8 | `string[]` | OUI (complétude) | idem |
| 10 | `resumePJ` / `resumePJList` (`dialog.html:L96-98`) | Chips noms PJ dans le résumé | P1 | `email.attachments[]` via bundle ou `/api/email_body` | `/api/email_body.attachments` (`dialog.js:L1087-1102`) | `[{name,size,is_inline}]` | non-blocant | Affiché ssi `_hasAttachments` |
| 11 | `resumeSpinner` (`dialog.html:L90`) | "Analyse en cours..." pendant MISS cache | P1 | — | — | — | non-blocant | Masqué dès T4 done |

### 3.C — Panneau gauche — Onglet « Mail reçu »

| # | Zone UI | Donnée | Priorité | Source actuelle | Endpoint API | Format | Blocant ? | Notes |
|---|---|---|---|---|---|---|---|---|
| 12 | `mailFrom` (`dialog.html:L104`) | "Nom <email>" expéditeur | P0 | URL params | — | string | OUI | `dialog.js:L796` |
| 13 | `mailMeta` (`dialog.html:L105`) | "A : …  \| Cc : …  \| Date" | P0 | URL params + `email.date`/`email.to`/`email.cc` | bundle ou `/api/email_body` (`dialog.js:L952-960`) | string | OUI | Date localisée fr-FR |
| 14 | `mailSubject` (`dialog.html:L106`) | Sujet complet | P0 | URL param | — | string | OUI | — |
| 15 | `pjList` (`dialog.html:L107`) | Chips PJ avec taille | P0 si PJ | `email.attachments[]` | bundle ou `/api/email_body` (`dialog.js:L1063`) | `[{name,size,is_inline}]` | OUI si `_hasAttachments` | Marque T7_pj_rendered |
| 16 | `mailBody` / `bodySpinner` (`dialog.html:L108-110`) | Body HTML sanitisé du mail | P0 | `email_cache` DB (cached=true) OU Graph API fetch | `/api/dialog_init.email.html_body` OU `/api/email_body?messageId=X` OU `/api/current_mail.mail.body` (`dialog.js:L876, L1027, L2912-2956`) | HTML sanitisé (scripts/iframe/onclick strippés) | OUI | Marque T3_body_rendered avec source `cache|graph|standalone`. 2 paths parallèles en standalone (fetch race) |

### 3.D — Panneau droit — Éditeur réponse (zone de travail principale)

| # | Zone UI | Donnée | Priorité | Source actuelle | Endpoint API | Format | Blocant ? | Notes |
|---|---|---|---|---|---|---|---|---|
| 17 | `fieldTo` (`dialog.html:L125`) | Destinataire pré-rempli selon mode | P0 | URL params + `_computeModalFields()` | — | email string | OUI | Vide en forward (garde forward) |
| 18 | `fieldCc` (`dialog.html:L130`) | Copies pré-remplies en reply_all | P0 si reply_all | URL params calcul `allCc` | — | email string | OUI si reply_all | `dialog.js:L586-608` |
| 19 | `fieldSubject` (`dialog.html:L135`) | Sujet préfixé (Re:/Fw:) | P0 | URL param + préfixe calculé | — | string | OUI | `dialog.js:L576` |
| 20 | `acTo` / `acCc` (`dialog.html:L126, L131`) | Suggestions autocomplete 2+ chars | P1 | `contact_profiles` DB | `/api/contact_profiles` (`dialog.js:L2624`) | `[{name,email,org}]` | non-blocant | Cache localStorage TTL 1h |
| 21 | `modeReply/ReplyAll/Forward` (`dialog.html:L141-143`) | Boutons mode actif | P0 | `_mode` état local | — | bool actif | OUI | Masqué si `_mode==='new'` |
| 22 | `fieldBrief` (`dialog.html:L148`) | Textarea brief instructions | P0 | saisie user | — | string | OUI (éditable) | placeholder varie selon mode |
| 23 | `em-imp-chip R/S/H` (`dialog.html:L153-161`) | Importance auto-détectée | P0 | Auto-detect via regex mots-clés + override user | — (local `dialog.js:L501`) | "R"\|"S"\|"H" | non-blocant (défaut S) | Passe H si mots sensibles (litige, bail...) |
| 24 | `btnGenerate` (`dialog.html:L171`) | Déclencheur manuel | P0 | — | — | bool disabled | non-blocant | Masqué (display:none) depuis 21/04, auto via `_tryInstantReply` |
| 25 | `formatBar` (`dialog.html:L178-263`) | Barre mise en forme rich text | P0 | — | — | static | non-blocant (décoratif) | Toujours affichée |
| 26 | `editor` (`dialog.html:L266`) | Contenu de la réponse (contenteditable) | P0 | **Flux prioritaire** : 1) draft user (`drafts_v2`) → 2) preemptive (`_reply_cache` BG spec) → 3) template (fix/appris) → 4) streaming Claude SSE | `/api/instant_reply` → `/api/match_template` → `/generate_reply` (`dialog.js:L1408, L1324, L1628`) | HTML | **OUI** — cœur du produit | Marque T5_reply_first_chunk / T5_reply_done avec source `draft\|preemptive\|template\|stream\|cache` |
| 27 | `genSpinner` (`dialog.html:L270`) | "Generation en cours..." | P1 | — | — | — | non-blocant | Masqué dès 1er chunk |
| 28 | `tplBadge` / `draftBadge` (injectés dynamiquement) | Badge indiquant source ("Réponse rapide 92%", "Brouillon il y a 3h") | P1 | `res.source/res.badge/res.confidence/res.timestamp` | `/api/instant_reply` (`dialog.js:L1503-1522`) + `/api/get_draft` (`dialog.js:L1534`) | texte + % + relative time | non-blocant | Critique pour la confiance user (savoir pourquoi ça va vite) |
| 29 | `refineInput` (`dialog.html:L277`) | Textarea modification | P0 (modif) | saisie user | — | string | non-blocant | Déclenche `/refine_reply` SSE (`dialog.js:L1787`) |
| 30 | `btnShorter/Deeper/Regen/Restore` (`dialog.html:L289-292`) | Actions de raffinement | P0 (modif) | État version stack | — | — | non-blocant | Stack versions local |
| 31 | `btnSend` (`dialog.html:L294`) | "Relire et envoyer" / "Valider et envoyer" | P0 | `_isStandardMode` via `/api/status` (`dialog.js:L1969`) | `/api/status` | bool disabled + libellé | OUI (action principale) | Libellé change selon mode |
| 32 | `infoEcheance` / `infoEcheanceContent` (`dialog.html:L301-303`) | Card "Echeance detectee" (pré-envoi) | P2 | BG scan échéances | (pas de fetch pré-envoi dans `dialog.js` actuel — info post-envoi uniquement) | ? | non-blocant | Actuellement placeholder "—" ; l'endpoint `/api/echeances/post_send` est consommé en post-envoi (`dialog.js:L2215`) |
| 33 | `infoClassement` / `infoClassementContent` (`dialog.html:L305-307`) | Card "Classement suggere" (pré-envoi) | P2 | BG scan classification | (idem — info post-envoi uniquement) | ? | non-blocant | Le dossier suggéré existe dans `suggest_folder` et `classification/post_send` |

### 3.E — Popups conditionnelles

| # | Zone UI | Donnée | Priorité | Source | Endpoint | Format | Blocant ? | Notes |
|---|---|---|---|---|---|---|---|---|
| 34 | `popupPjAnalysis` / `pjAnalysisList` (`dialog.html:L318-334`) | Checkboxes PJ à analyser | P0 (si PJ) | `_attachmentsList` | `/api/extract_attachments/<msgId>` à l'accept (`dialog.js:L678`) | `[{name,size,is_inline}]` | non-blocant (popup) | Déclenchée avant `generateReply()` |
| 35 | `popupFwdPj` / `fwdPjList` (`dialog.html:L337-353`) | Checkboxes PJ forward | P0 (si forward+PJ) | `_attachmentsList` | — (pas d'appel — note `dialog.js:L742`: route `save_original_attachments` n'existe pas) | idem | non-blocant | Filtrage non effectif en pratique |
| 36 | `popupSmartPaperclip` / `smartPaperclipFolder` (`dialog.html:L356-368`) | Dossier Windows suggéré | P2 | — | `/api/smart_paperclip?email=X&subject=Y` (`dialog.js:L760`) | `{folder: string}` | non-blocant | Action user explicite trombone |
| 37 | `popupEcheances` / `echeancesBody` (`dialog.html:L376-383`) | Cards échéances détectées post-envoi | P2 | BG scan | `/api/echeances/post_send/<msgId>` (poll 8×500ms) (`dialog.js:L2215`) | `{status, echeances:[{description,titre,date_echeance}]}` | non-blocant | Post-envoi uniquement |
| 38 | `popupClassMail` / `classMailSuggestion` / `classMailTree` (`dialog.html:L387-399`) | Suggestion + arbo dossiers Outlook | P2 | BG | `/api/classification/post_send/<msgId>` (poll 2x1,5s) + `/api/classify_email` (`dialog.js:L2257, L2330`) | `{status, suggestion:{folder_id,folder_path,source}, folders:[{id,name,depth}]}` | non-blocant | Post-envoi. Uniquement Mode Complet |
| 39 | `popupClassPJ` / `classPJList` / `classPJSuggestion` (`dialog.html:L402-413`) | Classement PJ Windows | P2 | BG | `/api/pj_classification/post_send/<msgId>` (poll) + `/api/classify_pj` (`dialog.js:L2358, L2416`) | `{status, pj_suggestions:{attachments,suggestion:{folder_path}}}` | non-blocant | Post-envoi |

---

## 4. Flux de chargement dialog — séquence T0→T7

Marquage perf défini dans `dialog.js:L108-123`, logs via `/api/perf_log`.

```
T0_script_start (L205)           — dialog.js parsé, variables URL init
   │
   ├─ [eager fetch html inline]  — window.__bundlePromise lancé AVANT parse JS (dialog.html:L27-43)
   │                                  fetch /api/dialog_init?message_id=X&from_email=Y
   │
T1_init_end (L390)               — IIFE init terminé : header peint, boutons câblés
   │
T2_header_rendered (L427)        — _updateHeader() : label + buttons
   │
   ├─ _loadMailBody() → _loadDialogBundle() (L840)
   │     ├─ Consomme bundlePromise (email + summary + contact_profile)
   │     │
   │     ├─ _renderMailBody(bundle.email) → T3_body_rendered (L951) source=cache|graph
   │     ├─ _renderAttachments(bundle.email.attachments) → T7_pj_rendered (L1078)
   │     ├─ _renderSummaryInstant(bundle.summary) → T4_summary_first_point + T4_summary_done (L981-1022) source=cache
   │     │     OU si MISS → _fetchMailSummary() → SSE /api/mail_summary_stream → T4 source=stream
   │     └─ _applyContactProfile(bundle.contact_profile) → T6_contact_profile (L973)
   │
   ├─ _detectMode() (L1969)      — fetch /api/status (cache localStorage 1h) → libellé btnSend
   │
   ├─ _loadContacts() (L2596)    — fetch /api/contact_profiles (cache localStorage 1h) → autocomplete
   │
   ├─ _restoreDraft() (L1532)    — fetch /api/get_draft (draft user antérieur)
   │
   ├─ setTimeout 50 ms → _tryInstantReply() (L2977)
   │     └─ fetch /api/instant_reply → source ∈ {draft|preemptive|template|none}
   │           ├─ HIT → editor.innerHTML = res.text + _showInstantReplyBadge
   │           │        → T5_reply_first_chunk + T5_reply_done (source=cache) (L1440-1442)
   │           └─ NONE → _triggerAutoGenerate() (attend body max 3s) → generateReply() :
   │                       ├─ _tryTemplateMatch() → /api/match_template
   │                       │    └─ HIT → affichage + T5 source=template (L1353-1355)
   │                       └─ MISS → _fetchGenerateReply() → /generate_reply SSE Claude
   │                            └─ 1er chunk → T5_reply_first_chunk source=stream (L1684)
   │                            └─ stream end → T5_reply_done (L1758)
```

Note : en mode **standalone PyQt** (99% des cas), `_loadMailBodyStandalone()` remplace `_loadDialogBundle()` et fait 2 fetches en parallèle `/api/email_body` + `/api/current_mail` (`dialog.js:L2884`). Le bundle tourne côté backend de toute façon pour pré-chauffer les caches.

---

## 5. Critère « complet » — données OBLIGATOIRES

Pour considérer le dialog **complet** (pas seulement ouvert), les 11 données suivantes doivent être peintes :

| Critère | Zone | Source idéale « instantanée » |
|---|---|---|
| C1 | Header libellé (mode + contact) | URL params — toujours immédiat |
| C2 | From / Subject / Meta mail reçu | URL params + bundle |
| C3 | Body HTML du mail reçu | `email_cache` DB (<50ms) |
| C4 | Points clés résumé IA | `mail_summaries` DB (<100ms) |
| C5 | Actions attendues résumé IA | `mail_summaries` DB |
| C6 | Tags contact (register, confidence) | `contact_profiles` DB |
| C7 | Liste PJ (noms + tailles) | `email_cache.attachments` |
| C8 | Réponse pré-générée dans l'éditeur | `_reply_cache` RAM (preemptive) ou `drafts_v2` DB ou `learned_templates` |
| C9 | Badge source réponse (transparence) | Dérivé de C8 |
| C10 | Champs To/Cc/Subject pré-remplis | URL params |
| C11 | Bouton Envoyer activé avec libellé correct | `/api/status` cache 1h |

**Ce qui N'EST PAS blocant pour « complet »** : échéances, suggestion classement mail, suggestion classement PJ, smart paperclip, autocomplete (nice-to-have qui se chargent en BG).

---

## 6. Latence cible par donnée — sensation « instantanée »

Seuil psycho-perceptuel : <100 ms = instantané, <500 ms = rapide, 500–1500 ms = perçu comme chargement, >1500 ms = attente.

| Zone | Latence cible max | Source pour tenir le budget | Fallback acceptable |
|---|---|---|---|
| C1 Header (URL params) | <10 ms | URL params (0 RTT) | — |
| C2 From/Subject/Meta | <10 ms | URL params | bundle (50 ms) |
| C3 Body HTML | <100 ms | `email_cache` cached=true | Graph fetch 500–2000 ms (cache miss) |
| C4/C5 Résumé (points+actions) | <150 ms | `mail_summaries` DB (bulk warmup 50 mails Haiku) | SSE stream Haiku 2–4 s (MISS) |
| C6 Tags contact | <100 ms | `contact_profiles` DB | — |
| C7 PJ liste | <100 ms | `email_cache.attachments` | avec C3 |
| C8 Réponse dans éditeur | **<500 ms** si cache preemptive/draft/template | `_reply_cache` RAM ou `drafts_v2` DB | SSE Claude : 1er chunk <4 s, complet 5–15 s |
| C9 Badge source | <50 ms après C8 | dérivé de C8 | — |
| C10 Champs compose | <10 ms | URL params + calcul local | — |
| C11 Bouton Envoyer | <50 ms | localStorage `em_status_v1` (TTL 1h) | fetch `/api/status` 100–300 ms |
| Echéances (post-envoi) | polling 500 ms x8 (=4s max) | BG scan `/api/echeances/post_send` | timeout → skip étape |
| Classement mail | polling 1,5 s x2 (=3s max) | BG scan `/api/classification/post_send` | timeout → skip étape |
| Classement PJ | idem | BG scan | timeout → skip |

**Objectif produit** : 8 critères sur 11 (C1, C2, C3, C4, C5, C6, C7, C10, C11) doivent être P<200 ms quand le mail est pré-chauffé. C8 est le plus critique et aussi le plus couvert (4 sources de cache).

---

## 7. Anomalies (zones actuellement incomplètes ou à latence inacceptable)

Conformément à la définition objective du kit (violation invariant OU échec smoke OU dysfonctionnement observable). Rappel : pas de fix proposé ici, c'est un audit de BESOINS.

| # | Zone | Problème observé | Preuve | Sévérité |
|---|---|---|---|---|
| A1 | `infoEcheance` / `infoEcheanceContent` (`dialog.html:L302-303`) | La card "Echeance detectee" est statiquement peuplée avec `—` et n'est jamais mise à jour pré-envoi. Le code ne contient aucun fetch `/api/echeances/scan` ou équivalent avant envoi — l'info échéance apparaît UNIQUEMENT en popup post-envoi (`dialog.js:L2215`). | Aucun `echeancesContent.innerHTML` / `infoEcheanceContent` dans `dialog.js` (grep négatif). | P1 — besoin UI déclaré mais non servi |
| A2 | `infoClassement` / `infoClassementContent` (`dialog.html:L306-307`) | Idem : card "Classement suggere" reste à `—`, jamais peuplée pré-envoi. Le dossier suggéré existe pourtant dans `/api/suggest_folder/<msgId>` et `smart_paperclip` mais n'est pas consommé pour cette card. | Aucune mise à jour de `infoClassementContent` trouvée dans `dialog.js`. | P1 — besoin UI déclaré mais non servi |
| A3 | Popup forward PJ (`popupFwdPj`) | Le filtrage PJ à inclure est UI-visible mais inopérant. Commentaire `dialog.js:L742-748`: « la route /api/save_original_attachments n'existe pas côté V2 backend (appel produisait 404 silencieux). Le forward côté Graph inclut automatiquement TOUTES les PJ ». | `dialog.js:L742` | P2 — feature fantôme |
| A4 | Onglet « PJ » du panneau gauche — référence `[data-tab="pj"]` | `dialog.js:L1081` essaye de mettre à jour le libellé `PJ (N)` sur un onglet `data-tab="pj"` qui n'existe PAS dans `dialog.html` (seuls `data-tab="resume"` et `data-tab="full"` sont déclarés `dialog.html:L79-80`). | `dialog.html:L78-81` vs `dialog.js:L1081` | P2 — code mort / besoin déclaré implicitement non rendu |
| A5 | Résumé IA — latence MISS cache | Si `/api/mail_summary?wait=2` retourne `status=none` (mail non warmup-é), fallback SSE `/api/mail_summary_stream` peut prendre 2–4 s. Pendant ce temps le résumé reste à `Analyse en cours...`. Pas anormal, mais écart visible quand body est déjà rendu à 50 ms. | `dialog.js:L3162` wait=2 long-poll | P2 — latence acceptable mais sous-optimale |
| A6 | T3_body_source = `perfreduce` prévu mais non documenté côté flux | Constante déclarée `dialog.js:L115` mais pas d'émission claire dans le code. L'ancien mode dégradé passait par messageParent (`dialog.js:L2531`) sans marquer T3 avec cette source. | `dialog.js:L115` | P3 — cosmétique doc |
| A7 | `smartPaperclip()` (trombone intelligent) | `dialog.js:L760` passe `subject` sans sanitization d'URL. `encodeURIComponent` est bien présent, OK. Pas d'anomalie mais à noter : action user manuelle, aucun pré-calcul BG. | — | P3 — non anomalie, observation |

**Aucune violation d'invariant détectée.** Les anomalies A1/A2 sont les plus notables — elles révèlent que les cards `em-info-row` du toolbar bas (zone pré-envoi) ont été **conçues pour afficher en temps réel les métadonnées IA (échéance + classement) mais leur source n'est pas câblée**. Le besoin UI est réel, la donnée est disponible (endpoints existent), le câblage est absent.

---

## 8. Synthèse pour mapping BG → besoins

Pour chaque besoin P0, la source BG idéale est identifiée :

| Besoin | Source BG requise | Couverture actuelle |
|---|---|---|
| Body mail | `email_cache` DB + Graph fetch | OK — 2 niveaux |
| Résumé (points/actions) | `mail_summaries` DB (warmup bulk 50 mails Haiku) + piggyback | OK — bulk+piggyback |
| Profil contact | `contact_profiles` DB (re-analyse tous les 3 mails) | OK |
| Liste PJ | `email_cache.attachments` | OK |
| Réponse pré-générée | `_reply_cache` RAM (TIER 1 spec préemptive + continuous loop 45s) + `learned_templates` + `drafts_v2` | OK — 4 couches |
| Badge source | dérivé | OK |
| Champs compose | URL params | OK (0 RTT) |
| Statut standard/dégradé | localStorage 1h + `/api/status` | OK |
| Autocomplete contacts | localStorage 1h + `/api/contact_profiles` | OK |
| **Echéance pré-envoi (A1)** | **manque** : pas de pré-calcul affiché pré-envoi | **non câblé** |
| **Classement pré-envoi (A2)** | **manque** : pas de pré-calcul affiché pré-envoi | **non câblé** |

Les **2 seuls besoins P1 non servis par BG** au moment de l'ouverture du dialog sont les cards `infoEcheance` et `infoClassement` (zones UI visibles avec `—`). Toutes les autres données sont couvertes par au moins un chemin de cache/DB.

---

## 9. Méthodologie

1. Lecture `audit/README.md` + `audit/PLAYBOOK.md` — workflow thématique appliqué.
2. Lancement `audit/tests/smoke_test.ps1` — 38/38 PASS, baseline propre.
3. Parcours `audit/checklists/flux_end_to_end.md` sections B, C, I, J — chaque étape mappée à la zone UI consommée.
4. Lecture complète `V2/dialog.html` (418 lignes).
5. Lecture ciblée `V2/dialog.js` (3368 lignes) : init + handlers fetch + zones perf marks + popups post-envoi.
6. Vérification endpoints `/api/dialog_init` (L3471), `/api/email_body` (L3877), `/api/mail_summary` (L3257), `/api/contact_profile` (L3787), `/api/instant_reply` (L5635), `/api/match_template` (L5848), `/api/extract_attachments` (L4531), `/api/smart_paperclip` (L5068), `/api/suggest_folder` (L4063), `/api/echeances*` (L4794+), `/api/classification/post_send`, `/api/pj_classification/post_send`.
7. Aucune proposition de fix formulée (audit de besoins).

---

**Fin du rapport Audit #2 — 38 besoins recensés, 2 besoins non câblés (A1/A2), 0 anomalie d'invariant.**
