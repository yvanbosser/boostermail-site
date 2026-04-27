# BoosterMail — Spec Installation Commerciale

> **Dernière mise à jour** : 26/04/2026

*Cree le 16/04/2026*

---

## Etat actuel (beta-testeurs)

ZIP de 236 Ko contenant le proto. L'utilisateur doit :
1. Installer Python 3 manuellement
2. Creer un compte Anthropic + obtenir une cle API
3. Editer config.json (JSON brut)
4. Lancer start.bat

Problemes : Python requis, cle API a obtenir, config.json a editer, pas d'installeur, pas de plugin Outlook V2.

### ATTENTION — fichiers a EXCLURE du ZIP beta-testeurs

Le ZIP ne doit PAS contenir les fichiers personnels du developpeur :
- `style_profile.txt` → EXCLURE (le style du dev, pas celui du testeur)
- `emails.db` / `boostermail.db` → EXCLURE (les mails/contacts du dev)
- `prefetch_cache.json` → EXCLURE (cache du dev)
- `drafts_v2.json` → EXCLURE (brouillons du dev)
- `config.json` → INCLURE mais avec "COLLER_ICI" (pas la vraie cle)

L'onboarding se lancera automatiquement au premier demarrage car style_profile.txt est absent.

---

## Contraintes identifiees pour le lancement commercial

### A. Systeme (BLOQUANTS)

| # | Contrainte | Solution | Effort |
|---|-----------|----------|--------|
| A1 | Python absent chez l'utilisateur | Packaging PyInstaller/Nuitka (exe autonome) | 3-5 jours |
| A2 | SmartScreen bloque l'exe non signe | Certificat EV Code Signing (~500 EUR/an) | 1-2 jours |
| A3 | Pare-feu bloque port 3443 | Regle firewall auto dans l'installeur | 0.5 jour |
| A4 | Droits admin pour certificat HTTPS | Installeur s'execute en admin (UAC prompt) | 1 jour |
| A5 | Port 3443 deja occupe | Detection + message d'erreur clair | 1 jour |
| A6 | OneDrive corrompt SQLite | Forcer install hors OneDrive (C:\BoosterMail) | 0.5 jour |

### B. Outlook / Microsoft (BLOQUANTS)

| # | Contrainte | Solution | Effort |
|---|-----------|----------|--------|
| B1 | Installation manifest (consentement obligatoire) | Sideload guide / Admin deploy / AppSource | Deja documente |
| B2 | OAuth2 admin consent en entreprise | Consent incremental + guide admin | 2-3 jours |
| B3 | Comptes perso outlook.com | Tester exhaustivement | 1 jour |
| B4 | Exchange On-Premise (pas de Graph) | Cibler M365 uniquement | Decision |
| B5 | Versions Outlook anciennes (2016/2019) | Matrice de compatibilite + tests | 2-3 jours |
| B6 | New Outlook (migration en cours) | Architecture V2 Graph API (en cours) | En cours |

### C. IA / API (BLOQUANTS)

| # | Contrainte | Solution | Effort |
|---|-----------|----------|--------|
| C1 | Cle API chez l'utilisateur | Proxy API central (l'utilisateur n'a pas de cle) | 3-5 jours + serveur |
| C2 | Cout API ~60-120 EUR/mois/user actif | Tiering modeles (Haiku R, Sonnet S/H) + cache | 3-5 jours |
| C3 | RGPD (mails envoyes a Anthropic US) | DPA Anthropic + consentement explicite + mentions legales | 2-3 jours |

### D. Deploiement

| # | Contrainte | Solution | Effort |
|---|-----------|----------|--------|
| D1 | 50 PC = 50 backends locaux | Hybride : proxy API central + backend local pour le manifest | 8-12 jours |
| D2 | Mises a jour automatiques | Auto-updater (Squirrel/WinSparkle) | 2-3 jours |
| D3 | Support utilisateur | Page diagnostic /api/health + logs anonymises | 3-5 jours |
| D4 | Desinstallation propre | Installeur MSI/NSIS avec desinstalleur | 1-2 jours |

### E. Commercial

| # | Contrainte | Solution | Effort |
|---|-----------|----------|--------|
| E1 | Certificat signature code | EV Code Signing ~500 EUR/an | Achat |
| E2 | AppSource (exige backend cloud, pas localhost) | Backend 100% cloud a terme | 15-30 jours |
| E3 | Concurrence Copilot M365 | Differenciateurs : style perso, profils contacts, scoring | Strategie |

---

## Chemin critique vers le lancement MVP

1. **Proxy API** (C1) — l'utilisateur n'a plus de cle API
2. **Packaging exe** (A1) — l'utilisateur n'installe pas Python
3. **Certificat EV** (E1) — SmartScreen ne bloque plus
4. **RGPD** (C4) — conformite europeenne
5. **Guide admin consent** (B2) — les PME peuvent installer
6. **Installeur automatique** — setup.exe fait tout

Total : ~15-20 jours de dev + ~1000 EUR/an de couts fixes

---

## Parcours cible utilisateur unique

```
1. Va sur boostermail.ai → telecharge setup.exe
2. Double-clic → UAC "Autoriser" → installation automatique
3. Ouvre Outlook → l'installeur a ouvert la page "Ajouter complement"
4. Clic "Installer BoosterMail" → bouton BM apparait
5. Clic bouton BM → connexion Microsoft (SSO, souvent 0 mot de passe)
6. Onboarding 2 min en fond → pret
```

## Parcours cible PME (10 personnes)

```
1. Le dirigeant teste sur son poste (parcours ci-dessus)
2. Satisfait → il va sur admin.microsoft.com
3. Il deploie le manifest pour son equipe (4 clics, 2 min)
4. Il envoie un mail a son equipe : "Installez setup.exe depuis ce lien"
5. Chaque collaborateur installe en 2 min
```
