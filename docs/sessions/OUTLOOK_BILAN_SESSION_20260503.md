# Bilan de session — 03/05/2026

> **Dernière mise à jour** : 03/05/2026 fin d'après-midi
> **Contexte** : session déclenchée par Yvan qui s'inquiète de ses factures Anthropic ~$75/jour. Investigation devenue audit Workflow 4 complet → fix majeur déployé.
> **Top commit final** : `680608b+`

---

## Mission accomplie

Identification et éradication d'**une boucle infinie d'appels API Claude** qui consommait ~4 000 appels/jour sans aucune corrélation avec l'usage utilisateur. Économie projetée : **~$700-1 200/mois (~$8 800-14 200/an)**.

---

## Récap commits (3 commits aujourd'hui)

| SHA | Sujet |
|---|---|
| `05b34a3` | fix(learning) : boucle infinie analyse contacts (économie ~$575/mois estimée → réelle ~$700-1 200) |
| `2cddd0a` | docs(audit) : rapport final + Pattern #24 + I-LEARN-01/02 |
| `680608b` | docs(audit) : rapport constat-only initial (avant fix) |

---

## Récit de la session

### Phase 1 — Investigation factures (Yvan inquiet)
Yvan partage 5 factures Anthropic auto-recharge ($45 chacune) reçues entre le 1er et le 3 mai, soit **$225 en 3 jours**. Demande : *« est-ce le coût du dev ou un bug ? ».*

### Phase 2 — Premiers diagnostics (zigzag mea culpa)
- **Erreur #1** : interprétation des logs `[learning]` → conclusion fausse « pic dev sprint »
- **Erreur #2** : sous-estimation du nombre de contacts en boucle (2 → 13 → 34 selon les angles)
- **Erreur #3** : analyse trop hâtive, plusieurs rectifications successives

### Phase 3 — Méthodologie correcte (suggérée par Yvan)
**Test du contrôle null** : un dimanche calme avec 2 mails Bankin' noreply + 0 envoi + 0 user action. Par design, BoosterMail aurait dû faire **0 appel API**. Or **~4 000 appels mesurés**.

→ Verdict immédiat irréfutable : **100% du coût d'aujourd'hui = bug pur** (et non sprint dev).

### Phase 4 — Audit Workflow 4 PLAYBOOK appliqué intégralement
Identification de **3 root causes distinctes** dans `_maybe_analyze_contact` (`V2/app_plugin.py`) :

- **RC1** : pas de skip noreply → 31 contacts piégés silencieux
- **RC2** : branche « Re-analyse forcee sample_count=0 » sans condition d'arrêt → 2 contacts (`yvan@gmail`, `support@coaxis`) en vraie boucle Claude
- **RC3** : `_should_analyze_contact()` sans mémoire « déjà analysé » → 34 contacts re-analysés à chaque cycle BG

### Phase 5 — Implémentation 4 fixes + déploiement
- **S1** : tuple `_AUTO_EMAIL_PATTERNS` + skip silencieux early
- **S2** : cooldown 24h via `_force_analysis_attempts` cache RAM + paramètre `bypass_cooldown=True` dans 3 routes user
- **S3** : `_should_analyze_contact(mail_count, existing_sample_count)` avec mémoire
- **S4** : `logger.warning` dans `analyze_contact_profile` pour révéler les `return None` silencieux (instrumentation)

### Phase 6 — Validation live (après deploy 16:52 UTC)
| Métrique | Avant | Après (12 min) | Chute |
|---|---|---|---|
| Appels API | 13/12min projeté | **3** (tous au démarrage) | **-77%** |
| Appels API hors restart | 13 | **0** | **-100%** |
| Cadence projetée 24h | 4 000/jour | ~10-50/jour | **~-98 à -99 %** |

**Validation par contrôle null** : depuis le restart 16:52, 0 appel pendant les 12 minutes suivantes alors que normalement c'était 13 appels/12min avant fix.

---

## Travail par bloc

### Bloc A — Investigation factures Anthropic
- Lecture des 5 PDF de factures BV8FQGDH-0013 à 0017
- Décomposition par modèle Claude (graphe console Anthropic)
- Identification que la clé `BoosterMail SaaS Production` est seule utilisée (pas de fuite)
- Calcul cadence appels API/heure → constat de cadence régulière 24/24

### Bloc B — Audit Workflow 4 PLAYBOOK
- Lecture `audit/PLAYBOOK.md` Workflow 4
- Test du contrôle null suggéré par Yvan (jour calme = baseline 0)
- Inventaire DB des 33 profils sample_count=0 → 3 catégories distinctes
- Identification de 11 contacts en boucle dans les logs
- Vérification `julien@solaris-gestion.fr` `manually_edited=1` → skip silencieux (donc pas dans la boucle)
- Investigation `_continuous_speculation_loop` → caller à chaque cycle ~80s

### Bloc C — Implémentation et déploiement
- Code modifié : `V2/app_plugin.py` (`_should_analyze_contact`, `_maybe_analyze_contact`, 3 routes user)
- Code modifié : `V2/claude_ai.py` (`analyze_contact_profile` instrumentation)
- Compile + commit `05b34a3` + scp + restart service à 16:52 UTC
- Validation 9 min puis 12 min plus tard → -77% à -100% selon métrique

### Bloc D — Documentation et artefacts d'audit
- Rapport constat-only initial : `audit/rapports/2026-05-03_audit_boucle_learning_sample_count.md`
- Rapport final post-fix : `audit/rapports/2026-05-03_audit_boucle_learning_FIX_DEPLOYE.md`
- **Pattern #24** dans `ANOMALIES_RECURRENTES.md` : Branche de rattrapage sans condition d'arrêt + sans cooldown = boucle API infinie
- **I-LEARN-01** dans `INVARIANTS.md` : cadence appels Anthropic API en BG bornée (< 50/jour sur jour calme)
- **I-LEARN-02** dans `INVARIANTS.md` : corrélation BG vs usage user (distribution horaire)

---

## Découvertes structurelles

### D1 — Erreur méthodologique répétée (mea culpa documenté)
J'ai zigzagué entre 3 verdicts contradictoires avant de mesurer le **signal le plus brut** (`POST api.anthropic.com` par heure). Documenté dans le rapport final : *« toujours commencer par les compteurs bruts, jamais par l'interprétation des logs métier ».*

### D2 — Test du contrôle null (suggéré par Yvan)
Méthodologie ajoutée comme outil systématique : sur un jour calme (0 usage user), tout coût API > 0 = bug pur. Plus rigoureux que toute interprétation de logs. À ajouter au PLAYBOOK Workflow 4 dans une session future.

### D3 — Pattern #24 nouveau identifié
La combinaison « branche de rattrapage + sans condition d'arrêt + sans cooldown + sans instrumentation des `return None` » est un anti-pattern systémique. Le checklist du Pattern #24 documente les 4 garde-fous nécessaires pour ce type de branche.

### D4 — Symbiose des fixes A2 (02/05) et S2 (03/05)
- A2 (commis Haiku idempotent, 02/05 soir) avait réduit la cadence de 240/h → 160/h (-33%)
- S2 (cooldown 24h sur learning) réduit ensuite de 160/h → ~3/h (-98%)
- Combinés, le coût total passe de ~$30-40/jour à ~$1-3/jour

---

## Livrables

### Code
- `V2/app_plugin.py` :
  - `_should_analyze_contact(mail_count, existing_sample_count=None)` avec mémoire RC3
  - `_maybe_analyze_contact(contact_email, bypass_cooldown=False)` avec skip RC1 + cooldown RC2
  - `_AUTO_EMAIL_PATTERNS` tuple
  - `_force_analysis_attempts` cache RAM + `_FORCE_ANALYSIS_COOLDOWN_SEC` 24h
  - 3 routes user passent `bypass_cooldown=True` (recalibrate, analyze_contact, post_send_learning)
- `V2/claude_ai.py` :
  - `analyze_contact_profile` instrumenté avec 3 `logger.warning` sur les paths `return None` silencieux

### Docs / Audit
- 2 rapports d'audit (`audit/rapports/2026-05-03_audit_boucle_learning_*.md`)
- Pattern #24 dans ANOMALIES_RECURRENTES
- I-LEARN-01 + I-LEARN-02 dans INVARIANTS

---

## État OVH

- ✅ Service `boostermail` actif (restart 16:52 UTC)
- ✅ Cadence post-fix : 3 appels API en 12 min puis 0 (vs 13/12min avant)
- ✅ Pas de redémarrage prévu d'ici minuit
- ✅ Cooldown 24h actif → instrumentation S4 visible demain matin ~17h UTC

---

## Sujets ouverts

### À surveiller demain matin (~17h UTC)
- Cadence stabilisée < 5 appels/h confirme le -98%
- Cooldown 24h expire → réessai unique → les **warnings JSON (S4)** révèleront pourquoi `yvan@gmail` et `support@coaxis` plantent silencieusement

### À investiguer en session suivante (B2 du rapport)
Pourquoi `analyze_contact_profile` retourne `None` silencieusement pour ces 2 contacts ? Hypothèses :
- (H1) Claude renvoie un texte non-JSON pour mail vers soi-même (`yvan@gmail`)
- (H2) Validation enum strict échoue → `return None`
- (H3) Exception non capturée par le try/except principal

L'instrumentation S4 doit fournir la réponse demain.

### Anomalies à fixer plus tard
- 31 noreply piégés ont déjà été skippés par RC1 (mais leur sample_count=0 reste en DB → bruit visuel sur le profil/contacts page si exposé)
- Recommandation : nettoyer les 33 profils `sample_count=0` qui sont en fait soit des automates soit des contacts non-analysables. Update SQL ou suppression. **À planifier en session SaaS.**

### Sujets business (côté Yvan)
- Mailbox `dpo@boostermail.ai`
- DPA Anthropic
- Marque INPI BoosterMail
- Compléter `[À COMPLÉTER]` dans `legal/`

---

## Caveats

Le fix RC3 (mémoire `existing_sample_count >= mail_count`) suppose que `sample_count` est toujours mis à jour correctement à la sauvegarde. Pour les 2 contacts (`yvan@gmail`, `support@coaxis`) qui plantent silencieusement, le cooldown 24h les protège, mais le bug racine reste à identifier (B2).

Si l'instrumentation S4 révèle un problème de prompt Claude (cas H1), il pourrait y avoir d'autres contacts impactés à terme. À surveiller.
