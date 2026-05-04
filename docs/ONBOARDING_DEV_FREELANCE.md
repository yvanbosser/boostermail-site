# Onboarding développeur freelance — BoosterMail

> **Dernière mise à jour** : 04/05/2026
> **Public visé** : développeurs intervenant ponctuellement sur le code BoosterMail dans le cadre d'un contrat de prestation freelance.
> **Premier destinataire** : Michael de Brauwer (Mikadb LLC), démarrage prévu 05/05/2026.

---

## Bienvenue

BoosterMail est un assistant email intelligent intégré à Microsoft Outlook (Add-in Office.js + backend Flask). Le produit est en mode SaaS sur `api.boostermail.ai` (VPS OVH) et utilisé en production par son fondateur quotidiennement.

Tu rejoins le projet en tant que prestataire indépendant. Ce document te donne **tout ce dont tu as besoin pour démarrer rapidement**, sans avoir à reconstituer 6 mois d'historique. Lis-le **dans l'ordre** ; les sections sont conçues pour être courtes et actionnables.

---

## 1 — Contexte produit en 5 minutes

BoosterMail est un assistant email qui :

- **S'intègre à Microsoft Outlook** (New Outlook desktop + Outlook Web) sous forme d'add-in Office.js
- **Génère des réponses email** adaptées au style de l'utilisateur et au profil du correspondant, en utilisant Claude (Anthropic API)
- **Apprend en continu** des corrections faites par l'utilisateur
- **Tourne en SaaS** sur `https://api.boostermail.ai` (VPS OVH Gravelines, Flask + nginx + systemd)

Le produit a deux versions :

| Version | Localisation | Statut | À toucher ? |
|---|---|---|---|
| **Proto** (port 5050) | `app.py`, `claude_ai.py`, `outlook_com.py`, `templates/` | Bêta-testeurs en production | ❌ **LECTURE SEULE — NE JAMAIS MODIFIER** |
| **V2 SaaS** (port 3443) | `V2/*` | Production sur OVH | ✅ Scope principal des missions |

**Règle d'or** : tout ce qui est sous `V2/` est modifiable par les freelances. Tout le reste est à laisser tranquille (sauf consigne explicite).

---

## 2 — Setup environnement local (étape par étape)

### 2.1 Prérequis

- **Windows 10/11** ou macOS récent (Outlook Desktop est Windows uniquement, mais V2 peut tourner en local sur les deux)
- **Python 3.10+** (testé jusqu'à 3.14)
- **Git 2.40+**
- **Microsoft Outlook** (New Outlook recommandé) avec un compte Microsoft 365 (perso ou tenant dev gratuit)
- **VS Code** ou tout autre IDE
- **Claude Code** pour bénéficier du contexte projet automatiquement (recommandé, voir § 6)

### 2.2 Cloner le repo

```bash
# Demander d'abord l'accès Collaborator au repo GitHub
git clone git@github.com:yvanbosser/boostermail-product.git C:/Users/<toi>/dev/boostermail
cd C:/Users/<toi>/dev/boostermail
```

### 2.3 Créer le `config.json` local

```bash
# À la racine du projet (C:\Users\<toi>\dev\boostermail\)
cp config.json.example config.json
```

Puis éditer `config.json` avec **TES propres clés** (jamais celles de la prod) :

- **`ANTHROPIC_API_KEY`** : ta propre clé (créée sur [Anthropic Console](https://console.anthropic.com)) ou celle qui te sera fournie comme « clé dev » avec budget plafonné
- **`flask_secret_key`** : générer aléatoirement
  ```bash
  python -c "import secrets; print(secrets.token_hex(32))"
  ```
- **`fernet_key`** : générer aléatoirement
  ```bash
  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  ```
- **`microsoft.*`** : laisser à blanc pour l'instant (tu pourras configurer plus tard si ta mission nécessite l'auth Microsoft réelle ; pour la plupart des fonctionnalités, un tenant Microsoft dev gratuit suffit)
- **`OPENAI_API_KEY`** : optionnel
- **`SENTRY_DSN`** : laisser vide

⚠️ **`config.json` est dans `.gitignore` — il ne doit JAMAIS être commité.** Vérifier avec `git status` avant chaque commit.

### 2.4 Installer les dépendances Python

```bash
cd V2
python -m venv venv
# Windows :
venv\Scripts\activate
# macOS/Linux :
source venv/bin/activate

pip install -r requirements.txt
```

### 2.5 Initialiser la base de données locale

La DB locale `V2/boostermail.db` est créée automatiquement au premier lancement. Pour partir d'une DB factice :

```bash
# Soit laisser V2 créer une DB vide à la volée (tables auto-créées au démarrage)
# Soit demander un dump anonymisé à l'équipe (jamais la DB de production réelle)
```

### 2.6 Générer les certificats HTTPS (auto-signés)

```bash
cd V2
python generate_cert.py
# Crée localhost.crt et localhost.key
```

### 2.7 Lancer V2

```bash
cd V2
python app_plugin.py
```

V2 démarre sur `https://localhost:3443`. Le navigateur affichera un avertissement de certificat auto-signé — accepter (ou installer le cert dans le keystore Windows pour s'en débarrasser).

### 2.8 Tester depuis Outlook

1. Activer le mode développeur d'Office.js dans Outlook
2. Side-loader le fichier `V2/manifest.xml` adapté pour pointer vers `https://localhost:3443/`
3. Ouvrir un mail dans la boîte de réception → cliquer le bouton BoosterMail → la modale s'ouvre

→ Documentation Microsoft : [Side-load an Outlook add-in for testing](https://learn.microsoft.com/en-us/office/dev/add-ins/outlook/sideload-outlook-add-ins-for-testing)

---

## 3 — Workflow Git (impératif)

### 3.1 Branches

- **`master`** : protégée. Aucun push direct possible. Tous les changements passent par PR.
- **`feat/<ton_nom>/<sujet>`** : ta branche de travail pour une nouvelle fonctionnalité.
- **`fix/<ton_nom>/<sujet>`** : pour un correctif.
- **`docs/<ton_nom>/<sujet>`** : pour une mise à jour documentation.

Exemple : `feat/michael/multi-tenant-user-isolation`

### 3.2 Commits

Format : `type(scope): description courte` en français, descriptive et préfixée par un type :

- `feat:` — nouvelle fonctionnalité
- `fix:` — correctif de bug
- `docs:` — documentation
- `refactor:` — refactoring sans changement fonctionnel
- `test:` — ajout/modification de tests
- `chore:` — tâche de maintenance

Exemple : `feat(auth): isolation des données par user_id en multi-tenant`

### 3.3 Pull Requests

- **Titre clair** + **description structurée** (objectif, ce qui change, ce qui ne change pas, captures avant/après si UI)
- Demander à PDLConsulting de **reviewer** (review obligatoire pour merger)
- Pas de force-push sur des branches partagées (cf. Charte sécurité art. 5.3)
- Une fois mergée, ta branche est supprimée

### 3.4 Pas de push direct sur `master`

C'est techniquement bloqué (protected branch). Si jamais tu y arrives, c'est qu'on a un bug de configuration GitHub à corriger.

---

## 4 — Documentation à lire (par ordre de priorité)

### 4.1 Avant la première session de code

1. **[`CLAUDE.md`](../CLAUDE.md)** (à la racine) — Référence complète du produit, architecture, conventions, règles absolues
2. **[`docs/SOMMAIRE_DETAILLE.md`](SOMMAIRE_DETAILLE.md)** — Index maître de toute la documentation
3. **[`docs/PLUS_TARD_VF.md`](PLUS_TARD_VF.md)** — Backlog des sujets à traiter
4. **Annexe Mission n° 1** signée — Périmètre précis et critères d'acceptation de TA mission

### 4.2 Avant de toucher au code V2

5. **[`audit/INVARIANTS.md`](../audit/INVARIANTS.md)** — Règles techniques opposables (code multi-tenant, clés canoniques, sécurité, etc.)
6. **[`audit/ANOMALIES_RECURRENTES.md`](../audit/ANOMALIES_RECURRENTES.md)** — Patterns de bugs identifiés sur le projet (pour ne pas les reproduire)
7. **[`audit/PLAYBOOK.md`](../audit/PLAYBOOK.md)** — Procédures (Workflow 4 diagnostic bug, Workflow 7 fin de session, etc.)

### 4.3 Pour comprendre l'historique récent

8. **`docs/sessions/OUTLOOK_BILAN_SESSION_*.md`** — Bilans des sessions de dev récentes (lire les 3 derniers)
9. **[`docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md`](outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md)** — Workflow OVH-first (depuis 27/04/2026, OVH est la version officielle)

### 4.4 Pour les missions spécifiques (à lire selon scope)

10. **[`docs/specs_proto/`](specs_proto/)** — Specs détaillées des fonctionnalités (R/S/H, scoring rédactionnel, profils contacts, etc.)
11. **[`docs/v2_specs/`](v2_specs/)** — Specs V2 (Phase 2, refonte UI, plan finalisation)
12. **[`docs/saas/`](saas/)** — Documentation infrastructure SaaS

---

## 5 — Conventions de code

### 5.1 Backend (Python)

- **Langue** : commentaires et noms de variables en français
- **Threading** : tout appel Outlook COM passe par `com_run()` (côté proto uniquement, V2 utilise Microsoft Graph)
- **DB** : `V2/database.py` (`Database` class) — toujours utiliser ses méthodes plutôt que des requêtes SQL directes
- **Imports** : `sys.path.insert(0, PLUGIN_DIR)` avant tout import local pour V2 (cohérence imports `V2/`)
- **Logging** : utiliser `logger = logging.getLogger('easymail.v1')`, pas de `print()`
- **Pas de modification de `app.py`, `claude_ai.py`, `outlook_com.py`, `templates/` (proto LECTURE SEULE)**

### 5.2 Frontend (HTML/CSS/JS)

- **Vanilla JS uniquement** — pas de framework (React, Vue, etc.)
- **Cache busting** : à chaque modification d'un `.js`/`.html`, bumper `_ADDIN_VERSION` dans `V2/autorunshared.js` ET le `?v=` dans `V2/autorun.html` + `V2/dialog.html`. Convention : `vN-fix-<sujet>-<JJ-MM>` (les deux doivent matcher).
- **No-cache** : tous les HTML doivent avoir les headers `Cache-Control: no-store, no-cache, must-revalidate`

### 5.3 Tests

- Le smoke test `audit/tests/smoke_test.ps1` doit passer 10/10 avant toute PR
- Pour les changements UI : captures avant/après dans la PR

---

## 6 — Outils recommandés

### 6.1 Claude Code (recommandé)

[Claude Code](https://www.claude.com/product/claude-code) est l'outil d'assistance IA en ligne de commande. Il lit automatiquement le `CLAUDE.md` du projet, ce qui te donne **un contexte complet du projet sans avoir à le réexpliquer à chaque session**.

- **Plan minimum recommandé** : Pro ($20/mois) ou Max selon volume
- **À noter** : ta licence est personnelle. Si elle est facturée à PDLConsulting selon le contrat, le mode de remboursement est précisé dans l'Annexe Mission. Si elle est à ta charge, c'est ton choix d'outils.
- **Conventions de sécurité** : le plan Pro/Max inclut un opt-out par défaut pour l'entraînement des modèles. Vérifier dans Settings → Privacy.

### 6.2 IDE

- **VS Code** : recommandé, gratuit, extensions Python + Pylance + GitLens utiles
- **Cursor** : alternative IA-native si tu préfères
- **JetBrains PyCharm** : aussi très bien

### 6.3 Outils Outlook

- **Office Add-ins Validator** : `npm install -g office-addin-manifest` pour valider le manifest XML
- **F12 Tools** : Ctrl+Maj+I dans la modale pour devtools (Edge WebView2)

---

## 7 — INTERDITS absolus

Ces règles découlent du NDA, du Contrat de prestation et de la Charte de sécurité informatique. Toute violation peut entraîner la résiliation immédiate du Contrat (art. 13.3 du Contrat).

### 7.1 Accès systèmes

- ❌ **Aucun accès SSH au VPS OVH** (`51.178.162.208`) — seul le client (Yvan) y a accès. Si tu as besoin de logs, demande à Yvan.
- ❌ **Aucun accès à la DB de production** (`/opt/boostermail/V2/boostermail.db` sur OVH)
- ❌ **Aucun accès au panel OVH Cloud, à la console Anthropic, à Sentry production, à UptimeRobot, à Stripe, à Azure portal**
- ❌ **Pas de modification du `config.json` de production** (clés API, secrets Microsoft, fernet_key)

### 7.2 Manipulation du code

- ❌ **Pas de fork du repo BoosterMail vers un compte GitHub public**
- ❌ **Pas de copie du code dans un service tiers public** (gist, pastebin, snippets de blog, ChatGPT/Claude.ai grand public sans opt-out)
- ❌ **Pas de force-push sur des branches partagées** (`master`, autres branches `feat/*` partagées)
- ❌ **Pas de modification de `app.py`, `claude_ai.py`, `outlook_com.py`, `templates/` (proto LECTURE SEULE — bêta-testeurs en production)**

### 7.3 IA générative

- ❌ **Pas de copie de code BoosterMail dans une IA grand public** (ChatGPT, Claude.ai, Gemini, Mistral Le Chat dans leurs versions grand public) — cf. NDA art. 2.7. Utiliser uniquement des outils avec opt-out d'entraînement (Claude Code, GitHub Copilot Business, ChatGPT Enterprise/Team, etc.)
- ❌ **Pas d'usage des données BoosterMail (code, emails, profils utilisateurs) pour entraîner un modèle d'IA** — cf. NDA art. 2.6

### 7.4 Communication externe

- ❌ **Pas de publication LinkedIn / GitHub / portfolio mentionnant BoosterMail ou PDLConsulting** sans accord écrit (cf. Contrat art. 4.8) — ni pendant le Contrat, ni dans les 24 mois qui suivent
- ❌ **Pas de mention de BoosterMail dans tes devis, propositions commerciales, CV** sans accord

### 7.5 Données personnelles

- ❌ **Pas de copie / téléchargement / export de données utilisateurs réels du SaaS**, sauf signature préalable d'un DPA (annexe 5 du pack juridique) et accord écrit explicite pour la mission concernée
- ❌ **Pas de lecture des logs de production contenant des emails utilisateurs**
- ✅ **Utiliser des jeux de données factices ou anonymisées en local pour les tests**

---

## 8 — Communication et suivi

### 8.1 Canaux

- **Email** : pour échanges officiels (factures, livraisons formelles, notifications juridiques)
- **Slack / WhatsApp** : à convenir au démarrage pour échanges opérationnels quotidiens
- **GitHub PR** : pour reviews techniques (privilégier les commentaires inline aux discussions séparées)

### 8.2 Fréquence

- **Quotidien** : court point Slack ou message asynchrone (avancement + blocages)
- **Hebdomadaire** : visio 30 min de point d'avancement (calendrier convenu au démarrage)
- **Urgences** : appel téléphonique si bloqueur > 1h ou découverte de bug critique

### 8.3 Confidentialité

- ⚠️ Pas d'extraits de code, captures, ou documentation envoyés dans des messageries non sécurisées (SMS, Telegram en clair, etc.) — cf. Charte sécurité art. 6.2
- Pour transférer des fichiers sensibles : préférer un partage GitHub privé ou un transfert chiffré

---

## 9 — Première mission : où chercher

L'Annexe Mission n° 1 te donne :

- L'**objectif business** de la mission
- Le **périmètre fonctionnel** (ce qui doit être fait)
- Le **périmètre technique** (fichiers concernés, environnements)
- Les **livrables attendus** avec dates
- Les **critères d'acceptation** (recette)
- Le **calendrier** prévisionnel
- Les **conditions particulières** (accès, restrictions)

Avant de commencer à coder, **lis d'abord** :

- L'Annexe Mission complète
- Les sections de `CLAUDE.md` qui concernent ta mission
- Les invariants `audit/INVARIANTS.md` qui touchent ton scope (notamment `I-CODE-05` multi-tenant si ta mission concerne ce sujet)
- Les patterns `audit/ANOMALIES_RECURRENTES.md` à éviter

Pose tes **questions tôt et fréquemment** — la pire erreur est de coder une semaine sur une mauvaise compréhension du scope.

---

## 10 — Premiers jours : checklist

- [ ] Compte GitHub Collaborator activé sur le repo
- [ ] Repo cloné en local
- [ ] `config.json` créé et configuré avec tes clés perso
- [ ] V2 lancé en local et accessible sur `https://localhost:3443`
- [ ] Add-in side-loadé dans Outlook et fonctionnel
- [ ] `CLAUDE.md` lu en entier
- [ ] Annexe Mission n° 1 lue et comprise
- [ ] Premier point d'avancement avec PDLConsulting (Yvan) calé
- [ ] Premier commit/PR de prise en main faite (par exemple : amélioration mineure de la doc, ou un commentaire pertinent dans le code)

---

## 11 — Aide et escalade

| Problème | Solution |
|---|---|
| Setup local cassé (V2 ne démarre pas) | Vérifier `config.json` complet, dépendances installées, certs générés. Sinon : Slack/email à Yvan |
| Bug rencontré dans le code existant | Documenter dans une issue GitHub avec reproduction. Discuter en review |
| Compréhension de spec floue | Demander immédiatement par message asynchrone (pas attendre la visio hebdo) |
| Suspicion de bug sécurité | **Notifier dans les 24h** par email à `security@boostermail.ai` (cf. NDA art. 2.1.f) |
| Conflit d'intérêt potentiel détecté | Notifier par écrit à `legal@boostermail.ai` (cf. Contrat art. 4.7) |
| Incident de sécurité (perte appareil, malware, fuite suspectée) | **Notifier dans les 24h** par email à `security@boostermail.ai` (cf. Charte sécurité art. 7.1) |

En cas de doute, **toujours demander avant de prendre l'initiative**. Le coût de quelques messages est largement inférieur au coût d'un développement à refaire.

---

## 12 — Bienvenue à bord

L'objectif est que tu sois autonome et productif rapidement, tout en respectant les protections juridiques et techniques que nous avons mises en place. Cette doc est vivante : si quelque chose te semble flou, manquant ou erroné, propose une PR `docs/<ton_nom>/clarify-onboarding`.

Bonne mission.

— Yvan BOSSER, PDLConsulting
