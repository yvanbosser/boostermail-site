# TODO — Prochaine session BoosterMail

*Mis à jour le 10/04/2026 — fin de session*

---

## PRIORITE #1 — Brancher le moteur IA (AUCUNE dépendance)

Le moteur du proto (génération, envoi, post-envoi) doit être porté dans la V1.
La carrosserie (dialog, overlay, boutons) est prête. Le moteur tourne à vide.

### Ce qu'il faut faire

1. **Lire claude_ai.py** (proto, LECTURE SEULE) — comprendre comment il assemble les blocs A→F
2. **Reproduire la logique** dans app_plugin.py (ou un nouveau core/prompt_builder.py)
   - Assemblage blocs : D (brief) → B (historique) → A (conversation) → C (mots-clés) → D2 (corrections) → E (importance) → F (échéances)
   - System prompt WOW 3 phases
   - Gestion importance R/S/H (max_tokens, troncature)
   - Dedup A+B vs C
3. **Compléter la route `/generate_reply`** dans app_plugin.py — elle doit appeler le prompt builder puis core/claude_provider.py
4. **Compléter la route `/refine_reply`**
5. **Compléter la route `/send_reply`** — envoi via Graph API (Mode Complet)
6. **Compléter le post-envoi** — 3 threads (échéances, classement, apprentissage)

### Ce qui est déjà prêt
- core/claude_provider.py : streaming, retry, caching — FONCTIONNE
- core/ai_provider.py : interface + factory — FONCTIONNE
- Graph API (outlook_graph.py) : lectures, envoi, dossiers — FONCTIONNE
- DB (boostermail.db) : 12 tables, integrity OK — FONCTIONNE
- dialog.js : UI prête, attend les données du backend

### Point clé : le cerveau est dans claude_ai.py (proto)
- core/ = le tuyau (reçoit prompt, retourne stream). PRÊT.
- claude_ai.py = le cerveau (assemble les blocs). DANS LE PROTO.
- Il faut EXTRAIRE la logique de claude_ai.py et la reproduire dans un module V1.
- NE PAS modifier claude_ai.py — le lire et s'en inspirer.

---

## PRIORITE #2 — Lancement instantané popup (problème Windows, NON RESOLU)

### Ce qui a été essayé et a échoué le 10/04
- VBS Startup → Windows lance trop tard (~2 min)
- Registre HKCU\Run → OneDrive bloque le .exe au boot
- PyInstaller onefile → 7s de décompression
- PyInstaller onedir → 4s, mieux mais pas instantané
- Registre + AppData/Local → non testé complètement (PC ralenti)

### État actuel
- launcher.ps1 existe mais non référencé
- BoosterMail.exe existe dans AppData/Local mais non utilisé
- VBS Startup désactivé
- Registre vidé
- Lancement MANUEL : `py -3 companion/popup_pyqt.py`

### Pistes à explorer (prochaine session)
- Tester le .exe depuis AppData/Local au reboot (sans les autres couches)
- Tester un .exe C# ultra-léger (50 Ko, <0.5s) comme launcher
- Accepter un lancement semi-auto (raccourci bureau ?)
- Appliquer la Règle 2 : micro-test chaque maillon ISOLEMENT

---

## PRIORITE #3 — Overlay auto + détection auto (en attente admin deploy)

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

## RAPPELS IMPORTANTS

### Terminologie
- **Mode Complet** (ex "Mode Standard") = connecté Microsoft, tout fonctionne
- **Mode Dégradé** (ex "Mode Performance Réduite") = pas connecté, quasi inutilisable
- Le Mode Dégradé n'est PAS un mode d'utilisation — c'est un état transitoire

### Philosophie produit
- **Une seule version : V1** (pas de V1.1)
- **La connexion Microsoft est obligatoire** — sans elle, pas de contexte = réponses génériques
- **Le chatbot d'onboarding prend l'utilisateur par la main** (docs/SPEC_ONBOARDING_COMPLET.md)
- **La popup de lancement = outil marketing** ("4h gagnées par semaine, activez en 2 min")

### NE PAS mélanger les 3 chantiers
Le 10/04, une journée a été perdue en mélangeant moteur + lancement + overlay.
Chaque chantier est INDÉPENDANT. Traiter un à la fois.

### DB active
- `boostermail.db` (emails.db = corrompue par OneDrive, ne PAS utiliser)
- app_plugin.py pointe vers boostermail.db (ligne 64)
