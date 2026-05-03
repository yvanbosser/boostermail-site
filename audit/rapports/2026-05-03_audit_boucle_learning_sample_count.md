# Audit ciblé — Boucle infinie `[learning] Re-analyse forcee`

> **Date** : 03/05/2026 (déclencheur : factures Anthropic ~$75/jour)
> **Workflow** : Workflow 4 — Diagnostic bug précis
> **Auditeur** : Claude Opus 4.7
> **Statut** : constat seul, pas de fix appliqué (instruction Yvan « d'abord fait un constat »)

---

## 1. Symptôme observé

Logs OVH `[learning] Re-analyse forcee de XXX (sample_count=0 anormal, rattrapage)` qui se répète à cadence ~45-80 s pour les mêmes contacts, sans `[learning] Profil sauvegarde:` qui suit.

**Échantillon 24h** :
- `4 126` appels Anthropic API
- `24 881` re-analyses de profils contacts (`[learning] Re-analyse|Premiere`)
- `cam***@acceo.eu` re-analysé `1 916×` en 24h (1× toutes les ~45 s)
- 9 autres contacts re-analysés `1 913–1 916×` chacun

---

## 2. Recherche pattern existant

Pattern proche identifié dans `audit/ANOMALIES_RECURRENTES.md` :

- **Pattern #2 — Patch-on-patch sans audit de l'existant** : la branche « rattrapage sample_count=0 » a été ajoutée le 30/04 PM (commentaire ligne 12542) sans vérifier les paths qui CRÉENT sample_count=0 ni la condition d'arrêt.
- **Pattern #3 — Exception swallowing silencieux** : pour `julien@solaris-gestion.fr` et `yvan.bosser@gmail.com`, l'analyse Claude semble échouer silencieusement (pas de `Profil sauvegarde:`, pas de `logger.error` non plus dans les logs).

Pas de pattern strict nouveau, mais **récidive de Pattern #2 + Pattern #3 combinés**.

---

## 3. État système

### 3.1 DB (live OVH `V2/boostermail.db`)

```
Total profils : 115
Profils avec sample_count=0 : 33

Décomposition :
  - 31 contacts SANS aucun mail envoyé (sent_mails=0)
    → noreply@*, no-reply@*, mailer-daemon, banques, etc.
  - 2 contacts AVEC sent_mails > 0 (vrais contacts) :
      julien@solaris-gestion.fr           sent=51   recv=35
      yvan.bosser@gmail.com               sent=266  recv=217
```

### 3.2 Logs (séquence type)

```
15:02:21 Re-analyse forcee de qua***@coaxis.com (sample_count=0 anormal, rattrapage)
                                                                ↑ pas de "Profil sauvegarde" qui suit
15:03:06 Re-analyse forcee de qua***@coaxis.com (sample_count=0 anormal, rattrapage)
                                                                ↑ 45 s plus tard, re-déclenchée
```

Comparaison avec un contact normal (sample_count > 0) :

```
15:02:11 Re-analyse de cam***@acceo.eu (mail #3)
15:02:16 Profil sauvegarde: cam***@acceo.eu — fournisseur, vouvoiement   ✅
```

---

## 4. Reproduction code (chaîne causale)

### 4.1 Caller principal — `_continuous_speculation_loop`

`V2/app_plugin.py` ligne 1503-1517 (commentaire « P0.2 fix 24/04 ») :

```python
unique_senders = list({_normalize_email(m.get('from_email')) for m in mails ...})
def _analyze_batch(senders):
    for em in senders:
        try:
            _maybe_analyze_contact(em)  # ← appelé sur chaque from_email
        except Exception as _e:
            logger.debug(...)
        time.sleep(0.5)
threading.Thread(target=_analyze_batch, ...).start()
```

→ chaque cycle de polling (~45-80 s) scanne tous les from_email du `_warmup_cache` (~75 mails) et appelle `_maybe_analyze_contact` pour chacun.

### 4.2 Bypass du filtre schedule — `_maybe_analyze_contact`

`V2/app_plugin.py` ligne 12552-12555 (commentaire « Fix 30/04 PM » — Pattern #2) :

```python
if existing.get('sample_count', 0) == 0:
    logger.info(f"[learning] Re-analyse forcee de ... (sample_count=0 anormal, rattrapage)")
elif not _should_analyze_contact(mail_count):
    return   # ← path normal qui économise l'API
else:
    logger.info(...)
```

→ quand `sample_count == 0`, le filtre `_should_analyze_contact` (schedule [1,2,3,4,5,7,9,13,17,25,50,100,...]) est **bypassé** : la re-analyse est forcée à CHAQUE cycle.

### 4.3 Return silencieux — pas de log

`V2/app_plugin.py` ligne 12582-12583 :

```python
threads = _db.get_threads_with_contact(contact_email, limit=50)
sent_mails = [t for t in threads if t['direction'] == 'sent']
...
if not sent_mails:
    return    # ← AUCUN log, AUCUN reset de sample_count
```

→ pour les 31 contacts noreply, l'exécution sort ici sans traces, `sample_count` reste à 0, → re-déclenchée au cycle suivant.

### 4.4 Cas `julien@solaris-gestion.fr` & `yvan.bosser@gmail.com`

Ces 2 contacts ont `sent_mails > 0`, donc devraient passer le check ligne 12582. L'analyse Claude est appelée (ligne 12597 `_pb_contact.analyze_contact_profile(...)`).

Si elle réussit, `claude_ai.py` ligne 1256 fait `profile['sample_count'] = sample_count` puis le `save_contact_profile` met à jour la DB.

**Pourtant aucun log `Profil sauvegarde:` n'apparaît pour ces 2 contacts dans les 24h de logs.**

3 hypothèses possibles, à confirmer en session de fix :
- (H1) L'analyse Claude lève une exception qui passe par le `except Exception` ligne 1266-1268 → `logger.error` mais retourne `None`. Mais on devrait voir l'erreur dans les logs.
- (H2) Le `_db.get_threads_with_contact(email, limit=50)` retourne `[]` (mauvais query case-sensitive ou autre) malgré sent=51 ou 266 dans la DB.
- (H3) Une exception silencieuse interne (par exemple `_clean_body`, `json.loads`, validation enum) → `return None` ligne 1156 sans log.

**Pattern #3 candidat** (exception swallowing silencieux).

### 4.5 Trois paths qui créent `sample_count=0`

`V2/app_plugin.py` :

| Ligne | Contexte | Trigger |
|---|---|---|
| 12241 | `_post_send_learning` (greeting/closing modifié) | user envoie un mail avec greeting/closing changé |
| 12735 | `api_analyze_contact` | route POST `/api/analyze_contact` |
| 12802 | `api_recalibrate_contacts` | route POST `/api/recalibrate_contacts` (batch) |

→ ces 3 paths sont **volontaires** (rattrapage). Le bug n'est PAS dans la création, mais dans **l'absence de garde de sortie de boucle**.

---

## 5. Coût réel imputable au bug

### 5.1 Bruit (31 contacts piégés sans appel Claude)

```
31 contacts × 1080 cycles/jour ≈ 33 480 logs/jour
                                + N requêtes SQL `get_threads_with_contact`
                                + 31 × 0.5 s sleep = 15 s/cycle CPU
```

**Coût Claude** : 0 (return early avant appel API).
**Coût indirect** : pollution logs (~70% du volume `[learning]`) + CPU/DB.

### 5.2 Vraies boucles Claude (2 contacts piégés)

```
2 contacts × 1080 cycles/jour = 2 160 appels Claude/jour
            × prix moyen analyze_contact ~$0.02/appel
            ≈ ~$43/jour SI l'analyse passait normalement
```

**Mais l'analyse semble échouer silencieusement** (pas de `Profil sauvegarde:` dans les logs). Donc le coût réel est probablement bien plus faible que 2 160 appels (l'analyse `return None` au prompt builder peut-être avant de lancer le call API, à confirmer).

### 5.3 Cause majeure de la facture $75/jour ?

**Le bug `sample_count=0` n'est probablement pas le coupable principal** des $75/jour observés. Les autres sources probables (à investiguer en session séparée) :

- **Multiples restarts du service** ce weekend (~5-6 restarts pour les fixes audit, Tier DB, recherche live) → chaque restart re-analyse les 76 mails du warmup avant le fix A2 de hier soir
- **Commis Haiku BG `[unified]`** sur tous les mails au warmup (avant fix A2 d'hier)
- **Re-analyses normales** des contacts qui passent le schedule (`Premiere analyse` / `Re-analyse de`) — ces vrais appels Claude sont nombreux
- **Routes user** (generate_reply, refine_reply) appelées pendant les tests live

À comparer avec le breakdown réel de la console Anthropic (https://console.anthropic.com/settings/usage par modèle / par jour).

---

## 6. Anomalies à corriger (à valider Yvan avant fix)

| # | Sévérité | Anomalie | Fix proposé |
|---|---|---|---|
| **B1** | 🔴 HIGH | 31 noreply piégés sample_count=0 sans sortie | Ajouter dans `_maybe_analyze_contact` un skip noreply (parité fix A3 commis) ; OU mettre `sample_count = -1` (sentinel "non analysable") après échec ; OU stocker une `last_attempt_at` et cooldown 24 h |
| **B2** | 🔴 HIGH | 2 contacts (julien, yvan@gmail) bouclent sans `Profil sauvegarde:` ni erreur visible | Investigation H1/H2/H3 ; ajouter `logger.error` explicite dans tous les `return None` de `analyze_contact_profile` |
| **B3** | 🟡 MEDIUM | Branche `sample_count=0` bypasse le filtre schedule SANS limite | Ajouter un cooldown : 1 re-analyse forcée par contact / 24 h max (champ `last_force_at`) |
| **B4** | 🟢 LOW | Pas de monitoring du nombre de re-analyses par contact | Compteur Sentry ou métric `learning_force_count` |

---

## 7. Recommandations

### 7.1 Fix court (30 min)
- Skip noreply dans `_maybe_analyze_contact` (B1) → résout 31/33 cas immédiatement
- Cooldown 24 h sur `Re-analyse forcee` (B3) → résout les 2 cas restants même si l'analyse échoue

### 7.2 Fix structurel (2-3 h)
- Investiguer pourquoi julien & yvan@gmail échouent silencieusement (B2) — debug en local avec un mock
- Ajouter une métric de monitoring Sentry « learning loops » (B4) — visibilité long terme

### 7.3 Vérifier la console Anthropic
Pour identifier la VRAIE source des $75/jour, comparer les quantités par modèle :
- Sonnet 4 vs Haiku 4.5
- Tokens input vs output
- Pic horaire (corrèle avec restarts vs usage normal)

→ permet de savoir si le bug `sample_count=0` est marginal (mes calculs) ou majeur.

---

## 8. Conclusion

**Bug confirmé** : 33 profils piégés en boucle de re-analyse forcée toutes les ~45 s. **31** sont du bruit pur (noreply, sortie silencieuse), **2** semblent générer des appels Claude inutiles mais sans log de succès.

**Coût direct estimé du bug** : faible (probablement < 10% de la facture).
**Coût indirect** : pollution logs majeure (~70% du volume `[learning]`), DB load constante, mauvaise observabilité.

**Cause systémique** : Pattern #2 récidive — la branche « rattrapage sample_count=0 » a été ajoutée sans condition d'arrêt ni audit des paths qui peuvent créer un sample_count=0 permanent.

Le fix B1 + B3 (1 h cumulée) éliminerait 100% du bruit + cap le coût Claude à 1 appel/jour/contact max.

---

## 9. Fichiers concernés

- `V2/app_plugin.py` lignes 1503-1517 (caller BG)
- `V2/app_plugin.py` lignes 12529-12631 (`_maybe_analyze_contact`)
- `V2/app_plugin.py` lignes 12241, 12735, 12802 (les 3 paths qui créent sample_count=0)
- `V2/claude_ai.py` lignes 1130-1268 (`analyze_contact_profile`)
- `V2/database.py` lignes 1310-1399 (`save_contact_profile`)
