# Inventaire V2 — map du territoire

> **Dernière mise à jour** : 22/04/2026
> **Rôle** : connaissance exhaustive du périmètre à auditer. Mis à jour à chaque ajout/retrait de fichier significatif.

---

## Périmètre total audité

| Composant | Fichiers principaux | Lignes | Rôle |
|---|---|---|---|
| **V2 backend** | `V2/app_plugin.py` | 7378 | Flask HTTPS port 3443, 80 routes |
| V2 auth | `V2/auth_microsoft.py` | 287 | OAuth Microsoft MSAL |
| V2 IA | `V2/claude_ai.py` | 1911 | Prompts + appels Claude |
| V2 DB | `V2/database.py` | 1423 | SQLite, 11+ tables |
| V2 Graph | `V2/outlook_graph.py` | 1059 | Client Microsoft Graph |
| V2 cert | `V2/generate_cert.py` | 73 | Génération cert auto-signé |
| V2 templates mail | `V2/templates_mail.py` | 413 | Templates fixes |
| V2 core (abstractions) | `V2/core/*.py` | 1254 | Providers IA + email + auth |
| **V2 frontend** | `V2/dialog.js` | 2822 | Dialog 80% |
| | `V2/popup.js` | 982 | Overlay |
| | `V2/taskpane.js` | 667 | Mode Office.js taskpane |
| | `V2/autorunshared.js` | 726 | Addin shared runtime |
| | `V2/commands.js` | 188 | Addin commands |
| V2 HTML | `V2/dialog.html` (390) + popup.html (299) + taskpane.html (19) + autorun.html (14) + commands.html (11) | 733 | UIs |
| V2 extension | `V2/extension/*` | ~300 | Extension Chrome (mode web) |
| **Companion** | `companion/companion.py` | 1123 | HTTP port 5051, COM Outlook + filesystem |
| Popup PyQt | `companion/popup_pyqt.py` | 1473 | Overlay Qt + dialog WebView |
| **Service** | `boostermail_service.py` | 717 | Superviseur qui lance tout au logon |
| **Install** | `install_outlook_addin.py` | 366 | Sideload addin (registry + cert + manifest copy) |
| | `install.ps1` | ~100 | Install initial |
| | `uninstall.ps1` | ~80 | Désinstallation |
| **Total audité** | | **~24 000 lignes** | |

---

## Routes V2 backend (80 routes `@app.route`)

### Groupe 1 — Infrastructure (6)
- `GET /` — landing backend
- `GET /api/status` — health check
- `GET /api/activation_status` — état activation user
- `GET /api/sse/events` — SSE broadcast
- `GET /api/warmup_status` — progression warmup
- `GET /plugin/<path:path>` — static assets + HTML

### Groupe 2 — Mail courant + polling (5)
- `POST /api/event/message_read` — Office.js push
- `POST /api/event/new_compose` — Office.js compose
- `GET /api/current_mail` — dernier mail connu
- `GET /api/current_compose` — dernier compose connu
- `GET /api/selected_mail` — fallback Mac

### Groupe 3 — Email body + metadata (5)
- `GET /api/email_body` — fetch body via Graph
- `GET /api/suggest_folder/<msg_id>` — suggestion classement
- `POST /api/classify_email` — classement mail
- `GET /api/folders` — arborescence folders Outlook
- `GET /api/onedrive/folders` + `GET /api/windows_folders`

### Groupe 4 — Génération + cache (8)
- `POST /api/instant_reply` — pipeline unifié (draft>preemptive>template>none)
- `GET /api/prefetch_status` — état spec BG
- `POST /api/trigger_prefetch` — force prefetch
- `POST /api/match_template` — template match
- `POST /api/template_feedback` — learning loop
- `POST /generate_reply` — SSE streaming Claude
- `POST /refine_reply` — SSE refinement
- `POST /send_reply` — envoi mail (Graph)

### Groupe 5 — Drafts + résumé (5)
- `POST /api/save_draft`
- `GET /api/get_draft`
- `GET /api/mail_summary` — résumé IA
- `POST /api/reply_cache/purge`
- `GET /api/post_send` — workflow post-envoi

### Groupe 6 — Classement / échéances / contacts (15+)
- `GET /api/echeances*` (multiple)
- `GET /api/contact_profile*`
- `POST /api/delete_email`, `/api/archive_email`
- `GET /api/smart_paperclip`
- `POST /api/pj_classification`
- etc.

### Groupe 7 — Onboarding + profil (6)
- `POST /api/start_onboarding`
- `GET /api/onboarding_status`
- `GET|POST /api/profile*`

### Groupe 8 — Proxy Companion (1 route whitelist)
- `ALL /api/companion/<path>` — proxy vers Companion 5051

### Groupe 9 — Debug + metrics (5)
- `POST /api/debug_addin_log`
- `GET /api/metrics`, `/api/scoring`, etc.

### Groupe 10 — OAuth Microsoft (4)
- `GET /auth/start`
- `GET /auth/callback`
- `POST /auth/logout`
- `GET /auth/status`

---

## Routes Companion (13)

- `GET /status` — health check
- `GET /folders` — scan filesystem (PJ Windows)
- `POST /copy` — copie fichier local (PJ Windows)
- `GET /current_selection` — mail sélectionné via COM Outlook (⚠ popup OOM)
- `POST /inject_reply` — injecte body dans compose Outlook (⚠ popup OOM)
- `GET /detect_compose` — détecte si compose ouvert (COM)
- `GET /prefetch_sender` — recherche expéditeur (COM)
- `GET /prefetch_subject` — recherche keyword (COM)
- `GET /api/get_table` — liste mails via COM Table
- `POST /open_dialog_native` — ouvre dialog PyQt
- `GET /search` — Windows Search (onboarding)
- `GET /scan_folders` — scan Outlook folders
- `GET /outlook_folders` — détection multi-account

---

## Flux principaux (end-to-end)

### Flux A — Boot PC → BM opérationnel
```
Windows logon
 → boostermail_service.py démarre (tray service)
 → install_outlook_addin.py exécuté (auto-réparation idempotente)
 → Companion lancé (port 5051)
 → V2 lancé (port 3443, dual-bind IPv4+IPv6)
 → popup_pyqt lancé si Outlook up (IPC 5052)
 → warmup V2 démarre (fetch 50 mails, résumés Haiku, prefetch 20 TIER 1)
 → user voit le bouton BM dans Outlook
```

### Flux B — Clic bouton BM dans Outlook
```
User clique BM dans action bar Outlook
 → autorunshared.js openEasyMailDialog
 → POST /api/event/message_read (avec metadata mail)
 → V2 stocke _current_mail_data, lance _run_prefetch BG
 → autorunshared.js → IPC vers popup_pyqt (5052)
 → popup_pyqt → signal Qt → dialog WebView charge
 → dialog.html / dialog.js init
 → dialog fetch /api/current_mail, /api/email_body
 → dialog fetch /api/instant_reply (draft > preemptive > template > none)
 → si none : dialog déclenche generateReply → SSE Claude stream
```

### Flux C — Envoi du mail
```
User clique Envoyer dans dialog
 → dialog.js _sendViaCompanion (malgré le nom, Graph-first)
 → POST /send_reply (Graph first avec client_request_id UUID)
   ↓ si 200
 → Graph API : createReply → PATCH body → send
 → response.success = true
 → dialog affiche "Mail envoye", post_send hooks
   ↓ si 403 Mode Dégradé
 → fallback /api/companion/inject_reply (COM, risque popup OOM)
```

### Flux D — Fermeture dialog
```
User clique × dialog
 → dialog.js _closeDialog → easymail://close-dialog
 → popup_pyqt._close_dialog → _force_overlay_geometry
 → retour à overlay (setFixedSize 80px folded par défaut)
```

### Flux E — Warmup au boot V2 (async, post-ready)
```
_warmup_done = True (flag)
 → 5 prefetch threads lancés (mails top 5)
 → _run_preemptive_bg (top 20 TIER 1, Claude Sonnet, stagger 500ms)
 → _background_preload_loop (non-traités, pause si user actif)
 → Windows folders pre-warm
 → PJ PDF pre-extract (top 10)
 → _bulk_preload_contacts (bulk DB read)
 → _bulk_prescan_echeances (heuristique regex)
 → _bulk_summaries_warmup (Haiku batch, 50 mails)
 → _continuous_speculation_loop (toutes les 45s, top 50)
```

### Flux F — Piggyback résumé sur /api/email_body
```
Dialog ouvre → fetch /api/email_body
 → V2 fetch Graph body
 → Si pas déjà en DB : thread BG summarize_mails_to_db
 → DB table mail_summaries enrichie
 → dialog fetch /api/mail_summary (retry 4x avec backoff)
 → affiche points + actions dans panneau gauche
```

### Flux G — Poll mail sélectionné (fallback)
```
V2 _poll_companion_loop toutes les 2s
 → try Graph get_received_emails(limit=1) FIRST (fix 21/04)
 → fallback Companion COM seulement si pas de Graph
```

### Flux H — Spec préemptive continue
```
Toutes les 45s :
 → scan top 50 mails _warmup_cache
 → filtre TIER 1 (contacts connus) + Smart Speculative 6 filtres
 → lance _run_prefetch + _start_speculative (stagger 2s)
 → _reply_cache[msg_id] = {status: 'done', text: Claude response}
```

---

## Tables DB (boostermail.db V2)

| Table | Colonnes clés | Rôle |
|---|---|---|
| `threads` | project, data | Cache contextes A/B |
| `contact_profiles` | email, name, org, greeting, register, confidence, etc. | Profils contacts auto-appris |
| `style_corrections` | proposed, sent, category | Apprentissage style |
| `metrics` | action, duration_ms, importance, direct_send | Métriques envois |
| `settings` | key, value | Config (anthropic_api_key, user_name, writing_level) |
| `score_history` | date, score | Évolution scoring 0-100 |
| `echeances` | description, date_echeance, type, priorite | Échéances détectées |
| **`mail_summaries`** (21/04) | message_id PK, points JSON, actions JSON, model | Résumés IA batch Haiku |
| `treated_emails` | entry_id PK, action | Mails répondus/classés |
| `folder_classifications` | entry_id, folder_path, keywords | Classement Outlook |
| `pj_classifications` | sender, attachment, folder | Classement PJ Windows |
| `learned_templates` | pattern, core, register, status | Templates auto-appris |
| `email_cache` | entry_id PK, email JSON | Cache mails recent |
| `folder_cache` | folder_path, folder_id | Cache dossiers Outlook |

---

## Fichiers de config / secrets

| Fichier | Contenu |
|---|---|
| `config.json` | `anthropic_api_key`, `openai_api_key`, `fernet_key`, `microsoft` (OAuth), `google` (OAuth). NE JAMAIS commiter |
| `V2/manifest.xml` | Manifest Office.js addin, contient Id GUID + URLs https://localhost:3443 |
| `V2/localhost.crt` | Cert TLS auto-signé (SAN : localhost + 127.0.0.1 + ::1) |
| `V2/localhost.key` | Clé privée RSA 2048 |
| `V2/boostermail.db` | SQLite, WAL mode |
| `V2/prefetch_cache_v2.json` | Cache prefetch persistant (TTL 48h, atexit save) |
| `style_profile.txt` (racine) | Profil de style utilisateur (8000+ chars) |

---

## Dépendances critiques (`requirements.txt`)

- `flask==3.0.0`
- `anthropic==0.40.0`
- `msal`
- `pywin32==308` (COM Companion)
- `PyQt6` + `PyQt6-WebEngine`
- `cryptography` (cert)
- `requests`
- `PyPDF2`, `python-docx`, `openpyxl` (optionnelles pour OCR PJ)

---

## Ce que je consulte en premier lors d'un audit

1. `smoke_test.ps1` → état baseline objectif
2. Ce fichier (INVENTAIRE) → "qu'est-ce que je dois couvrir ?"
3. `INVARIANTS.md` → "quelles sont les règles non-négociables ?"
4. `ANOMALIES_RECURRENTES.md` → "quels patterns déjà vus pour chercher en priorité ?"
