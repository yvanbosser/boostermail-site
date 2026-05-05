## SPEC ÉCHÉANCES — BoosterMail (consolidée)

> **Dernière mise à jour** : 05/05/2026
>
> **Statut** : source de vérité unique pour la fonctionnalité « Échéance ». Remplace `SPEC_ECHEANCES_OPTIMISATION.md` (proto, 06/04/2026, à archiver avec bandeau).
>
> **Origine** : audit complet 05/05 — état V2 SaaS sous-estimé jusque-là (mémoires + analyses pointaient vers OneDrive obsolète). Découverte : la feature est implémentée à ~90 % en V2. Cette spec consolide l'existant V2 + les décisions Yvan + le gap restant.

---

## 1. Vue d'ensemble — 3 phases

| Phase | Sujet | Quand | Coût IA |
|---|---|---|---|
| **A** | Détection des engagements pris | Pré-envoi (BG) + post-envoi (rattrapage) | 0 dans 70-80 % des cas (pré-filtre regex) |
| **B** | Suivi & visualisation | À la demande utilisateur (overlay) | $0 (lecture DB) |
| **C** | Auto-annulation & rappels | Au fil de l'eau + planifié | $0 (heuristique pure) |

**Promesse marketing** : « Zéro échéance oubliée » — tenir cette promesse exige que les 3 phases tournent sans intervention utilisateur sauf marquage final.

---

## 2. Scope V1 (validé Yvan 05/05)

✅ **In-scope** — Engagements **sortants** uniquement (l'utilisateur déclare/promet quelque chose dans un mail qu'il envoie).

❌ **Out-of-scope** — Détection automatique des deadlines dans les mails **reçus**. Trop complexe (faux positifs, ambiguïtés de date, multilingue). La landing `index.html` promet « Détection automatique des deadlines » — c'est du marketing en avance sur le scope produit, à ne pas prendre comme spec.

❌ **Out-of-scope** — Synchronisation avec Tâches Outlook natives (Yvan 05/05 : « sûrement pas »). On garde notre propre store + UI.

❌ **Out-of-scope V1** — Multi-tenant strict (isolation DB par `user_id`). Travail en cours côté infra mais non bloquant pour la feature échéance MVP.

---

## 3. Pipeline de détection (phase A)

```
Mail user envoyé
        ↓
[Pré-scan BG avant envoi]  — POST /api/echeances/pre_scan
        ↓
Pré-filtre regex _has_echeance_pattern(text)
   ├─ Pas de date détectée                                    → SKIP (économie 100%)
   ├─ Date + mots de RÉFÉRENCE ("suite à", "comme convenu")   → SKIP (date passée)
   └─ Date + mots d'ENGAGEMENT ("avant le", "deadline")        → APPEL IA
        ↓
[Scan IA]  — claude_ai.scan_echeances_batch(mails_batch)
   ├─ Modèle Sonnet 4.6, max 2000 tokens, T° 0.2
   ├─ Prompt = mail body 1500 chars + calendrier 30j + règles strictes
   └─ Validation post-IA : _validate_echeance_date() (corrige hallucinations dates)
        ↓
[Déduplication]  — _db.echeance_exists(correspondant, description_keywords)
   └─ Threshold 60% mots communs (stop-words FR exclus)
        ↓
[Persistance]  — _db.save_echeance(data)
        ↓
[Cache pré-scannées par mail]  — _echeance_pre_scan_cache (RAM)
        ↓
[Trigger UI post-envoi]  — GET /api/echeances/post_send/<message_id>
   └─ Le dialog poll cette route, affiche popup "Échéance détectée — OK / Ignorer"
```

### Patterns regex du pré-filtre (`app_plugin.py:8905-8922`)

| Type | Patterns |
|---|---|
| **Dates** (`_ECHEANCE_DATE_PATTERNS`) | `1/2`, `1-2`, `1.2`, `9 avril`, `15 mai`, jours nommés ± "prochain", `demain`, `après-demain`, `fin semaine`, `semaine prochaine`, `sous 8j`, `dans 2 semaines`, trimestres |
| **Référence passée** (`_ECHEANCE_REFERENCE_WORDS`) | `lors de`, `suite à`, `comme convenu`, `reçu le`, `envoyé le`, `signé le`, `depuis le` |
| **Engagement** (`_ECHEANCE_ENGAGEMENT_WORDS`) | `avant le`, `d'ici le`, `au plus tard`, `je reviens`, `deadline`, `expire le`, `sous \d+`, `pourriez-vous`, `prière de`, `rendez-vous`, `réunion prévue` |

### Mots-clés qui NE déclenchent PAS (trop vagues)
- `bientôt`, `rapidement`, `prochainement`, `dès que possible`, `aujourd'hui`, `ce soir`

### Zone scannée
- Réponse de l'utilisateur uniquement
- PAS le mail original cité (après "De : ... Envoyé : ...")
- PAS la signature

---

## 4. Schéma DB (`database.py:293-309` + migrations 470-480)

| Colonne | Type | Défaut | Notes |
|---|---|---|---|
| `id` | INTEGER PRIMARY KEY AUTOINCREMENT | — | Clé primaire |
| `email_entry_id` | TEXT | NULL | IMID du mail source (lookup mail original) |
| `correspondant` | TEXT | NULL | Email normalisé (`_normalize_email`) |
| `correspondant_nom` | TEXT | NULL | Display name humain |
| `date_echeance` | TEXT | NULL | `YYYY-MM-DD` |
| `description` | TEXT | NULL | Texte actionnable court |
| `type` | TEXT | NULL | `engagement_pris` / `engagement_recu` / `deadline` / `obligation` |
| `priorite` | TEXT | NULL | `haute` / `moyenne` / `basse` |
| `extrait_mail` | TEXT | NULL | Passage ≤ 100 chars du mail |
| `direction` | TEXT | NULL | `sent` (V1) / `received` (V2 si scope étendu) |
| `statut` | TEXT | `'active'` | `active` / `terminee` / `annulee` / `archived` |
| `rappel_jours` | INTEGER | `3` | ⚠ Stocké mais **non exploité** (cf gap §10) |
| `original_subject` | TEXT | NULL | Sujet du mail source |
| `created_at` | TEXT | `datetime('now', 'localtime')` | Timestamp création |
| `completed_at` | TEXT | NULL | Timestamp clôture (si `statut=terminee`) |
| `nb_relances` | INTEGER | `0` | Tracking relances envoyées |
| `relances_dates` | TEXT | `'[]'` | JSON array des dates de relance |

**Indexes** : aucun explicite (gap perf à anticiper si > 10 k lignes).

**Cache associé** : table `mail_echeance_cache` (clé = `message_id`) — évite les re-scans IA d'un même mail.

---

## 5. UI — overlay BoosterMail

### Pattern d'intégration

L'écran échéances vit dans **`V2/templates/echeances.html`** servi via `GET /plugin/echeances` par `app_plugin.py:13312`. Il s'ouvre dans la **fenêtre overlay PyQt** (`companion/popup_pyqt.py`, `QMainWindow` + `QWebEngineView`) — la même fenêtre que les pages Profil et Contacts.

Header bleu cohérent (`linear-gradient(135deg, #0F6CBD → #1976D2)`) + onglets de navigation `/plugin/contacts` / `/plugin/profile` / `/plugin/echeances`.

### Visibles à l'écran

- 3 onglets : **En cours / Dépassées / Archivées** avec compteurs
- Sections temporelles dans "En cours" : « À relancer aujourd'hui / demain / avant fin de semaine / semaine prochaine et plus »
- Cards échéance : avatar correspondant, sujet original, date relative, badge retard rouge/orange
- Recherche texte (description / correspondant / sujet)
- Mémorisation onglet actif (sessionStorage + URL `?tab=`)
- Empty states par onglet (« Aucune relance en cours — tout est à jour ✓ »)
- Boutons par card : **Relance rapide / 2ème relance / Nème relance** (libellé dynamique selon `nb_relances`), **Réponse déjà reçue**, **Modifier**, **Supprimer**
- Détail échéance (panel sticky droite) : extrait mail envoyé, statut, historique des relances cliquables
- Toast UNDO 4s sur action « Réponse reçue »
- Popup modif date avec dropdown -4j à +90j, blocage date passée, skip week-end → lundi
- Popup mini-confirm sur suppression et « Vider l'archive »

### Confirmation immédiate post-envoi (dans le dialog principal)

Workflow chaîné `dialog.js` :
```
Envoi → POST /api/echeances/post_send/<message_id>
      → poll GET /api/echeances/post_send/<message_id>
      → si échéance détectée : popup minimal "Échéance détectée — OK, note / Ignorer"
      → puis enchaîne : Classement mail → Classement PJ → Fermeture
```

### Interdits absolus

- Pas de `window.open()` pour ouvrir les pages overlay (régression connue, cf `ui_design_specs.md`)
- Pas d'overlay positionné en taskpane à droite (interdit Yvan 29/04, mémoire `feedback_taskpane_interdit.md`)
- Pas d'affichage du contenu intégral des mails en clair (PII)

---

## 6. Actions utilisateur

| Action | Endpoint | Effet |
|---|---|---|
| **Marquer "Réponse reçue"** | `PUT /api/echeances/<id>` `{statut: 'terminee'}` | Set `completed_at`, toast UNDO 4s côté UI |
| **Annuler** | `PUT /api/echeances/<id>` `{statut: 'annulee'}` | Idem |
| **Modifier la date** | `PUT /api/echeances/<id>` `{date_echeance: 'YYYY-MM-DD'}` | Skip week-end côté JS avant envoi |
| **Supprimer** | `PUT /api/echeances/<id>` `{statut: 'annulee'}` | Pas de DELETE physique en V1 (audit trail) |
| **Vider l'archive** | `POST /api/echeances/purge_archives` | DELETE WHERE `statut IN ('terminee', 'annulee')` |
| **Voir mail original** | `GET /api/echeances/<id>/mail` | ⚠ Stub V2 — retourne juste `{message_id, subject}` (cf gap §10) |
| **Voir mail de relance** | `GET /api/echeances/search_relance_mail?subject=&correspondant=` | Recherche dans threads, retourne corps mail |
| **Relancer** | `GET /api/echeances/<id>/relance` | ⚠ Stub V2 — retourne `{subject_prefilled}` mais ne génère pas de brouillon (cf gap §10) |

---

## 7. Auto-annulation (réponse correspondant détectée)

**Fonction** : `_auto_cancel_echeances_on_reply(to_email, subject, cached_email, exclude_ids=None)` (`app_plugin.py:8957`)

**Logique** :
- Déclencheur : utilisateur RÉPOND à un mail reçu (PAS sur envoi spontané)
- Matching correspondant : email du `from` du mail reçu vs `correspondant` en DB
- Matching sujet : strip préfixes (Re:, Fw:, Fwd:, Tr:), lowercase, ≥ 3 mots communs (longueur ≥ 4 chars) entre sujet du mail et `description` de l'échéance
- Action : `UPDATE echeances SET statut='terminee'` + log
- Coût : **$0** (pure heuristique)

**Évolution prévue** : popup explicite "X a répondu à votre demande du [date]. Supprimer l'échéance ?" avec [Supprimer] [Conserver] (cf gap §10 — actuellement annulation silencieuse, sans confirmation utilisateur).

---

## 8. Rappels J-1 ouvré

### Règle métier

Rappel proposé = **1 jour ouvré avant l'échéance**.

| Échéance tombe un | Rappel proposé le |
|---|---|
| Mardi | Lundi |
| Mercredi | Mardi |
| Jeudi | Mercredi |
| Vendredi | Jeudi |
| Lundi | Vendredi (pas dimanche) |
| Samedi | Vendredi |
| Dimanche | Vendredi |

### État actuel V2

⚠️ **Calcul J-1 ouvré présent côté JS** (`templates/echeances.html` fonctions `getRelanceLabel`, `skipWeekend`, `getFridayDate`) pour l'affichage « À relancer aujourd'hui / demain / cette semaine ».

⚠️ **Aucun job/cron côté serveur** pour pousser un rappel proactif (notification, mail, popup). La colonne `rappel_jours` est stockée mais jamais consommée.

→ Voir gap §10 point 3.

---

## 9. Routes API — inventaire complet (V2)

| Route | Méthode | Ligne | Rôle |
|---|---|---|---|
| `/api/echeances` | GET | `app_plugin.py:8080` | Liste filtrable (`statut`, `correspondant`) |
| `/api/echeances/urgent` | GET | 8089 | Actives ≤ 3j + dépassées |
| `/api/echeances/<id>` | PUT | 8096 | Update (statut/date/description) |
| `/api/echeance/<message_id>` | GET | 8360 | Porte dédiée Phase 3 (25/04), trigger BG si miss |
| `/api/echeances/pre_scan` | POST | 8387 | Pré-scan BG avant envoi (cache RAM) |
| `/api/echeances/purge_archives` | POST | 8462 | Vider l'archive |
| `/api/echeances/search_relance_mail` | GET | 8474 | Cherche mail de relance dans threads |
| `/api/echeances/check_sender` | GET | 8501 | A des échéances actives liées à cet expéditeur ? |
| `/api/echeances/post_send/<message_id>` | POST | 11742 | Scan IA post-envoi (BG + cache) |
| `/plugin/echeances` | GET | 13312 | Page HTML overlay |
| `/api/echeances/<id>/relance` | GET | 13497 | ⚠ Stub — gap §10 |
| `/api/echeances/<id>/mail` | GET | 13520 | ⚠ Stub — gap §10 |

---

## 10. Gaps restants — plan d'action

### ~~Gap 1 : Routes stubs `/relance` et `/mail`~~ ✅ CLOSE 05/05/2026

**Implémenté** : `app_plugin.py:13497` (`/relance`) retourne maintenant `{to, to_name, subject, brief, type, nb_relances, days_late, echeance}` avec brief texte plain neutre (court le 1er coup, plus appuyé pour les relances suivantes). `app_plugin.py:13520` (`/mail`) retourne `{message_id, subject, correspondant, correspondant_nom, extrait_mail, created_at, date_echeance}` pour alimenter une modale d'aperçu locale.

### ~~Gap 2 : Redirection `/new_mail?...` héritée du proto~~ ✅ CLOSE 05/05/2026

**Implémenté** : décision Yvan 05/05 = option **mailto:** pour MVP. Frontend `relancer(id)` (`echeances.html`) construit `mailto:to?subject=&body=` avec encodeURIComponent + tracker la relance via `PUT /api/echeances/<id>` (incrément `nb_relances` + ajout date à `relances_dates` JSON) avant ouverture. Limite : plain text uniquement, pas de HTML — option 2 (companion COM riche HTML) à envisager si besoin user remonté.

**Bonus implémenté** : frontend `voirMail(id)` ne navigue plus vers JSON brut — réutilise la modale `relance-mail-modal` existante en l'adaptant pour afficher l'aperçu (correspondant, sujet, dates, extrait_mail). Évolution future : intégration **Microsoft Graph webLink** pour ouvrir le mail directement dans Outlook Web/Desktop.

### Gap 3 : Scheduler des rappels J-1 ouvré (priorité moyenne, ~1 jour)

**État** : aucun mécanisme serveur pour pousser un rappel à J-1. La colonne `rappel_jours` (défaut 3) est stockée mais inerte.

**Options** :
- **a)** Worker externe (APScheduler) lancé au démarrage du service systemd → lit `echeances` toutes les heures, envoie notifications (mail, push, popup overlay) pour celles dont la date == aujourd'hui + `rappel_jours` ouvrés
- **b)** Endpoint `/api/echeances/send_reminders` appelé par cron Linux toutes les heures (logique métier dans Python, scheduling externe)
- **c)** Polling client (overlay vérifie au démarrage les échéances `urgent` et alerte) — plus léger mais nécessite que l'utilisateur ouvre l'overlay

**Recommandation** : option (b) pour V1 (simple, débuggable, déterministe). Migration vers (a) si besoin de notifications push temps réel.

### Gap 4 : Popup d'auto-annulation (priorité basse, ~2h)

**État** : `_auto_cancel_echeances_on_reply` annule en silence (passe à `terminee` sans demander). L'utilisateur peut rater une échéance qui aurait dû être maintenue (ex : réponse du correspondant qui ne traite pas le sujet).

**À faire** : au lieu de `UPDATE statut='terminee'` direct, créer un état intermédiaire `pending_confirmation` + popup overlay « X a répondu à votre demande du [date]. Supprimer l'échéance ? [Supprimer] [Conserver] » au prochain ouverture overlay.

### Gap 5 : Indexes DB (priorité basse, ~10 min)

**État** : pas d'index sur `(statut, date_echeance)` ou `(correspondant)`. OK tant que < 10 k lignes par utilisateur.

**À faire** : `CREATE INDEX idx_echeances_statut_date ON echeances(statut, date_echeance);` + `CREATE INDEX idx_echeances_correspondant ON echeances(correspondant);` quand on passera multi-tenant.

---

## 11. Économie d'appels IA

| | Sans pré-filtre | Avec pré-filtre (V2 actuel) |
|---|---|---|
| Appels IA scan/jour (1 user) | ~17 | ~3-5 |
| Appels évités/jour | — | ~12-14 |
| Économie/jour ($) | — | ~$0.07-0.08 |
| Économie/mois ($) | — | ~$1.70 |
| Auto-annulation | — | Heuristique, $0 |
| Calcul rappel J-1 ouvré | — | Heuristique JS, $0 |

**À l'échelle SaaS** : 100 / 1000 / 10000 users → économie $170 / $1700 / $17000 par mois. Le pré-filtre devient **critique** au-delà de 50-100 utilisateurs.

---

## 12. Décisions historiques (timeline)

| Date | Décision |
|---|---|
| 06/04/2026 | Spec initiale `SPEC_ECHEANCES_OPTIMISATION.md` (proto Flask local) |
| ~14/04/2026 | Port V2 SaaS avec écran `V2/templates/echeances.html` aligné overlay |
| 22/04/2026 | Guard prompt injection ajouté à `scan_echeances_batch` |
| 25/04/2026 | Phase 3 — porte dédiée `/api/echeance/<message_id>` (split du `/api/mail_preview`) |
| 29/04/2026 | Migration modèle `claude-sonnet-4-20250514` (deprecated) → `claude-sonnet-4-6` |
| 05/05/2026 | Audit complet + spec consolidée — découverte de l'écart entre mémoires (qui pointaient OneDrive/V1_outlook obsolète) et code V2 réel. Cible « meilleur des 2 mondes » réduite à 5 gaps précis (cf §10). |

---

## 13. Tests et validation

### Smoke test (à intégrer)

```bash
# Vérifier que les routes principales répondent 200
curl -sk https://api.boostermail.ai/api/echeances | jq '.echeances | length'
curl -sk https://api.boostermail.ai/api/echeances/urgent | jq '.echeances | length'
curl -sk https://api.boostermail.ai/api/echeances/<id> -X PUT -d '{"statut":"active"}'
```

### Test UI alignement (Workflow 9 PLAYBOOK)

`audit/tests/e2e/test_ui_specs.py` doit inclure `test_echeances_overlay_3_tabs_and_sections` (vérifie présence des 3 onglets + 4 sections temporelles + boutons par card).

### Tests fonctionnels

- Envoyer un mail avec « avant vendredi » → vérifier création échéance + popup post-envoi
- Recevoir réponse du correspondant → vérifier auto-annulation (logs `_auto_cancel_echeances_on_reply`)
- Marquer « Réponse reçue » → vérifier UNDO 4s + remise en `active` si clic UNDO
- Modifier date d'une échéance qui tombe samedi → vérifier décalage au lundi côté JS
