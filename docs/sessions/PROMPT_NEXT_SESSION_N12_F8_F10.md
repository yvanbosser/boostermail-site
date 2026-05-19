# Prompt prochaine session — N12 Phase 1 : F8 + F10 mails sortants

> **Préparé** : 14/05/2026 soir (clôture session N11 + Option A + batterie d'intégration 48 scénarios)
> **À utiliser** : début de la prochaine session, copier-coller dans le chat.
> **Branche** : `feat/yvan/frontend` (déjà à jour sur `product`, sommet `27fd74b`)

---

## Le prompt à utiliser

```
Salut. On reprend la refonte BoosterMail V2 où on s'est arrêtés.

CONTEXTE
========
Session précédente a livré N11 (dispatcher unique 3 branches), N11 Option A
(réactivation Échéance VIP entrants), et une batterie d'intégration N0→N11
de 48 scénarios E2E (38 initiaux + 10 famille F cuisine avancée). Tous verts.
Voir commit `27fd74b` (clôture) sur branche `feat/yvan/frontend`.

3 observations honnêtes ont été documentées post-batterie :
- Obs-F6 : TOCTOU possible sur idempotence _prewarm_unified_for_mail
- Obs-F8 : test tautologique (mocke un cas que la vraie chaîne ne peut produire)
- Obs-F10 : asymétrie scan_echeance entre entrants VIP et compose sortants

MISSION DE CETTE SESSION
========================
Traiter F8 + F10 ENSEMBLE, scope **mails sortants uniquement** (Phase 1).
Phase 2 entrants VIP viendra dans une session ultérieure.

DOCUMENTS À LIRE EN PRIORITÉ
============================
1. `docs/architecture/REFONTE_N1_N11_JOURNAL.md` §6 bis « Préparation N12 »
   → contient le plan préliminaire validé en fin de session précédente.
2. `docs/architecture/V12/V12_INVARIANTS.md` → sections « Obs-F6/F8/F10 » + I-BRANCHES-N11-OPTION-A
3. `docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md` (consolidée 14/05)
4. `V2/tests/test_integration_N0_N11.py` → comprendre les tests existants
   (notamment F10 actuel tautologique à réécrire)

VISION YVAN (reformulée en fin de session précédente)
=====================================================
1. L'utilisateur rédige un mail sortant (nouveau OU réponse à un mail reçu)
2. Le mail est scanné par le commis Haiku unifié N6.1
3. Des règles précises sont appliquées pour détecter une échéance
4. Soit aucune échéance détectée (silence)
   Soit une échéance détectée → traitée et confirmation demandée à l'user
   via dialog « Échéance détectée — OK / Ignorer »

LE TROU UNIQUE À COMBLER
========================
Route `/api/post_generation_analyze` (app_plugin.py:14006) appelle le commis
Haiku, écoute `kind == 'echeance'`, puis sérialise tel quel dans la réponse
JSON SANS AUCUNE VALIDATION. Si Haiku rend une fiche pourrie (description
vide, date `15 décembre 2026`, date passée), le frontend reçoit la bourde
et le dialog s'affiche cassé.

PLAN PRÉLIMINAIRE VALIDÉ (à confirmer en début de session)
==========================================================
3 vérifications minimales appliquées juste avant `jsonify(result)` :
1. La fiche est un `dict`
2. La fiche contient une `description` non vide (après strip)
3. La fiche contient une `date` au format `YYYY-MM-DD` parseable
   ET dans le futur

Si une seule échoue → `echeance = None` → dialog ne s'affiche pas.

Effort estimé : ~20 lignes (1 petite fonction + 1 appel) + 3 tests + 30-45 min.

DÉCISIONS DÉJÀ PRISES (NE PAS REVENIR DESSUS)
==============================================
- Phase 1 = SORTANTS UNIQUEMENT (entrants VIP = Phase 2 plus tard)
- PAS de helper `_should_scan_echeance` créé en Phase 1 (code mort en germe)
- PAS de modification du prompt Haiku en Phase 1 (Acte 3 reporté Phase 2)
- PAS de réintroduction du pré-filtre regex N6.3 supprimé
- F8 actuel reste tautologique jusqu'à Phase 2

DÉCOUVERTES À NE PAS PERDRE (économise re-cartographie)
=======================================================
- `_validate_echeance_date()` existe (claude_ai.py:3212) pour le Sonnet
  post-envoi, PAS pour le Haiku compose pré-envoi
- `utils_date.extract_fr_dates` existe (parser dates FR)
- Pipeline post-envoi `/api/echeances/post_send` reste séparé du compose
  pré-envoi (Sonnet → table `echeances` vs Haiku → `mail_echeance_cache`)
- Le sub-agent démolisseur a déjà cartographié les 3 call sites + les 4
  vraies bourdes possibles non couvertes par F8 actuel

PACTE
=====
« supprimer les patches sur patch sur patch par un code parfaitement propre,
robuste, pertinent, rapide, efficace »

4 défenses méthodologiques :
1. Démolisseur pré-impl (déjà fait pour F8/F10, pas à relancer)
2. Plan v2 après ses retours
3. Regard frais pré-commit (sub-agent qui audite avant push)
4. Audit rétrospectif post-commit (chasse récidives, -bis si nécessaire)

ATTITUDE ATTENDUE
=================
- Pas de tableau avec 35 règles (Yvan l'a explicitement remonté comme bazar)
- Pas de cheerleading
- Aller au plus simple ALIGNÉ avec la vision Yvan
- Si Yvan dit « simple », c'est SIMPLE. Pas de sur-ingénierie.
- Reformuler la vision produit AVANT de proposer du code

PUIS APRÈS PHASE 1 (à enchaîner si temps disponible)
=====================================================
Phase 2 = appliquer le validateur aussi côté entrants VIP
         (`_prewarm_unified_for_mail`), créer le décideur
         `_should_scan_echeance(mode, branch)` factorisé, réécrire F8
         avec les 4 vraies bourdes possibles (au lieu du cas tautologique
         actuel), enrichir le prompt commis section E avec exemples.

PUIS APRÈS PHASE 2
==================
N12 « La SALLE » = tests fonctionnels routes user × 3 branches (matrice
9 cas slide 9 PPTX) via Flask test_client.

Backlog : Obs-F6 TOCTOU (lock par-mid sur check idempotence).

GO. Tu peux commencer par lire le journal §6 bis + me confirmer que tu as
bien le contexte avant de proposer un plan v1.
```

---

## État de la branche à reprise

```
Branche : feat/yvan/frontend
Sommet  : 27fd74b docs(architecture) : journal enrichi avec prep N12 Phase 1 sortants
Tracking: product/feat/yvan/frontend (à jour)
Tests   : 48/48 intégration E2E verts (test_integration_N0_N11.py)
```

## Fichiers clés à consulter dans l'ordre

1. `docs/architecture/REFONTE_N1_N11_JOURNAL.md` §6 bis « Préparation N12 »
2. `docs/architecture/V12/V12_INVARIANTS.md` § Obs-F6/F8/F10 + I-BRANCHES-N11-OPTION-A
3. `docs/specs_proto/SPEC_ECHEANCES_BOOSTERMAIL.md` (consolidée 14/05)
4. `V2/app_plugin.py:14006` (route `api_post_generation_analyze`)
5. `V2/tests/test_integration_N0_N11.py` (F8/F10 actuels à réécrire)
6. `V2/claude_ai.py:3212` (`_validate_echeance_date` existant — référence)
