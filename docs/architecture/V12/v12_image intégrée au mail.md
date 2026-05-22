# V12 — Analyse IA des images intégrées dans les mails reçus

> **Statut** : 🟡 Cadrage produit terminé — à mettre en chantier
> **Date de cadrage** : 2026-05-22
> **Branche cible** : `feat/yvan/frontend` (cadrage) puis `feat/michael/multi-user` (implémentation)
> **Propriétaire produit** : **Yvan**
> **Implémentation** : **Mika** (Michael)
>
> **Documents liés** :
> - [docs/architecture/V12/V12_INVARIANTS.md](V12_INVARIANTS.md) — règles absolues (invariants I-VISION-* à ajouter)
> - [docs/architecture/V12/V12_SALLE.md](V12_SALLE.md) — moteur V12 source de vérité
> - [docs/specs_proto/SPEC_SYSTEM_PROMPT.md](../../specs_proto/SPEC_SYSTEM_PROMPT.md) — blocs A/B/C/D du contexte de génération (Bloc I s'ajoute ici)
> - [docs/architecture/V12/v12 - nouveau mail.md](v12%20-%20nouveau%20mail.md) — compose V12 (contexte de génération symétrique)

---

## 0. Sommaire

1. [Vision et problème](#1-vision-et-problème)
2. [État de l'art — ce qui existe, ce qui manque](#2-état-de-lart--ce-qui-existe-ce-qui-manque)
3. [Flux technique en 4 étapes](#3-flux-technique-en-4-étapes)
4. [Détection de la coupure signature](#4-détection-de-la-coupure-signature)
5. [Double filtre — taille + dimensions](#5-double-filtre--taille--dimensions)
6. [Appel Claude Vision](#6-appel-claude-vision)
7. [Cache et performances](#7-cache-et-performances)
8. [Bloc I — Intégration dans le contexte de génération](#8-bloc-i--intégration-dans-le-contexte-de-génération)
9. [Intégration au pipeline Smart Speculative](#9-intégration-au-pipeline-smart-speculative)
10. [Cas particuliers](#10-cas-particuliers)
11. [Décisions tranchées](#11-décisions-tranchées)
12. [Invariants](#12-invariants)
13. [Métriques de succès](#13-métriques-de-succès)
14. [Historique du document](#14-historique-du-document)
- [Annexe A — Récapitulatif pour Mika](#annexe-a--récapitulatif-pour-mika)

---

## 1. Vision et problème

### 1.1 Le problème — Claude est aveugle sur les images

Quand un contact envoie un mail avec des images dans le corps, Claude lit uniquement le texte. Les images = boîtes noires. La réponse générée peut rater l'essentiel du message.

> *Exemples concrets :*
> - Un client envoie une **capture d'écran d'une erreur** → Claude ne voit pas le message d'erreur, répond à l'aveugle
> - Un partenaire joint un **tableau de chiffres en image** → Claude ne peut pas commenter les données
> - Un prestataire envoie un **plan ou schéma** → Claude répond sans voir le plan
> - Un fournisseur envoie un **bon de commande scanné** → Claude ne voit pas les références ni les montants
> - Un contact envoie une **capture d'écran d'un contrat ou document** → Claude ignore le contenu

### 1.2 Pivot conceptuel — affichage ≠ analyse

Dans l'architecture proto local (`app.py`), les images devaient être **affichées** dans l'UI BoosterMail (fenêtre distincte d'Outlook) — d'où le travail coûteux Phase 1/Phase 2 (placeholder SVG + extraction COM + polling).

Dans l'architecture V2 plugin Outlook, ce problème d'affichage **n'existe plus** : Outlook rend le mail nativement avec ses images. Le dialog BoosterMail n'a pas à reconstruire le rendu.

**Le vrai gap, c'est l'analyse sémantique** : les images sont visibles pour l'utilisateur, mais invisibles pour Claude.

### 1.3 La solution — Bloc I dans le contexte de génération

Analyser le contenu visuel des images via **Claude Vision** et injecter les descriptions dans un nouveau **Bloc I** du contexte de génération. Claude reçoit la description textuelle des images → la réponse générée tient compte de ce que l'utilisateur a vu.

---

## 2. État de l'art — ce qui existe, ce qui manque

### 2.1 Ce qui existe

| Élément | Où | Statut |
|---|---|---|
| Mécanisme Phase 1/Phase 2 (affichage images) | `app.py` (proto), `outlook_com.py:save_inline_images()` | ✅ Proto uniquement — **devenu obsolète** en V2 plugin |
| Détection `isInline=true` sur les attachments | `V2/outlook_graph.py:356` | ✅ Détecte mais **ignore** les images inline |
| Filtre inline dans la liste PJ | `V2/dialog.js:2887` : `if (att.is_inline) return;` | ✅ Correct — les inline ne sont pas des PJ classiques |
| Extraction texte des PJ documents | `extract_attachment_text()` (PDF, Word, Excel) | ✅ Actif — **ne couvre pas les images inline** |
| OCR PDF scanné via Claude Vision | `claude_ai.py` (PJ de type PDF image) | ✅ Actif — **ciblé PJ, pas images corps du mail** |

### 2.2 Ce qui manque

**Aucune analyse IA du contenu des images intégrées dans le corps des mails reçus.**

Vérifications exhaustives :
- ❌ 0 appel Claude Vision sur les images inline du corps
- ❌ 0 route `/api/vision/images/` dans V2
- ❌ 0 table de cache pour les descriptions d'images
- ❌ 0 Bloc I dans le contexte de génération

### 2.3 Trace documentaire du gap

- `docs/analyses_proto_v2/PLAN_PORTAGE_PROTO_V2.md:219-230` — **Task 3.4 « Inline Images Cache »** listée mais **jamais exécutée** (préface : « Plan jamais exécuté »). Attention : cette task ciblait l'AFFICHAGE (désormais résolu via plugin Outlook) — le présent chantier cible l'ANALYSE, sujet différent.
- `docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md` — 7 gaps listés, images inline non mentionnées = **8e gap implicite**.

---

## 3. Flux technique en 4 étapes

```
Mail reçu avec images dans le corps
         │
         ▼
① EXTRACTION (Graph API)
   GET /messages/{id}/attachments?$select=id,isInline,contentId,contentType,size,name
   → filtre isInline=true
   → filtre taille ≥ 5 Ko (voir §5)
   → filtre position : avant coupure signature (voir §4)
   → cap : 3 premières images dans l'ordre HTML
   Pour chaque image retenue :
     GET /messages/{id}/attachments/{att_id}/$value  (bytes bruts)
   [Optionnel] filtre dimensions ≥ 100×100 px via Pillow
         │
         ▼
② ANALYSE (Claude Vision)
   Modèle : claude-sonnet-4-20250514
   1 appel par image retenue
   Prompt : description factuelle 2-3 phrases
   Résultat : texte structuré court
         │
         ▼
③ CACHE (DB — table image_vision_cache)
   Clé : (user_id, internet_message_id, sha256(bytes[:1024]))
   Pas de TTL — l'analyse d'une image ne change jamais
   Hit cache → 0 appel Vision
         │
         ▼
④ INJECTION (Bloc I dans le prompt de génération)
   [BLOC I — Images intégrées]
   Image 1 : ...description...
   Image 2 : ...description...
   → Claude calibre sa réponse en tenant compte des données visuelles
   → Si 0 image analysée : Bloc I absent
```

---

## 4. Détection de la coupure signature

Le HTML d'un mail contient des marqueurs de coupure signature reconnaissables. On arrête de lire les images dès qu'on rencontre le premier marqueur (priorité décroissante) :

### 4.1 Marqueurs HTML clients Outlook

| Marqueur | Client | Fiabilité |
|---|---|---|
| `<div class="signature"` ou `<div id="Signature"` | Outlook Classic / 365 | ⭐⭐⭐ Très fiable |
| `<div data-signatureuserid=` | Outlook 365 moderne | ⭐⭐⭐ |
| `<div class="OutlookMessageHeader"` | Outlook (mail transféré) | ⭐⭐ |

### 4.2 Marqueurs HTML autres clients

| Marqueur | Client |
|---|---|
| `<div class="gmail_signature"` | Gmail |
| `<div class="moz-signature"` | Thunderbird |
| `<div class="yahoo-signature"` | Yahoo Mail |

### 4.3 Marqueurs texte universels

- `<p>-- </p>` ou `<div>-- </div>` (RFC 3676 signature separator)
- `-- \n` ou `\n-- \n` dans le texte brut
- `<br>--<br>`

### 4.4 Marqueur structurel fallback

`<hr>` suivi d'un bloc contenant ≥ 2 des patterns suivants : email (`@`), téléphone (`+33`, `06`, `07`), URL (`http`), nom propre + titre professionnel.

### 4.5 Comportement si aucun marqueur

Si aucun marqueur détecté dans le HTML : on traite la **totalité du body** (pas de coupure supposée). Les images de signatures non marquées sont analysées — faux positif tolérable (une description de logo n'impacte pas négativement la génération).

### 4.6 Implémentation

Helper `_find_signature_split(html_body: str) → int` dans `V2/app_plugin.py`.
- Retourne l'**indice de caractère** dans le HTML où commence la signature
- Retourne `len(html_body)` si aucun marqueur (= analyser tout le body)
- Les `<img src="cid:...">` et `<img src="data:...">` situés **avant** cet indice sont les candidats à l'analyse

---

## 5. Double filtre — taille + dimensions

### 5.1 Filtre 1 — Taille fichier (avant récupération des bytes)

| Paramètre | Valeur |
|---|---|
| Seuil | ≥ **5 120 octets** (5 Ko) |
| Données source | Champ `size` dans la réponse `GET /attachments` (sans les bytes) |
| Coût | **0 appel supplémentaire** — `size` est dans les métadonnées |
| Élimine | Espaceurs transparents 1×1 px, puces décoratives, icônes 16-32 px, pixels de tracking |

Ce filtre est l'étape 1 — le moins coûteux. Il évite de télécharger les bytes d'images qui ne présentent aucun intérêt analytique.

### 5.2 Filtre 2 — Dimensions (après récupération des bytes)

| Paramètre | Valeur |
|---|---|
| Seuil | ≥ **100 × 100 px** (largeur ET hauteur) |
| Implémentation | `PIL.Image.open(io.BytesIO(img_bytes)).size` |
| Coût | 1 GET bytes par image qui a passé le filtre taille |
| Élimine | Bandeaux décoratifs très fins, images quasi-carrées mais minuscules |
| Statut V1 | **Optionnel** — le filtre taille couvre l'essentiel. Activable en V2 si faux positifs persistent. |

### 5.3 Récapitulatif des filtres

```
[Liste attachments Graph]
        │
        ▼ isInline=true
        ▼ size ≥ 5 120 octets       ← Filtre 1 (sans bytes)
        ▼ position avant signature  ← Filtre 3 (analyse HTML)
        ▼ 3 premières seulement     ← Cap
        │
        ▼ GET bytes ($value)
        ▼ dimensions ≥ 100×100 px   ← Filtre 2 optionnel (avec bytes)
        │
        ▼ → Prêt pour analyse Vision
```

---

## 6. Appel Claude Vision

### 6.1 Modèle et paramètres

| Paramètre | Valeur |
|---|---|
| Modèle | `claude-sonnet-4-20250514` (même que la génération email) |
| `max_tokens` | 200 |
| Température | 0.1 (factuel, déterministe) |
| Dépendance externe | **Aucune** — même API Anthropic déjà utilisée |

### 6.2 Format d'appel API

```python
{
  "model": "claude-sonnet-4-20250514",
  "max_tokens": 200,
  "temperature": 0.1,
  "messages": [{
    "role": "user",
    "content": [
      {
        "type": "image",
        "source": {
          "type": "base64",
          "media_type": "<content_type>",  # image/jpeg, image/png, image/gif, image/webp
          "data": "<base64_bytes>"
        }
      },
      {
        "type": "text",
        "text": (
          "Décris le contenu informationnel de cette image en 2-3 phrases factuelles. "
          "Identifie les données chiffrées, tableaux, schémas, structures et éléments textuels visibles. "
          "Ignore les éléments purement décoratifs. "
          "Si l'image est décorative ou ne contient pas d'information utile, réponds uniquement : 'Image décorative.'"
        )
      }
    ]
  }]
}
```

### 6.3 Formats d'image supportés

| Format | Supporté | Action si non supporté |
|---|---|---|
| JPEG (`image/jpeg`) | ✅ | — |
| PNG (`image/png`) | ✅ | — |
| GIF (`image/gif`) | ✅ | — |
| WebP (`image/webp`) | ✅ | — |
| BMP | ❌ | Ignorée silencieusement |
| TIFF | ❌ | Ignorée silencieusement |
| SVG | ❌ | Ignorée silencieusement |
| ICO | ❌ | Ignorée silencieusement |

### 6.4 Exemples de sorties attendues

**Tableau de données :**
> « Tableau de 4 colonnes : Référence produit, Quantité, Prix HT, Prix TTC. Lignes visibles : REF-A (×5, 45 € HT, 54 € TTC), REF-B (×2, 120 € HT, 144 € TTC). Total TTC en bas de tableau : 306 €. »

**Organigramme :**
> « Organigramme de 3 équipes sous une direction centrale : Commercial (5 pers.), Technique (3 pers.), Support (2 pers.). »

**Capture d'écran d'erreur :**
> « Capture d'écran d'un message d'erreur Windows : "ERREUR 0x80070057 — Le paramètre est incorrect." Boutons visibles : Réessayer, Annuler. »

**Schéma architectural :**
> « Schéma de 4 blocs reliés en séquence : Entrée → Traitement → Validation → Sortie. Flèches bidirectionnelles entre Traitement et Validation. »

### 6.5 Estimation des coûts

| Paramètre | Estimation |
|---|---|
| Tokens input image | ~500–1 500 selon résolution |
| Tokens input prompt | ~50 |
| Tokens output | 100–200 max |
| Coût par image | ~$0.003–0.008 |
| Coût par mail (3 images max) | ≤ **$0.024** |
| Coût mensuel (30 mails/j avec images) | ≤ **$0.72 / user** (worst case) |

---

## 7. Cache et performances

### 7.1 Nouvelle table — `image_vision_cache`

```sql
CREATE TABLE image_vision_cache (
    user_id              TEXT NOT NULL,
    internet_message_id  TEXT NOT NULL,
    image_hash           TEXT NOT NULL,   -- sha256(bytes[:1024])
    content_type         TEXT,            -- image/jpeg, image/png, etc.
    description          TEXT NOT NULL,   -- résultat Claude Vision
    created_at           DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, internet_message_id, image_hash)
);
CREATE INDEX idx_vision_cache_mid
    ON image_vision_cache(user_id, internet_message_id);
```

**Multi-tenant** : `user_id` scopé (invariant `I-MT-01`).

### 7.2 Clé de cache

`sha256(bytes[:1024])` — hash partiel des 1 024 premiers octets de l'image.

**Justification** : les 1 024 premiers octets contiennent le header complet de l'image (magic bytes, dimensions, metadata EXIF/PNG, début des données pixels). Probabilité de collision sur des images naturelles = quasi nulle. Calcul instantané (pas besoin de hasher toute l'image).

### 7.3 Pas de TTL

L'analyse d'une image est **déterministe et immuable** — la même image retournera toujours la même description. Pas de TTL nécessaire.

Purge éventuelle : liée au cycle de vie du thread/mail (si le thread est supprimé de `threads`, les entrées `image_vision_cache` associées peuvent être nettoyées par une purge périodique).

### 7.4 Hit rate attendu

Faible (5–10 %) — chaque mail est généralement unique. Cas d'utilisation du cache :
- L'utilisateur ouvre et ferme le même mail plusieurs fois dans la session
- Le mail est ré-analysé après une mise à jour du profil contact
- Même image d'en-tête reçue régulièrement d'un même contact (logo institutionnel qui aurait passé le filtre taille)

---

## 8. Bloc I — Intégration dans le contexte de génération

### 8.1 Position dans le prompt

Les blocs actuels du contexte de génération (cf. `SPEC_SYSTEM_PROMPT.md`) s'enchaînent dans l'ordre : D → B → A → C → D2 → E.

Le **Bloc I** s'insère **entre le Bloc A** (corps du mail reçu) **et le Bloc C** (contexte historique) :

```
D → B → A → [I] → C → D2 → E
```

Rationale : le Bloc I décrit le contenu visuel du mail reçu, qui fait partie du même message que le Bloc A. Les mettre côte à côte permet à Claude de lier texte et images d'un même mail.

### 8.2 Format du Bloc I

```
[BLOC I — Images intégrées dans le mail reçu]
Image 1 : Tableau de 4 colonnes — Référence produit, Quantité, Prix HT, Prix TTC.
           Lignes : REF-A (×5, 45 € HT, 54 € TTC), REF-B (×2, 120 € HT, 144 € TTC). Total TTC : 306 €.
Image 2 : Organigramme — Direction centrale + 3 équipes (Commercial 5p., Technique 3p., Support 2p.).
```

### 8.3 Règles d'injection

| Cas | Comportement |
|---|---|
| 0 image analysée | Bloc I **absent** du prompt (pas de section vide) |
| 1–3 images analysées | Bloc I injecté avec descriptions dans l'ordre HTML |
| Description < 20 chars (ex: « Image décorative. ») | Description ignorée, image absente du Bloc I |
| Bloc I total > 300 tokens | Tronquer les descriptions les plus longues |

### 8.4 Instruction à ajouter dans le system prompt

```
Si le Bloc I est présent, tenir compte des données visuelles pour contextualiser la réponse.
Ne pas citer les images explicitement ("j'ai vu votre image") sauf si c'est naturel dans le contexte.
Les données du Bloc I ont la même valeur que les données textuelles du mail.
```

---

## 9. Intégration au pipeline Smart Speculative

### 9.1 Mail H / contact VIP (Smart Speculative actif)

```
Ouverture du mail par l'utilisateur
        │
        ▼ _prewarm_mail_preview (BG)
        ├── Extraction inline images (Graph)
        ├── Analyse Vision (1 appel / image, parallélisé)
        ├── Write cache image_vision_cache
        └── [Continue pré-génération réponse en parallèle]

Clic "Générer"
        │
        ▼ Lecture cache image_vision_cache → Bloc I reconstruit
        ▼ Contexte complet = A + I + C + ... → réponse instantanée
```

**Résultat** : au clic Générer, les descriptions d'images sont déjà en cache → **zéro latence ajoutée**.

### 9.2 Mail S ou R (sans pré-génération)

```
Clic "Générer"
        │
        ├── Thread 1 : Résumé du mail (streaming)
        ├── Thread 2 : Génération réponse (streaming)
        └── Thread 3 : Extraction + analyse images (parallèle)
                 │
                 ▼ si disponible avant fin génération : Bloc I injecté
                 ▼ si timeout 10s dépassé : génération continue sans Bloc I
```

**Timeout 10s** : si l'extraction Graph ou l'appel Vision dépasse 10s, la génération démarre sans Bloc I. La réponse n'est pas bloquée par les images.

### 9.3 Guard anti-garbage (cohérent avec `_is_garbage_draft`)

- Description retournée par Vision < 20 chars → description ignorée
- Description contenant un pattern de refus Claude (« Je ne peux pas analyser ») → description ignorée
- Exception Anthropic sur l'appel Vision → image ignorée silencieusement, log Sentry `WARNING`

---

## 10. Cas particuliers

### 10.1 Images encodées en data URI dans le HTML

Certains clients mail (Gmail, Outlook Web) incluent les images directement en data URI (`<img src="data:image/png;base64,..."/>`). Dans ce cas :
- **Aucun appel Graph** `/attachments` nécessaire pour ces images
- On extrait le base64 directement depuis le HTML (`re.findall(r'data:image/[^;]+;base64,([^"\']+)', html_body)`)
- Le double filtre (taille via `len(base64) × 0.75` et dimensions) s'applique de la même façon

### 10.2 Formats non supportés par Claude Vision

BMP, TIFF, ICO, SVG → ignorés silencieusement. Pas d'erreur, log `DEBUG` uniquement.

### 10.3 Image illisible ou corrompue

Si les bytes sont invalides / Pillow ne peut pas décoder → image ignorée. Warning Sentry. Pas d'erreur fatale sur la génération.

### 10.4 Mail en texte brut (pas de HTML)

Pas d'images inline possibles. `_extract_inline_images_for_analysis()` retourne `[]` immédiatement. Aucun appel Graph inutile.

### 10.5 Cap 3 images — critère de sélection

Si le mail contient N > 3 images éligibles (au-dessus de la signature, ≥ 5 Ko, format supporté) :
- On prend les **3 premières dans l'ordre d'apparition dans le HTML**
- Les images en haut du mail sont généralement les plus porteuses de sens (pièce maîtresse du message)
- Les images du bas sont souvent des détails secondaires ou des récurrences

### 10.6 Signatures déguisées en contenu

Certains expéditeurs placent leur signature en milieu de mail (avant leur message principal). Le filtre "avant signature" peut analyser une image de logo dans ce cas. **Faux positif tolérable** : une description d'image décorative n'impacte pas négativement la génération (elle est simplement ignorée si < 20 chars via la règle §8.3).

### 10.7 Mail transféré avec images du mail original

Un mail transféré contient le corps original (avec ses images) + le message de l'expéditeur actuel. Les images du corps transféré peuvent se trouver sous une balise `<div class="OutlookMessageHeader"` ou `<blockquote>`. Le filtre signature peut ou non les exclure selon le client.

**Comportement acceptable** : analyser ces images si elles sont dans le body avant la coupure. Elles font partie du contexte du mail transféré.

---

## 11. Décisions tranchées

### 11.1 Décisions Yvan (session 22/05/2026)

| # | Décision | Choix retenu |
|---|---|---|
| **D1** | Périmètre des images à analyser | Corps du mail uniquement — **avant coupure signature** (exclut logos, signatures, bannières légales) |
| **D2** | Filtre taille | **≥ 5 Ko** validé |
| **D3** | Filtre dimensions | **≥ 100 × 100 px** validé (optionnel V1 si le filtre taille est suffisant) |
| **D4** | Timing de l'analyse | **Background pour H/VIP** (Smart Speculative) — **au clic en parallèle pour S/R** |
| **D5** | Cap images par mail | **3 images maximum** dans l'ordre d'apparition HTML |
| **D6** | Emplacement dans le contexte | **Nouveau Bloc I dédié** — pas fusionné avec le Bloc A texte |
| **D7** | Technologie d'analyse | **Claude Vision** (`claude-sonnet-4-20250514`) — pas d'OCR tiers, pas de dépendance externe |

### 11.2 Décisions techniques

| # | Décision | Justification |
|---|---|---|
| **T1** | Cache via nouvelle table `image_vision_cache` | User-scopé, multi-tenant safe (I-MT-01) |
| **T2** | Clé cache = `(user_id, internet_message_id, sha256(bytes[:1024]))` | Hash partiel rapide, collision quasi-nulle sur images naturelles |
| **T3** | Pas de TTL sur le cache | Analyse déterministe et immuable |
| **T4** | Extraction via Graph API `/$value` (pas de COM, pas de Companion) | V2 SaaS = OVH Linux, sans accès COM. Graph est la seule source disponible. |
| **T5** | Timeout 10s sur l'analyse image | Génération non bloquante — dégradation gracieuse si Graph ou Vision lents |
| **T6** | Bloc I absent si 0 image analysée | Pas de section vide dans le prompt |
| **T7** | Position Bloc I : entre Bloc A et Bloc C | Images = contenu du mail reçu, à côtoyer le Bloc A texte |

---

## 12. Invariants

4 nouveaux invariants à ajouter à [`V12_INVARIANTS.md`](V12_INVARIANTS.md) :

### I-VISION-01 : Maximum 3 images analysées par mail

Les 3 premières images éligibles dans l'ordre d'apparition HTML. Au-delà → ignorées.
- **Test** : `count(images_analyzed_per_mail) ≤ 3`
- **Pourquoi** : coût Vision + latence. Les 3 premières images sont les plus porteuses de sens.

### I-VISION-02 : Filtre taille minimale ≥ 5 Ko

Toute image < 5 120 octets est ignorée **sans appel Vision**.
- **Test** : grep `_extract_inline_images_for_analysis` → seuil `5120` présent
- **Pourquoi** : évite d'appeler Vision sur des espaceurs, pixels de tracking, icônes 16px

### I-VISION-03 : Filtre position — avant coupure signature uniquement

Aucune image après la coupure signature n'est analysée.
- **Test** : `_find_signature_split(html_with_signature_img)` → image après split absente du résultat
- **Pourquoi** : logos et photos de signatures ne doivent pas polluer le contexte de génération

### I-VISION-04 : Cache obligatoire par (user_id, internet_message_id, image_hash)

Même image reçue 2× → résultat lu en cache, 0 appel Vision.
- **Test** : mock → `vision_api_called_count == 1` après 2 appels avec même `(mid, hash)`
- **Pourquoi** : éviter les appels Vision redondants quand l'utilisateur ouvre plusieurs fois le même mail

---

## 13. Métriques de succès

### 13.1 Métriques de couverture

| Métrique | Calcul | Cible |
|---|---|---|
| % mails avec ≥ 1 image analysée | (mails avec Bloc I) / (mails avec images éligibles) | ≥ 80 % |
| Taux d'échec analyse | (timeout + format non supporté + Graph error) / (tentatives) | ≤ 5 % |
| Hit rate cache | (hits) / (tentatives) | Faible attendu (~5-10 %), non critique |

### 13.2 Métriques qualité

| Métrique | Calcul | Cible |
|---|---|---|
| Taux de modification réponse sur mails avec images | (drafts modifiés manuellement) / (drafts générés avec Bloc I) | Baisse observée vs sans Bloc I |
| Score rédactionnel moyen sur mails avec images analysées | Scoring BoosterMail 0-100 | Progression sur 4 semaines |

### 13.3 Métriques coût

| Métrique | Calcul | Cible |
|---|---|---|
| Coût Vision mensuel par user actif | Logs Sentry / facture Anthropic | ≤ $1 / user / mois |
| Part Vision dans budget Anthropic total | (Coût Vision) / (Coût Anthropic total) | ≤ 15 % |

---

## 14. Historique du document

| Date | Auteur | Modification |
|---|---|---|
| 2026-05-22 | Yvan + Claude (session cadrage) | **Création initiale.** Pivot conceptuel : le problème n'est pas l'AFFICHAGE des images inline (résolu par le plugin Outlook qui rend nativement) mais l'ANALYSE du contenu pour enrichir la génération de réponse. 7 décisions Yvan tranchées (D1-D7) + 7 décisions techniques (T1-T7). 4 invariants créés (I-VISION-01/02/03/04). Flux 4 étapes : Extraction Graph API → Analyse Claude Vision → Cache `image_vision_cache` → Injection Bloc I entre Bloc A et Bloc C. Timing : background pour H/VIP (Smart Speculative), parallèle au clic pour S/R avec timeout 10s. Cap 3 images / mail dans l'ordre HTML. Double filtre : position avant signature + taille ≥ 5 Ko. Estimation Mika : 4 phases, 5-8 j. |

---

## Annexe A — Récapitulatif pour Mika

> Lecture rapide au démarrage du chantier. Détails dans les sections ci-dessus.

### A.1 Migration DB

- [ ] `CREATE TABLE image_vision_cache` (user_id, internet_message_id, image_hash, content_type, description, created_at)
- [ ] `CREATE INDEX idx_vision_cache_mid ON image_vision_cache(user_id, internet_message_id)`
- [ ] Incrément `__SCHEMA_VERSION__`
- [ ] Helper migration vN → vN+1 dans `V2/database.py`

### A.2 Helpers Python nouveaux

- [ ] `_find_signature_split(html_body: str) → int`
  — Retourne l'indice caractère de début de signature dans le HTML. `len(html_body)` si non trouvé.
  — Marqueurs par priorité : `div.class/id signature` (Outlook/Gmail/Thunderbird) → `<p>-- </p>` → `<hr>` + bloc identité
- [ ] `_extract_inline_images_for_analysis(message_id: str, html_body: str, access_token: str) → List[dict]`
  — Graph `GET /attachments` (métadonnées) → filtre `isInline=True` + taille ≥ 5 Ko + position avant signature
  — Cap 3 premières dans l'ordre HTML (`cid:` matching entre HTML et liste attachments)
  — Pour chaque retenue : Graph `GET /attachments/{att_id}/$value` (bytes) + filtre dimensions optionnel via Pillow
  — Retourne `[{att_id, content_type, bytes, image_hash}]`
- [ ] `_describe_image_vision(image_bytes: bytes, content_type: str) → str`
  — Appel Claude Vision `claude-sonnet-4-20250514` + prompt factuel
  — `max_tokens=200`, `temperature=0.1`
  — Retourne la description ou `""` si format non supporté / erreur
- [ ] `_get_or_create_vision_description(user_id: str, internet_message_id: str, img: dict) → str`
  — Hit cache `image_vision_cache` → retourne description
  — Miss → appelle `_describe_image_vision` → write cache → retourne description

### A.3 Route API nouvelle

- [ ] **CRÉER** `GET /api/vision/images/<message_id>`
  — Retourne `[{index, description}]` pour les images analysées du mail
  — Utilisé par le BG (préchargement VIP) et le frontend (injection Bloc I en streaming)
  — `200 OK` avec tableau (éventuellement vide) — pas de `404`

### A.4 Intégration Smart Speculative

- [ ] Dans `_prewarm_mail_preview` (mails VIP/H) : ajouter appel `_extract_inline_images_for_analysis` + `_get_or_create_vision_description` en parallèle de la pré-génération
- [ ] Dans le path "au clic Générer" (S/R) : Thread 3 Vision avec timeout 10s — résultat injecté si disponible avant fin génération, ignoré sinon

### A.5 Injection Bloc I dans le contexte

- [ ] Dans le helper de construction du contexte (là où les blocs A/B/C sont assemblés) :
  - Lire `image_vision_cache` pour `(user_id, internet_message_id)`
  - Filtrer les descriptions < 20 chars
  - Construire le Bloc I (format §8.2)
  - Insérer entre Bloc A et Bloc C
- [ ] Ajouter l'instruction Bloc I dans le system prompt (§8.4)

### A.6 Tests

- [ ] `tests/test_vision.py::test_signature_split_outlook_div`
- [ ] `tests/test_vision.py::test_signature_split_gmail_div`
- [ ] `tests/test_vision.py::test_signature_split_no_signature`
- [ ] `tests/test_vision.py::test_image_filter_size_below_5ko`
- [ ] `tests/test_vision.py::test_image_filter_above_signature_excluded`
- [ ] `tests/test_vision.py::test_cap_3_images_order_preserved`
- [ ] `tests/test_vision.py::test_cache_hit_no_second_vision_call`
- [ ] `tests/test_vision.py::test_no_cross_tenant_leak_vision_cache`
- [ ] `tests/test_vision.py::test_timeout_10s_graceful_degradation`
- [ ] `tests/test_vision.py::test_bloc_i_absent_if_no_images`
- [ ] `tests/test_vision.py::test_bloc_i_skips_short_descriptions`
- [ ] `tests/test_vision.py::test_unsupported_format_ignored_silently`

### A.7 Documentation à mettre à jour

- [ ] `docs/SOMMAIRE_DETAILLE.md` — référencer ce doc (règle M2)
- [ ] `docs/architecture/V12/V12_INVARIANTS.md` — ajouter `I-VISION-01/02/03/04`
- [ ] `docs/specs_proto/HISTORIQUE_DECISIONS.md` — entrée 22/05/2026 (7 décisions tranchées)
- [ ] `docs/PLUS_TARD_VF.md` — noter que Task 3.4 « Inline Images Cache » est **REMPLACÉE** par ce chantier (contexte différent : affichage → analyse)

### A.8 Phases d'implémentation recommandées

| Phase | Contenu | Durée |
|---|---|---|
| **Phase 1** | Helper `_find_signature_split` + `_extract_inline_images_for_analysis` + migration DB `image_vision_cache` + tests unitaires filtres | 2-3 j |
| **Phase 2** | Helper `_describe_image_vision` + wrapper cache `_get_or_create_vision_description` + route `/api/vision/images/` + tests cache | 1-2 j |
| **Phase 3** | Intégration Smart Speculative (BG VIP) + path "au clic" S/R avec timeout 10s | 1-2 j |
| **Phase 4** | Injection Bloc I dans le helper de contexte + mise à jour system prompt + tests E2E | 1 j |
| **Total** | | **5-8 j / dev** |

---

*Fin du document — `v12_image intégrée au mail.md`*
