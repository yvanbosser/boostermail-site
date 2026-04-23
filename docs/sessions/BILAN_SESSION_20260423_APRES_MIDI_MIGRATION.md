# Bilan session 2026-04-23 après-midi — Migration proto→V2 + déblocage nav

> **Contexte** : après matinée de fixes code (résumé, vitesse, complétude), l'user teste en condition réelle et constate que les caches sont toujours vides.
>
> **Découverte majeure** : la DB V2 n'a jamais reçu les données du proto. La "migration du 18/04" n'avait transféré que **21 settings**, laissant **3042 threads + 103 profils + 37 corrections + 48 metrics** dans la DB proto.

---

## Front 1 — Migration des données (commit `e818db9`)

### Contexte

Le `CLAUDE.md` indique : *"DB V2/boostermail.db (séparée, **migrée depuis proto le 18/04**)"*. Ce texte est **trompeur** : seuls les settings ont été migrés. Le Plan 3 (portage caches) a été pensé pour **porter la LOGIQUE** (filtres Smart Speculative, hooks) mais jamais pour **porter les DONNÉES**.

Conséquence : depuis le 18/04, V2 tourne en "cold mode" permanent, tous les caches d'apprentissage vides, aucun historique, chaque clic BM = génération Claude en live sans contexte.

### Données inventoriées

| Table proto | Rows | Rôle |
|---|---|---|
| `contact_profiles` | 103 | Tags vouvoiement/confiance, registre, tone, organization |
| `threads` | 3042 | Historique bilateral (contextes A/B/C du proto) |
| `style_corrections` | 37 | Diff proposé/envoyé appris |
| `folder_classifications` | 84 | Historique classement mails |
| `pj_classifications` | 42 | Historique classement PJ Windows |
| `echeances` | 10 | Échéances détectées et suivies |
| `metrics` | 48 | Durée/importance/direct_send par envoi |
| `treated_emails` | 141 | Mails archivés/répondus/supprimés |
| `folder_cache` | 313 | Arborescence dossiers Outlook |

### Livrable

**Script `V2/migrate_proto_to_v2.py`** :
- Dry-run par défaut (sécurité)
- Backup automatique `V2/boostermail.db.pre_migration_<TS>` avant écriture
- INSERT OR IGNORE (respecte l'existant côté V2)
- Schémas vérifiés compatibles préalablement
- Usage : `python migrate_proto_to_v2.py --execute`

### Résultat

```
3820 rows lues dans proto
3820 rows copiées en V2
0 doublon ignoré
0 erreur
```

V2 DB est maintenant au même niveau de richesse que le proto.

### Impact attendu

- **T6 (tags contact)** enfin émis sur les 103 contacts connus
- **Contextes A/B/C** construits depuis `threads` en DB (local, rapide) au lieu de 3 searches Graph live (2-3s)
- **Cache préemptif** peut se construire dès maintenant car l'historique est présent
- **Classement mails/PJ** : suggestions basées sur 84+42 classifications

---

## Front 2 — Débloquer boutons Profil/Contacts/Échéances (commit `e7760bb`)

### Contexte

L'user constate : *"la page profil n'étant pas accessible dans v2"*. Les 3 boutons du header dialog (Profil/Contacts/Échéances) utilisent `window.open('/plugin/popup.html?view=X')`. Or `popup_pyqt.py` intercepte **toutes** les `window.open` avec `_BlackholePage` qui refuse toute navigation, pour éviter les popups résiduelles Edge. Les boutons de nav étaient **muets** sans que l'user le sache.

### Livrable

Nouvelle classe `_ChildPopupPage` dans `popup_pyqt.py` qui distingue :
- **URL localhost/127.0.0.1** (interne BoosterMail) → crée une **vraie QWebEngineView secondaire** 700×600, `WA_DeleteOnClose`, visible comme fenêtre Qt indépendante
- **URL externe** (admin.cloud.microsoft, edge://…) → refuse (comportement `_BlackholePage` préservé pour éviter fuite vers navigateur système)

`certificateError` accepte localhost (self-signed V2 inchangé).

### Impact

L'user peut maintenant cliquer Profil / Contacts / Échéances → mini-fenêtre Qt avec popup.html?view=X. Utile pour vérifier son profil, éditer contacts, consulter échéances.

---

## Front 3 — Vérification hooks d'apprentissage V2 (aucune modif)

### Audit code

Les hooks post-envoi dans `app_plugin.py` sont **tous présents et correctement câblés** :

| Hook | Fonction DB | Ligne | Déclenchement |
|---|---|---|---|
| Thread envoyé | `save_to_thread(sent)` | 6921 | Chaque envoi |
| Thread reçu | `save_to_thread(received)` | 6937 | Reply/reply_all |
| Métriques | `save_metric` | 6954 | Chaque envoi |
| Corrections | `save_correction` | 6982 | Diff proposé/envoyé |
| Profil contact | `save_contact_profile` | 7004, 7056 | Changement registre / re-analyse |
| Score history | `save_score_history` | 7253 | Recalibrage adaptatif |
| Writing level | `save_setting(writing_level)` | 7248 | Changement N1-N10 |
| Convergence | `save_setting(writing_converged)` | 7259 | 5 scores dans ±3 |
| Échéances | `save_echeance` | 6701 | BG scan |
| Analyse contact | `analyze_contact_profile` | 7381 | Tous les 3 mails / contact |

**Conclusion** : aucune modification nécessaire côté code. Les hooks attendaient juste d'avoir une DB peuplée pour commencer à enrichir. Maintenant que Front 1 a migré les données, V2 va accumuler naturellement à chaque envoi.

---

## Commits de la session

```
e7760bb Front 2 : débloquer boutons Profil/Contacts/Échéances
e818db9 Front 1 : migration proto → V2 (3820 rows)
a4a7f4c Chef sortant : cleanup SSE au close dialog
f915cdd Rapport session matin
c5bf64b Modèle Haiku EOL → haiku-4-5
b075546 Placeholder bloquait la chaîne de réponse
1093db9 T3 mark + rendu PJ standalone
4b6e122 Office.js 'defer' → 'async'
62066a3 Alerter certs doublon au sideload
ea73bda Architecture 3 portes + pré-chauffe (base)
```

---

## Ce qui doit apparaître au prochain test utilisateur

Après restart popup_pyqt (via réouverture Outlook) :

1. **Tags vouvoiement/confiance** dans le header dialog sur les 103 contacts connus
2. **Cache résumé** qui grossit de façon autonome au fil des usages
3. **Boutons Profil/Contacts/Échéances** qui ouvrent des fenêtres Qt secondaires
4. **Réponses préemptives** qui s'accumulent dans `_reply_cache` à mesure que l'user ouvre des mails
5. **Performance** améliorée sur les contacts connus (plus de search Graph live puisque threads est plein)

---

## Points d'attention pour la suite

1. **Le script `migrate_proto_to_v2.py` est one-shot**. Ne pas relancer sans raison (protégé par INSERT OR IGNORE mais pollue les logs).
2. **Le cert doublon `067F...`** dans HKLM n'a pas été nettoyé (nécessite commande admin manuelle, documentée dans `boostermail.log` au prochain sideload).
3. **Mécanismes proactifs de génération préemptive** : vérifier en runtime que `continuous_speculation_loop` tourne bien côté V2 (normalement il tourne en thread daemon au démarrage).
