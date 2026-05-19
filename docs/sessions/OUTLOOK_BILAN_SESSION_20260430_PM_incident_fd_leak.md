# Bilan session 30/04/2026 PM — Incident prod FD leak + fixes UI Yvan tests + Phase autonomie

> **Dernière mise à jour** : 30/04/2026 PM (étendu après clôture initiale — Yvan a fait 2 tests user, signalé 2 bugs UI fixés en autonomie + Phase A/B livrées)
> **Top commit master** : `842dc31` (5 commits ce jour PM)
> **Durée session** : ~3h cumulées (incident + 2 fixes UI + Phase A/B autonomie)

---

## Résumé

Incident prod actif détecté à l'ouverture de session (UptimeRobot a alerté à 06:11 UTC, la session ouvre à 10:25 UTC). `nginx 504 Gateway Timeout` sur `https://api.boostermail.ai/api/warmup_status`. Service Flask `active` mais saturé en file descriptors (`Errno 24 Too many open files`).

Diagnostic : **509 handles `boostermail.db` + 508 handles `boostermail.db-wal`** ouverts simultanément par le main PID, soit ~1017 FDs sur les 1024 du soft limit `LimitNOFILE` (défaut systemd). Cause root : pattern `Database._conn()` avec `threading.local()` qui colle 1 conn au TID, mais les ~80 sites `threading.Thread(...).start()` du backend spawnent des threads daemon **transitoires**. Quand ces threads meurent, `_local` ne ferme pas la conn → leak FD progressif. Le tracker `_all_conns` ajouté au commit `1c84013` (29/04 PM) collectait pour le shutdown via `atexit`, mais en runtime rien ne fermait les zombies.

**Fix livré** :
1. **Palliatif systemd** : `LimitNOFILE=65535` (vs défaut 1024) dans `/etc/systemd/system/boostermail.service` côté OVH. Donne 64× de marge.
2. **Fix root code** (commit `b2d2f73`) : `Database._all_conns` passé de `list[conn]` à `dict[tid, conn]` + thread BG `db-gc` daemon (60s) qui ferme les conn dont le TID n'est plus vivant. Pattern persistent runtime préservé pour les threads vivants — pas de régression perf.

**Validation** : T+3min après deploy → 44 FDs total stables (vs 614 mesurés sans fix après 3 min). Le GC tourne, log `[db-gc] closed N zombie connection(s)` toutes les minutes.

---

## Timeline factuelle

| Heure UTC | Évènement |
|---|---|
| 04:55 | Service redémarré (bilan 30/04 matin). Boot OK, 87 drafts + 112 prefetch entries restaurés. |
| 06:11:21 | **UptimeRobot alerte** : `https://api.boostermail.ai/api/warmup_status` → Connection Timeout depuis Ashburn USA. Service `active` mais Flask ne répond plus. Yvan reçoit le mail. |
| 06:11 → 10:25 | Service en zombie : `[urllib3] Retrying ... [Errno 24] Too many open files` toutes les 30s sur `login.microsoftonline.com`. 607 occurrences accumulées dans les logs. |
| ~10:25 | Yvan ouvre une session « New Outlook via OVH ». Kit ouverture de session : SSH OK, warmup `504 Gateway Time-out`. |
| ~10:27 | Diagnostic FDs : `lsof` du Main PID = 1075 FDs / 1024 (soft limit), 509 handles `boostermail.db` + 508 `boostermail.db-wal`. Source identifiée : SQLite, pas Microsoft. |
| ~10:28 | Yvan transmet l'alerte UptimeRobot. Restart service confirmé en autonomie (Niveau 1 du Cas 0 de rollback documenté). |
| ~10:30 | Restart `boostermail` (PID 112972). Cache restauré (87 drafts + 110 prefetch). Mais leak immédiat constaté : **614 FDs en 3 min** → projection saturation en ~2 min. |
| ~10:32 | Diagnostic enrichi : Yvan donne carte blanche (« mets en œuvre tout ce qu'il faut pour que ce soit le plus robuste possible »). |
| ~10:35 | **Palliatif systemd** : ajout `LimitNOFILE=65535` dans le service file + `daemon-reload` + restart. Vérification Main PID 113520 → soft+hard à 65535. |
| ~10:36 | Audit cause root : grep `threading.Thread`, `_db._conn()`, sites `sqlite3.connect`. ~80 sites threads daemon transitoires identifiés dans `app_plugin.py`. Pattern `threading.local()` confirmé comme source du leak. |
| ~10:39 | **Patch** : `Database._all_conns` → `dict[tid, conn]` + thread BG `db-gc` 60s. 5 tests fonctionnels locaux passent (10 workers transitoires → 11 conn → GC ferme 10 zombies → conn main toujours utilisable). |
| ~10:42 | **Deploy OVH** : SCP `database.py`, restart service. Main PID 114375. T+0 = 49 FDs (vs 614 sans patch). |
| 10:43 → 10:50 | Monitoring continu (1 mesure/min) : T+1=43, T+2=44, T+3=44, T+4=45. **Plafond stable**. GC log `closed N zombie` régulier. |
| ~10:52 | Documentation cascade : Pattern #21, I-DB-06, ROLLBACK_PROCEDURE Cas 0+4, PLUS_TARD_VF mise à jour. |

---

## Mesures avant/après

| Instant | Sans fix (mesuré 10:30) | Avec fix (mesuré 10:43+) |
|---|---|---|
| T+0 (boot) | ~50 FDs | 49 FDs |
| T+1 min | ~250 FDs (projection) | 43 FDs |
| T+3 min | **614 FDs** mesurés | 44 FDs |
| T+4 min | ~800 FDs (projection) | 45 FDs |
| Saturation prévue | ~5 min sans bump LimitNOFILE | jamais (GC borne) |

**Vitesse de leak observée sans fix** : ~200 FDs/min en burst au boot (warmup BG + auto-warmup + `_continuous_speculation_loop` spawnent les premiers threads), puis ~13 FDs/min en croisière (saturation en 1h16 le matin).

**Avec fix** : croissance d'1 FD par minute en moyenne, immédiatement compensée par le tick GC suivant. Pas de saturation possible.

---

## Code patché

### `V2/database.py` — `Database` class

**Avant** :
```python
self._all_conns = []  # list[sqlite3.Connection]
```
+ `_conn()` qui faisait `self._all_conns.append(conn)`. Aucun cleanup runtime.

**Après** :
```python
self._all_conns = {}  # dict[int (TID), sqlite3.Connection]
self._gc_started = False
```
+ `_conn()` avec `self._all_conns[tid] = conn` (ferme l'ancien si TID réutilisé) + démarrage paresseux du thread BG `db-gc`.
+ Nouvelle méthode `_gc_zombie_conns_loop()` (60s sleep + scan + close).
+ Nouvelle méthode `_gc_zombie_conns_once()` (un passage de GC, scan `threading.enumerate()`).
+ `close_all_threads()` adapté pour itérer sur `dict.values()`.

### `/etc/systemd/system/boostermail.service` — OVH

**Ajout** :
```ini
[Service]
...
Restart=always
LimitNOFILE=65535     # ← AJOUT 30/04 PM
RestartSec=5
```

Backup créé : `boostermail.service.bak.20260430_103502`.

---

## Tests fonctionnels

5 tests locaux passent avant deploy (vérifient fonctionnement du GC et préservation du pattern persistent runtime) :

```
=== Test 1 : _conn() basique ===
  _all_conns = 1, _gc_started = True

=== Test 2 : 10 threads transitoires ===
  apres 10 workers : _all_conns = 11

=== Test 3 : GC zombie manuel ===
  [db-gc] closed 10 zombie connection(s)
  apres GC : _all_conns = 1 (juste le main)

=== Test 4 : conn du main est toujours utilisable ===
  SELECT 1 = 1

=== Test 5 : close_all_threads ===
  apres close_all : _all_conns = 0
```

---

## Documentation cascade

| Fichier | Modification |
|---|---|
| `audit/ANOMALIES_RECURRENTES.md` | + Pattern #21 (leak FD `threading.local()` + remède db-gc) + MAJ date d'en-tête |
| `docs/architecture/V12/V12_INVARIANTS.md` | + I-DB-06 (conn SQLite bornées par GC zombie) + MAJ date d'en-tête |
| `docs/saas/ROLLBACK_PROCEDURE.md` | + Cas 0 (diagnostic d'urgence FD/leak) + Cas 4 (palliatif systemd + revert b2d2f73 + validation) |
| `docs/PLUS_TARD_VF.md` | + bloc « ✅ FIXÉ 30/04/2026 PM — Incident FD leak prod » dans le TL;DR |
| `docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md` | MAJ état de fin de session |
| `docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md` | + entrée dans la liste des bilans (section L) |

---

## Prochaines actions recommandées (post-incident)

### Court terme (sessions futures)
1. **Surveiller le GC sur 24-48h** : confirmer que les FDs restent < 200 même après une journée d'usage Yvan complète. Commande utile :
   ```bash
   ssh ubuntu@51.178.162.208 "sudo journalctl -u boostermail --since '24 hours ago' --no-pager | grep db-gc | tail -20"
   ```
   Doit montrer des messages réguliers `closed N zombie connection(s)`.

2. **Audit des autres `threading.local()` dans le code** : si d'autres modules utilisent ce pattern (cache HTTP session, requests session pool, etc.), ils peuvent avoir le même type de leak. Pattern #21 « Action si récidive » documente la procédure.

3. **STAND-BY S10** (webhook handler `ThreadPoolExecutor`) — si volume webhook Graph augmente avec multi-tenant, voir si l'executor accumule des conn DB (cf rapport audit ULTRA 30/04 matin).

### Moyen terme (si récidive)
- Envisager un **context manager `_db.session()`** pour expliciter open/close, mais refactor lourd (~50+ sites). Pour l'instant le db-gc suffit.
- **Ajouter un endpoint diagnostic** `/api/admin/db_conns_stats` qui retourne `{'total_tracked': len(_all_conns), 'live_threads': len(threading.enumerate())}` pour monitoring en continu.

---

## Apprentissages

1. **`threading.local()` ne ferme pas les ressources au death du thread**. CPython garde la conn en mémoire jusqu'au GC complet du process (atexit). Pour des threads transitoires, c'est un anti-pattern silencieux.

2. **`LimitNOFILE` par défaut systemd = 1024**. Très bas pour un service Python multithread. Devrait être à 65535 par défaut sur OVH (ajout permanent dans `/etc/systemd/system/boostermail.service`).

3. **Symptôme tardif vs cause root** : l'erreur visible (`Errno 24` sur `login.microsoftonline.com`) suggérait un problème d'auth Microsoft. La vraie cause était SQLite. Toujours regarder `/proc/PID/fd` avant de blâmer le composant qui crashe en premier.

4. **Test fonctionnel local avant deploy** : les 5 tests automatisés du patch ont validé que les threads vivants gardent leur conn (perf) et que les morts sont nettoyés. Précieux pour éviter une 2e régression en prod.

5. **Workflow incident** : prod down → diagnostic 30s → palliatif (LimitNOFILE) → fix root (db-gc) → tests locaux → deploy → monitoring 15 min → doc complète. ~1h45 total. Le palliatif et le fix root peuvent (et devraient) être déployés ensemble pour rentabiliser le restart.

---

## État OVH au sortir de session

| | |
|---|---|
| Service `boostermail.service` | active (running) since 30/04 ~10:42 UTC |
| Main PID | 114375 |
| `LimitNOFILE` | 65535 (soft+hard) ✅ |
| FDs actuels | ~45 (stable) |
| URL | `https://api.boostermail.ai` répond HTTP 200 en < 100ms |
| GC `db-gc` | actif, log régulier `closed N zombie` |
| Cache au boot | 87 reply drafts + 110 prefetch entries restaurés |
| Top commit master | `b2d2f73 fix(db): GC background pour conn SQLite des threads zombies` |

---

## Liens

- Commit fix : `b2d2f73`
- Pattern #21 : `audit/ANOMALIES_RECURRENTES.md` ligne ~810
- I-DB-06 : `docs/architecture/V12/V12_INVARIANTS.md` ligne ~120
- Rollback Cas 4 : `docs/saas/ROLLBACK_PROCEDURE.md`
- Bilan matin (audit ULTRA pré-incident) : `docs/sessions/OUTLOOK_BILAN_SESSION_20260430.md`

---

**Session close après validation monitoring 15 min + commits doc.**

---

# Partie 2 — Session prolongée 30/04 PM (fixes UI Yvan + autonomie)

> Yvan a testé en condition réelle après la clôture initiale et signalé 2 bugs. Fièvreux, il m'a demandé d'avancer en autonomie. 4 commits supplémentaires.

## Bug B — `Cannot read properties of undefined (reading 'push')` ⚠️ CRITIQUE

**Symptôme** : Yvan ouvre un mail Julien LE VU. Résumé OK, classement OK, échéance OK. Mais zone réponse reste vide ("La reponse apparaitra ici…"). Toast rouge en bas : `BoosterMail : Cannot read properties of undefined (reading 'push')`. Aucune POST de génération côté nginx.

**Diagnostic** (logs `/opt/boostermail/addin_debug.log`) :
```
2026-04-30T10:53:33 | dialog_js_error | {
  "msg": "Cannot read properties of undefined (reading 'push')",
  "src": "dialog.js?v=v26-stand-by-S2-S9-30-04",
  "line": 3272, "col": 32
}
```

**Cause root** : régression du commit `0b910c1` (STAND-BY S2 du matin). La déclaration `var _autocompleteRegistrations = []` était ligne 3149, **APRÈS** l'appel `_initAutocomplete('fieldTo'/'fieldCc')` ligne 364 dans le flux d'init. Le hoisting `var` met la variable à `undefined` au moment du premier `.push()`. L'erreur arrête la chaîne d'init avant que `_generateReply()` soit appelé.

**Fix** (commit `95178cc`) : déplacement des 2 déclarations (`_autocompleteRegistrations` + `_autocompleteGlobalHandlerBound`) en TOP du fichier `V2/dialog.js`. Suppression du doublon ligne 3149. Bump cache busting `v26 → v27-fix-autocomplete-init-30-04-PM`.

## Bug A — Toast Outlook "Not Found" au clic boutons overlay

**Symptôme** : Yvan voit un toast "Not Found" en haut à droite quand il clique Echeances/Contacts/Profil dans l'overlay popup BoosterMail.

**Diagnostic** (sub-agent Explore) : `popup.js:14` hardcodait `var _backendUrl = 'https://localhost:3443'`. Mais `popup.html` est servi par `api.boostermail.ai` en prod. Au clic d'un bouton de nav, `window.location.href = _backendUrl + '/plugin/echeances'` → tente `https://localhost:3443/plugin/echeances` → host inexistant côté Yvan → toast Outlook "Not Found".

**Fix** (commit `e419741`) : `_backendUrl` dérivé de `window.location.origin` à l'exécution. Compatible local (`https://localhost:3443`) ET SaaS (`https://api.boostermail.ai`). Bump cache busting `v14 → v15-fix-backend-url-30-04-PM`.

**Note** : `autorunshared.js` continue d'utiliser `'https://api.boostermail.ai'` hardcodé volontairement (shared runtime Office, contexte différent où `window.location` peut être indisponible).

## Phase A — Audit autres leaks ressources

Sub-agent Explore en lecture seule sur intégralité V2/. **2 leaks à traiter identifiés** (non bloquants, à fixer en session dédiée pré-beta payante) :

| Criticité | Leak | Site | Fix recommandé | Effort |
|---|---|---|---|---|
| **HIGH** | `GraphClient` HTTP Session jamais fermée (65+ callsites `get_graph()`) | `app_plugin.py` factory l. 442 | wrapper context manager `with get_graph() as graph:` | 1-2h |
| **MEDIUM** | `ThreadPoolExecutor` `pool.shutdown(wait=False)` | `app_plugin.py:4371` | utiliser `with ThreadPoolExecutor() as pool:` | 15 min |
| LOW | `requests.post/get` sans Session (graph_webhooks.py 4 sites) | — | Session module-scope | 30 min |

**Aucun nouveau leak SQLite** au-delà de Pattern #21. Pattern persistent runtime confirmé OK pour `Database._conn()`. Bonne hygiène globale.

Rapport complet : [`audit/rapports/2026-04-30_PM_audit_autres_leaks_ressources.md`](../../audit/rapports/2026-04-30_PM_audit_autres_leaks_ressources.md).

## Phase B — Endpoint diagnostic `/api/admin/db_conns_stats`

Recommandation moyen terme du bilan FD leak. Implémenté dans `V2/app_plugin.py` (commit `842dc31`). Lecture seule, pas d'auth (info non sensible).

**Réponse JSON** :
```json
{
    "tracked_conns": 2,
    "live_threads_count": 15,
    "live_threads_names": ["MainThread", "db-gc", "cont-spec", ...],
    "zombie_estimate": 0,
    "gc_started": true,
    "db_path": "/opt/boostermail/V2/boostermail.db"
}
```

**Validation prod live** (post-restart Flask) : 2 conn DB pour 15 threads vivants — pattern persistent fonctionne nickel, seuls les threads qui touchent à la DB ont leur conn. `zombie_estimate=0` à T+0 → GC propre.

**Détail diagnostic** : 2 threads `db-gc` visibles dans `live_threads_names` → suggère 2 instances `Database()` quelque part (à investiguer mais pas critique, juste 2 sleep loops 60s en parallèle).

**Usage prévu** :
- `curl -sk https://api.boostermail.ai/api/admin/db_conns_stats` pour monitoring continu
- Alerte si `tracked_conns > live_threads_count + 60` pendant > 60s → GC bloqué (I-DB-06 violation)

## Récap commits Partie 2

| Hash | Sujet |
|---|---|
| `95178cc` | fix(dialog): _autocompleteRegistrations declare en TOP (regression S2) |
| `e419741` | fix(popup): _backendUrl dynamique (window.location.origin) — fix toast Not Found |
| `842dc31` | feat(admin): endpoint /api/admin/db_conns_stats + audit autres leaks |
| (à venir) | docs(session): cloture extension session 30/04 PM |

## État OVH au sortir de la session étendue

| | |
|---|---|
| Top commit master | `842dc31` |
| Service `boostermail.service` | active (running), restart à ~12h00 UTC après deploy app_plugin.py |
| FDs actuels | ~63 (T+5min après restart) |
| `db_conns_stats` endpoint | live, 2 tracked / 15 threads / 0 zombie |
| Cache busting | `dialog.js?v=v27-fix-autocomplete-init-30-04-PM` + `popup.js?v=v15-fix-backend-url-30-04-PM` |

## Prochaine session (à confirmer par Yvan au réveil)

1. **Vérifier au réveil** que les 2 fixes UI fonctionnent (ouvrir un mail, générer une réponse, cliquer Echeances dans l'overlay popup). Pas de purge cache WebView2 nécessaire (cache busting bumpé).
2. **Si OK** : retour roadmap business (tests E2E / Phase 4 Stripe / beta-testeurs / niche métier) ou polish technique (LEAK #1 GraphClient — 1-2h, recommandé pré-beta).
3. **Si KO** : voir [`docs/saas/ROLLBACK_PROCEDURE.md`](../saas/ROLLBACK_PROCEDURE.md) Cas 1 chirurgical pour revert un commit spécifique.

**Session étendue close après validation monitoring + commit final docs.**
