# Observabilité — alertes Phase 6 audit remediation 08/05/2026

> **Source** : plan `audit/rapports/2026-05-08_audit_remediation_PLAN.md` Phase 6.2
> **Cible** : configuration côté OVH `api.boostermail.ai` (journalctl + Sentry/Loki)
> **Statut** : à activer post-déploiement

---

## Logs émis par le code Phase 1-6

Tous ces logs sortent vers `journalctl -u boostermail` (logger `easymail.claude` ou root). Ils sont structurés pour parsing facile.

| Log | Niveau | Émis quand | Phase |
|---|---|---|---|
| `[pii-redacted] count=N patterns=siret,phone,...` | INFO | PII détectée et redactée dans Blocs A/B/C | 1.1 |
| `[brief-sanitize] suspicious_pattern=directive_header,xml_tag,...` | WARNING | Brief utilisateur contient pattern d'injection | 1.2 |
| `[pj-truncation] kept=5000 omitted=N` | INFO | PJ tronquée à 5K chars | 1.3 |
| `[upload-block] file=... declared=N > limit=...` | WARNING | Upload PJ rejeté (50 MB par fichier) | 1.3 |
| `[upload-block] mid=... cumul=N+new > limit=...` | WARNING | Upload PJ cumulé rejeté (25 MB par mail) | P1-A1 fix |
| `[speculative] cascade Haiku->Sonnet: resume utilise (N points, M actions)` | INFO | Cascade résumé Haiku au lieu de PJ raw | 1.3 |
| `[prompt-dedup] mail courant retiré du bloc A` | DEBUG | Dédup A vs Mail reçu | 2.1 |
| `[prompt] PROFIL tier=full/medium/light/none` | DEBUG | Tier de confiance choisi | 2.2 |
| `[D2-timestamp] futur (-Nj) ts=...` | WARNING | Clock skew dans timestamp correction | P2-A6 fix |
| `[prompt-skip-c] sujet trop generique` | INFO | Skip Bloc C par stopwords | 3.2 |
| `[prompt-skip-c-stranger] contact inconnu hors domaine` | INFO | Skip Bloc C contact étranger | 4.2 |
| `[prompt-skip-d2] profil confiant + récent + corrections intégrées` | INFO | Skip Bloc D2 | 3.3 / P3-A5 |
| `[prompt-keep-d2] profil récent mais correction postérieure` | DEBUG | Skip D2 refusé (correction non intégrée) | P3-A5 fix |
| `[prompt] decay skip : interaction <30j` | DEBUG | Decay confiance épargné | 4.3 |
| `[prompt-conflict] D=vouvoiement, B_detected=tutoiement` | WARNING | Contradiction registre | 4.4 |
| `[prompt-conflict] D.tone=..., D2_correction=plus_chaleureux` | WARNING | Contradiction ton | 4.4 |
| `[prompt-conflict] D.length=..., D2_correction=plus_long` | WARNING | Contradiction longueur | 4.4 |
| `[context-b-balanced] N envoyés + M reçus` | DEBUG | Balance Bloc B 5+5 | 4.1 |
| `[generate_reply] message_id non-canonique` | WARNING | Frontend envoie un id non RFC 2822 | P2-A5 fix |
| `[security-block] vector=subject pattern_detected subject=...` | WARNING | Subject piégé détecté | 6.1 |
| `[prompt-size] tokens~N chars=N brief=N G=N D=... B=...` | INFO | Mesure taille prompt par bloc | 6.1 |
| `[prompt-size-alert] prompt > 50K tokens` | WARNING | Prompt trop gros (alerte coût) | 6.1 |

---

## Alertes recommandées (à configurer côté OVH)

### Alerte qualité — taux de conflits inter-blocs

```bash
# Nombre de [prompt-conflict] / 24h
sudo journalctl -u boostermail --since "24h ago" | grep -c "prompt-conflict"

# Total de prompts générés / 24h (via [prompt-size])
sudo journalctl -u boostermail --since "24h ago" | grep -c "prompt-size"
```

**Seuil** : ratio `[prompt-conflict] / [prompt-size]` > 5 % → alerte qualité.
**Action** : analyser si les profils contact dérivent du comportement réel utilisateur (B vs D), planifier re-analyse via `_maybe_analyze_contact`.

### Alerte sécurité — tentatives d'attaque

```bash
sudo journalctl -u boostermail --since "1d ago" | grep -E "brief-sanitize|security-block"
```

**Seuil** : > 1 / jour / utilisateur → potentielle tentative d'escalade.
**Action** : vérifier l'utilisateur (compte compromis ?), bloquer temporairement si pattern récurrent.

### Alerte coût — prompts hors-norme

```bash
sudo journalctl -u boostermail --since "1h ago" | grep "prompt-size-alert"
```

**Seuil** : N'IMPORTE QUEL match → alerte immédiate (prompt > 50K tokens).
**Action** : identifier le mail (subject + correspondent), vérifier PJ/historique anormal, ajuster les limites si dérive systémique.

### Alerte upload — DoS PJ

```bash
sudo journalctl -u boostermail --since "1h ago" | grep "upload-block"
```

**Seuil** : > 5 / heure → tentative de DoS via uploads géants.
**Action** : identifier l'utilisateur, rate-limiter ses POSTs.

---

## Métriques globales — quotidien

### Économie tokens cumulée

```bash
# Volume tokens / 24h
sudo journalctl -u boostermail --since "24h ago" \
  | grep "prompt-size" \
  | awk -F"tokens~" '{print $2}' | awk '{sum+=$1} END {print sum}'
```

### Skip Bloc C / D2 stats

```bash
sudo journalctl -u boostermail --since "24h ago" \
  | grep -cE "prompt-skip-c|prompt-skip-d2"
```

### Cascade Haiku → Sonnet hit rate

```bash
sudo journalctl -u boostermail --since "24h ago" \
  | grep "cascade Haiku->Sonnet" | wc -l
```

---

## Dashboard SaaS

Phase 6.3 — différé en `PLUS_TARD_VF` entry #17 (audit remediation observabilité). Le dashboard agrégerait ces métriques sur un Grafana ou un panel interne.

À faire en post-bêta après stabilisation des logs et observation 7-15 jours en prod.

---

**Auteur** : Claude Opus 4.7 + Yvan Bosser
**Date** : 2026-05-08
**Référence plan** : `audit/rapports/2026-05-08_audit_remediation_PLAN.md` Phase 6
