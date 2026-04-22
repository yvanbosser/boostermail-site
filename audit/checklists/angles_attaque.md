# Checklist — 10 angles d'attaque

> **Usage** : balayage **obligatoire** lors d'un audit complet. Un audit qui n'a pas parcouru ces 10 angles n'est pas un audit complet.

---

## Angle 1 — Sécurité

| Point | Questions à se poser |
|---|---|
| Secrets | Aucun secret hardcodé ? Aucune clé dans les logs ? Config dans `.gitignore` ? |
| Auth | OAuth flow correct ? Refresh token géré par MSAL ? Logout complet ? |
| TLS | Cert valide + SAN complète ? Min TLS 1.2 ? Pas de renégociations suspectes sous charge ? |
| XSS | Tous `innerHTML` avec source externe sont `_escapeHtml()` ? |
| Prompt injection | Prompts Claude ont des gardes explicites contre les pseudo-instructions dans les mails ? |
| SQL injection | Toutes queries utilisent `?` placeholders ? |
| CSRF | POSTs critiques protégés (CORS strict, origin check) ? |
| IDOR | Routes `/api/something/<id>` vérifient que l'user a accès à cet id ? |
| Data leak | Body mail jamais envoyé à un tiers non attendu ? |

**Fichiers à scruter** : `V2/auth_microsoft.py`, `V2/core/auth_base.py`, dialog.js (escape), prompts Claude, `V2/database.py`

---

## Angle 2 — Performance

| Point | Questions |
|---|---|
| Latence baseline | `/api/status` < 500 ms ? |
| Latence dialog load | `[full-load]` < 200 ms en logs popup_pyqt ? |
| Spec Claude ready | Dialog ouvert avec spec prête = réponse instantanée affichée ? |
| Cache hit rate | Logs `instant_reply HIT/MISS` : ratio HIT raisonnable sur contacts connus ? |
| Warmup non-bloquant | V2 répond pendant warmup ? |
| Batch Haiku résumé | 50 mails en 5 batches de 10 = combien de temps ? |
| Prefetch parallèle | 5 threads prefetch en // ou sériel ? |
| SSE throughput | Dialog reçoit chunks sans buffer ? |

**Commandes utiles** :
```bash
curl -w "@curl-format.txt" -o /dev/null -s https://localhost:3443/api/status
```

---

## Angle 3 — UX

| Point | Questions |
|---|---|
| Feedback visuel | User voit un état (loading / done / error) à chaque action ? |
| Temps perçu | Actions critiques < 2s, sinon feedback intermédiaire ? |
| Erreurs parlantes | Messages d'erreur compréhensibles (pas "HTTP 500" nu) ? |
| Reprise sur erreur | User peut retenter facilement ? |
| Pas de blocage | Clic possible même si backend lent (via timeout + feedback) ? |
| Cohérence visuelle | Badge template / draft / préemptif visibles et distinguables ? |
| Overlay pratique | Drag possible ? Fold / unfold marche ? Taille canonique ? |
| Dialog UX | Placeholder pendant Claude streame ? Pas de zone vide mystérieuse ? |

---

## Angle 4 — Spécificités Windows OS

Voir `specificites_windows.md` pour le détail complet.

### Résumé
- IPv6 vs IPv4 `localhost`
- cp1252 console encoding
- WebView2 cache / cache invalidation
- Outlook OOM Guardian (popup 10 min)
- Cert Trusted Root (popup de confirmation)
- Registry `HKCU\Wef\Developer` (sideload addin)
- Process management (orphan zombies)
- schannel TLS quirks

---

## Angle 5 — Cache / Data lifecycle

| Point | Questions |
|---|---|
| Cohérence cross-cache | Si `_reply_cache[X]` purge, est-ce que `_prefetch_cache[X]` purge aussi ? |
| Invalidation événementielle | Mail delete / archive / classify → tous caches purgés ? |
| TTL vs événement | Conflit entre TTL (48h prefetch) et purge événementielle ? |
| Orphans | Mails supprimés dans Outlook → orphans dans DB ? Cleanup ? |
| Persistance | `prefetch_cache_v2.json` sauvé et rechargé correctement ? Sur kill -9 ? |
| Idempotence caches | 2 requêtes simultanées pour même mail ne créent pas 2 entrées ? |
| Hit rate monitoring | Logs visibles pour mesurer ? |
| Staleness | Si mail edité (rare), résumé DB à jour ? |

**Fichiers** : `app_plugin.py` (_prefetch_cache, _reply_cache, _warmup_cache, _c_keyword_cache), `database.py` (save_*, get_*, has_*)

---

## Angle 6 — Réseau / communication inter-process

| Point | Questions |
|---|---|
| Protocole | HTTP / HTTPS / SSE cohérents entre composants ? |
| CORS | Origines whitelistées correctement ? Pas `*` |
| Timeouts | Tous les fetch ont un timeout ? Adapté (3s pour status, 30s pour send) ? |
| Retry | Retry automatique sur 5xx / network ? Backoff ? |
| Connexions ouvertes | Pas de socket leak (pattern #6) ? |
| IPv4 vs IPv6 | Cohérent partout ? Pas de `localhost` hardcodé côté serveur ? |
| Companion ↔ V2 ↔ popup_pyqt | Flux bien défini ? |
| SSE | Événements broadcast OK ? Clients lents non bloquants ? |

---

## Angle 7 — Data integrity / intégrité

| Point | Questions |
|---|---|
| DB integrity | `PRAGMA integrity_check` OK ? |
| Transactions | Critical writes dans transactions ? Rollback sur erreur ? |
| Migrations | Schema migrations idempotentes ? |
| Backup | Stratégie de backup / recovery claire ? |
| FK constraints | Si pas de FK, orphans possibles — documenté ? |
| Unique constraints | Clés primaires qui matchent la logique métier ? |

---

## Angle 8 — Idempotence

| Point | Questions |
|---|---|
| Send mail | Idempotent via `client_request_id` UUID ? |
| Delete mail | Si déjà supprimé, retourne 200 ? Pas d'erreur ? |
| Classify mail | Deux classify identiques n'ajoutent qu'une ligne DB ? |
| Save draft | Idempotent par message_id ? |
| Install addin | Idempotent (certutil `-f`, `INSERT OR REPLACE`, etc.) ? |
| Warmup | Ne refait pas les résumés déjà en DB (`has_mail_summary`) ? |

---

## Angle 9 — Observabilité

| Point | Questions |
|---|---|
| Logs visibles | Actions critiques loggées avec context (msg_id, user, durée) ? |
| Niveaux log | INFO / WARNING / ERROR utilisés correctement ? |
| Log files | `boostermail.log`, `popup_pyqt.log`, `addin_debug.log` présents ? |
| Stderr V2 | Erreurs Python capturées quelque part ? |
| Metrics | Compteurs hits/misses/errors visibles ? |
| Alertes | Conditions anormales génèrent un log WARNING ? |
| Debug endpoints | `/api/status`, `/api/metrics` retournent info utile ? |

---

## Angle 10 — Déploiement / résilience

| Point | Questions |
|---|---|
| Cold start | Premier démarrage (no cache) fonctionne ? |
| Warm start | Reboot PC → tout se relance automatiquement ? |
| Crash recovery | Si V2 crash, superviseur relance dans < 60s ? |
| Outlook down | V2 + Companion + popup_pyqt survivent ? |
| Réseau down | Backend continue de tourner (on HTTPS local) ? |
| Graph unavailable | Mode Dégradé fonctionne ? |
| Update git auto | `_check_git_updates` ne casse pas l'état courant ? |
| Rollback | Si une release casse, rollback facile ? |
| Orphans proc | Pas de processus zombie après kill / restart ? |

---

## Règle meta

**À chaque audit COMPLET, je coche tous les points de ces 10 angles.**

**À chaque audit THÉMATIQUE, je parcours UNIQUEMENT les angles pertinents :**
- Audit sécurité → angles 1, 4
- Audit perf → angles 2, 6
- Audit UX → angles 3, 4
- Audit data → angles 5, 7, 8
- Audit prod → angles 9, 10

**Un point laissé sans réponse = anomalie potentielle non évaluée = audit incomplet.**
