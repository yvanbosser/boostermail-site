# Tests E2E BoosterMail — squelette

> **Créé** : 30/04/2026 PM (autonomie convalescence Yvan, choix 5A)
> **Statut** : SQUELETTE — à étendre selon les flux critiques observés en prod

## Objectif

Tester automatiquement les endpoints API critiques de BoosterMail pour détecter les régressions avant déploiement. Évite les tests manuels répétés dans Outlook.

## Périmètre actuel (squelette)

3 modules de tests :

- **`test_health.py`** : disponibilité et structure des endpoints non-PII (warmup, db_conns_stats)
- **`test_gdpr.py`** : cycle complet des endpoints GDPR (export, deletion request/cancel/status)
- **`test_classement.py`** : route classement (placeholder, à étendre quand mocks Graph dispos)

## Périmètre à étendre (à faire)

Flux critiques non couverts par ce squelette (nécessitent mocks Graph API ou environnement de test isolé) :

- Ouverture mail + génération réponse SSE (besoin mock Anthropic)
- Refine d'une réponse
- Envoi via Graph (besoin tenant Microsoft de test)
- Post-send (apprentissage)
- Saisie manuelle classement avec création folder Graph

## Prérequis

```bash
pip install pytest requests
```

## Lancement

```bash
# Sur la prod OVH (live, ne touche qu'aux endpoints non destructifs) :
pytest audit/tests/e2e/ -v --base-url=https://api.boostermail.ai

# Sur le local (si V2 tourne en localhost:3443) :
pytest audit/tests/e2e/ -v --base-url=https://localhost:3443

# Un test précis :
pytest audit/tests/e2e/test_health.py::test_warmup_status_returns_200 -v
```

## Conventions

- **Aucune destruction** : ces tests ne font QUE des GET ou POST avec body de validation (ex: `{"confirm": "DELETE_MY_ACCOUNT"}` est testé mais on cancel immédiatement après).
- **Idempotents** : chaque test doit pouvoir tourner plusieurs fois sans laisser d'état.
- **Indépendants** : pas d'ordre requis entre tests (chaque test pose ses pré-conditions).

## Coverage actuel

| Endpoint | Méthode | Couvert |
|---|---|---|
| `/api/warmup_status` | GET | ✅ |
| `/api/admin/db_conns_stats` | GET | ✅ |
| `/api/gdpr/export` | GET | ✅ |
| `/api/gdpr/deletion_status` | GET | ✅ |
| `/api/gdpr/request_deletion` | POST | ✅ (cycle complet) |
| `/api/gdpr/cancel_deletion` | POST | ✅ |
| `/api/admin/recalibrate_contacts_signature?dry_run=true` | POST | ✅ |
| `/api/dialog_init` | GET | ❌ (besoin auth Microsoft + messageId) |
| `/generate_reply` | POST | ❌ (SSE streaming + Anthropic) |
| `/api/instant_reply` | POST | ❌ (besoin auth + body) |
| `/api/classify_email_manual` | POST | ❌ (besoin Graph token + folder réel) |

## CI à venir

Quand on aura un Github Actions configuré : lancer ces tests automatiquement à chaque push sur master, exit 1 si échec, alert Slack/email.

## Maintenance

À chaque ajout d'endpoint dans `app_plugin.py` qui peut être testé en lecture seule :
1. Ajouter un `def test_*()` dans le module pertinent
2. Documenter dans le tableau Coverage ci-dessus
3. Le faire tourner localement pour valider
