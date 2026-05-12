# Méthodologie de refonte par niveau — BoosterMail

> **Version consolidée 12/05/2026** — après les leçons cumulées des refontes N1, N2, N3, N4, N5.
>
> **Statut** : référence obligatoire à appliquer à chaque niveau (N6 → N12).
>
> **Audit du document** : à relire AVANT chaque nouvelle Phase A. Toute déviation doit être justifiée explicitement.

---

## 0. Le pacte — règles absolues

| Règle | Description |
|---|---|
| **Objectif** | Retrouver l'effet Wouah de BoosterMail qui a régressé à cause de patches successifs |
| **Méthode** | **RÉÉCRIRE propre**, jamais patcher un patch |
| **Tranchage** | Si hésitation entre 2-3 options → **toujours la plus robuste**, automatiquement (sans demander) |
| **Engagement** | Pas de yes-man, pas de mini-commit correctif, pas de complaisance |
| **Test ultime** | À chaque "es-tu sûr que c'est propre ?" du user, la réponse doit être **OUI sans avoir besoin d'un correctif derrière** |

---

## 1. La liste noire des patterns interdits

Ces patterns ont été identifiés en plantant. Si je suis tenté de les écrire, **stop**.

### Patterns de code interdits

- **DRY violation** : recopier la logique d'un helper existant au lieu de l'appeler
  - *Exemple N5* : recopier le test "sample_count >= 1 OR manually_edited" dans `api_instant_reply` au lieu d'appeler `_filter_2_is_vip` → patch sur patch dans un correctif
- **`try/except: pass` silencieux** (vs `try/except: ... log.debug(...)`)
  - *Pattern Audit #3 du 29/04* : un except silencieux cache un vrai problème
- **Code mort qui survit** : variable jamais lue, fonction appelée nulle part, étiquette de cache jamais posée
  - *Exemple N5* : sources `'template'` et `'preemptive'` référencées partout mais jamais créées
- **Commentaires mensongers après refonte** : commentaire qui décrit l'ancien comportement
  - *Exemple N4* : *"ordre choisi pour minimiser le coût moyen"* alors qu'on a justement choisi le pire ordre
- **Fail-open partiel** : la docstring promet "fail-open total" mais le try/except ne couvre qu'un chemin
  - *Exemple N5 1re passe* : protégeait l'appel DB mais pas `int(profile.get('sample_count'))` qui crashe sur `'abc'`
- **Signature changée sans migration de tous les callers** : changer `bool` → `(bool, str)` sans MAJ les 4 sites qui destructurent
  - *Exemple N4 sub-agent* : aurait cassé 4 call sites + perdu une métrique de prod
- **Parsing à 1 seul format** : helper qui gère 3 formats alors qu'il en existe 5-6
  - *Exemple N5* : helper email qui ne gérait pas RFC 5322 `"Alice <alice@x.com>"` → tokens parasites
- **Cache class-level dans contexte multi-user** : `Database._USER_FIRST_NAME_CACHE` mono → bombe au merge Michael
  - *Pattern N3* : post-it obligatoire dans PLUS_TARD_VF.md
- **2 `Database()` dans le même TID** : violation `I-DB-CONN-01`, ferme la conn de l'instance d'origine
  - *Bug latent corrigé N3* : `user_context._get_user_id_from_db()` était fautif

### Patterns méthodologiques interdits

- **Mini-commit correctif après audit POST** : si je trouve un bug après un commit, je RÉÉCRIS la partie défaillante en 1 commit unique, je ne patche pas
  - *Leçon N5* : un mini-commit correctif introduit ses propres patches (cf le piège du wording UNKNOWN→PARTIEL qui a dupliqué la logique VIP)
- **Yes-man qui dit GO quand c'est sale** : si le sub-agent regard frais trouve un problème, je ne propose pas GO niveau suivant — je règle d'abord
- **Logique recopiée dans les tests** : un test doit appeler le vrai code, pas reproduire la logique en local
  - *Leçon N3* : le test du cooldown reproduisait la logique → faux test
- **Invariant écrit dans un .md sans test mécanique** : si l'invariant ne peut pas être vérifié par un grep/AST scan, il n'existe pas
  - *Leçon N4* : tous les invariants doivent être testables mécaniquement

---

## 2. Checklist mentale AVANT d'écrire la 1re ligne de Phase D

À cocher mentalement **avant** chaque fonction non triviale que j'écris :

| # | Question | Action si oui |
|---|---|---|
| **A** | **DRY check** : ai-je un helper existant pour ce que je m'apprête à coder ? | Je l'utilise, pas de recopie |
| **B** | **Fail-open exhaustif** : ma fonction peut-elle recevoir un input pourri à chaque niveau (DB corrompue, type inattendu, conversion qui plante) ? | Je liste TOUS les chemins de plantage et les traite explicitement |
| **C** | **Tous les formats d'entrée** : si je parse quelque chose (email, date, body, JSON), combien de formats possibles ce parsing doit-il gérer ? | Je liste les 5-6 formats AVANT, pas après |
| **D** | **Signature stable** : si je change la signature d'un helper, combien de callers à migrer ? | Migration faite dans le même commit, pas après |
| **E** | **Multi-tenant** : ce que j'écris est-il user-scoped ? Le cache que je touche utilise-t-il `_UserScopedDict` ? Itère-je avec `.items()` ou `iter_user_caches()` ? | Si BG thread → `iter_user_caches()` obligatoire |
| **F** | **DB pourrie** : si la valeur en DB est de type inattendu (string au lieu de int, None inattendu), que se passe-t-il ? | `_safe_int()`-like helpers, jamais `int(value)` direct sans try |

Si **une seule** réponse me met mal à l'aise, je prends 5 min de plus pour résoudre AVANT de coder, pas après.

---

## 3. Méthodologie en 7 phases

### Phase A — Cartographie exhaustive (AVANT tout code)

**A.1** Triangulation **4 sources** :
- 🔍 Grep mots-clés du domaine (FR + EN)
- 🔍 Grep symboles découverts
- 🔍 Suivi des call sites (qui m'appelle ? qui je rappelle ?)
- 🔍 Sub-agent regard frais qui chasse les angles morts

**A.2** Pour chaque morceau : qualification **PATCH / CODE LÉGITIME / CODE MORT**
- Pour chaque PATCH : pourquoi il a été ajouté (commit blame), rustine encore quelque chose ?

**A.3** Lister **tous les commentaires** qui parlent du niveau (pour MAJ/suppression)

**A.4** **Livrable validé par Yvan avant Phase B** — pas de code avant validation

### Phase B — Les 4 rappels obligatoires

Dans un langage simple, **moins technique** (le user n'est pas dev) :

- **Code actuel** : ce que ça fait aujourd'hui, en français normal
- **Règles définies** : ce que la PPTX dit + tes arbitrages
- **Finalité** : à quoi sert ce niveau dans la chaîne
- **Réalité vs Objectif** : où on diverge

### Phase C — Plan + sub-agent démolisseur

**C.1** Chantiers numérotés (but, fichiers, risque, dépendances)

**C.2** **Règle de tranchage automatique** : robustesse > élégance > rapidité (sans demander)

**C.3** Sub-agent regard frais qui **démolit le plan** avant que Yvan valide

**C.4** Restituer les critiques du sub-agent **brutes** au user (sans édulcorer)

**C.5** Validation explicite Yvan avant code

### Phase D — Refonte propre (substitution, pas fix)

**Règles strictes** :

1. **Checklist mentale (1-6) appliquée systématiquement** AVANT chaque fonction
2. On ne patche pas un patch — on l'**enlève** et on écrit propre
3. Une seule source de vérité par concept
4. Migrations DB idempotentes et transactionnelles
5. Garde-rails systématiques (try/except qui **logge**, pas silencieux)
6. Fonctions courtes (> 100 lignes → refactor en sous-fonctions)
7. **Audit des call sites** en fin de Phase D : tous alignés sur le nouveau contrat ?
8. **Relire chaque commentaire touché** : dit-il la vérité du code nouveau ?

### Phase E — Tests exhaustifs

**E.1** Tests fonctionnels : **appellent le vrai code, pas logique recopiée**

**E.2** Tests d'invariants : **mécaniques** (regex/AST scan), pas juste écrits

**E.3** Tests de non-régression : suite N précédents reste verte

**E.4** Tests des cas limites : None, vide, types pourris, casse limite, DB corrompue

**E.5** **Un test par promesse de docstring** : si la docstring dit "fail-open sur input pourri" → un test qui le vérifie effectivement

### Phase F — Auto-audit méta (DOUBLE étape, OBLIGATOIRE)

**F.1** Grille des 5 questions pourries (auto-imposées) :

1. Les tests testent-ils VRAIMENT ce qu'ils prétendent tester ?
2. Les invariants sont-ils testables MÉCANIQUEMENT ?
3. Le flag/data ajouté est-il CONSOMMÉ quelque part ?
4. Quels chemins ne sont PAS couverts ?
5. Qu'est-ce qui va péter SILENCIEUSEMENT au merge avec une autre branche ?

**F.2** **Sub-agent regard frais POST-implementation AVANT le commit** (pas après) :

- Mission : trouver les patches résiduels, doublons cachés, optimisations manquées, fragilités, reliquats
- **Si fragilité trouvée → RÉÉCRIRE propre en remplaçant la partie défaillante**
- **Refuser le mini-commit correctif** — c'est un patch sur patch
- **Ne pas commit tant que le sub-agent ne valide pas blanc**

### Phase G — Déploiement propre

- Commit **unique** (pas accumulation)
- Message qui explique le **POURQUOI**, pas le **QUOI**
- Update `audit/INVARIANTS.md` avec nouveaux invariants
- Update `docs/PLUS_TARD_VF.md` si dette explicite reportée
- Push + merge `feat/yvan/frontend`
- **Bilan honnête /10** sans complaisance
- **Engagement explicite** : « pas de mini-commit correctif derrière »

---

## 4. Le réflexe « post-commit » interdit

Si un problème est trouvé **après** le commit :

❌ **Pas un mini-commit correctif** (= patch sur patch)

✅ Réflexion : « cette partie est-elle propre dans son ensemble ? »

✅ Si non : **réécriture en un seul commit unique** intitulé `refonte(Nx) : remise au propre`

✅ Le titre dit la vérité (« réécriture », pas « fix »)

✅ Sub-agent regard frais sur la nouvelle version AVANT push

---

## 5. Communication avec Yvan

### Quand restituer techniquement vs en clair

Par défaut, **moins technique** :
- Pas de noms de fonctions / lignes de code dans le corps
- Analogies cuisine (videur, frigo, chef Sonnet, commis Haiku)
- Tableaux visuels plutôt que paragraphes
- Mon avis explicite + impact business / ressenti user

**Plus technique** uniquement si Yvan demande explicitement.

### Quand poser une question vs trancher seul

**Trancher seul** :
- Choix techniques sans impact produit (set vs string, ordre des règles internes, nom d'une fonction)
- Si "robustesse vs élégance" → toujours robustesse, sans demander

**Demander à Yvan** :
- Choix produit (Q1-Qx de N4, N5) : ajout/suppression de règle métier, comportement utilisateur perceptible
- Trade-off coût Anthropic vs ressenti user
- Décision de garder ou supprimer une dette (vs corriger maintenant)

### Quand restituer un audit

**Toujours, sans édulcorer**, après chaque sub-agent regard frais. Format :
- 🔴 Bloquants (= obligation de corriger)
- 🟡 Importants (= forte recommandation)
- ⚪ Mineurs (= dette acceptable si documentée)
- 🟢 Ce qui est validé (rassurer = info aussi utile)

---

## 6. Indicateurs de qualité finale (par niveau)

| Indicateur | Cible |
|---|---|
| **Tests** | 100 % verts sur tous les niveaux précédents + le nouveau |
| **Sub-agent regard frais PRÉ-commit** | Validation blanche (aucun BLOQUANT, aucun IMPORTANT) |
| **Patterns interdits** | 0 introduit (vérifié par grep automatique dans les tests d'invariants) |
| **Mini-commits correctifs derrière** | 0 — engagement explicite |
| **Bilan /10** | Code propre ≥ 9, Flux fluide ≥ 9, Robuste ≥ 9 |

---

## 7. Invariants accumulés (référence)

Pour chaque niveau passé, un invariant testable a été ajouté dans `audit/INVARIANTS.md` :

- **I-CANON-01** (N1+N2) : clé canonique IMID dans tous les caches
- **I-NOREPLY-01** (N1) : 1 seule liste no-reply (`_AUTO_EMAIL_PATTERNS`)
- **I-CONTACT-01** (N3) : garde anti-inversion DB-side dans `save_contact_profile`
- **I-DB-CONN-01** (N3) : 1 seule `Database()` par db_path par TID
- **I-FILTRE-01** (N4) : Filtre 1 = OR strict de 5 règles atomiques
- **I-FILTRE-2-01** (N5) : Filtre 2 = profil enrichi OU manuellement édité (`_filter_2_is_vip` unique)

**Chaque nouveau niveau doit ajouter au moins 1 invariant testable** au document.

---

## 8. Dettes documentées (référence)

Centralisées dans `docs/PLUS_TARD_VF.md` :

- **#19** Cache `Database._USER_FIRST_NAME_CACHE` mono-user → merge Michael
- **#20** Statut `C:\EasyMail\claude_ai.py` (hors V2) à confirmer
- **#21** Décodage entités HTML (`&nbsp;`) dans `_clean_body_text`
- **#22** Règle 5 CC dépend de `_get_my_email` (mono-user) → merge Michael
- **#23** Pattern itération `_UserScopedDict.items()` vs `iter_user_caches()` → merge Michael
- **#24** Limitation IDN (domaines unicode) dans `_extract_emails_from_field`

**Chaque nouvelle dette identifiée et reportée doit y être ajoutée**, avec priorité + plan de résolution + effort estimé.

---

## 9. Historique des leçons par niveau

| Niveau | Leçon principale | Pattern interdit identifié |
|---|---|---|
| N1 | Triangulation 4 sources obligatoire | Listes parallèles divergentes |
| N2 | Migrations DB idempotentes | TTL purge sans transaction |
| N3 | Cache class-level = bombe multi-tenant | 2 `Database()` dans le même TID |
| N4 | Sub-agent regard frais POST-impl révèle ce que la 1re passe a raté | Mini-commit correctif acceptable mais risqué |
| **N5** | **Le mini-commit correctif EST un piège** | **Réécriture propre, pas patch sur patch** |
| N6+ | À identifier en cours de route | À identifier |

---

## 10. Engagement explicite pour la suite

À partir de N6, **pour chaque niveau** :

1. Je relis ce document AVANT Phase A
2. J'applique la checklist mentale (section 2) systématiquement
3. Je lance le sub-agent regard frais PRÉ-commit (Phase F.2)
4. Je refuse les mini-commits correctifs derrière
5. Je restitue les audits **brutalement** à Yvan
6. Je tranche moi-même sur les choix techniques (robustesse > élégance)
7. Je demande à Yvan **uniquement** sur les choix produit

**Si je dévie de cette méthodo, Yvan me reprend et je note l'erreur dans la section 9 (leçons par niveau) pour ne plus la refaire.**
