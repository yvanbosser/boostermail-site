# SPEC — Pièces jointes V2 : pré-traitement BG + popup marketing

> **Status** : DRAFT OUTLINE (26/04/2026, autonome)
> **À valider** par user avant implémentation
> **Précède** : `SPEC_FONCTIONNALITES_PROTO.md §4` (proto, à marquer obsolète après validation)

---

## Contexte

V2 a pour ambition de mettre en BG le **maximum de travail** sur les mails entrants, pour que l'utilisateur ait un dialog **instantané** au clic. Le proto fait un flow séquentiel (popup → spinner extraction → génération). V2 V3 inverse : tout est déjà fait quand l'user arrive.

---

## 1. Flow cible (BG côté backend)

À chaque mail reçu (via Graph webhook polling ou `message_read`) :

```
1. Détection mail entrant (has_attachments = true)
2. BG #A : extraction texte PJ via Graph API + PyPDF2 (PDF ≤ 10 pages)
   → stocké dans _pj_text_cache[IMID] = {results: [...], pages_warning: ...}
3. BG #B : génération réponse Claude AVEC le texte PJ injecté
   → stocké dans _reply_cache[IMID] (via drafts_v2.json)
4. BG #C : 5 plats Phase 1+2+3 (résumé / réponse / échéance / classement / classement PJ)
```

À l'arrivée du clic user, **tout est déjà prêt**.

### Limites BG actuelles
- **Formats** : PDF only (`_PDF_EXTS`). docx/xlsx/images = à étendre (P3)
- **Pages PDF** : max 10 par PDF (cf. `SPEC_OCR_LIMITE.md`)
- **PDF par mail** : max 3 (`_MAX_PRE_OCR_PDFS`)
- **Cache RAM** : 30 mails (`_MAX_PJ_TEXT_CACHE`)

---

## 2. Flow popup côté frontend

### 2.A — Cas BG terminé (95%+ des cas en régime stable)

```
Click BM → dialog 80% s'ouvre → popup PJ apparaît
  ↓
Popup affiche barre de progression rapide (animation 200-500ms)
  + indicateur "X pages sur Y analysées" (si applicable)
  ↓
Click "Oui" : popup disparaît + draft cache HIT instant
Click "Non" : popup disparaît + draft cache HIT instant (qui inclut PJ — choix user validé 26/04)
```

**Décision UX user (26/04)** : Click "Non" → afficher le cache (qui inclut PJ),
PAS régénérer sans PJ. Économie 1 appel Claude inutile dans 99% des cas.

### 2.B — Cas BG pas encore terminé (rare, mail très récent)

```
Click BM → dialog 80% s'ouvre → popup PJ apparaît
  ↓
Click "Oui" : popup affiche progression réelle (extraction + génération en stream)
Click "Non" : pas d'analyse PJ → streaming Claude sans contexte PJ
```

---

## 3. Trois invariants à figer

### PJ-1 — Étiquetage canonique BOÎTE 1 (`_pj_text_cache`)

`_pj_text_cache` est indexé par **IMID canonique** (Phase 1).
Tous les sites d'écriture/lecture utilisent l'IMID, jamais l'Entry ID Graph.

**Status au 26/04** : ✅ aligné (fix Pattern #14 du 26/04 sur site 690 + résolution IMID→EntryID interne).

### PJ-2 — Frontière Graph dans les fonctions BG

Toute fonction BG qui appelle Graph API (`get_attachments`, `get_attachment_content`, etc.) doit résoudre IMID → Entry ID **en interne**, avant l'appel.

**Pattern aligné** sur `api_extract_attachments` (fix 26/04) et 5 sites historiques (2646, 4248, 4404, 4922, 8214).

**Status** : ✅ aligné (fix 26/04 sur `_start_pj_pre_extract_v2`).

### PJ-3 — BOÎTE 2 = source primaire pour le rendu user

Le frontend popup PJ ne doit **JAMAIS** appeler `/api/extract_attachments` quand le draft cache (`_reply_cache`) est plein. Il doit utiliser `/api/instant_reply` qui sert le draft déjà-prêt (incluant le contexte PJ injecté en BG).

`/api/extract_attachments` reste pour le cas « BG pas encore terminé OU contexte PJ requis hors flow standard ».

**Status au 26/04** : ❌ NON appliqué. Le frontend appelle `extract_attachments` sur clic "Oui". À implémenter (chantier ouvert).

---

## 4. Plan de chantier (à valider user)

### Pré-requis (déjà faits)
- ✅ Fix Pattern #14 sur `_pj_text_cache` (26/04)
- ✅ Fix bug #3 Graph 400 (26/04)
- ✅ Phase 1 strict `_canonical_mid` (25/04)
- ✅ Phase 3 — 3 routes API séparées (25/04)

### Chantiers ouverts (par priorité)

| # | Chantier | Effort | Priorité |
|---|---|---|---|
| **A** | Click "Non" popup PJ → instant_reply (au lieu de regenerate) | ~5 lignes JS | 🔴 P0 |
| **B** | Click "Oui" popup PJ → instant_reply quand cache plein (avec animation faux progress) | ~10 lignes JS | 🟠 P1 |
| **C** | Barre de progression dans popup (port `pj-progress-list`/`pj-progress-bar` du proto) | ~30 lignes HTML+JS | 🟠 P1 |
| **D** | Indicateur « X pages sur Y » dans popup (récup `warning` depuis `_pj_text_cache` ou réponse extract) | ~10 lignes | 🟡 P2 |
| **E** | Persister `pj_warnings` avec le draft → `instant_reply` les renvoie | ~15 lignes Python | 🟡 P2 |
| **F** | Étendre formats PJ en BG (docx, xlsx, OCR images) | Plus gros chantier | 🟢 P3 |

---

## 5. Patterns du proto à porter (références)

### Barre de progression (proto `email_detail.html`)
- HTML structure : `<div id="pj-progress-list">` + `<div id="pj-progress-bar">` + `<div id="pj-progress-pct">`
- JS animations lignes 2241-2272 du proto
- Fill progressif au fur et à mesure des extractions

### Indicateur pages (proto `app.py`)
- `result["warning"] = f"⚠️ Seules {_pdf_extracted} pages sur {_pdf_total} ont été analysées (PDF volumineux)"` (ligne 1664)
- Affiché dans popup en proto

---

## 6. Questions ouvertes pour user

1. **Click "Non" sur popup PJ** : confirmé option a) afficher le cache (incluant PJ) — décision 26/04 ✅
2. **Faux progress pour cache HIT** : confirmé OK — décision 26/04 ✅
3. **Pages tronquées dans popup** : confirmé à implémenter (port pattern proto) ✅
4. **Étendre formats PJ en BG** : pas encore tranché. Aujourd'hui PDF only.
5. **Cache size global `_MAX_PJ_TEXT_CACHE = 30`** : OK confirmé (limite RAM, pas limite analysable).

---

## 7. Décisions stratégiques (HISTORIQUE_DECISIONS à mettre à jour)

- **PJ analyse en BG (V2)** vs **PJ analyse à la demande (proto)** : V2 inverse, BG fait tout.
- **Popup PJ = marketing** (montrer la magie au user) + indicateur pages tronquées (transparence).
- **Click "Non" affiche cache PJ** (pas régénère sans PJ) — économie API.
- **Anthropic 100%** pour V2 (OpenAI réservé au SaaS futur, hors scope).

---

## 8. Suivi

- **Auteur draft** : 26/04/2026, en autonomie
- **Status** : DRAFT, à valider par user
- **Prochaine étape** : valider le draft, puis implémenter chantiers A→E
- **Référence proto** : `templates/email_detail.html` (lignes 837-845, 2241-2272), `app.py` (1664, 1815, 1828)
- **Status `_pj_text_cache`** : ✅ aligné Phase 1 (fix 26/04)
