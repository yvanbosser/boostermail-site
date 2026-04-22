# Checklist — flux end-to-end à valider

> **Usage** : lors d'un audit complet, parcourir chaque flux et vérifier que chaque étape fonctionne. Pour chaque étape, noter si ✅ / ⚠️ / ❌.

---

## Flux A — Boot PC → BM opérationnel

| # | Étape | Critère de succès | Comment vérifier |
|---|---|---|---|
| A1 | Superviseur démarre au logon | Process `boostermail_service.py` actif | `Get-Process python* \| Where-Object CommandLine -like '*boostermail_service*'` |
| A2 | Auto-sideload addin exécuté | Log `Auto-sideload addin : OK` | `Get-Content boostermail.log -Tail 20` |
| A3 | Companion lancé | Port 5051 listening | `Get-NetTCPConnection -LocalPort 5051` |
| A4 | V2 lancé | Port 3443 listening sur **2 interfaces** (IPv4 + IPv6) | `Get-NetTCPConnection -LocalPort 3443` → 127.0.0.1 + ::1 |
| A5 | Cert TLS valide avec SAN complète | Thumbprint = `V2/localhost.crt` + SAN 3 entrées | `certutil -dump V2/localhost.crt` |
| A6 | Registry addin présent | `HKCU\...\Wef\Developer\{Id} = chemin_manifest` | `reg query "HKCU\Software\Microsoft\Office\16.0\Wef\Developer"` |
| A7 | Outlook up → popup_pyqt lancé | Log `Popup PyQt lancee` | log superviseur |
| A8 | Bouton BM visible dans Outlook | Test user visuel | user |

---

## Flux B — Clic bouton BM dans Outlook

| # | Étape | Critère | Vérif |
|---|---|---|---|
| B1 | Office.js `item_changed_fired` | Log `addin_debug.log` | `Get-Content addin_debug.log -Tail 10` |
| B2 | `button_clicked` event | Log idem | idem |
| B3 | POST `/api/event/message_read` | Response 200 | `addin_debug.log` `newOutlook_fetch_result status=200` |
| B4 | IPC vers popup_pyqt | Log `[ipc] HTTP POST /open_dialog reçu` | `popup_pyqt.log` |
| B5 | Signal Qt émis en < 10 ms | `[ipc] signal émis en X ms` | idem |
| B6 | `[hot] open_dialog_via_ipc START` | Log idem | idem |
| B7 | Dialog `[full-load] T+X ms DONE` avec X < 200 | Log idem + I-UX-01 | idem |
| B8 | Dialog visible et chargé | Test user visuel | user |
| B9 | Pas de popup OOM Outlook pendant B1-B8 | Observation visuelle user | user |

---

## Flux C — Dialog ouvert → réponse instantanée

| # | Étape | Critère | Vérif |
|---|---|---|---|
| C1 | Dialog fetch `/api/current_mail` | Response 200 avec mail courant | curl test |
| C2 | Dialog fetch `/api/email_body?messageId=X` | Response 200 avec body HTML | curl test |
| C3 | Piggyback résumé lancé (si mail inconnu DB) | Log `[summary] ...` | curl test `/api/mail_summary` |
| C4 | Dialog fetch `/api/instant_reply` | Response avec source = draft / preemptive / template / none | log V2 `[instant_reply] HIT/MISS` |
| C5 | Si source=none → auto-trigger generateReply | Log `auto-generateReply() déclenchée` | console dialog |
| C6 | `/generate_reply` stream SSE commence | Chunks arrivent dans l'éditeur | user visuel |
| C7 | Premier chunk < 4 s après click BM | Latence totale mesurable | chronométrer |
| C8 | Résumé se peuple dans panneau gauche | Points + Actions visibles | user visuel |

---

## Flux D — Envoi du mail

| # | Étape | Critère | Vérif |
|---|---|---|---|
| D1 | User click "Envoyer" → `_sendViaGraph` ou `_sendViaCompanion` | `client_request_id` UUID généré | console JS |
| D2 | POST `/send_reply` avec UUID | Response 200 `{success: true}` | curl post test |
| D3 | Graph API chaîne createReply→PATCH→send | Log V2 `[send_reply] OK mode=reply req=...` | log V2 |
| D4 | Mail visible dans Outlook Sent Items | Test user visuel | user |
| D5 | Idempotence : retry avec même UUID → dedup | Log V2 `[send_reply] DEDUP` | curl post répété |
| D6 | Post-send hooks : post_send, mark_treated, purge cache | Log idem | log V2 |
| D7 | Pas de popup OOM pendant envoi | Observation | user |

---

## Flux E — Fermeture dialog → retour overlay

| # | Étape | Critère | Vérif |
|---|---|---|---|
| E1 | Click × dialog → `easymail://close-dialog/reply` | Log popup_pyqt `Action easymail://close-dialog/reply` | popup_pyqt.log |
| E2 | `_close_dialog()` → `_force_overlay_geometry()` | Log `Fermeture dialog, retour overlay` | idem |
| E3 | Overlay affiché sur taille fixe (fold par défaut) | `setFixedSize` appliqué, hauteur FOLDED_H | popup_pyqt.log `_FOLDED_H` |
| E4 | Placeholder progression cleared si en cours | `_progressPlaceholderActive = false` | console JS |
| E5 | Draft auto-save persisté via `keepalive:true` | Entrée dans DB `drafts_v2` | `_db.get_draft` |

---

## Flux F — Warmup au boot V2

| # | Étape | Critère | Vérif |
|---|---|---|---|
| F1 | Log `Lancement backends au logon` | présent dans boostermail.log | log |
| F2 | V2 `_warmup_done = True` après ~30-60s | Log `Warmup terminé` | log V2 stderr |
| F3 | `_run_preemptive_bg` : 20 TIER 1 spéculation lancées (stagger 500ms) | Log `Spéculation préemptive : N candidat(s)` | log V2 |
| F4 | `_bulk_summaries_warmup` : ~50 mails batch Haiku → DB | Log `[warmup] résumés IA : +N` | log V2 |
| F5 | `_background_preload_loop` actif | Log `Background preload loop` | log V2 |
| F6 | Fast path cache chaud : si `prefetch_cache_v2.json` < 48h → skip Graph fetch | Log `Warmup FAST PATH` | log V2 |
| F7 | Pendant warmup : endpoints V2 répondent toujours | curl en parallèle du warmup | test manuel |

---

## Flux G — Polling mail sélectionné (Graph first)

| # | Étape | Critère | Vérif |
|---|---|---|---|
| G1 | `_poll_companion_loop` tourne toutes les 2s | Log périodique | log V2 |
| G2 | En Mode Complet (Graph dispo) : **jamais** d'appel Companion COM | Log `Source de données : Graph API` | log V2 |
| G3 | En Mode Dégradé (pas Graph) : fallback Companion `/current_selection` | Log `Source : Companion COM (Mode Degrade fallback)` | log V2 |
| G4 | Pas de popup OOM pendant polling | Observation user | user |

---

## Flux H — Spec préemptive continue

| # | Étape | Critère | Vérif |
|---|---|---|---|
| H1 | `_continuous_speculation_loop` cycle toutes les 45s | Log `[cont-spec] cycle : N nouveau(x) candidat(s)` | log V2 |
| H2 | Scan top 50 mails `_warmup_cache` | idem | log |
| H3 | Priorité TIER 1 > TIER 2 | `tier1=X, tier2=Y` dans log | log |
| H4 | Skip déjà traités (`_db.is_treated`) + déjà dans `_reply_cache` | Log `Skip` | log |
| H5 | Stagger 2s entre lancements | Observation log timestamps | log |

---

## Flux I — Résumé IA (piggyback + warmup)

| # | Étape | Critère | Vérif |
|---|---|---|---|
| I1 | Warmup bulk : 50 mails → Haiku batch chunks de 10 | Log `[warmup] résumés IA : +N` | log |
| I2 | Piggyback `/api/email_body` : si mail absent DB → scan isolé | Log `[summary-piggyback] ...` | log V2 |
| I3 | Table `mail_summaries` remplie | `SELECT COUNT(*) FROM mail_summaries` | DB query |
| I4 | Dialog fetch `/api/mail_summary?message_id=X` avec retry backoff 4× | Response 200 ou none puis 200 après retry | curl + observation dialog |
| I5 | Points + Actions affichés panneau gauche | Visuel user | user |
| I6 | Clé `internet_message_id` (pas Graph id hex) | DB `SELECT message_id FROM mail_summaries LIMIT 5` → format `<x@y>` | DB query |

---

## Flux J — Classement post-envoi (optionnel)

| # | Étape | Critère | Vérif |
|---|---|---|---|
| J1 | Après envoi, popup suggère classement | UI visuel | user |
| J2 | Scan 8 tiers effectué | Log `[classify] tier N match` | log V2 |
| J3 | Folder suggéré avec confidence | Response JSON | curl `/api/suggest_folder/<msg_id>` |
| J4 | User accepte → POST `/api/classify_email` | Response 200 | curl test |
| J5 | Graph move → mail dans bon dossier | `graph.move_message` success | log + user vérifie Outlook |

---

## Règles meta

**Un flux est considéré OK si et seulement si toutes ses étapes critiques sont ✅.**

**Priorité lors d'un audit** :
1. Flux A (boot) — si cassé, rien ne marche
2. Flux B (clic BM) — feature la plus visible
3. Flux C (instant reply) — différenciateur produit
4. Flux D (envoi) — finalité
5. Flux E (fermeture) — hygiène UX
6. Flux F-J — flux de fond, à vérifier si anomalies détectées en A-E

**Un flux partiellement OK ne doit pas être noté comme OK.**
