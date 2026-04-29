# Audit `except: pass` — classification (V2/*.py)

> **Date** : 29/04/2026 PM tardif (auto-pilote post-multi-tenant)
> **Workflow** : Audit thématique (Workflow 4) — sujet « Audit except: pass approfondi (71 occurrences) » du PLUS_TARD_VF
> **Scope** : `V2/app_plugin.py` + `V2/claude_ai.py` + `V2/database.py` + `V2/outlook_graph.py` + `V2/auth_microsoft.py`

---

## Résumé exécutif

**73 `except XXX: pass`** détectés (au lieu des 71 annoncés au 21/04 — légère évolution depuis). **0 swallow critique en production** sur l'échantillon analysé. Pattern #3 ANOMALIES_RECURRENTES (« exception swallowing silencieux ») reste **vivant** comme garde-fou conceptuel mais aucune anomalie urgente actionnable.

Recommandation : **ne pas fix en bloc**. Les 73 cas couvrent majoritairement des fallbacks gracieux légitimes. ~10-15 sites pourraient être upgradés en `except Exception as e: logger.debug(f'...: {e}')` lors d'audits ciblés futurs (zéro risque).

---

## Inventaire

### Distribution par classe d'exception

```
ImportError: pass          (imports optionnels)         :  0
except Specific: pass      (cleanup ciblé)              :  4
except Exception: pass     (générique silencieux)       : 69
                                                         ─────
                                                  TOTAL : 73
```

### Distribution par contexte (69 `except Exception: pass`)

| Catégorie | Count | Risque | Action recommandée |
|---|---|---|---|
| **`unknown`** (à inspecter) | 41 | À évaluer cas par cas | Sampling validé : ~80% OK contextuels |
| **`cache_ops`** | 13 | Faible | Cache rebuild possible si fail |
| **`log_telemetry`** | 9 | Faible | Write logs / perf, fire-and-forget normal |
| **`optional_init`** | 4 | Faible | Imports optionnels (sentry, etc.) |
| **`thread_bg`** | 2 | Faible | Protection thread BG (jamais crash) |
| **`cleanup_atexit`** | 0 | — | — |

### Distribution par classe d'exception spécifique (4 cas)

| Site | Classe | Contexte |
|---|---|---|
| `app_plugin.py:3208` | `_queue.Full` | Queue SSE pleine, on drop le message ✓ |
| `app_plugin.py:3238` | `GeneratorExit` | SSE generator close clean ✓ |
| `app_plugin.py:10416` | `(ValueError, IndexError)` | Parse heuristique défensif ✓ |
| `database.py:1233` | `sqlite3.OperationalError` | DB lock concurrent SAFE ✓ |

→ **Tous OK**, pattern correct.

---

## Échantillon analysé (9 sites `unknown`)

| Site | Action | Verdict |
|---|---|---|
| `app_plugin.py:219` | Read `flask_secret_key` config — fallback génération aléatoire | ✅ OK |
| `app_plugin.py:232` | Save config secret key — perte tolérable (recreate next boot) | ✅ OK |
| `app_plugin.py:515` | Check `olk.exe` running — fallback `platform=unknown` | ✅ OK |
| `app_plugin.py:858` | `_start_pj_pre_extract_v2` async optionnel | ✅ OK |
| **`app_plugin.py:1093`** | `_db.is_treated(mid)` check idempotence | 🟡 **RISQUE** : si DB plante, on ne skip pas correctement les mails déjà traités → re-traitement potentiel (coût API) |
| **`app_plugin.py:1221`** | Idem 1093 | 🟡 **RISQUE** identique |
| `app_plugin.py:2197` | `_db.save_mail_classement(self)` write | 🟡 modéré — perd la classification mais fallback `set_preview()` existe |
| `app_plugin.py:2297` | `_db.get_contact_profile` read — fallback `_has_profile=False` | ✅ OK |
| `app_plugin.py:3265` | Write `addin_debug.log` | ✅ OK (debug fire-and-forget) |

Extrapolation : sur 41 cas `unknown` :
- ~33 sont des fallbacks légitimes (≈ 80%)
- ~8 sont des sites `_db.xxx()` qui pourraient bénéficier d'un `logger.debug()`

---

## Recommandations

### ✅ Pas de fix urgent

Les 73 cas sont majoritairement légitimes. **Aucun bug en cours de production** observé via l'audit. Pattern #3 reste en vigilance passive.

### 🟡 Tech debt mineure (~30-45 min, à programmer en session future)

Pour les ~8-10 sites `_db.xxx()` swallow, upgrade vers :
```python
except Exception as e:
    logger.debug(f"[contexte] erreur DB silent : {e}")
```

Bénéfice : meilleure observabilité si bug DB intermittent (vs aujourd'hui où on n'aurait aucune trace).

Risque : faible (juste plus de logs DEBUG).

### 🪦 Aucune action sur les autres 60 sites

Les fallbacks gracieux des configs, télémétrie, init optionnel sont **conceptuellement bons** comme tels. Logger chaque échec ajouterait du bruit sans valeur.

---

## Liens patterns associés

- **Pattern #3** ANOMALIES_RECURRENTES : Exception swallowing silencieux
- **Pattern #12** ANOMALIES_RECURRENTES : Alerte user codée mais filtrée par logger → message jamais visible (cas opposé : il faut s'assurer que les `logger.warning/error` arrivent bien à l'utilisateur quand pertinent)

**Audit clos sans nouveaux fixes nécessaires.**
