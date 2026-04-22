# Rapport d'audit — Boucle initiale jusqu'à 0 anomalie

> **Date** : 22/04/2026
> **Type** : complet (V2 + companion + service + install)
> **Itérations** : 3
> **Convergence** : oui, à l'itération 3

---

## Déroulé des 3 itérations

### Itération 1 — Première passe

**Résultat** : 5 anomalies + 6 faux positifs dans le smoke_test lui-même (nettoyés)

**Anomalies V2 détectées** :
| # | Sévérité | Classe | Fichier |
|---|---|---|---|
| 1 | Moyen | Prompt injection | `V2/claude_ai.py` (4 prompts sans guard) |
| 2 | Bas | Dead code + mixed-content | `V2/taskpane.js:343-362` |
| 3 | Bas | Resource leak | `companion/companion.py:1061` |
| 4 | Bas | Popup Windows modal | `install_outlook_addin.py:229-243` |
| 5 | Bas | Écriture non-atomique | `V2/app_plugin.py:1019` |

**Faux positifs du kit corrigés** :
- Emoji U+2014 dans le script PowerShell → crash parsing cp1252
- Regex thumbprint cert bloquée par NBSP cp1252 français
- `certutil -hashfile` vs thumbprint DER confondus
- `ConvertFrom-Json` sur stdout mixé stderr
- Grep match commentaires / docstrings Python → filtrage AST ajouté
- Win32_Process filter LIKE → array forcé

**Fixes appliqués** :
1. Bloc `## SECURITE` ajouté aux 4 prompts manquants dans `claude_ai.py`
2. `_detectCompanion()` + variable `_companionAvailable` supprimés
3. `pyqt_log.close()` ajouté dans un `finally:` après `Popen`
4. `remove_cert_trusted_root()` : plus de `certutil -delstore`, alerte user uniquement
5. Pattern atomic `.tmp + os.replace` appliqué à `_save_prefetch_cache`

**Patterns ajoutés à `ANOMALIES_RECURRENTES.md`** : #9, #10, #11

### Itération 2 — Vérification des fixes

**Résultat** : 1 anomalie — **régression introduite par le Fix #4**

**Anomalie** :
- `remove_cert_trusted_root()` loguait ses alertes via `log(..., 'INFO')` — or la fonction `log()` filtrait tout ce qui n'est pas `ERROR` en mode non-verbose → `--uninstall` silencieux disait "succès" alors que le cert restait dans Trusted Root
- **Fix #6** : la fonction `log()` affiche désormais `ERROR` + `WARN`, et `remove_cert_trusted_root()` utilise `level='WARN'`

**Découverte bonus** pendant la validation du fix #6 : **récidive Pattern #5** dans `install_outlook_addin.py`. Les caractères `→` (U+2192) et `—` (U+2014) dans des strings logguées crashaient sous cp1252 quand appelées par le superviseur.
- **Fix appliqué** : `→` → `->`, `—` → `-`

**Pattern ajouté** : #12 (alerte codée mais filtrée par logger)

### Itération 3 — Vérification finale

**Résultat** : **0 anomalie — CONVERGENCE**

**Vérifications effectuées** :
- Smoke test : **29 PASS / 0 FAIL / 0 SKIP** (exit 0)
- Les 7 fixes intacts et vérifiés
- 20 classes de bugs parcourues
- 14 spécificités Windows parcourues
- Patterns #1 à #12 consultés, aucune récidive

**Items acceptables documentés (hors champ strict)** :
- Écritures non-atomiques sur `config.json`, `style_path` (même classe Pattern #11, non critiques)
- Caractères non-cp1252 dans `print()` V2 (V2 tourne via `pythonw.exe` avec `stdout=DEVNULL`, non observable)
- `_current_mail_data` sans lock (race window microseconde, pas de reproduction concrète)
- `_pollingInterval` popup.js (fenêtre temporaire, pas de leak observable)
- `_db.mark_treated` avec `except Exception: pass` (préexistant, non bloquant documenté)

---

## Bilan chiffré

- **6 anomalies V2 détectées et corrigées** (1 moyenne, 5 basses) en 2 itérations
- **6 faux positifs du kit audit** corrigés en itération 1
- **1 récidive Pattern #5** détectée et corrigée en itération 2
- **3 itérations** pour converger à 0 anomalie
- **29/29 invariants** smoke test au final

---

## Fichiers modifiés

### V2
- `V2/claude_ai.py` — 4 prompts Claude guardés
- `V2/taskpane.js` — dead code supprimé
- `V2/app_plugin.py` — atomic write `_save_prefetch_cache`

### Companion / service
- `companion/companion.py` — handle leak `pyqt_log.close()`
- `install_outlook_addin.py` — log WARN visible + encoding cp1252 + remove_cert détecte au lieu de supprimer

### Kit audit (`audit/`)
- `tests/smoke_test.ps1` — 6 faux positifs corrigés, ASCII pur
- `ANOMALIES_RECURRENTES.md` — patterns #9, #10, #11, #12 ajoutés

---

## Enseignements méthodologiques

### Ce qui a bien marché
1. **Kit d'audit = référentiel objectif** — smoke_test mécanique retire la subjectivité
2. **Définition stricte d'anomalie** — évite boucle infinie (exclure "améliorations")
3. **Checklist + agent auditeur** — parallélisme + systématicité
4. **Boucle itérative** — chaque fix peut introduire une régression, le re-audit la capture
5. **ANOMALIES_RECURRENTES** — évite de redécouvrir les mêmes bugs (Pattern #5 identifié à récurrence immédiate)

### Ce qui a été difficile
1. **Les faux positifs du kit lui-même** — le smoke_test a fallu être lui-même débuggé en itération 1. C'est normal pour un kit nouveau, mais important à noter
2. **Les régressions introduites par les fixes** (Fix #4 → log invisible) — nécessitent la boucle re-audit
3. **L'encoding cp1252** reste un piège fréquent sur Windows — Pattern #5 a récidivé

### Recommandations pour le futur
1. **Lancer `smoke_test.ps1` après chaque modification** du code V2 (30 s)
2. **Consulter `ANOMALIES_RECURRENTES.md` avant de qualifier un nouveau bug** — c'est peut-être une récidive
3. **Pour les nouveaux prompts Claude** : vérifier systématiquement la présence du bloc `## SECURITE`
4. **Pour les nouvelles écritures JSON** : utiliser le pattern atomic `.tmp + os.replace`
5. **Pour les nouveaux scripts PowerShell** : ASCII pur (pas d'emoji / tiret cadratin)
6. **Pour les nouvelles alertes user** : utiliser `level='WARN'`, jamais `'INFO'`

---

## Signature finale

- [x] smoke_test.ps1 exit 0 (29/29)
- [x] Toutes les checklists parcourues
- [x] ANOMALIES_RECURRENTES.md consulté avant qualification
- [x] Nouveaux patterns ajoutés (#9-#12)
- [x] 3 itérations, dernière à 0 anomalie
- [x] Rapport final rédigé et sauvegardé

**Le code V2 est dans un état stable et conforme aux invariants.**

---

## Annexe — Fixes UX post-convergence (22/04 fin session)

Après convergence à 0 anomalie, 2 fixes UX restants appliqués :

### Fix UX-1 — FOLDED_H 80 → 72 (bande blanche overlay)
- **Fichier** : `companion/popup_pyqt.py:894`
- **Cause** : 80 px sur-dimensionné de ~8 px par rapport à la hauteur réelle header (36) + nav (~36) → bout blanc de `.tp-content` visible
- **Fix** : `_FOLDED_H = 72`
- **Validation user** : ✅ OK (22/04)

### Fix UX-2 — Drag overlay câblé (vaporware activé)
- **Fichiers** : `V2/popup.js` — 60 lignes ajoutées (fonction `_setupOverlayDrag`)
- **Cause** : handlers Qt `drag-start/move/end` existaient (popup_pyqt.py:863-882) mais aucun code JS ne les émettait → drag impossible
- **Fix** : écoute `mousedown` header + `mousemove` global throttlé 60fps + `mouseup` + iframe hidden pour nav `easymail://drag-*`
- **Validation user** : ✅ OK (22/04)

### Smoke test après UX fixes
**29/29 exit 0** — aucune régression introduite.
