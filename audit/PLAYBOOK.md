# Playbook — workflows types

> **Rôle** : pour chaque type de demande user, la séquence d'étapes à suivre. Évite d'improviser.

---

## Workflow 1 — "Fais-moi un audit complet de V2"

### Objectif
Identifier toutes les anomalies détectables dans le périmètre V2 + companion + service + install.

### Durée estimée
45-60 min pour le 1er audit, 15-30 min pour les re-audits après fixes.

### Étapes

1. **État baseline (5 min)**
   - `powershell -File audit/tests/smoke_test.ps1` → note exit code
   - Si exit > 0 : noter chaque FAIL comme anomalie
   - Si exit = 0 : on continue, 0 anomalie invariant

2. **État des données (5 min, NOUVEAU 23/04 — OBLIGATOIRE AVANT le code)**
   - Lancer les 3 commandes de `checklists/etat_donnees.md §8` :
     * Comptages de rows des tables d'apprentissage DB V2
     * Test API pour chaque modèle Claude référencé
     * Présence des fichiers cache persistants
   - **Règle** : si une anomalie de données sort ici, la corriger AVANT de chercher dans le code
   - **Historique** : 2 mois + 5 jours de bugs UX invisibles étaient des défauts de données, pas de code

3. **Lecture contextuelle (5 min)**
   - `audit/INVENTAIRE_V2.md` : rappel du périmètre
   - `audit/ANOMALIES_RECURRENTES.md` : patterns déjà vus, en particulier **Pattern #13 (données vides servies OK)**

4. **Balayage par classes (15 min)**
   - Parcourir `audit/checklists/classes_bugs.md`
   - Pour chaque classe (1→20) : exécuter les commandes proposées + inspection visuelle
   - Noter chaque anomalie au format `templates/anomalie.md`

5. **Balayage par flux (15 min)**
   - Parcourir `audit/checklists/flux_end_to_end.md`
   - Pour chaque flux (A→J) : vérifier chaque étape avec les commandes indiquées
   - Tout flux avec ≥1 étape ❌ → anomalie(s) à consigner

6. **Balayage par angles (10 min)**
   - Parcourir `audit/checklists/angles_attaque.md`
   - 10 angles, cocher chaque question
   - Questions sans réponse = anomalie potentielle à investiguer

7. **Pièges Windows (5 min)**
   - Parcourir `audit/checklists/specificites_windows.md`
   - Vérifier les 14 pièges spécifiques

8. **Rapport (10 min)**
   - Remplir `audit/templates/rapport_audit.md`
   - **Inclure obligatoirement la section "État des données"** (cf. `checklists/etat_donnees.md §10`)
   - Compte anomalies par sévérité
   - Attacher preuves factuelles
   - Sauver dans `audit/rapports/YYYY-MM-DD_HHMM_complet_iterN.md`

9. **Mise à jour ANOMALIES_RECURRENTES (5 min)**
   - Toute anomalie détectée **immédiatement** ajoutée
   - Patterns déjà connus : noter "récidive de Pattern #X"

### Critères de fin
- Si 0 anomalie ET smoke_test exit 0 → audit terminé, rapport signé
- Si ≥1 anomalie → rapport rendu, user décide de la suite

---

## Workflow 2 — "Audit thématique sécurité"

### Étapes
1. smoke_test.ps1 (baseline)
2. INVARIANTS catégorie "Sécurité" (I-SEC-01..05 + I-CERT-*)
3. classes_bugs.md : classes 3 (swallowing), 4 (SQL), 5 (XSS), 6 (prompt), 15 (logs secrets), 18 (config)
4. angles_attaque.md : angle 1 (Sécurité)
5. Rapport thématique

### Durée : 20-30 min

---

## Workflow 3 — "Audit thématique performance"

### Étapes
1. smoke_test.ps1
2. INVARIANTS catégorie "UX / Latence" (I-UX-*)
3. Métriques live : 
   - curl `-w "%{time_total}"` sur 10 endpoints
   - Logs latence dialog `[full-load]`
   - Cache hit/miss `[instant_reply]`
4. angles_attaque.md : angle 2 (Performance), 5 (Cache), 6 (Network)
5. classes_bugs.md : classe 10 (leaks), 11 (error HTTP timeouts)
6. Rapport

### Durée : 20-30 min

---

## Workflow 4 — "Diagnostic bug précis" (user signale un symptôme)

### Étapes

1. **Recherche pattern déjà vu (5 min)**
   - Lire `ANOMALIES_RECURRENTES.md` — le symptôme signalé est-il dans un pattern existant ?
   - Si oui : appliquer le fix canonique, pas besoin d'audit complet

2. **État système (5 min)**
   - `powershell -File audit/tests/diagnostic_pack.ps1` → rapport complet
   - Identifier les anomalies liées au symptôme

3. **Reproduction (5 min)**
   - Tenter de reproduire le bug avec curl / test isolé
   - Si reproductible : preuve factuelle pour le rapport

4. **Grep ciblé (5 min)**
   - Commandes du `classes_bugs.md` liées à la classe de bug suspectée

5. **Fix + validation**
   - Appliquer fix
   - Relancer smoke_test.ps1
   - Ajouter pattern à ANOMALIES_RECURRENTES si nouveau
   - Ajouter invariant à INVARIANTS.md + check dans smoke_test si applicable

### Durée : 15-30 min selon complexité

---

## Workflow 5 — "Boucle audit→fix→audit jusqu'à 0 anomalie"

### Étapes (récurrentes)

```
ITÉRATION N
├─ Workflow 1 (audit complet) → X anomalies détectées
├─ Si X = 0 → FIN (rapport final signé)
├─ Si X > 0 :
│  ├─ Appliquer TOUS les fixes des anomalies
│  ├─ Mettre à jour ANOMALIES_RECURRENTES.md
│  ├─ Itération N+1 du workflow
```

### Garde-fous anti boucle infinie

- **Définition stricte d'anomalie** : violation d'invariant OU échec smoke OU dysfonctionnement observable. Pas "amélioration".
- **Patterns récurrents détectés dans 2 itérations consécutives** = cause racine plus profonde → arrêt boucle, investigation user
- **Max 5 itérations** : si encore des anomalies après, c'est que la méthode échoue → discussion user

---

## Workflow 6 — "Après un fix appliqué, vérif rapide"

### Étapes
1. smoke_test.ps1 (exit 0 obligatoire)
2. Test end-to-end du flux modifié
3. Logs : pas d'ERROR nouveau
4. Le fix est loggé dans ANOMALIES_RECURRENTES

### Durée : 5 min

---

## Workflow 9 — "Audit UX/design alignment" (ajouté 01/05/2026)

### Origine

Création suite à un trou structurel détecté dans la session 30/04 PM autonomie : le fichier `V2/popup.html` affichait 7 boutons (3 nav + 4 ancien design taskpane) alors que les specs documentaient « 3 boutons seulement » (cf `docs/specs_proto/SPEC_FONCTIONNALITES_PROTO.md:488` + bilan 23/04).

**8 audits ULTRA passés sans détecter ça** : tous orientés bugs techniques (race conditions, fuites FD, sécurité, encoding, datetime, etc.) — Pattern PLAYBOOK #5. Aucun n'avait pour mission de **confronter le rendu visuel aux specs**.

### Objectif

Détecter automatiquement les **écarts entre intention UX/design et rendu effectif** :
- Éléments présents dans le HTML/UI mais NON spécifiés (régression : héritage d'un ancien design pas nettoyé)
- Éléments spécifiés MAIS absents du rendu (oubli d'implémentation)
- Éléments présents mais avec un mauvais comportement / texte / position

### Quand faire ce workflow

- **Après chaque décision UX** d'Yvan qui change un écran (priorité 1)
- **Avant chaque audit ULTRA** (priorité 2 — sinon on cherche des bugs de précision dans une UI déjà fausse)
- **Au moins 1× par semaine** quand on est dans une phase de polish UI

### Étapes

1. **Source de vérité — `audit/checklists/ui_design_specs.md` (15 min)**
   - Liste les écrans user-facing avec pour chacun : ce qui DOIT être visible (boutons, sections, états).
   - Mise à jour par Yvan à chaque décision UX. **Si la spec change, ce fichier change AVANT le code**.

2. **Audit automatisé — `audit/tests/e2e/test_ui_specs.py` (1 min)**
   - `python -m pytest audit/tests/e2e/test_ui_specs.py -v`
   - Parse chaque HTML, extrait les éléments visibles via BeautifulSoup, compare aux specs.
   - Échoue à un `assert` si écart détecté.
   - **Exit 0 = écrans conformes**. Exit ≠ 0 = écrans à fixer.

3. **Audit visuel manuel (10 min, complément)**
   - Yvan ouvre chaque écran user-facing dans Outlook réel
   - Confronte avec la spec
   - Signale les écarts en mots simples (« je vois X au lieu de Y »)

4. **Fix + MAJ specs (variable)**
   - Si écart détecté = bug → fixer le code (sans toucher la spec)
   - Si écart détecté = ancienne spec → MAJ `ui_design_specs.md` avec la nouvelle décision
   - Re-lancer `test_ui_specs.py` jusqu'à exit 0

### Critères de fin

- `test_ui_specs.py` exit 0
- `audit/checklists/ui_design_specs.md` reflète l'intention courante d'Yvan
- Aucun écart visuel-spec connu non noté dans `PLUS_TARD_VF.md`

### Pourquoi ce workflow EXISTE et pas avant

Trou détecté **après 7-8 audits ULTRA passés sans le voir** (exemple popup.html). Les sub-agents Explore cherchaient des défauts de code ; aucun n'avait de référentiel UX à confronter. Ce workflow comble cette lacune.

---

## Règles communes à tous les workflows

1. **Je ne dis jamais "c'est fixé" sans smoke_test exit 0 + preuve visible**
2. **Je consulte ANOMALIES_RECURRENTES.md AVANT de qualifier un nouveau bug**
3. **Tout nouveau pattern est ajouté à ANOMALIES_RECURRENTES.md dans la session**
4. **Tout rapport d'audit est sauvé dans `audit/rapports/`**
5. **Définition d'anomalie = objective** (pas de "code plus propre" subjectif)

---

## Workflow 7 — "Kit fin de session" (trigger : Yvan tape "kit fin de session")

### Objectif
Garantir une clôture de session 100% propre — aucune information perdue, aucune incohérence entre docs, aucune modif locale non commitée. Reproduit la rigueur du kit audit pour l'aspect documentaire.

### Engagement Claude (opposable)
- **Je ne déclare PAS la session close avant que `audit/tests/cloture_check.sh` retourne exit 0.**
- **Si je modifie un doc qui contient un chiffre dynamique (commits, audits, etc.), je relance `cloture_check.sh` dans la foulée.**
- **Je ne touche pas au `PROMPT_REPRISE_NEW_OUTLOOK.md` sans relancer le check de cohérence après.**

### Étapes (ordre strict)

1. **Pré-clôture — état des lieux (2 min)**
   - `git status --short` → noter modifs locales en cours
   - `git log --oneline --since='today 00:00' | wc -l` → noter le compte de commits du jour
   - Si modifs en cours : commiter le travail technique en commits granulaires AVANT d'attaquer la doc

2. **Bilan de session (10-15 min)**
   - Créer/MAJ `docs/sessions/OUTLOOK_BILAN_SESSION_AAAAMMJJ[_descriptif].md`
   - Sections obligatoires : Mission accomplie, Récap commits, Découvertes, Travail par bloc, Livrables, État OVH, Sujets ouverts
   - Format hash commit : `89e6524+` (avec le `+` qui signifie "et les commits suivants potentiels"), PAS de chiffre figé dans l'en-tête

3. **MAJ docs en cascade (10 min)**
   Ordre obligatoire (suit le graphe de dépendances) :
   - **`docs/PLUS_TARD_VF.md`** : sujets résolus → DÉJÀ FAIT, nouveaux → catégorie, caducs → ABANDONNÉ + MAJ date d'en-tête
   - **`docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md`** : MAJ date d'en-tête + section L (liste bilans)
   - **`docs/specs_proto/HISTORIQUE_DECISIONS.md`** : nouvelle entrée SI décision structurelle (sinon skip)
   - **`audit/INVARIANTS.md`** : nouveaux invariants SI détectés (sinon skip)
   - **`audit/ANOMALIES_RECURRENTES.md`** : nouveaux Patterns SI détectés (sinon skip)
   - **`docs/SOMMAIRE_DETAILLE.md`** : entrée bilan + statuts à jour

4. **MAJ `docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md` (5 min)** ⚠️ TOUJOURS EN DERNIER
   - Section "ÉTAT DE FIN" : reformulée avec le nouveau contexte
   - Top commit hash référencé : doit matcher `git log --oneline -1` au moment du commit final
   - Format : utiliser `git log` comme vérité, pas figer un chiffre

5. **Lancer `cloture_check.sh` (1 min)**
   ```bash
   bash audit/tests/cloture_check.sh
   ```
   - Si exit 0 → continuer étape 6
   - Si exit ≥ 1 → fix les anomalies listées + relancer le script + boucle jusqu'à exit 0

6. **Commit final unique des MAJ docs**
   - 1 seul commit thématique `docs(session): cloture session AAAAMMJJ — bilan + MAJ cascade`
   - Fast-forward master
   - Si `cloture_check.sh` retournait exit 0 avant ce commit, il continuera à retourner exit 0 après (le commit ne touche pas aux invariants)

7. **Validation finale (30 sec)**
   - `git status --short` → vide
   - `git log --oneline --since='today 00:00' | wc -l` → compte final
   - `bash audit/tests/cloture_check.sh` → exit 0 confirmé

### Critères de succès (tous obligatoires)
- ✅ `git status --short` vide
- ✅ `cloture_check.sh` exit 0
- ✅ `PROMPT_REPRISE_NEW_OUTLOOK.md` reflète l'état au moment de la clôture
- ✅ Bilan de session complet (toutes sections obligatoires remplies)

### Anomalies récurrentes à éviter (vécu 27/04/2026)
- Annoncer "session close" sans avoir lancé `cloture_check.sh`
- Modifier `PLUS_TARD_VF` sans propager dans `PROMPT_REPRISE`
- Figer un chiffre de commits qui devient obsolète au commit suivant (auto-référence) → utiliser `git log` comme source dynamique
- Oublier d'ajouter au backlog les sujets émergents constatés en cours de session

---

## Workflow 8 — "Kit ouverture de session" (trigger : Yvan copie le PROMPT_REPRISE)

### Objectif
Démarrer une nouvelle session avec le contexte complet de la session précédente, sans rien perdre.

### Activation
Yvan copie-colle `docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md` dans la nouvelle session Claude. Le prompt référence ce workflow.

### Étapes (à exécuter par Claude au démarrage)

0. **Vérification racine (5 sec, OBLIGATOIRE — ajout 05/05/2026)**
   - Confirmer que toute exploration projet vise `C:\EasyMail\` — JAMAIS `C:\Users\yvanb\OneDrive\Desktop\EasyMail\` (vestige pré-12/04, contenu périmé + souvent cloud-only illisible).
   - Si un `pwd` ou un Glob retourne un chemin OneDrive lié au projet → arrêter et alerter Yvan.
   - Couvert par `I-SESS-05` dans `audit/INVARIANTS.md` (vérification mécanique en fin de session via `cloture_check.sh`).

1. **Vérification worktree (30 sec)**
   - `git -C C:/EasyMail branch --show-current` → doit retourner `master`
   - `git -C C:/EasyMail log --oneline -5` → top doit matcher l'état décrit dans le PROMPT_REPRISE
   - Si worktree différent (style `claude/happy-XXXX`), exécuter `git fetch && git merge master --no-edit`

2. **Tests de validation infra (30 sec)**
   - `ssh -o BatchMode=yes -o ConnectTimeout=5 ubuntu@51.178.162.208 "echo OK_SSH_KEY_WORKS"`
   - `curl -sk https://api.boostermail.ai/api/warmup_status` → 200 OK
   - Si l'un échoue → arrêter et alerter Yvan

3. **Lecture docs obligatoires (5 min, dans l'ordre)**
   - `docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md` (référence vivante)
   - `docs/PLUS_TARD_VF.md` (TL;DR en haut)
   - Dernier `docs/sessions/OUTLOOK_BILAN_SESSION_*.md` (contexte session précédente)
   - `audit/INVARIANTS.md` (consultation rapide — surtout I-SESS-* + I-CACHE-* + I-SEC-* récents)
   - `audit/ANOMALIES_RECURRENTES.md` (Patterns récents, surtout #18 cache WebView2)

4. **Synthèse rapide à Yvan (1 min)**
   - "Session précédente : X commits, Y audits clos, sujet en cours = Z (ex: Coaxis ETA J+2/3)"
   - "Que veux-tu attaquer ? Ou je consulte PLUS_TARD_VF et propose ?"

### Critères de succès
- ✅ Worktree à jour (top commit match attendu)
- ✅ OVH joignable (SSH + warmup)
- ✅ Claude a lu les 5 docs obligatoires
- ✅ Yvan a la main pour décider l'attaque

---

## Index rapide

| Demande user | Workflow |
|---|---|
| "Audit complet V2" | 1 |
| "Audit sécurité" | 2 |
| "Audit performance" | 3 |
| "Il y a un bug : [symptôme]" | 4 |
| "Boucle jusqu'à 0 anomalie" | 5 |
| "Après un fix, vérif" | 6 |
| **"Kit fin de session"** | **7** |
| **(Yvan copie PROMPT_REPRISE_NEW_OUTLOOK)** | **8** |
