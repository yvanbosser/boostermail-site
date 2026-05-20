# SPEC — Audit de boîte mail BoosterMail

> **Statut** : 🟡 Cadrage produit terminé, à mettre en chantier
> **Date de cadrage** : 12/05/2026 (session conception Yvan)
> **Branche** : `feat/yvan/frontend`
> **À destination de** : équipe BoosterMail (Yvan + Michael), pour cadrage commun avant codage
> **Documents liés** :
> - [docs/PLUS_TARD_VF.md](../PLUS_TARD_VF.md) — bloc 12/05/2026 (décisions tranchées de la session)
> - [docs/specs_proto/SPEC_ARBRE_DECISIONNEL.md](SPEC_ARBRE_DECISIONNEL.md) — moteur `_is_discarded` à enrichir
> - [docs/specs_proto/SPEC_CLASSEMENT_BOOSTERMAIL.md](SPEC_CLASSEMENT_BOOSTERMAIL.md) — feature classement existante
> - [docs/architecture/V12/v12 _ spec - mission audit complet.md](../architecture/V12/v12%20_%20spec%20-%20mission%20audit%20complet.md) — **chantier différé** (proposition d'arborescence personnalisée + classement bulk), cadrage démarré 20/05/2026, déplacé dans le dossier V12

---

## 1. Vision produit

### Pourquoi cette feature

Trois objectifs d'origine pour la feature « audit boîte mail » :

1. **Permettre aux utilisateurs dont la boîte mail est devenue le bordel de repartir sur une base propre.**
2. **Permettre à un employeur d'harmoniser les boîtes mail de ses collaborateurs** — chacun avec quasiment la même arborescence, ce qui facilite la reprise en cas de départ d'un collaborateur (argument de vente fort côté licence pro).
3. **Optimiser le fonctionnement de BoosterMail lui-même**, qui fonctionne mieux avec une arborescence bien organisée.

### Scope MVP arrêté

Sur les 3 sous-features initialement envisagées (doublons + analyse arborescence + proposition d'arborescence optimisée), **seul le volet "nettoyage de bruit" est conservé pour le MVP**. La proposition d'arborescence optimisée est différée — chantier à part entière trop complexe pour être traité dans la même mise en chantier.

**Le MVP couvre 6 catégories de "bruit"** identifiables avec faible taux de faux positifs :

| # | Catégorie | Définition | Détection |
|---|---|---|---|
| 1 | **Doublons** | Mails strictement identiques (niveaux 1 et 2 uniquement) | Niveau 1 = même `Message-ID`. Niveau 2 = même expéditeur + même sujet + hash corps normalisé identique. |
| 2 | **Spams confirmés** | Mails déjà dans le dossier Junk/Courrier indésirable d'Outlook | L'user (ou Outlook) a déjà tranché — on ne fait que continuer |
| 3 | **Mails techniques périmés** | Codes 2FA, liens de réinit MdP, liens de vérif d'inscription | Patterns expéditeur (no-reply@, etc.) + mots-clés sujet/corps + ancienneté > 30j |
| 4 | **Invitations calendrier passées** | Invitations à des réunions ayant eu lieu il y a > 30j | Type MIME / patterns + date de réunion extraite |
| 5 | **Newsletters / pubs** | Mails marketing légitimes | Header `List-Unsubscribe` + expéditeurs `news@`, `newsletter@`, etc. |
| 6 | **Notifications réseaux sociaux** | LinkedIn, Facebook, Twitter, etc. | Expéditeurs typés (notifications-noreply@linkedin.com, etc.) |

### Différé / hors scope MVP

- **Proposition d'arborescence optimisée** (analyse + suggestion + drag&drop user) — chantier à part entière.
- **Doublons de niveau 3** (mail A cité intégralement dans la réponse B) — risque trop élevé de perte d'info (PJ différentes, statut lu/non-lu, chronologie).
- **Quasi-doublons** (newsletters récurrentes identiques sauf date) — autre feature de "nettoyage de bruit".
- **Mails jamais ouverts depuis > X mois** — trop risqué (user peut ne pas utiliser l'aperçu).
- **Mails avec grosses PJ anciennes** — gain d'espace mais faux positifs possibles (PJ légales, contrats).
- **Mode admin/employeur** (template d'arborescence imposé sur 3 niveaux + déploiement multi-user + harmonisation) — évoqué dans la session mais reporté au chantier "arborescence".

---

## 2. Principe directeur : « moins supprimer que trop »

**Règle absolue** : sur toute action de masse, BoosterMail penche systématiquement du côté **sous-action** plutôt que sur-action.

- Aucun mail n'est supprimé ou déplacé sans validation explicite de l'user (sauf cas où l'user a déjà tranché en amont via paramétrage).
- Quand on hésite entre deux seuils de détection, on choisit le plus conservateur.
- Faux négatif (un peu de bruit qui reste) >>> faux positif (mail légitime perdu).

→ Cf [feedback_prudence_suppression](../../../Users/yvanb/.claude/projects/C--EasyMail/memory/feedback_prudence_suppression.md) (mémoire Claude).

---

## 3. Deux types d'audit distincts

### 3.1 Audit ponctuel (chantier événementiel)

**Analogie** : grand ménage de printemps. On vide, on trie, on reconstruit propre.

- **Déclenchement** : l'user clique « Lancer un audit complet » dans le dashboard. À tout moment de son choix.
- **Périmètre** : scan complet du stock existant (potentiellement 10 000+ mails).
- **Granularité** : par défaut toute la boîte, mais possibilité de **restreindre à un sous-arbre** (ex : « audite juste mon dossier Clients »).
- **Durée** : plusieurs dizaines de minutes minimum sur grosse boîte (throttling Microsoft Graph).
- **UX pendant le scan** :
  - Dialog Office **fermable**, scan continue en arrière-plan côté backend SaaS.
  - Si Outlook ferme, état sauvegardé backend, reprise au redémarrage.
  - **Notification dans Outlook à la fin** : « Audit terminé, ouvrir le dashboard pour voir le rapport ».
- **Sortie** : rapport affiché dans la zone "audit ponctuel" du dashboard (cf §5).

### 3.2 Audit permanent (flux continu)

**Analogie** : passer un coup de balai tous les jours. Maintient l'état propre obtenu après le grand ménage.

- **Activation** : automatique dès l'installation de BoosterMail, sur tous les nouveaux mails reçus à partir de ce moment-là. Aucune feature à activer par l'user.
- **Périmètre** : flux entrant (nouveaux mails) + balayage périodique sur les mails déjà reçus pour les catégories à péremption temporelle.
- **Action immédiate** : **aucun déplacement automatique**. Le mail reste dans l'Inbox, posé avec une **catégorie Outlook visible** (« BoosterMail: Newsletter », etc.).
- **Action différée** : l'user reçoit des rappels périodiques (cf §7) pour traiter les paquets accumulés.

---

## 4. Architecture

### 4.1 Client (add-in Outlook)

- **UI dans Dialog Office** (intégrée à l'add-in, pas de page web séparée — décision Michael).
- **Pas de traitement temps réel** sur les mails entrants côté client.
- Sert uniquement à : afficher le dashboard, lancer l'audit ponctuel, afficher les popups par catégorie, gérer les cases à cocher, appliquer les actions Supprimer/Déplacer.

### 4.2 Backend SaaS (indispensable pour mode permanent)

- **Webhook Microsoft Graph** sur chaque boîte mail user inscrite : notification à chaque nouveau mail entrant → analyse côté serveur → pose du flag (catégorie Outlook) via Microsoft Graph API.
- **Balayage périodique quotidien** (cron 3h-5h UTC) pour les catégories à péremption temporelle (mails techniques J+30, invitations J+30 post-réunion). Ne re-scanne pas toute la boîte : uniquement les mails qui pourraient avoir franchi un seuil depuis hier.
- **Persistance des décoches** (apprentissage, cf §6).
- **Persistance des compteurs** par catégorie (zone permanente + zone ponctuelle, cf §5).

> **Note importante pour Michael** : le backend SaaS, qui était optionnel pour le mode ponctuel (le scan peut tourner depuis le client), devient **indispensable** pour le mode permanent. Sans backend, un user qui ferme Outlook le vendredi soir et reçoit 200 mails le week-end retrouve une Inbox bordélique le lundi.

### 4.3 Moteur de détection : enrichir `_is_discarded`

Un concept "mail écarté" existe déjà dans BoosterMail ([V2/app_plugin.py:5860](../../V2/app_plugin.py)) : `_is_discarded(mail_data)` décide si BM va pré-cuisiner une réponse pour ce mail ou pas. Aujourd'hui un mail est écarté si body < 10 caractères sans `?`, mail déjà répondu, etc.

**Décision** : enrichir `_is_discarded` avec les nouvelles catégories de l'audit, plutôt que créer un moteur parallèle. Un seul filtre, deux usages :
- **Interne** (existant) : pas de pré-cuisinage de réponse pour les mails écartés.
- **Externe** (nouveau) : flag/déplacement visible pour l'user.

Tout mail identifié comme spam/doublon/newsletter/etc. est par définition un mail "pour lequel on ne génère pas de réponse" — la logique est cohérente.

---

## 5. Dashboard — 2 zones distinctes

Le dashboard BoosterMail (que Michael bâtit sur `feat/michael/multi-user`) affiche deux zones nettement séparées avec **les mêmes 6 catégories mais des chiffres différents**. Les compteurs ne se mélangent **jamais** : chaque zone a sa propre vie.

### 5.1 Zone permanente (par défaut, visible à l'ouverture)

Compteurs continus, mis à jour au fil de l'eau depuis l'installation de BoosterMail.

```
╔════════════════════════════════════════════════╗
║  ZONE PERMANENTE — depuis l'installation BM    ║
║                                                ║
║  🚫 Spams identifiés          :    47          ║
║  📋 Doublons identifiés       :     8          ║
║  📰 Newsletters identifiées   :   312          ║
║  🔔 Notifications réseaux     :   124          ║
║  🔐 Mails techniques périmés  :     6          ║
║  📅 Invitations passées       :    11          ║
║                                                ║
║  📅 Prochain rappel hebdo : 19/05/2026         ║
╚════════════════════════════════════════════════╝
```

### 5.2 Zone audit ponctuel (chantier explicite)

État initial (aucun audit lancé) :

```
╔════════════════════════════════════════════════╗
║  ZONE AUDIT PONCTUEL                           ║
║                                                ║
║  Dernier audit lancé : aucun                   ║
║  [ ▶ Lancer un audit complet de la boîte ]     ║
╚════════════════════════════════════════════════╝
```

Après un audit ponctuel terminé :

```
╔════════════════════════════════════════════════╗
║  ZONE AUDIT PONCTUEL                           ║
║                                                ║
║  Audit du 15/05/2026 — terminé                 ║
║                                                ║
║  🚫 Spams trouvés dans le stock  : 1 853       ║
║  📋 Doublons trouvés             :   247       ║
║  📰 Newsletters trouvées         : 3 412       ║
║  🔔 Notifications anciennes       : 1 089       ║
║  🔐 Mails techniques périmés     :   156       ║
║  📅 Invitations passées          :   389       ║
║                                                ║
║  [ Voir le détail par catégorie ]              ║
║  [ ▶ Relancer un audit complet ]               ║
╚════════════════════════════════════════════════╝
```

**Notification spécifique à la fin du chantier ponctuel** : « Audit terminé, X mails identifiés répartis en 6 catégories. Ouvrir le dashboard pour traiter les paquets. »

---

## 6. Workflow user uniforme via popup

Le même workflow s'applique aux deux zones du dashboard : un clic sur une catégorie (ex : "Spams") ouvre une popup qui liste les mails identifiés.

### 6.1 Popup standard (spams, mails techniques, invitations, newsletters, notifications)

- Affichage **chronologique** (du plus ancien au plus récent, ou inverse — à confirmer mise en chantier).
- **Cases à cocher**, toutes **pré-cochées par défaut**.
- Sémantique unifiée : **coché = sera supprimé/déplacé, décoché = reste dans l'Inbox**.
- L'user peut **décocher** un mail pour le préserver (= signaler un faux positif).
- 2 boutons d'action en bas de la popup :
  - **Supprimer** (définitivement)
  - **Déplacer dans `_BoosterMail_Audit/<catégorie>`** (sous-dossier dédié)

### 6.2 Cas particulier des doublons

Les doublons sont affichés en **paquets visuels** (interligne marquée entre paquets) :

```
[Paquet 1] Decathlon — Promo flash
  ☐  12/03/2026   ← le plus ancien, décoché par défaut (= conservé)
  ☑  14/03/2026   ← pré-coché (= sera supprimé)
  ☑  15/03/2026   ← pré-coché (= sera supprimé)

[Paquet 2] Stéphane Dufau — Re: projet X
  ☐  03/04/2026
  ☑  04/04/2026
```

**Sémantique cohérente avec les autres catégories** : coché = ce qui part. Le plus ancien est décoché par défaut (= conservé), les exemplaires plus récents sont pré-cochés (= supprimés). L'user peut inverser : décocher le plus récent et cocher le plus ancien si c'est l'inverse qu'il veut conserver.

**Règle de pré-sélection automatique** : si plusieurs exemplaires existent, BM pré-décoche celui qui est :
1. Déjà rangé dans un sous-dossier (pas dans Inbox) — il a été classé par l'user, donc « jugé important ».
2. Sinon, celui avec un drapeau / catégorie / statut Important.
3. Sinon, le plus ancien.

---

## 7. Notifications hebdomadaires et saturation

### 7.1 Rappel hebdomadaire

Cron côté backend SaaS : une fois par semaine, BM vérifie les mails accumulés en mode permanent depuis le dernier nettoyage, **âgés de plus de 7 jours**. S'il y en a, notification :

> *« Vous avez X spams âgés de plus de 7 jours, voulez-vous les supprimer ? »*

Le délai de 7 jours laisse le temps à l'user de repérer un éventuel faux positif avant d'être sollicité pour suppression.

### 7.2 Alerte de saturation

Si un sous-dossier de `_BoosterMail_Audit` dépasse un seuil de volume (à définir à la mise en chantier, configurable), alerte d'urgence :

> *« Votre dossier spams est saturé (XXXX mails > 7 jours), confirmer la suppression ? »*

---

## 8. Apprentissage des faux positifs

Chaque case **décochée** par l'user (« ce n'est pas un spam », « cette newsletter, je la veux ») est **mémorisée côté backend SaaS** :
- Clé : `(expéditeur, catégorie)`.
- Effet : les futurs mails du même expéditeur ne seront plus signalés dans cette même catégorie.
- Persistance par catégorie × expéditeur, suit l'user entre machines.

**Cette logique est ce qui rend l'outil intelligent au fil du temps** plutôt qu'un moteur statique. Sans elle, l'user se voit re-proposer les mêmes faux positifs à chaque cycle.

À designer plus précisément à la mise en chantier (ex : faut-il aussi mémoriser les cases qui restent cochées sans action comme validation tacite ? Ou seulement les décoches actives ?).

---

## 9. Péremption temporelle (J+30 harmonisée)

Pour les catégories à péremption temporelle, seuil unique : **30 jours**.

| Catégorie | Déclencheur de péremption |
|---|---|
| Mail technique (code 2FA, lien réinit MdP, lien vérif inscription) | J+30 post-réception, quoi qu'il arrive (ouvert/cliqué ou non — décision Yvan 12/05) |
| Invitation calendrier | J+30 post-date de la réunion, sans distinction répondue / non répondue |

Le balayage périodique quotidien (3h-5h UTC) vérifie quels mails ont franchi ce seuil depuis la veille et les flague.

---

## 10. Sous-dossiers de quarantaine

Quand l'user clique « Déplacer » sur une catégorie, les mails partent dans un sous-dossier dédié, à côté de l'Inbox :

```
📁 _BoosterMail_Audit
   ├── 📁 Doublons
   ├── 📁 Spams
   ├── 📁 Mails techniques
   ├── 📁 Invitations passées
   ├── 📁 Newsletters et pubs
   └── 📁 Notifications réseaux
```

Préfixe `_` pour que le dossier apparaisse en haut de la liste (tri alphabétique).

**Comportement** :
- Quand un sous-dossier est vidé (l'user a tout traité), il **disparaît automatiquement**.
- Quand tous les sous-dossiers sont vides, le dossier parent `_BoosterMail_Audit` disparaît aussi.

**Cas user qui sort un mail manuellement du dossier** (drag vers Inbox) : à traiter comme un signal d'apprentissage (= faux positif). Mécanisme à designer à la mise en chantier — sans doute via custom property Outlook sur le mail (qui survit même si l'user désinstalle BoosterMail) ou via mapping Message-ID stocké côté backend SaaS.

---

## 11. Décisions tranchées en session 12/05/2026

Ordre chronologique (du début à la fin de la session) :

| # | Décision | Tranchée par |
|---|---|---|
| 1 | Audit accessible depuis le dashboard utilisateur (Michael) — pas un onboarding obligatoire, outil à la demande | Yvan |
| 2 | Persistance des préférences user/admin côté backend SaaS (suit entre machines) | Yvan |
| 3 | Phases distinctes : audit doublons + audit autres catégories indépendants | Yvan |
| 4 | Granularité possible : auditer un sous-arbre, pas forcément toute la boîte | Yvan |
| 5 | Arborescence optimisée DIFFÉRÉE (chantier à part entière) | Yvan |
| 6 | Vue intégrée à l'add-in Outlook (Dialog Office), pas page web séparée | Michael |
| 7 | Principe « moins supprimer que trop » (mémoire feedback) | Yvan |
| 8 | Scope MVP = 6 catégories (doublons, spams, mails techniques, invitations, newsletters, notifications) | Yvan |
| 9 | Sous-dossiers dédiés par catégorie (option B, pas mélange) | Yvan |
| 10 | Mode permanent activé automatiquement dès l'installation, sur les nouveaux mails reçus à partir de ce moment | Yvan |
| 11 | Réutiliser le moteur `_is_discarded` enrichi (pas de moteur parallèle) | Yvan (Option A) |
| 12 | Balayage périodique côté backend, quotidien 3h-5h UTC | Yvan |
| 13 | Mail technique périmé à J+30 (même si ouvert/cliqué) | Yvan |
| 14 | Invitation passée périmée à J+30 (sans distinction répondue/non répondue) | Yvan |
| 15 | Aucun auto-déplacement de mail entrant en mode permanent — flag visible uniquement | Yvan |
| 16 | Workflow user uniforme via popup dashboard avec cases pré-cochées | Yvan |
| 17 | Sémantique unifiée : coché = ce qui part, décoché = reste dans Inbox (piste 1) | Yvan |
| 18 | Doublons affichés en paquets (3 lignes avec interligne marquée), le plus ancien décoché par défaut | Yvan |
| 19 | Mémorisation des décoches comme apprentissage (par expéditeur × catégorie) | Yvan |
| 20 | Dashboard structuré en 2 zones distinctes (permanente + ponctuelle), compteurs séparés | Yvan |
| 21 | Notifications hebdomadaires de nettoyage + alerte saturation | Yvan |
| 22 | UX scan ponctuel : Dialog fermable, scan continue backend, notif à la fin | Yvan |

---

## 12. Points à finaliser avant codage

Cf [docs/PLUS_TARD_VF.md](../PLUS_TARD_VF.md) bloc 12/05/2026 pour le détail. Synthèse :

- **Intégration concrète dans le dashboard de Michael** (structure, endpoints, où poser les 2 zones).
- **Seuils chiffrés** : taille de la popup avant pagination ? Seuil exact de saturation dossier (configurable user ? volume vs nombre de mails) ?
- **Cadence notification hebdo** : fixe ou configurable (mensuel pour les users qui en reçoivent peu) ?
- **Mocks UI précis** des popups, notamment pour les newsletters (regroupement par expéditeur ? filtres rapides ?).
- **Apprentissage** : faut-il mémoriser les cases qui restent cochées sans action comme validation tacite, ou seulement les décoches actives ?
- **Custom property Outlook vs backend** : pour mémoriser le dossier source d'un mail déplacé (si user le sort à la main, on doit pouvoir le remettre à sa place d'origine).

---

## 13. Mode admin/employeur (DIFFÉRÉ — rattaché au chantier arborescence)

Cette dimension a été évoquée en session 12/05 mais **reportée** au chantier "arborescence optimisée" qui est lui-même différé.

Idée à retenir pour quand on l'attaquera :

- Modèle envisagé : système avec un interrupteur « gouvernance admin » optionnel.
  - **Admin ON** : template d'arborescence imposé sur 3 niveaux + personnalisation libre en dessous.
  - **Admin OFF** (ou pas d'admin du tout, user solo) : BoosterMail suggère, l'user décide tout.
- 3 sources de template admin envisagées (par ordre de priorité) :
  1. BoosterMail analyse les boîtes existantes des collaborateurs (snapshots légers des structures) et propose un template harmonisé.
  2. Templates métier pré-faits (cabinet d'avocats, agence com, e-commerce, etc.).
  3. Saisie manuelle.
- Argument business : ce que l'employeur achète n'est pas « ranger les mails » mais « pouvoir reprendre la boîte d'un collaborateur qui part en 10 minutes parce que tout le monde est organisé pareil ». Justifie une licence pro plus chère.

→ À reprendre lors de la mise en chantier de la feature arborescence.
