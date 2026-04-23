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

## Règles communes à tous les workflows

1. **Je ne dis jamais "c'est fixé" sans smoke_test exit 0 + preuve visible**
2. **Je consulte ANOMALIES_RECURRENTES.md AVANT de qualifier un nouveau bug**
3. **Tout nouveau pattern est ajouté à ANOMALIES_RECURRENTES.md dans la session**
4. **Tout rapport d'audit est sauvé dans `audit/rapports/`**
5. **Définition d'anomalie = objective** (pas de "code plus propre" subjectif)

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
