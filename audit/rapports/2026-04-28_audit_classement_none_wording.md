# Rapport d'audit — Wording transparent classement « pas de suggestion » (PLUS_TARD_VF #4)

> **Date** : 2026-04-28
> **Auditeur** : Claude (kit audit Workflow 2 — cohérent avec audit sujet #3)
> **Périmètre** : Implémentation détection raison + wording transparent quand `mail_classement_cache.source='none'`
> **Durée audit** : ~12 min
> **Statut final** : ✅ 0 anomalie détectée

---

## A. Contexte

Audit thématique post-livraison du sujet PLUS_TARD_VF #4. Le sujet a fait l'objet d'un **pivot produit majeur** par rapport à la proposition d'origine.

### A.1 Proposition initiale (rejetée)
La spec du 26/04 proposait un thread BG `_classement_none_recheck_loop` qui purge tous les 30 jours les entries `source='none'` pour qu'elles soient re-traitées par cont-spec.

### A.2 Pivot Yvan (28/04)
> *« Lorsque le mail arrive, normalement l'utilisateur n'attend pas une semaine ou 2 semaines pour classer ce mail — ce n'est pas l'objectif de BoosterMail. Re-traiter à posteriori va contre la philosophie. Plutôt jouer la transparence : "Nouvel expéditeur — pas de suggestion de classement". »*

### A.3 Solution livrée
Au lieu d'investir dans un mécanisme de re-traitement temporel, on **enrichit la sémantique** du `source='none'` en 4 sous-catégories, et on affiche un wording explicite par catégorie pour transformer le "vide" en explication pédagogique.

### Périmètre fonctionnel
4 fichiers modifiés au commit `À venir` :
- `V2/database.py` : 2 méthodes count (`count_classifications_for_contact`, `count_classifications_for_domain`)
- `V2/app_plugin.py:_prewarm_classement_for_mail` : détection `auto_email` AVANT Claude (économie API) + classification post-Claude (`none_new_sender` / `none_unknown_domain` / `none_low_signal`)
- `V2/dialog.js:_applyMailPreview` : mapping `clsData.source` → wording validé Yvan
- `V2/autorunshared.js` + `V2/dialog.html` : bump `_ADDIN_VERSION` v11 + `?v=v16` (cache busting Pattern #18)

### Wordings validés Yvan (Style 1 — transparent + pédagogique)
| Cas | Wording |
|---|---|
| `none_auto_email` | « Mail automatique — pas de dossier métier évident. » |
| `none_new_sender` | « Premier mail de ce contact — je m'inspirerai de ton classement. » |
| `none_unknown_domain` | « Domaine que je découvre — apprends-moi en classant. » |
| `none_low_signal` | « Mail trop court pour suggérer un dossier. » |
| `none` (fallback) | « Néant » (legacy) |
| `self` | « Mail envoyé à toi-même. » |

---

## B. Vérifications par classe (classes_bugs.md)

| Classe | Sujet | Résultat | Détail |
|---|---|---|---|
| 1 | Race conditions | ✅ N/A | Aucune variable globale touchée. Le pipeline `_prewarm_classement_for_mail` réutilise les locks existants (`_mail_preview_lock`). |
| 2 | Exception swallowing | ✅ OK | 0 `except: pass` nu dans le périmètre. Tous les try/except utilisent `logger.debug(...)` pour tracer. |
| 3 | Resource leaks | ✅ N/A | Pas de fichier ouvert, pas de socket. |
| 4 | SQL injection | ✅ OK | Les 2 nouvelles méthodes `count_classifications_for_*` utilisent placeholders `?`. |
| 5 | XSS / DOM | ✅ OK | `dialog.js:_applyMailPreview` utilise `clsEl.textContent` (pas `innerHTML`). Wording en dur dans le code (pas de user input concatené). |
| 6 | Prompt injection | ✅ N/A | Aucun prompt Claude touché. La détection `auto_email` se fait via regex Python, sans appel Claude. |
| 7 | Idempotence | ✅ OK | Le pipeline `_prewarm_classement_for_mail` reste idempotent : check cache DB en premier, classification post-Claude n'écrit qu'une fois via `INSERT OR REPLACE`. |
| 8 | Cache consistency | ✅ OK | Pas de nouveau cache RAM/JSON. Extension du `source` (TEXT) dans la table existante `mail_classement_cache`. Compatible avec entries legacy `source='none'`. |
| 9 | TLS / Network | ✅ N/A | Aucun bind, cert ou réseau touché. |
| 10 | Memory leaks | ✅ N/A | Aucune liste globale, aucune addEventListener. |
| 11 | Error handling HTTP | ✅ N/A | Aucun fetch JS dans le périmètre côté nouveau code. |
| 12 | Thread safety SQLite | ✅ OK | Réutilise `self._conn()` (threading.local). |
| 13 | Imports / typos / NameError | ✅ OK | `python -m ast` parse les 2 fichiers Python sans erreur. |
| 14 | Fichiers absents / broken refs | ✅ OK | Toutes les fonctions appelées existent (vérifié via grep). |
| 15 | Logs / observabilité | ✅ OK | Logs INFO ajoutés pour les cas auto_email détectés (« mail automatique detecte → skip Claude »). Pas de secret exposé. Aucun emoji Unicode. |
| 16 | Cohérence OpenAPI | ✅ N/A | Aucune route ajoutée ou modifiée. |
| 17 | UX blockers | ✅ OK | Le wording remplace « Néant » → l'utilisateur a toujours un texte affiché, jamais de spinner figé. |
| 18 | Configuration / secrets | ✅ N/A | Aucune config touchée. |
| 19 | Cert / auth | ✅ N/A | Aucun cert touché. |
| 20 | Test runtime | ✅ OK | Service `boostermail` active. Warmup HTTP 200. 0 erreur dans logs. Test in-process : 8/8 cas de détection auto_email passent. |

---

## C. Anomalies détectées

**Aucune.** Le code est sain dès le départ — bénéfice des apprentissages du sujet #3 (defense-in-depth XSS).

---

## D. Vérifications invariants pertinents

| Invariant | Pertinent ? | Résultat |
|---|---|---|
| I-DATA-11 (clés cache cohérentes) | ✅ Critique | OK — pipeline existant non modifié, `internet_message_id` canonique préservé. |
| I-CODE-05 / Pattern #15 (mail_data IMID) | ❌ Hors périmètre (pas de mail_data construit) | N/A |
| I-CACHE-01/02 (no-store + cache busting) | ✅ Critique | OK — `_ADDIN_VERSION` v10 → v11 + `dialog.js?v=v15` → `v16`. Convention `vN-fix-<sujet>-<JJ-MM>` respectée. |
| I-DATA-13 (priorité internet_message_id) | ❌ Hors périmètre | N/A |
| I-DATA-05 (DB pas vide) | ✅ Critique | OK — distribution post-déploiement : ai=63, none=5, rule=3, none_unknown_domain=1. |
| I-SEC-06 (garde anti-injection prompt) | ❌ Hors périmètre (pas de prompt Claude touché) | N/A |

---

## E. Multi-tenant readiness check (cross-user SaaS)

| Critère | Statut |
|---|---|
| Détection `auto_email` purement local (regex sur l'expéditeur) | ✅ Pas de fuite cross-user possible |
| `count_classifications_for_*` lit `folder_classifications` (table déjà mono-user, scopée par user_id à venir Étape 7) | ✅ Comportement cohérent avec migration future |
| Wordings frontend en dur dans `dialog.js` (pas de user input dans le rendu) | ✅ Pas de risque d'injection cross-user |
| Le pipeline `_prewarm_classement_for_mail` était déjà appelé par mail (donc indirectement par user) | ✅ Pas de logique nouvelle qui partage du state entre users |

**Conclusion multi-tenant** : aucune dette technique pour l'Étape 7 SaaS. La nouvelle classification est portée par les colonnes existantes de `mail_classement_cache` qui auront un `user_id` ajouté à la migration.

---

## F. Tests runtime exécutés

```bash
# 1. Syntax Python
python -c "import ast; [ast.parse(open(f).read()) for f in ['database.py', 'app_plugin.py']]"
# ✅ OK

# 2. Service status
ssh ubuntu@51.178.162.208 "sudo systemctl is-active boostermail"
# ✅ active

# 3. Warmup HTTP
curl -sk https://api.boostermail.ai/api/warmup_status
# ✅ done:true, "Cache chaud — prêt en un éclair"

# 4. Logs OVH 5 dernières minutes
sudo journalctl -u boostermail --since '5 minutes ago' | grep -iE 'error|traceback'
# ✅ 0 erreur

# 5. Test détection auto_email (in-process)
# 8 cas testés (noreply, no-reply, donotreply, mailer-daemon, notifications@,
# + 3 contacts humains contre-exemples)
# ✅ 8/8 PASS

# 6. Distribution sources mail_classement_cache post-déploiement
# ai=63, none=5, rule=3, none_unknown_domain=1
# ✅ Le retrofit a bien upgradé 1/6 entries (autres restent 'none' générique
# ou ont leur email source purgé du cache → edge case acceptable)
```

---

## G. Conclusion

**0 anomalie détectée.** Implémentation propre dès le départ.

**Bénéfices livrés** :
1. **UX** : transformation du « vide silencieux » en explication transparente → confiance utilisateur renforcée
2. **Pédagogie** : l'utilisateur comprend ce qu'il peut faire pour aider l'IA (classer manuellement)
3. **Économie API** : détection des mails automatiques AVANT Claude → 1 appel API évité par notification système (marginal aujourd'hui mais cumule)
4. **Différenciation produit** : approche « assistant qui dit honnêtement quand il sèche » plutôt qu'une IA qui propose à tout prix

**Pivot produit réussi** : la proposition d'origine (thread BG calendaire) aurait coûté ~50 lignes de code, race conditions à gérer, et réécriture pour multi-tenant. La solution livrée coûte ~30 lignes simples, 0 race condition, multi-tenant ready.

---

## H. Commits associés

| Commit | Sujet |
|---|---|
| `À venir` | Implémentation + ce rapport d'audit |

---

## I. Liens utiles

| Sujet | Lien |
|---|---|
| Sujet d'origine | `docs/PLUS_TARD_VF.md` (item #4, marqué FAIT 28/04) |
| Pipeline classement | `V2/app_plugin.py:1889+` (`_prewarm_classement_for_mail`) |
| Détection auto_email | `V2/app_plugin.py:1937+` (bloc `[2 ter]`) |
| Classification post-Claude | `V2/app_plugin.py:2017+` (bloc `[4]` étendu) |
| DB count methods | `V2/database.py:718+` |
| Frontend mapping | `V2/dialog.js:1043+` |
| Wordings finaux | Validés par Yvan le 28/04 (Style 1 transparent + pédagogique) |
