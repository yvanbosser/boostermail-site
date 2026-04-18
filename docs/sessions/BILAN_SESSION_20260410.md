# Bilan session du 10/04/2026

---

## Ce qui a été fait

### Organisation du projet
- Rangement complet de l'arborescence (8 dossiers backup regroupés, corbeille/ créée, docs/ organisé)
- V1_plugin/ archivé dans corbeille/ (remplacé par V2/)
- 6 Setup ZIP anciens archivés (V6 conservé dans installer/)
- STRUCTURE_PROJET.md créé (carte complète du projet)
- NOUVELLE_SESSION.md créé (guide démarrage + méthode de travail)
- SPEC_UI_TABLEAUX_V10.docx généré (consolide V7/V8/V9, anciens supprimés)

### Audit complet du codebase
- 4 audits parallèles : app_plugin.py, JS, DB, infrastructure
- 103 points analysés, 12 critiques trouvées et corrigées
- 2ème passe : 1 deadlock trouvé et corrigé (régression du fix #6)
- 3ème passe : 0 problème restant
- Étanchéité proto vérifiée (seul database.py touché, rétrocompatible)

### Corrections critiques appliquées
1. `_db.init()` ajouté dans app_plugin.py (tables non créées sur DB vide)
2. manifest.xml FunctionFile V1.1 → autorunHtmlUrl (le bon shared runtime)
3. autorunshared.js body.getAsync race condition corrigée
4. dialog.js XSS _escapeAttr pour onclick inline
5. app_plugin.py _cache_set protégé par RLock (deadlock évité)
6. app_plugin.py proxy Companion whitelist
7. database.py SQL borné à 15 mots-clés
8. claude_provider.py format prompt sync harmonisé
9. app_plugin.py CORS, secret key aléatoire, debug conditionnel
10. outlook_graph.py gestion 403 Forbidden
11. companion.py DASL injection sanitisée
12. database.py busy_timeout=5000

### DB réparée
- emails.db corrompue par OneDrive → nouvelle boostermail.db créée
- app_plugin.py pointe vers boostermail.db

### Documents créés/mis à jour
- `docs/SPEC_ONBOARDING_COMPLET.md` — parcours utilisateur complet avec chatbot
- `docs/SPEC_CHATBOT_INSTALLATION.md` — spec du chatbot d'installation
- `docs/GUIDE_INSTALLATION_PLUGIN.md` — guide admin deploy + self-install + sideload
- `docs/MAIL_DEMANDE_ADMIN_DEPLOY.md` — mail envoyé à Compta Santé

---

## Ce qui n'a PAS marché

### Lancement instantané popup (échec)
- VBS Startup → Windows lance trop tard (~2 min)
- Registre HKCU\Run → OneDrive bloque le .exe au boot
- PyInstaller onefile → 7s de décompression
- PyInstaller onedir → 4s, pas assez
- Toutes les couches empilées ont ralenti le PC
- Nettoyé : registre vidé, VBS désactivé, lancement MANUEL uniquement

### Temps perdu
- Trop de temps passé sur le lancement instantané (problème Windows)
- Mélange des 3 chantiers (moteur + lancement + overlay)
- Corrections sur corrections sans prendre de recul

---

## Décisions stratégiques prises

### 1. Une seule version : V1
V1.1 (hybride COM + Office.js) abandonnée : COM ne fonctionne pas sur New Outlook.

### 2. Mode Complet obligatoire
- "Mode Standard" renommé "Mode Complet"
- "Mode Performance Réduite" renommé "Mode Dégradé"
- Le Mode Dégradé n'est PAS utilisable (pas de contexte = réponses génériques)
- La connexion Microsoft est une condition, pas une option

### 3. Popup de lancement = marketing
"Répondez à vos mails 5x plus vite. 4h gagnées par semaine. Activez en 2 minutes."
Pas de bouton Annuler. Réapparaît tant que non activé.

### 4. Chatbot d'onboarding
- Détection auto de l'email via Office.js
- Fenêtre Microsoft SSO avec email pré-rempli
- 90% des cas : 0 mot de passe (Windows SSO)
- Chatbot guide les 10% restants étape par étape
- Bouton "Mot de passe oublié" ouvre directement la page Microsoft

### 5. Roadmap installation
- Court terme : sideload + chatbot onboarding
- Moyen terme : AppSource (1 clic)
- Long terme : certification M365 (LaunchEvent pour tous = le graal)

### 6. Trois chantiers indépendants
1. Moteur IA (priorité #1, aucune dépendance)
2. Lancement instantané (problème Windows, non résolu)
3. Overlay auto + détection auto (attente admin deploy)

### 7. Méthode de travail
8 règles documentées dans NOUVELLE_SESSION.md :
tester avant de promettre, prototyper petit, identifier les risques,
ne pas accumuler les couches, séparer recherche et implémentation,
étanchéité proto, socle Gmail, audit systématique.

---

## Prochaine session — priorité absolue

**BRANCHER LE MOTEUR IA** dans la V1.

C'est le cœur du produit. Le dialog est prêt (forme 95%). Le backend est prêt (47 routes). Le core/ est prêt (claude_provider fonctionne). Il manque le cerveau : la construction du prompt WOW (blocs A→F) adaptée aux données Graph API.

Voir `V2/TODO_SESSION_SUIVANTE.md` pour le détail.

---

## État de l'infrastructure au 10/04/2026 soir

| Composant | État |
|---|---|
| Proto (app.py:5050) | ✅ Intact, non touché |
| Backend V1 (app_plugin.py:3443) | ✅ Fonctionne, 47 routes, audit passé |
| Companion (companion.py:5051) | ✅ Fonctionne |
| DB (boostermail.db) | ✅ Neuve, 12 tables, integrity OK |
| Manifest (manifest.xml V1.3) | ✅ Sideloadé dans New Outlook |
| Dialog (dialog.html/js/css) | ✅ Forme 95%, fond squelette |
| Overlay (popup.html/js) | ✅ Forme validée, fond non alimenté |
| Popup PyQt (popup_pyqt.py) | ✅ Réécrit, propre, loading screen |
| Core (claude_provider, ai_provider) | ✅ Audit passé, prompt caching harmonisé |
| autorunshared.js | ✅ Audit passé, body.getAsync corrigé |
| VBS Startup | ⚠️ Désactivé (ne lance que backend) |
| Registre Windows | ⚠️ Vidé |
| BoosterMail.exe (PyInstaller) | ⚠️ Existe mais non utilisé |
| Admin deploy | ⏳ Mail envoyé, en attente réponse |
