# Checklist — État des données

> **Ajout 23/04/2026** : catégorie créée après la découverte que 5 jours de
> "complétude mauvaise" étaient dus à une DB V2 vide, invisible aux 10 audits
> code précédents. Les audits applicatifs **doivent** désormais tester
> l'état des données **en plus** de la cohérence du code.

---

## Principe général

Un audit code valide que **les routes répondent, que les fonctions ne plantent pas, que les caches existent**. Mais il ne vérifie PAS que **ces caches contiennent quelque chose**. Un backend peut répondre 200 en servant du vide — et le comportement utilisateur est alors dégradé sans aucune trace d'erreur.

**Règle d'or** : pour chaque cache / table / fichier référencé par le code, poser deux questions :
1. *"Le code sait le lire ?"* (test classique)
2. *"Y a-t-il quelque chose dedans à lire ?"* (test de données)

---

## 1. Tables DB critiques — état attendu

### Tables d'apprentissage utilisateur

| Table | Vide = problème ? | Ce que ça casse si vide |
|---|---|---|
| `contact_profiles` | ✅ oui (si user actif >1 mois) | Tags vouvoiement/confiance invisibles, registre non adapté |
| `threads` | ✅ oui | Contextes A/B/C = 3 searches Graph live à chaque génération (lent) |
| `style_corrections` | 🟡 tolérable au début | Pas d'apprentissage des corrections user |
| `metrics` | 🟡 tolérable | Pas de stats usage |
| `treated_emails` | ✅ oui (si user actif) | Re-proposition de mails déjà traités |
| `folder_cache` | ✅ oui (Mode Complet) | Scan Graph des dossiers à chaque classement |
| `folder_classifications` | 🟡 tolérable au début | Suggestions classement moins bonnes |
| `pj_classifications` | 🟡 tolérable au début | Suggestions PJ moins bonnes |
| `echeances` | 🟡 tolérable | Pas d'échéances suivies (peut être vide légitimement) |
| `mail_summaries` | ✅ oui (si clics BM récents) | Résumé = stream Claude à chaque clic (lent) |
| `email_cache` | ✅ oui (après usage) | Body refetch Graph à chaque ouverture |
| `learned_templates` | 🟡 se construit progressivement | Pas de réponses rapides templates |
| `settings` | ❌ JAMAIS vide | App inutilisable (clés API, fernet, etc.) |

### Tests mécaniques à lancer

```python
import sqlite3
con = sqlite3.connect('V2/boostermail.db')
for table in ['contact_profiles', 'threads', 'style_corrections',
              'metrics', 'treated_emails', 'folder_cache',
              'mail_summaries', 'email_cache']:
    cur = con.cursor()
    cur.execute(f'SELECT COUNT(*) FROM {table}')
    n = cur.fetchone()[0]
    print(f'{table:30s} {n}')
```

---

## 2. Caches en mémoire (perdus au restart V2)

Les caches RAM sont inspectables via `/api/*` routes diagnostiques (si exposées) OU indirectement via les logs :

| Cache Python | Route diag | Indicateur que ça marche |
|---|---|---|
| `_warmup_cache` | `/api/warmup_status` | `loaded >= total` en `done` |
| `_prefetch_cache` | `/api/prefetch_status` | Entries présentes après `message_read` |
| `_reply_cache` | — | Logs `[reply_cache] hit` au fil des clics BM |
| `_c_keyword_cache` | — | Logs `[cache-C]` |
| `_echeance_pre_scan_cache` | — | Logs `[prescan-ech]` |

**Symptôme "cache vide"** : dans les logs V2, absence totale de lignes `hit`, seulement des `miss` ou `fetch fresh`.

---

## 3. Fichiers de cache persistants (survivent au restart)

| Fichier | Rôle | Vide/absent = problème ? |
|---|---|---|
| `V2/prefetch_cache_v2.json` | Prefetch reload au démarrage | ✅ oui, warmup cold |
| `V2/addin_debug.log` | Trace click Outlook addin | 🟡 info utile pour diag |
| `V2/pyqt_dialog.log` | Logs PyQt dialog | 🟡 pour diag |
| `logs/perf/perf_*.json` | Timings dialog 80% | 🟡 empty = pas de mesure possible |
| `C:\EasyMail\popup_pyqt.log` | Log popup_pyqt | ✅ oui si Outlook tourne |

---

## 4. Fichiers de configuration — sanity check

```bash
# config.json doit contenir les 5 clés
python -c "
import json
c = json.load(open('config.json'))
required = ['ANTHROPIC_API_KEY', 'fernet_key', 'microsoft', 'flask_secret_key', 'OPENAI_API_KEY']
missing = [k for k in required if k not in c or not c[k]]
print('MISSING:' if missing else 'OK', missing)
"
```

---

## 5. Modèles Claude utilisés — pas d'EOL silencieux

**Règle absolue** : tout modèle Claude référencé dans le code doit être testé contre l'API avant toute mise en prod.

```python
# Pour chaque modèle dans V2/claude_ai.py et V2/app_plugin.py
import anthropic
client = anthropic.Anthropic(api_key=...)
for model in ['claude-sonnet-4-20250514', 'claude-haiku-4-5', ...]:
    try:
        r = client.messages.create(model=model, max_tokens=5,
                                   messages=[{'role':'user','content':'hi'}])
        print(f'OK  {model}')
    except Exception as e:
        msg = str(e)[:80]
        print(f'FAIL {model} : {msg}')
        # Si 404 / not_found → modèle deprecated → corriger code
```

**Historique** : `claude-3-5-haiku-20241022` retiré 19/02/2026 → 404 silencieux pendant 2 mois → résumés vides en DB. Si ce test avait existé, détection immédiate.

---

## 6. Cohérence proto ↔ V2 (si les 2 coexistent)

Si `C:\EasyMail\boostermail.db` (proto) existe ET `C:\EasyMail\V2\boostermail.db` (V2) existe :

| Comparaison | Attendu |
|---|---|
| Nombre de `contact_profiles` proto vs V2 | V2 ≥ proto (ou égal post-migration) |
| Nombre de `threads` | V2 ≥ proto |
| Nombre de `style_corrections` | V2 ≥ proto |
| Settings (anthropic_api_key, fernet_key, user_name) | Identiques |

**Divergence** suspecte : proto plein + V2 vide → migration manquante (cf. `V2/migrate_proto_to_v2.py`).

---

## 7. Signes visuels de "DB vide" côté user

Si un utilisateur signale :
- "Les tags vouvoiement ne s'affichent plus"
- "C'est plus lent qu'avant"
- "Je ne retrouve pas mes contacts"
- "Le résumé est toujours vide"
- "Les réponses Claude démarrent à chaque fois de zéro"

→ **Premier réflexe** : compter les rows de chaque table DB V2. Si plusieurs tables sont à 0, **c'est un défaut de données**, pas un bug de code.

---

## 8. Règle meta — avant TOUT audit applicatif

Faire d'abord ces 3 commandes dans l'ordre :

```bash
# 1. Rows par table
python -c "
import sqlite3
con = sqlite3.connect('V2/boostermail.db')
for t in ['contact_profiles','threads','style_corrections','metrics','treated_emails','folder_cache','mail_summaries','email_cache','learned_templates','settings']:
    cur = con.cursor()
    cur.execute(f'SELECT COUNT(*) FROM {t}')
    print(f'{t:30s} {cur.fetchone()[0]}')
"

# 2. Modèles Claude OK (cf section 5)

# 3. Fichiers cache présents
ls -la V2/prefetch_cache_v2.json logs/perf/*.json 2>&1 | head
```

**Si une anomalie sort de ces 3 commandes, la priorité est là AVANT de chercher dans le code.**

---

## 9. Historique des bugs "données" rencontrés

| Date | Symptôme | Cause racine | Détection |
|---|---|---|---|
| 18/04 → 23/04 | "Complétude mauvaise", tags absents, résumés vides | DB V2 pas migrée depuis proto (0 profils, 0 threads) | Diag manuel SELECT COUNT |
| 19/02 → 23/04 | 9 résumés `points=[]` empilés en DB | Modèle Haiku EOL 19/02 → 404 silencieux | Test direct API |

---

## 10. Pour ajouter une catégorie "données" à un nouveau audit

Template à copier dans le rapport d'audit :

```markdown
## État des données

### Comptages tables DB V2
- contact_profiles : X
- threads : X
- mail_summaries : X
- (etc.)

### Résumés vides en DB
- Ratio points=[] & actions=[] / total : X%

### Modèles Claude actifs
- [x] claude-sonnet-4-20250514 : OK
- [x] claude-haiku-4-5 : OK

### Cohérence proto vs V2
- contact_profiles : proto=X, V2=Y (diff=Z)
- threads : proto=X, V2=Y (diff=Z)

### Anomalies détectées
- [ ] ...
```
