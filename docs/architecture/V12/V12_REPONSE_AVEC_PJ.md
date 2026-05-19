# V12 — Réponse avec pièces jointes

> **Doc CURRENT — source de vérité pour le flux PJ entrant → réponse générée.**
> Créée le 2026-05-19, à la demande d'Yvan, à destination de Michael.
> Branche : `feat/yvan/frontend`.
> Dépendances : [V12_CUISINE.md](V12_CUISINE.md), [V12_SALLE.md](V12_SALLE.md).

---

## Sommaire

1. [Vue d'ensemble en 30 secondes](#1-vue-densemble-en-30-secondes)
2. [Le flux complet, étape par étape](#2-le-flux-complet-étape-par-étape)
   - 2.1 [Détection à l'arrivée du mail](#21-détection-à-larrivée-du-mail)
   - 2.2 [Pré-extraction BG (cache)](#22-pré-extraction-bg-cache)
   - 2.3 [OCR Claude Vision (PDF scannés)](#23-ocr-claude-vision-pdf-scannés)
   - 2.4 [Pop-up frontend "Analyse des PJ"](#24-pop-up-frontend-analyse-des-pj)
   - 2.5 [Trois chemins utilisateur : Analyser / Ignorer / cache HIT](#25-trois-chemins-utilisateur--analyser--ignorer--cache-hit)
   - 2.6 [Fallback cache si refus utilisateur](#26-fallback-cache-si-refus-utilisateur)
   - 2.7 [Injection dans le prompt et génération](#27-injection-dans-le-prompt-et-génération)
3. [Exclusions et limites](#3-exclusions-et-limites)
4. [Modifications du 2026-05-19](#4-modifications-du-2026-05-19)
5. [Invariants à respecter](#5-invariants-à-respecter)
6. [Points de vigilance pour la suite](#6-points-de-vigilance-pour-la-suite)
7. [Référence — chemins de fichiers](#7-référence--chemins-de-fichiers)

---

## 1. Vue d'ensemble en 30 secondes

**Analogie** : imagine un restaurant. Quand une commande complexe arrive (mail
avec PJ), le commis (thread BG) pré-prépare les ingrédients (texte des PJ) dès
l'arrivée. Quand le client (Yvan) clique "Répondre", le chef (Claude Sonnet) a
déjà tout sous la main. Si certains ingrédients ne sont que des photos brutes
(PDF scannés), un OCR Claude Vision les transcrit en texte avant utilisation.
Si le client dit "pas le temps, vas-y comme ça" (clic "Ignorer"), le chef
utilise quand même ce que le commis a pré-préparé — pas de gâchis.

**En une phrase** : la pré-extraction tourne en BG dès `message_read`, alimente
un cache RAM (`_pj_text_cache`), et `/api/generate_reply` consomme ce cache
**même si** l'utilisateur a refusé l'analyse profonde au clic.

---

## 2. Le flux complet, étape par étape

### 2.1 Détection à l'arrivée du mail

**Déclencheur** : endpoint `/api/event/message_read` ([V2/app_plugin.py:5827](../../../V2/app_plugin.py)).

Le plugin Outlook (manifest + `autorunshared.js`) émet un événement
`message_read` dès l'ouverture d'un mail. La payload contient le flag
`has_attachments` (bool).

```
Outlook → autorunshared.js → POST /api/event/message_read
                              ↓
                  Si has_attachments=true :
                    _start_pj_pre_extract_v2() (thread BG)
```

**Garantie** : le déclenchement est **idempotent**. Si l'utilisateur ré-ouvre
le mail, le check `existing.get('status') in ('running', 'done')` empêche un
double lancement (cf. lock atomique TOCTOU, [V2/app_plugin.py:11209](../../../V2/app_plugin.py)).

### 2.2 Pré-extraction BG (cache)

**Fonction** : `_start_pj_pre_extract_v2()` ([V2/app_plugin.py:11197](../../../V2/app_plugin.py)).

Lance un thread daemon qui :

1. Résout `message_id` (IMID canonique) → `graph_id` (Entry ID Graph API)
2. Récupère la liste des PJ via Graph API si non fournie
3. Filtre les PJ : exclut `is_inline=true` (signatures, logos embedded), garde
   uniquement les `.pdf` non-inline, **max 5 par mail**
   (`_MAX_PRE_OCR_PDFS = 5`)
4. Pour chaque PDF :
   - Télécharge via `graph.get_attachment_content()`
   - Sauve dans un fichier temp Windows-safe (sanitization des caractères
     réservés `< > : " / \ | ? *`)
   - Extraction texte via **PyPDF2** (max 10 pages, troncature à 10K chars)
   - Si texte < 50 chars → **fallback OCR Claude Vision** (cf. 2.3)
5. Stocke dans `_pj_text_cache[message_id]` :
   ```python
   {
       'status': 'running' | 'done' | 'error',
       'results': [
           {'index': int, 'name': str, 'text': str},
           ...
       ],
       'ts': time.time()
   }
   ```

**Concurrence** : `_pj_text_cache_lock` (threading.Lock) protège toutes les
lectures/écritures (race condition BG vs main thread).

**LRU** : `_MAX_PJ_TEXT_CACHE = 30` mails en cache RAM. Au-delà, éviction
LRU (`_trim_dict_cache`).

### 2.3 OCR Claude Vision (PDF scannés)

**Nouveau au 2026-05-19** — branchement réactivé après dormance V2.

Implémenté à [V2/app_plugin.py:11301-11338](../../../V2/app_plugin.py).
Déclenchement : si PyPDF2 retourne < 50 chars (PDF image, scan,
facture photographiée).

**Stack** :

| Étape | Outil | Détail |
|---|---|---|
| PDF → images | **PyMuPDF** (`fitz`) | `page.get_pixmap(dpi=150)`, max 10 pages |
| Encodage | base64 PNG | Pour transit JSON vers Claude |
| OCR | **`ai_provider.ocr_pdf_multi()`** | 1 seul appel Vision multi-pages |
| Stockage | `_pj_text_cache` | Comme l'extraction PyPDF2 normale |

**Provider** : implémenté dans `ClaudeProvider.ocr_pdf_multi()`
([V2/core/claude_provider.py:221](../../../V2/core/claude_provider.py)). Retry
auto 3× sur erreur `overloaded`, max 8000 tokens.

**Si > 10 pages** : préfixe ajouté en début du texte OCR :
`[NOTE : Ce PDF contient X pages. Seules les 10 premières ont été analysées.]`

**Gardes-fous** :
- `ImportError` si PyMuPDF absent → log warning, on continue avec texte vide
- `NotImplementedError` si provider non-Claude → log info, fallback texte vide
- `Exception` générique → log warning, ne casse pas le BG thread

**Coût** : 1 appel Claude Vision par PDF scanné (max 5 par mail).
À surveiller en facturation.

### 2.4 Pop-up frontend "Analyse des PJ"

**HTML** : [V2/dialog.html:380-408](../../../V2/dialog.html).
**Logique** : `_showPjAnalysisPopup()` ([V2/dialog.js:914](../../../V2/dialog.js)).

**Déclenchement** : à l'ouverture du dialog de réponse, si
`_hasAttachments && !_pjChoiceMade && _attachmentsList.length > 0`.

**Phase 1 — sélection** :
- Affiche TOUTES les PJ avec checkbox
- **Cochage intelligent** : les images (`.png .jpg .jpeg .gif .bmp .webp .svg`)
  sont **décochées par défaut**, les autres formats cochés
- 2 boutons : `[Analyser]` / `[Ignorer]`

**Phase 2 — progression** (si Analyser) :
- Liste verticale avec spinner par PJ
- Barre de progression `N / total`
- Icônes : ⏳ (en attente) / spinner (en cours) / ✅ (OK) / ⚠️ (warning) / ❌ (erreur)
- **Batch parallèle** : 3 extractions simultanées (`BATCH_SIZE = 3`)

### 2.5 Trois chemins utilisateur : Analyser / Ignorer / cache HIT

```
                ┌─────────────────────────────────┐
                │  Pop-up "Analyse des PJ" affichée
                └─────────────────────────────────┘
                              │
       ┌──────────────────────┼──────────────────────┐
       ▼                      ▼                      ▼
  [Analyser]              [Ignorer]          réponse cachée déjà
       │                      │              affichée (instant_reply HIT
       ▼                      ▼              déclenché en parallèle)
 acceptPjAnalysis()    skipPjAnalysis()             │
       │                      │                     ▼
 extraction PJ par PJ   _extractedPjContext = ''   on garde la réponse,
 (3 en parallèle)       puis :                      pas de regénération
       │              ─ _editorHasRealContent()?    (cache contient déjà
       ▼                  ├─ oui : on garde         le contexte PJ).
 _extractedPjContext      │       (idem ↗)
 = concat(all_results)    └─ non : generateReply()
                                  avec pj_context=''
                                  → fallback cache (cf. 2.6)
       │
       ▼
 generateReply()
 avec pj_context plein
```

**Note pour Michael** : le chemin "cache HIT" (réponse spéculative pré-générée
livrée d'office) a été décidé par Yvan le 2026-05-02. La cuisine garantit que
la réponse cachée intègre déjà l'analyse PJ — cf.
[V12_CUISINE.md](V12_CUISINE.md) section spéculation.

### 2.6 Fallback cache si refus utilisateur

**Nouveau au 2026-05-19** — décision Yvan, [V2/app_plugin.py:12790-12808](../../../V2/app_plugin.py).

**Problème historique** : `skipPjAnalysis()` vide `_extractedPjContext = ''`.
Le frontend envoie donc `pj_context: ''` à `/api/generate_reply`. La
pré-extraction BG (qui a tourné dès `message_read`) est **gaspillée**.

**Correctif appliqué** : dans `/api/generate_reply`, juste après
`pj_context = data.get('pj_context', '')[:5000]`, si `pj_context` est vide ET
qu'il existe un `_pj_text_cache[message_id]` avec `status == 'done'`, on
hydrate `pj_context` depuis le cache :

```python
pj_context = '\n\n'.join(
    f"--- {r.get('name', 'PJ')} ---\n{r.get('text', '')}"
    for r in _cached_results
)[:5000]
```

**Couvre 2 cas** :
1. User clique "Ignorer" → BG cache utilisé
2. User clique "Analyser" mais toutes les extractions au clic échouent
   (réseau, format inattendu) → BG cache utilisé en secours

**Single source of truth backend** : aucune modif côté front nécessaire. Le
flux frontend reste inchangé.

### 2.7 Injection dans le prompt et génération

**Endpoint** : `/api/generate_reply` ([V2/app_plugin.py:12670](../../../V2/app_plugin.py)).

**Pipeline** :

1. Lecture body / from / subject / importance
2. Cache préemptif HIT ? → stream réponse pré-générée et return
3. **Lecture pj_context** (5000 chars max) + fallback cache (cf. 2.6)
4. Rate limiting 2s / mail
5. Construction prompt via `_get_prompt_builder()`
6. Injection du `pj_context` dans le prompt utilisateur (cf.
   [V2/app_plugin.py:13044-13058](../../../V2/app_plugin.py))
7. Appel Claude streaming (SSE)
8. Stockage proposé via `_store_proposed(message_id, full_text)`

**Instructions Claude pour les PJ** (extrait du prompt) :
- "Tu DOIS démontrer une lecture APPROFONDIE des PJ"
- "Interdit de dire 'ci-joint le document'"
- "Cite des éléments SPÉCIFIQUES (dates, noms, montants)"

**Réponse spéculative** : `_start_speculative()` ([V2/app_plugin.py:7861](../../../V2/app_plugin.py))
pré-génère **toute** la réponse en BG dès `message_read` (attend la
pré-extraction PJ max 10s). Pose le résultat dans `_reply_cache[message_id]`
pour livraison instantanée (cf. cuisine 3 étoiles Michelin).

---

## 3. Exclusions et limites

| Critère | Valeur | Référence |
|---|---|---|
| **Inline images** (logos, signatures embedded) | exclues automatiquement | `is_inline` flag Graph |
| **Images en PJ explicite** (.png, .jpg, etc.) | décochées par défaut, restent cochables | `dialog.js:919` |
| **Extensions pré-extract** | `.pdf` uniquement | `_PDF_EXTS = {'.pdf'}` |
| **Max PDFs par mail (pré-extract BG)** | 5 | `_MAX_PRE_OCR_PDFS = 5` |
| **Max pages par PDF (PyPDF2 + OCR)** | 10 | `reader.pages[:10]`, `min(total, 10)` |
| **Max chars texte/PJ après extraction** | 10 000 | `text[:10000]` |
| **Max chars pj_context dans prompt** | 5 000 | `data.get('pj_context', '')[:5000]` |
| **Cache RAM mails** | 30 | `_MAX_PJ_TEXT_CACHE = 30` |
| **Formats API extract** (au clic user) | PDF, DOCX, XLSX, TXT, CSV, HTM, HTML | `app_plugin.py:10087-10122` |
| **XLSX (au clic)** | 3 feuilles × 50 lignes | `app_plugin.py:10111` |
| **Batch parallèle frontend** | 3 PJ simultanées | `BATCH_SIZE = 3` |

---

## 4. Modifications du 2026-05-19

**Contexte** : Yvan a fait un point sur le flux PJ avec Claude.
3 décisions prises et appliquées localement (pas encore commit/push, working
tree `feat/yvan/frontend`). Backup local dans
`_BACKUP_AVANT_PUSH/PJ_OCR_FALLBACK_20260519/`.

### 4.1 Limite PDFs 3 → 5

**Fichiers** :
- `V2/app_plugin.py:11193` — constante `_MAX_PRE_OCR_PDFS = 5`
- `V2/app_plugin.py:11204` — docstring alignée
- `app.py:474` — code legacy proto (cohérence)
- `docs/v2_specs/SPEC_PJ_BG_V2.md:33` — spec V2

**Justification** : un dossier RH ou compilation de devis peut contenir 5+
PDFs. Latence BG estimée à 25s max en séquentiel pour 5 × 10 pages, acceptable
car invisible (avant clic user). Snapshots historiques (audit 24/04, spec
proto, plans datés) **non touchés** pour préserver la chronologie.

### 4.2 OCR Claude Vision réactivé

**Fichier** : `V2/app_plugin.py:11301-11338` (remplace `logger.info("TODO")`).

Implémentation portée du proto `outlook_com.py:_ocr_pdf` :
- PyMuPDF (`fitz`) pour PDF → PNG dpi=150
- `ai_provider.ocr_pdf_multi(pages_b64)` (1 appel multi-pages)
- 3 gardes-fous (ImportError, NotImplementedError, Exception)
- Préfixe NOTE si > 10 pages

**Dépendance ajoutée** : `requirements.txt` → `PyMuPDF` (installé en local
v1.27.2.2 chez Yvan, absent du requirements avant aujourd'hui).

### 4.3 Fallback cache si refus user

**Fichier** : `V2/app_plugin.py:12790-12808` (juste après lecture `pj_context`).

**Décision Yvan 2026-05-19** mémorisée : `feedback_pj_cache_refus.md`. Le
travail BG ne doit pas être jeté quand l'utilisateur clique "Ignorer". Le
backend pioche dans `_pj_text_cache` si `pj_context` arrive vide.

---

## 5. Invariants à respecter

| Code | Invariant |
|---|---|
| **I-PJ-01** | `_pj_text_cache` est protégé par `_pj_text_cache_lock` sur **toutes** les lectures/écritures (race condition BG vs main) |
| **I-PJ-02** | La pré-extraction BG est idempotente : double `message_read` du même mail ne relance pas le thread |
| **I-PJ-03** | Max 5 PDFs pré-extraits par mail (`_MAX_PRE_OCR_PDFS`) |
| **I-PJ-04** | Max 10 pages PDF (PyPDF2 ET OCR Vision) |
| **I-PJ-05** | OCR Vision fallback déclenché ssi texte PyPDF2 < 50 chars |
| **I-PJ-06** | Si `pj_context` vide à `generate_reply`, lookup cache avant génération |
| **I-PJ-07** | Inline images jamais pré-extraites (`is_inline=true` skip) |
| **I-PJ-08** | `pj_context` capé à 5000 chars avant injection prompt |
| **I-PJ-09** | Fichier temp PDF nettoyé en `finally` (pas de leak Windows %TEMP%) |
| **I-PJ-10** | Provider OCR optionnel : `NotImplementedError` graceful si non-Claude |

---

## 6. Points de vigilance pour la suite

### 6.1 Multi-tenant (SaaS)

Le BG thread `_start_pj_pre_extract_v2()` n'a **pas de Flask context** → écrit
dans `UserScopedDict` sub-cache `'default'`. Tant que mono-user (poste Yvan
local), aucun problème. Quand Michael basculera multi-tenant côté SaaS, il
faudra propager le `user_id` au thread.

**Pattern de référence** : voir `iter_user_caches(cache_name)` dans
`V2/user_scoped_cache.py:244`. Solution probable : capture du
`user_id = user_context.get_current_user_id()` AVANT lancement du thread,
puis injection en kwarg.

### 6.2 Coût Claude Vision

5 PDFs × 1 appel Vision = jusqu'à 5 appels Vision/mail. Tarif Claude Vision
est plus élevé qu'un Sonnet texte. Surveiller la facture Anthropic les
premiers jours post-déploiement. Optimisation possible : ne pas OCR si nom de
PJ contient `signature`, `logo`, ou taille fichier < 50 KB.

### 6.3 PyMuPDF pas dans requirements antérieurs

Risque sur les anciens déploiements (poste démo, CI) : pip install n'avait
jamais installé PyMuPDF. Le branchement OCR retournera silencieusement
`ImportError` → log warning. À surveiller au prochain `pip install -r`
propre.

### 6.4 Formats non-PDF en pré-extraction

DOCX, XLSX, etc. ne sont **pas** pré-extraits en BG (seulement au clic via
`/api/extract_attachments`). Pour étendre, dupliquer la logique PDF en
ajoutant les extensions à `_PDF_EXTS` et un dispatcher par format. Roadmap
P3 selon [SPEC_PJ_BG_V2.md](../../v2_specs/SPEC_PJ_BG_V2.md).

### 6.5 Latence pré-extract à 5 PDFs

En séquentiel : 5 × 5s/PDF ≈ 25s. Si l'utilisateur clique très vite, la
réponse spéculative attend la pré-extraction max 10s (`_start_speculative`)
→ peut partir sans tous les PDFs. Le fallback cache (§2.6) couvre le cas si
ça arrive après-coup. Paralléliser le BG (batch 3 en parallèle) ferait
tomber à ~10s. Roadmap si signal client.

---

## 7. Référence — chemins de fichiers

### Backend

| Composant | Fichier:ligne |
|---|---|
| Endpoint `message_read` | `V2/app_plugin.py:5827` |
| Pré-extraction BG | `V2/app_plugin.py:11197` |
| Constante `_MAX_PRE_OCR_PDFS = 5` | `V2/app_plugin.py:11193` |
| Branchement OCR (nouveau) | `V2/app_plugin.py:11301-11338` |
| Endpoint `extract_attachments` (au clic) | `V2/app_plugin.py:10009` |
| Endpoint `generate_reply` | `V2/app_plugin.py:12670` |
| Fallback cache PJ (nouveau) | `V2/app_plugin.py:12790-12808` |
| Réponse spéculative | `V2/app_plugin.py:7861` |
| Injection PJ dans prompt | `V2/app_plugin.py:13044-13058` |
| Provider OCR Vision | `V2/core/claude_provider.py:179-259` |
| Interface abstraite OCR | `V2/core/ai_provider.py:120-126` |
| UserScopedDict (multi-tenant) | `V2/user_scoped_cache.py:223` |

### Frontend

| Composant | Fichier:ligne |
|---|---|
| Pop-up HTML | `V2/dialog.html:380-408` |
| `_showPjAnalysisPopup()` | `V2/dialog.js:914` |
| Cochage intelligent images | `V2/dialog.js:919` |
| `acceptPjAnalysis()` | `V2/dialog.js:960` |
| `skipPjAnalysis()` | `V2/dialog.js:947` |
| Envoi `pj_context` au backend | `V2/dialog.js:3043` |

### Docs liées

| Doc | Rôle |
|---|---|
| [V12_CUISINE.md](V12_CUISINE.md) | Refonte N1-N11 (cuisine globale BG) |
| [V12_SALLE.md](V12_SALLE.md) | Refonte salle (réponse synchrone côté user) |
| [V12_INVARIANTS.md](V12_INVARIANTS.md) | Tous les invariants V12 |
| [SPEC_PJ_BG_V2.md](../../v2_specs/SPEC_PJ_BG_V2.md) | Spec V2 pré-extraction BG (origine) |
| [SPEC_OCR_LIMITE.md](../../specs_proto/SPEC_OCR_LIMITE.md) | Spec proto limite OCR (10 pages décidées) |
| [PLUS_TARD_VF.md](../../PLUS_TARD_VF.md) | OCR différé (raison historique désactivation V2) |

### Mémoire Claude pertinente

- `feedback_pj_cache_refus.md` — décision Yvan 19/05 sur réutilisation cache
- `feedback_branche_feat_yvan.md` — branche `feat/yvan/frontend` obligatoire
- `feedback_commentaire_ment.md` — vérifier qu'un commentaire ne nomme pas du code mort
- `feedback_reflexion.md` — chercher le problème de fond avant de patcher

---

*Doc rédigée par Claude le 2026-05-19 sur demande Yvan, destinée à Michael
pour review/intégration. État du code : modifs présentes localement sur
`feat/yvan/frontend` (working tree, non commit). Backup sécurisé dans
`_BACKUP_AVANT_PUSH/PJ_OCR_FALLBACK_20260519/`.*
