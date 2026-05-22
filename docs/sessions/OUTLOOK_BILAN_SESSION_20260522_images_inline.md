# Bilan de session — 22/05/2026 — Cadrage analyse IA images intégrées dans les mails reçus

> **Date** : 2026-05-22
> **Branche** : `feat/yvan/frontend`
> **Top commit** : `f0374e1`
> **Mode** : nocode strict (cadrage + rédaction doc, aucune modification code)
> **Durée** : ~2h de discussion + ~30 min de rédaction

---

## 🚨 RÈGLE GIT ABSOLUE

| Contributeur | Branche de push obligatoire |
|---|---|
| **Yvan** | `feat/yvan/frontend` |
| **Michael** | `feat/michael/multi-user` |

**JAMAIS de push direct sur `dev` ou `master`.**

---

## 1. Déclencheur

Yvan : *« nous allons travailler sur la gestion et lecture des images intégrées dans l'email reçu »*.

Objectif initial : comprendre ce qui est en place (mécanisme proto Phase 1/Phase 2) et voir comment aller plus loin.

---

## 2. Pivot conceptuel clé

**Découverte centrale de la session :**

Le travail fait sur le proto local (extraction COM, `save_inline_images()`, cache `_inline_images_cache`, route `/api/inline_images/`, placeholder SVG + polling JS) était nécessaire parce que le **proto était une fenêtre distincte d'Outlook** — il devait reconstruire le rendu des images.

Mais en V2, on est **dans Outlook** (plugin Office.js). Outlook rend le mail nativement avec ses images. Le dialog BoosterMail n'a pas à afficher le mail. Ce problème d'affichage **n'existe plus**.

**Le vrai gap**, c'est que les images sont visibles pour l'utilisateur mais **invisibles pour Claude**. La réponse générée peut rater l'essentiel si le mail contient un tableau, un schéma, une capture d'écran, un bon de commande scanné.

---

## 3. Démarche

5 échanges de cadrage :

| Étape | Sujet |
|---|---|
| 1 | Recherche doc existante — agent Explore : état proto + état V2 (complet) |
| 2 | Confirmation par Yvan du pivot conceptuel (affichage → analyse) |
| 3 | Arbitrage des 3 questions (Q1 périmètre / Q2 timing / Q3 injection) |
| 4 | Validation Q1-bis (taille min) + Q2-bis (cap 3 images) |
| 5 | Rédaction spec + invariants + commit + push |

---

## 4. Décisions tranchées (7 Yvan + 7 techniques)

### 4.1 Décisions Yvan

| # | Décision |
|---|---|
| D1 | Images dans le corps uniquement — **avant coupure signature** (exclut logos, signatures, bannières) |
| D2 | Filtre taille **≥ 5 Ko** validé |
| D3 | Filtre dimensions **≥ 100 × 100 px** validé (optionnel V1) |
| D4 | **Background pour H/VIP** (Smart Speculative) — **au clic en parallèle pour S/R** |
| D5 | **Cap 3 images maximum** par mail dans l'ordre d'apparition HTML |
| D6 | **Nouveau Bloc I dédié** dans le contexte de génération (entre Bloc A et Bloc C) |
| D7 | **Claude Vision** (`claude-sonnet-4-20250514`) — pas d'OCR tiers, zéro dépendance externe |

### 4.2 Décisions techniques

| # | Décision |
|---|---|
| T1 | Cache via nouvelle table `image_vision_cache` (user-scopé) |
| T2 | Clé cache = `(user_id, internet_message_id, sha256(bytes[:1024]))` — pas de TTL |
| T3 | Pas de TTL — analyse déterministe et immuable |
| T4 | Extraction via Graph API `/$value` (pas de COM, pas de Companion) |
| T5 | Timeout 10s — génération non bloquante |
| T6 | Bloc I absent si 0 image analysée (pas de section vide) |
| T7 | Position Bloc I : entre Bloc A et Bloc C |

---

## 5. Livrables

| Livrable | Fichier | Statut |
|---|---|---|
| Spec cadrage | `docs/architecture/V12/v12_image intégrée au mail.md` (~350 lignes) | ✅ Créé |
| Invariants | `docs/architecture/V12/V12_INVARIANTS.md` — Catégorie 18 (`I-VISION-01/02/03/04`) | ✅ Mis à jour |
| Sommaire | `docs/SOMMAIRE_DETAILLE.md` — entrée 22/05/2026 | ✅ Mis à jour |
| Historique | `docs/specs_proto/HISTORIQUE_DECISIONS.md` — entrée 22/05/2026 | ✅ Mis à jour |
| Commit | `f0374e1` sur `feat/yvan/frontend` | ✅ Pushé |

---

## 6. État pile Mika

| Chantier | Estimation | Doc | Statut |
|---|---|---|---|
| Classement PJ V12 | ~13-18 j | `v12 _ classement PJ.md` | ✅ Cadré 21/05 AM |
| Nouveau mail V12 | ~14.5 j | `v12 - nouveau mail.md` | ✅ Cadré 21/05 PM |
| Fenêtre rédaction grande/petite | ~4 j | `v12 fenetre de rédaction...md` | ✅ Cadré 21/05 PM |
| **Images intégrées** | **~5-8 j** | **`v12_image intégrée au mail.md`** | ✅ **Cadré 22/05** |
| **Total** | **~37-45 j** | — | — |

---

## 7. Sujets ouverts / prochaine session

- **BoosterMail cassé** (travail de Mika sur le passage en SaaS) — à investiguer quand Mika livrera
- **Briefing Mika** sur les 4 chantiers cadrés (PJ + nouveau mail + fenêtre rédaction + images) — message Slack/mail à préparer
- **PLUS_TARD_VF** : Task 3.4 "Inline Images Cache" à marquer REMPLACÉE par ce chantier (contexte différent : affichage → analyse)
- **Options en attente** (cf `PROMPT_NEXT_SESSION_20260522.md`) : migration VPS 6 points, tech debt Sonnet 4.6/4.7, WIP dialog.html/dialog.js

---

## 8. Ce qui N'a PAS changé

- Aucun code touché (nocode strict)
- WIP `V2/dialog.html` + `V2/dialog.js` inchangés (volontaire)
- `tools/*` inchangés

---

*Fin du bilan — session 22/05/2026*
