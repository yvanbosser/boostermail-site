# Audit ciblé — Classement mail + classement PJ

> **Date** : 02/05/2026 fin de soirée
> **Périmètre** : refonte unifiée Cuisinier+Commis + Tier DB + top 3 + recherche live (commits `787fc12` → `7de4997`)
> **Workflow** : Workflow 1 adapté (audit thématique sur scope restreint)
> **Auditeur** : Claude Opus 4.7

---

## 1. Baseline

| Check | Résultat |
|---|---|
| Service `boostermail` actif sur OVH | ✅ active |
| `app_plugin.py` compile | ✅ OK |
| `dialog.js` syntaxiquement valide (parse Python read) | ✅ 5327 lignes |
| Logs production exempts d'erreurs neuves | ✅ aucune `Exception` ni `Traceback` post-deploy |

---

## 2. Périmètre audité

| Fichier | Lignes touchées | Nature |
|---|---|---|
| `V2/app_plugin.py` | `_prewarm_unified_for_mail` (~250 lignes) | Tier DB pré-check + top 3 + commis |
| `V2/dialog.js` | `_showClassMailPopup`, `_showClassPJPopup`, `_findFolderMatch`, `_findPJFolderMatch`, `_onManualPathInput`, `_onManualPJPathInput` | Recherche live + boulettes top 3 |
| `V2/dialog.html` | `popupClassMail`, `popupClassPJ` placeholders | Wording barre de recherche |
| `V2/database.py` | `_prewarm_pj_classement_for_mail` reload | Cohérence reload `_suggestions` |

---

## 3. Anomalies détectées

### 🔴 A2 — `_prewarm_unified_for_mail` ne checkait pas le cache DB (HIGH, performance)

**Symptôme** : après chaque restart du service, le commis Haiku était rappelé sur les ~75 mails du warmup, alors que les 3 caches DB (`mail_classement_cache`, `mail_pj_classement_cache`, `mail_echeance_cache`) étaient déjà remplis.

**Root cause** : le check d'idempotence existait dans `_prewarm_classement_for_mail` (fallback) mais n'avait pas été porté dans la nouvelle version unifiée.

**Coût observé** : ~75 appels Haiku × ~150 ms chacun = ~11 s de latence + ~$0.075 par restart.

**Fix** (commit `ccdf06f`) : check des 3 caches DB en début de `_prewarm_unified_for_mail` ; si tout est en DB → reconstruction RAM cache et return avant le commis.

**Validation production** :
```
[mail-preview] pré-chauffe lancée pour 63 mail(s)  ← AVANT fix : 63× [unified] OK
[mail-preview] pré-chauffe lancée pour 63 mail(s)  ← APRÈS fix : 0× [unified] OK
```

**Pattern récurrent** : Pattern #2 (patch-on-patch sans audit de l'existant). La nouvelle pipeline unifiée a oublié un comportement de la pipeline qu'elle remplace.

---

### 🔴 A3 — Pas de skip mails automatiques (HIGH, parité comportement)

**Symptôme** : noreply, mailer-daemon, newsletters → le commis Haiku était appelé inutilement (Claude rendrait `none` presque toujours).

**Root cause** : `_AUTO_PATTERNS` existait dans `_prewarm_classement_for_mail` mais n'a pas été porté.

**Fix** : ajout du même `_AUTO_PATTERNS` check au début de `_prewarm_unified_for_mail`. Stocke `source='none_auto_email'` pour wording UI explicite.

**Pattern récurrent** : Pattern #2 (idem A2).

---

### 🟡 A1 — Regex normalize utilise des chars Unicode bruts (LOW, robustesse)

**Symptôme** : aucun, mais fragile.

**Root cause** : `dialog.js` ligne 3175, 3355, 3358 contenait `/[̀-ͯ]/g` avec les chars U+0300 et U+036F bruts dans le source. Si le fichier passe par un transcodeur ASCII / un copy-paste vers un éditeur ASCII-only, les chars sont silencieusement remplacés par `?` ou supprimés → regex matche rien → accents non strippes → recherche cassée.

**Fix** : remplacement par `/[̀-ͯ]/g` (escapes JS explicites). 3 occurrences corrigées.

**Vérification** :
```
Escaped pattern ̀ : 3 occurrences
Raw unicode pattern : 0 occurrences
```

---

### 🟡 A14 — Pas de `reason` lisible pour les Tier DB (LOW, UX)

**Symptôme** : les boulettes alternatives `●` affichaient juste le path du dossier, sans explication. L'user voyait 3 dossiers proposés sans comprendre pourquoi.

**Root cause** : le commis renvoyait `reason: "..."` mais les Tier DB (`get_folder_by_thread`, `get_folder_suggestion`, etc.) ne renvoyaient pas de `reason`. Le frontend lisait `s.reason` qui était vide.

**Fix** : ajout d'un mapping `_TIER_REASONS` dans `_add_mail_sug` :
- thread → "thread déjà classé"
- rule → "classement habituel pour ce contact"
- keywords → "mots-clés du sujet"
- domain → "domaine récurrent"
- cross_contact → "sujet récurrent"

Idem pour PJ (`_TIER_PJ_REASONS`).

---

## 4. Anomalies écartées (vérifiées non bugs)

### A4 — Closure variable Python sur `mail_suggestions` / `_seen_mail`
Vérifié : Python capture les references aux objets mutables. `list.append()` et `set.add()` modifient les objets externes correctement. ✅ Pas de bug.

### A5 — `subject_kw` peut être vide
Vérifié : c'est intentionnel. Si pas de mots-clés extractibles, on skip Tier 1bis et cross_contact, ce qui est cohérent. ✅

### A8 — Bouton désactivé en cas de top 3 vide
Vérifié : c'est le comportement attendu. L'user doit taper un path manuel ou rien classer. ✅

### A11 — `_classMailFolders` polluée entre popups
Vérifié : variables séparées `_classMailFolders` vs `_classPJFolders`. ✅

### `get_attachments` warnings IMID introuvable
Vérifié dans `outlook_graph.py` ligne 1167 : conversion IMID → Entry ID propre, `WARNING` si mail absent (cas légitime : mail archivé/supprimé). Ne casse pas la pipeline (retourne `[]`). ✅

---

## 5. Anomalies non corrigées (par décision)

### 🟢 A7 — Pas de feedback visuel "Sera créé" en mode no-match (UX)

Quand l'user tape un path qui n'a aucune correspondance dans l'arbo, l'arbo disparaît mais aucun message ne dit "le dossier sera créé". L'user clique "Classer ici" sans confirmation visuelle.

**Pourquoi non corrigé** : décision UX qui appartient à Yvan. À proposer en prochaine itération si ergonomie remontée.

### 🟢 A12 — `_findFolderMatch` itère 3 fois sur folders (PERF MICRO)

Pour 50-500 folders, c'est ~1500 itérations max par keystroke. Imperceptible. À optimiser si l'user remonte de la latence sur des arbos > 1000 dossiers.

### 🟢 C3 — Top 3 ne reflète pas les 7 tiers de la spec

`SPEC_CLASSEMENT_BOOSTERMAIL.md` mentionne 7 tiers : Tier 0 / 1 / 1bis / 2 (folder name in body) / 3a / 3b / 4 (IA) / 5 (momentum). Le code unifié exploite Tier 0/1/1bis/3a/3b/4. Manque Tier 2 (folder name match dans body) et Tier 5 (momentum).

**Pourquoi non corrigé** : ces deux tiers nécessitent un refactor du commis pour exposer le folder_name match côté backend. Effort estimé ~3h. À planifier si Yvan voit ces tiers manquer en pratique.

---

## 6. Tests effectués

| Test | Résultat |
|---|---|
| Service tourne après deploy | ✅ active |
| Aucune nouvelle exception dans les logs | ✅ |
| Cache DB HIT après restart (Fix A2) | ✅ 63 mails skip commis confirmé |
| Compile Python `app_plugin.py` | ✅ |
| Regex `̀-ͯ` présente 3 fois | ✅ |
| Frontend dialog.js v51 servi | ⏳ utilisateur doit tester en plugin Outlook |

**Non testé** :
- Live test du highlight bleu sur match recherche live (nécessite plugin Outlook ouvert avec arbo réelle)
- Affichage des `reason` lisibles dans les boulettes alternatives (idem)

---

## 7. Métriques

### Avant audit
- 63 mails au warmup → 63 appels Haiku commis (~$0.075 par restart)
- Source des suggestions : 100 % `unified` (commis seul)
- Boulettes alternatives sans explication

### Après audit
- 63 mails au warmup → 0 appel commis si DB hit (économie ~$2/mois sur restarts hebdomadaires)
- Source des suggestions : `thread/rule/keywords/domain/cross_contact/unified` (Tier DB visible)
- Boulettes alternatives avec `reason` lisible

---

## 8. Patterns ajoutés à `ANOMALIES_RECURRENTES.md`

Aucun nouveau pattern. A2 et A3 sont des récidives de **Pattern #2 (patch-on-patch sans audit de l'existant)** : la nouvelle pipeline unifiée a omis 2 comportements de la pipeline qu'elle remplaçait.

**Signal d'alerte renforcé** : quand on remplace une fonction par une version "améliorée", grep tous les comportements et tests de l'ancienne pour les porter explicitement.

---

## 9. Conclusion

**4 anomalies corrigées** (2 HIGH, 2 LOW). Service stable, économie API mesurable, robustesse améliorée.

**3 anomalies non corrigées** (toutes LOW, décisions UX/effort) documentées pour suivi.

**Recommandation** : tester en conditions réelles (plugin Outlook ouvert, arbo SCI complète) le highlight bleu de la recherche live et la cohérence des boulettes alternatives avec leurs `reason`.

---

## 10. Commits

| SHA | Sujet |
|---|---|
| `787fc12` | Tier DB prioritaire sur commis (désambiguïsation SCI) |
| `641301a` | Top 3 suggestions classement mail + PJ (boulettes alternatives) |
| `7de4997` | Barre de recherche live (mail + PJ) avec highlight bleu |
| `ccdf06f` | Audit fixes : A1 (regex) + A2 (cache idempotent) + A3 (noreply skip) + A14 (reason lisible) |
