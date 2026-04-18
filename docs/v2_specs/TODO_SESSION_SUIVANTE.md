# TODO — Prochaine session BoosterMail

> **Dernière mise à jour** : 18/04/2026 (consolidation doc + bilan post V1_outlook→V2)

---

## État actuel (18/04/2026)

- **V2 est autonome** : libs et DB copiées localement, plus de dépendance au proto
- **Dossier V1_outlook renommé V2/** (sessions 14-18/04)
- **Doc consolidée** dans `docs/` (63 fichiers, SOMMAIRE_DETAILLE.md créé)
- **3 plans d'action** documentés : Plan 1 (doc), Plan 2 (flux), Plan 3 (caches inventaire)
- **22 manques V2 vs proto identifiés** — voir `docs/analyses_proto_v2/V2_vs_PROTO_GAPS.md`

---

## PRIORITÉ #1 — Plan 2 : Optimisation des flux (9h15)

**Doc** : `docs/plans/PLAN_2_OPTIMISATION_FLUX.md`

Le moteur IA V2 est branché. Ce qui reste = porter les optimisations proto pour atteindre le flux optimal :

| Phase | Sujet | Durée |
|---|---|---|
| 0 | Popup moderne PyQt (popup à chaque démarrage Outlook) | 1h |
| **1** | **⭐ Templates 45 fixes + appris (pipeline $0/50ms, 20-40% des mails)** | **1h30** |
| 2 | Caches : purge événementielle preemptive + 6 filtres Smart Spec + 5 caches manquants | 2h30 |
| 3 | Warmup 8s orchestré (parallélisation + pré-warm templates) | 1h |
| 4 | PyQt chaud (hot instance, dialog en 200ms) | 1h30 |
| 5 | Dialog « réponse directe » (hit template/preemptive → affichage immédiat) | 45min |
| 6 | Background speculation continue (avec 6 filtres et purge événementielle) | 1h |

**Impact attendu** : 40-60% des mails répondus instantanément, coût API -40 à -50%.

---

## PRIORITÉ #2 — Lancement instantané popup (problème Windows, NON RESOLU)

### Ce qui a été essayé et a échoué le 10/04
- VBS Startup → Windows lance trop tard (~2 min)
- Registre HKCU\Run → OneDrive bloquait le .exe au boot (OneDrive plus en jeu depuis 12/04)
- PyInstaller onefile → 7s de décompression
- PyInstaller onedir → 4s, mieux mais pas instantané
- Registre + AppData/Local → non testé complètement (PC ralenti)

### État actuel
- `launcher.ps1` existe mais non référencé
- `BoosterMail.exe` existe dans AppData/Local mais non utilisé
- VBS Startup désactivé
- Registre vidé
- Lancement MANUEL : `py -3 companion/popup_pyqt.py`

### Pistes à explorer (prochaine session)
- Tester le .exe depuis AppData/Local au reboot (sans les autres couches)
- Tester un .exe C# ultra-léger (50 Ko, <0.5s) comme launcher
- Accepter un lancement semi-auto (raccourci bureau ?)
- Appliquer la Règle 2 : micro-test chaque maillon ISOLÉMENT
- **Phase 4 du Plan 2** (PyQt chaud) pourrait résoudre partiellement ce point

---

## PRIORITÉ #3 — Overlay auto + détection auto (en attente admin deploy)

### Dépendance
- Mail envoyé à Compta Santé pour admin deploy — EN ATTENTE
- Alternative long terme : certification AppSource (3-6 mois)

### Ce qui fonctionne déjà en sideload
- Le bouton BoosterMail (#7b) dans Outlook → ouvre le dialog
- Après le 1er clic bouton → ItemChanged s'active → overlay se met à jour
- SSE entre backend et overlay PyQt

### Ce qui ne fonctionne PAS en sideload
- ItemChanged au démarrage (nécessite LaunchEvent = admin deploy)
- Détection auto clic "Répondre" (nécessite LaunchEvent)
- Overlay alimentée au démarrage (nécessite warmup Graph + détection mail)

---

## PRIORITÉ #4 — Plan 1 : Application de la documentation (en cours, ~4h)

**Doc** : `docs/plans/PLAN_1_APPLICATION_DOCUMENTATION.md`

| Phase | Statut |
|---|---|
| 1. Finalisation structure | ⏸️ doublons + commit repoussés |
| 2. Datation systématique | ✅ terminée (63 docs datés) |
| 3. Identification périmés | ✅ terminée (6 docs marqués + 3 mis à jour) |
| 4. Mise à jour specs maîtres | 🔄 en cours (CLAUDE.md à jour, V2_MASTER_SPEC à faire, TODO à jour) |
| 5. Règles de maintenance | ⏳ à faire |

---

## RAPPELS IMPORTANTS

### Terminologie officielle (décision 10/04/2026)
- **Mode Complet** (ex « Mode Standard ») = connecté Microsoft, tout fonctionne
- **Mode Dégradé** (ex « Mode Performance Réduite ») = pas connecté, quasi inutilisable
- Le Mode Dégradé n'est PAS un mode d'utilisation — c'est un état transitoire

### Philosophie produit
- **Une seule version : V2** (V1.1 hybride abandonnée 10/04, backend V1 séparé abandonné 13/04)
- **La connexion Microsoft est obligatoire** — sans elle, pas de contexte = réponses génériques
- **Le chatbot d'onboarding prend l'utilisateur par la main** (`docs/installation/SPEC_ONBOARDING_COMPLET.md`)
- **La popup de lancement = outil marketing** (« 4h gagnées par semaine, activez en 2 min »)

### NE PAS mélanger les chantiers
Le 10/04, une journée a été perdue en mélangeant moteur + lancement + overlay.
Chaque chantier est INDÉPENDANT. Traiter un à la fois.

### DB actives
- **Proto** : `C:/EasyMail/boostermail.db`
- **V2** : `V2/boostermail.db` (séparée depuis 18/04, migrée depuis proto avec 21 settings)
- `emails.db` = corrompue par OneDrive, NE PAS utiliser
- V2/app_plugin.py pointe vers `V2/boostermail.db`

### Étanchéité proto/V2
- `app.py`, `claude_ai.py`, `outlook_com.py` = LECTURE SEULE pour la V2
- V2 a ses propres copies dans `V2/` depuis le 18/04
- Toute modification du proto doit être auditée (risque bêta-testeurs en prod)
