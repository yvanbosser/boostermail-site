# PLUS TARD — Idees et ameliorations a traiter ulterieurement

*Cree le 14/04/2026 — Mis a jour le 16/04/2026*

---

## 1. Pop-up post-envoi unifiee (UX)

Regrouper les 4 pop-ups post-envoi en une seule avec sections depliables.

---

## 2. Bouton "Boite de reception" BoosterMail

Creer une inbox V2 (n'existe pas encore). Le proto a templates/inbox.html.

---

## ~~3. Speculation — charger le body complet en arriere-plan~~ FAIT (16/04/2026)

Implemente : le preload BG appelle graph.get_email_by_id() + _html_to_text() pour chaque mail echantillonne. Le body complet (3000 chars max) est utilise pour la speculation.

---

## 4. Modele IA moins cher pour le resume

Tester Claude Haiku 4 quand disponible.

---

## ~~5. Lancement instantane au demarrage Windows~~ FAIT (16/04/2026)

Implemente : boostermail_service.py (superviseur) + tache planifiee AtLogOn.
Le superviseur detecte Outlook (fenetre visible via EnumWindows), affiche la popup marketing tkinter, lance les backends.
Cycle : Outlook ferme → backends arretes → Outlook rouvre → popup + backends relances.

---

## 6. Test Classic Outlook et Outlook Web

Tester bouton ruban, Companion COM, extension Chrome overlay.

---

## ~~7. Phase 3 — Post-envoi complet~~ FAIT (16/04/2026)

Recalibrage adaptatif, re-analyse contacts, categorisation corrections — tout implemente.

---

## ~~8. Phase 4 — Onboarding complet via Graph API~~ FAIT (16/04/2026)

300 envoyes + 500 recus via Graph, paires, corpus, Claude, scoring, indexation — teste et valide (84/100 N9).

---

## 9. Rangement du projet V2

Les fichiers V2 sont toujours dans V1_outlook/.

---

## 10. Icone barre des taches (system tray)

Quand l'utilisateur clique "Lancer" dans la popup marketing, une icone BM apparait dans la barre des taches (zone de notification). Clic gauche → ouvre l'inbox BM. Clic droit → menu (Ouvrir, Quitter).

---

## 11. Detection automatique du "Repondre"

Quand l'utilisateur clique Repondre/Rep.tous/Transferer dans Outlook :
- Le LaunchEvent detecte → le backend lance la speculation
- Notification Windows toast "Generer avec BM ?"
- L'utilisateur clique → dialog 80% avec reponse deja prete
Necessite admin deploy ou AppSource pour etre fiable a 100%.

---

## 12. Installation commerciale

Spec complete dans docs/SPEC_INSTALLATION_COMMERCIALE.md.
Bloquants : proxy API, packaging exe, certificat EV, RGPD, guide admin consent.
Effort : ~15-20 jours dev + ~1000 EUR/an.

---

## 13. Overlay Outlook

Tentatives echouees (16/04) : PyQt6 FramelessWindowHint (buggy), pywebview (incompatible Python 3.14), Edge --app (latence + detection fragile).
Extension Chrome (content.js) fonctionne pour Outlook Web mais pas testee sur New Outlook app.
Decision : l'overlay n'est PAS prioritaire. Le bouton barre d'action + popup marketing suffisent pour le MVP.
A revisiter quand AppSource sera en place (taskpane epingle par admin).
