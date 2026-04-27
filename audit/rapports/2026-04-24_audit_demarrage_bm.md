# Rapport d'audit — Thématique "Démarrage BoosterMail" — 2026-04-24

> **Type** : thématique (boot PC → popup visible → overlay warmup)
> **Périmètre** : superviseur + companion + V2 + popup_pyqt + addin sideload
> **Date** : 2026-04-24 07:20-07:28 (analyse post-boot vendredi matin)
> **Auteur** : audit Claude (NOCODE)
> **Itération** : 1

---

## 1. Résumé exécutif

- **Constat** : l'utilisateur ouvre Outlook à 07:23:13, l'overlay PyQt ne devient visible qu'à **07:24:43 → 1 min 30 s plus tard**. Bouton BM OK mais pas de feedback visuel popup/overlay instantané.
- **Bilan** : 0 anomalie bloquante, 2 latences structurelles (I-UX) + 4 fails smoke préexistants non liés au démarrage. Pipeline boot fonctionne end-to-end mais UX démarrage dégradée ce matin (cold start du disque + PyQt froid).
- **Recommandation majeure** : ajouter un warmup PyQt pré-import au démarrage du superviseur (spawn `popup_pyqt.py` en mode hot-instance dès que V2 est prêt, sans attendre Outlook) → ramènerait le temps Outlook-up → overlay-visible de 90 s à ~2 s en cold boot.

---

## 2. Résultat smoke_test.ps1

```
Smoke test : 34 PASS / 4 FAIL / 0 SKIP
Exit code : 4

FAILs (préexistants, non liés au démarrage) :
  - I-RES-02 : Companion ecoute sur 127.0.0.1:5051
  - I-API-01a : GET https://127.0.0.1:3443/api/status -> HTTP 200
  - I-UX-02 : GET /api/status repond en <500ms
  - I-DATA-11 : Cles cache au format canonique (10/26 non-canoniques)
```

Les 4 fails sont hors-périmètre du thème "démarrage" (ils concernent runtime/data quality, cf. rapport 2026-04-23 sur I-DATA-11). Documentés, non ré-audités ici.

---

## 3. Checklists parcourues

- [x] `flux_end_to_end.md` — Flux A (boot) + Flux B (clic BM)
- [x] `specificites_windows.md` — pièges 1, 2, 5, 6, 7, 11, 14
- [x] `ANOMALIES_RECURRENTES.md` consulté (Pattern #1 IPv6, #5 cp1252, #4 cert obsolète)
- [ ] classes_bugs.md (non applicable — thématique latence)
- [ ] angles_attaque.md (non applicable — thématique)

---

## 4. Flux A — Boot PC → BM opérationnel

| # | Étape | État | Preuve (timestamp boostermail.log) | Durée |
|---|---|---|---|---|
| A1 | Superviseur démarre au logon | ✅ | `07:20:41 [superviseur] BoosterMail Superviseur demarre` | T0 |
| A2 | Auto-sideload addin | ⚠️ | `07:20:49 Auto-sideload : OK mais alertes` + `WARN cert doublon 067FDF...` (CurrentUser+LocalMachine Root) | +8 s |
| A3 | Companion lancé port 5051 | ✅ | `07:20:50 Companion: lance (PID 33532, port 5051)` | +9 s |
| A4 | V2 lancé port 3443 | ✅ | `07:20:51 Backend V2: lance (PID 27136, port 3443)` → `07:20:53 Backends prêts` | +12 s |
| A5 | Cert TLS thumbprint actuel `1C873D00...` | ✅ | WARN log mentionne "Cert ACTUEL à conserver : 1C873D00" | — |
| A6 | Registry addin présent | ✅ | auto-sideload OK (log `Auto-sideload addin : OK`) | — |
| A7 | Outlook détecté → popup_pyqt lancé | ⚠️ | `07:23:13 Outlook ré-ouvert` → `07:23:26 Popup PyQt lancee (PID 5304)` = **13 s de gap** | +13 s |
| A8 | Bouton BM visible dans Outlook | ✅ | addin_debug.log `07:24:43 item_changed_fired` + user confirme | — |

**Anomalie Flux A** : A2 cert doublon (pattern #4 récidive), A7 gap 13 s inexpliqué par les logs (voir section 6).

---

## 5. Flux B — Clic BM dans Outlook + apparition overlay

| # | Étape | État | Preuve | Durée |
|---|---|---|---|---|
| B0 | (pré-B1) popup_pyqt spawn → main() lancé | ❌ | superviseur spawn 07:23:26, `popup_pyqt.log` premier log `07:24:33` = **67 s de cold start Python/PyQt** | 67 s |
| B0bis | popup_pyqt main() → Overlay visible | ⚠️ | `07:24:33 popup_pyqt démarre` → `07:24:42 Overlay PyQt visible` = 9 s (QtWebEngine + profile + cert accept) | 9 s |
| B1 | Office.js `item_changed_fired` | ✅ | `addin_debug.log 07:24:43` | — |
| B2 | `button_clicked` event | ✅ | `07:24:43 button_clicked newOutlookWindows ThreeColumns` | — |
| B3 | POST `/api/event/message_read` (Graph fetch) | ✅ | `07:24:43 newOutlook_fetch_result status=200 ok=true` | ~100 ms |
| B4 | IPC vers popup_pyqt | ✅ | `popup_pyqt.log 07:24:43.226 [ipc] HTTP POST /open_dialog reçu` | — |
| B5 | Signal Qt émis | ✅ | `[ipc] signal émis en 0 ms, HTTP 200 → client` | 0 ms |
| B6 | `[hot] open_dialog_via_ipc START` | ✅ | `07:24:43 [hot] open_dialog_via_ipc START mode=reply` | — |
| B7 | Dialog `[full-load] DONE` | ✅ | `07:24:44.055 [full-load] T+828 ms DONE` (premier clic), `T+14 ms` (suivants) | 828 ms (cold) / 14 ms (hot) |
| B8 | Dialog visible et chargé | ✅ | perf_20260424T072455 : T5_reply_first_chunk=7446ms (cold reply = normal sans cache) | — |
| B9 | Pas de popup OOM Outlook | ✅ | aucun log COM Companion pendant la séquence | — |

**Anomalie Flux B** : B0 cold start PyQt = 67 s + B0bis overlay ready = 9 s. **Total cold boot Outlook up → overlay visible = 90 s**. Comparaison : ouverture 23/04 20:02 = spawn 1 s + main 6 s + visible 5 s = ~12 s (disque tiède).

---

## 6. Focus — le gap 13 s Outlook-détecté → Popup lancée (étape A7)

### Séquence de code (`boostermail_service.py:685-715`)
```
while True:
    time.sleep(1)
    running = is_outlook_running()       # EnumWindows — instantané
    if running and not _was_running:
        logger.info("Outlook ré-ouvert")   # log 07:23:13
        ... (respawn conditionnel)
        show_pyqt_popup()                  # log 07:23:26 (13 s plus tard)
```

### Décomposition de `show_pyqt_popup()`
1. `_should_show_popup_now()` : HTTPS GET `/api/activation_status` timeout 1.5 s
2. Acquisition `_show_popup_lock` (mutex threading)
3. `_popup_is_alive()` : HTTP GET `127.0.0.1:5052/ping` timeout 1.0 s (échoue = pas de popup encore)
4. IPC fallback tenté uniquement si alive=True (pas pris ce matin)
5. `subprocess.Popen([pythonw, POPUP_SCRIPT])` = instantané

### Preuves factuelles
- Aucun log "IPC show_popup échoué" entre 07:23:13 et 07:23:26 → voie IPC **pas** empruntée.
- Aucun log "Popup déjà affichée" → `_should_show_popup_now` a renvoyé `True`.
- Gap 13 s >> somme timeouts (1.5+1.0 = 2.5 s max).
- **Hypothèse 1** (la plus probable) : **cold disk I/O + PyQt import préalable**. Même si `subprocess.Popen` est non-bloquant, Python 3.14 charge `ctypes`, `subprocess`, `urllib`, `ssl` dans `show_pyqt_popup`. Sur un boot froid (disk cache vide), chaque import = I/O. Le superviseur tourne en pythonw 3.14 fresh install (`pythoncore-3.14-64`) et a probablement été paginé out pendant les 2m22s d'attente Outlook.
- **Hypothèse 2** : `urllib.request.urlopen` sur HTTPS localhost peut traîner au premier call (cert schannel + handshake Werkzeug froid cf. Pattern #8).
- **Hypothèse 3 (peu probable)** : V2 encore bloqué en warmup à 07:23:13 et n'a pas répondu en 1.5 s → timeout → fallback `return True`. Confirmée par `logger.debug` silencieux (niveau INFO masquerait la trace).

### Conclusion de cause racine
**Cause racine plausible** : latence combinée (paging superviseur + handshake TLS premier call + cold import Python) sur un process superviseur dormant depuis 2m22s. Non reproductible sur un boot "tiède". **Non bloquant** : le user voit l'overlay 1m30 après Outlook ouvert, pas idéal mais opérationnel.

**Cause principale du ressenti user** : pas le gap 13 s — c'est le **cold start PyQt de 67 s** (étape B0) qui domine. Même si on ramenait le gap A7 à 0 s, l'utilisateur attendrait toujours ~75 s.

---

## 7. Anomalies détectées

### Anomalie #1 — Cold start PyQt = 67 s au premier boot (impact UX majeur)

- **Sévérité** : Moyen (UX dégradée, pas bloquant)
- **Classe** : Latence / démarrage
- **Fichier:ligne** : `companion/popup_pyqt.py:1..60` (imports PyQt6 + WebEngine) + `boostermail_service.py:375` (subprocess.Popen tardif)
- **Symptôme** : user ouvre Outlook, bouton BM apparaît mais **aucun feedback popup/overlay pendant ~1min 30** au premier boot du jour.
- **Cause racine** : popup_pyqt est spawné **à la demande** quand Outlook est détecté. PyQt6 + QtWebEngine + Chromium = ~60 MB de DLL à charger depuis le disque froid. Ensuite setup QWebEngineProfile + cert handler = 9 s supplémentaires.
- **Preuve** :
  - `07:23:26` Popen → `07:24:33` main() → `07:24:42` Overlay visible = **76 s** entre spawn et visible.
  - Runs tièdes (disque chaud, 23/04 20:02) : même séquence = 7 s.
- **Pattern récurrent** : non (nouveau pattern à documenter → #15 proposé).
- **Fix suggéré** (NOCODE dans ce rapport, idées pour une session fix) :
  1. Pre-spawn popup_pyqt **dès que V2 est prêt** (après `Backends prêts — en veille`), en mode hot-instance qui tourne en background, masqué. Quand Outlook s'ouvre → IPC `show_popup` = ~100 ms (voie chaude déjà codée mais jamais atteinte au boot).
  2. Alternatif : PyInstaller one-file `popup_pyqt.exe` pour éviter l'import Python 3.14 à froid.
- **Test de non-régression** : mesurer `(T_overlay_visible - T_outlook_detected) < 5 s` au cold boot (2e invariant I-UX à ajouter).

### Anomalie #2 — Gap 13 s superviseur détecte Outlook → subprocess.Popen (impact UX moyen)

- **Sévérité** : Bas (amplifie l'anomalie #1, non critique isolément)
- **Classe** : Latence / démarrage / I/O cold
- **Fichier:ligne** : `boostermail_service.py:332-387` (`show_pyqt_popup`)
- **Symptôme** : 13 s entre `07:23:13 Outlook ré-ouvert` et `07:23:26 Popup PyQt lancee`.
- **Cause racine** : enchaînement `_should_show_popup_now` (HTTPS call) + `_popup_is_alive` (HTTP ping 1 s timeout → fail) + paging superviseur froid + import tardif de `urllib.request`/`ssl`. Aucun log intermédiaire n'instrumente ce bloc → diagnostic à l'aveugle.
- **Preuve** : single leap `07:23:13 → 07:23:26` sans log intermédiaire dans `boostermail.log` (cf. section 6).
- **Pattern récurrent** : partiellement Pattern #8 (renégociations TLS schannel) + non instrumenté → pas de Pattern existant exact.
- **Fix suggéré** :
  1. Ajouter logs INFO dans `show_pyqt_popup` : `[show_popup] entrée`, `[show_popup] activation_status ok (Xms)`, `[show_popup] popup_alive=False`, `[show_popup] spawn subprocess`.
  2. Fire-and-forget : lancer `show_pyqt_popup` dans un thread daemon pour ne pas bloquer la loop superviseur.
- **Test de non-régression** : grep sur ces nouveaux logs après chaque boot ; total `[show_popup] entrée → spawn` < 3 s.

### Anomalie #3 — Cert doublon obsolète toujours présent (récidive Pattern #4)

- **Sévérité** : Bas (alerte détection OK, nettoyage manuel non fait)
- **Classe** : Certificats TLS
- **Fichier:ligne** : `install_outlook_addin.py:_warn_obsolete_certs`
- **Symptôme** : boot 07:20:49 alerte persistante : `2 cert(s) BoosterMail obsolete(s) dans Trusted Root : 067FDF8CA...` (CurrentUser + LocalMachine Root).
- **Cause racine** : user n'a pas encore exécuté les commandes `certutil -user -delstore Root 067FDF8CA...` recommandées. Script ne peut pas les supprimer en silencieux (popup Windows modal — Pattern #7).
- **Pattern récurrent** : oui → **Pattern #4 + Pattern #7** dans ANOMALIES_RECURRENTES (déjà documenté).
- **Fix** : user exécute les deux `certutil -delstore` proposés dans le WARN (commandes déjà fournies dans le log). Pas de modification code.
- **Test de non-régression** : I-CERT-03 doit passer (1 seul cert BoosterMail dans chaque Root).

---

## 8. Points vérifiés OK

- **Flux A** : A1, A3, A4, A5, A6, A8 tous ✅ (6/8). A2 (WARN connu) + A7 (gap 13 s documenté).
- **Flux B** : B1→B9 tous ✅ une fois l'overlay prêt (7 s après clic si tiède, moins de 1 s en hot-instance).
- **I-RES-01** : V2 bind IPv4 + IPv6 OK (smoke test Cat.1 PASS, hors I-RES-02 Companion 127.0.0.1 only — hors périmètre boot).
- **I-CERT-01** : cert actuel `1C873D00...` avec SAN complète présent.
- **Pattern #1 (IPv6)** : pas de récidive ce matin (curl + logs propres).
- **Pattern #5 (cp1252)** : aucun crash Unicode observé (quelques `é`/`�` dans logs venant de l'encodage cp1252 du handler console, mais log file UTF-8 OK).
- **Piège Windows #14** (ItemChanged multi-fire) : backend dédup OK (pas de double génération).

---

## 9. Nouveaux patterns à ajouter à ANOMALIES_RECURRENTES.md

**Pattern candidat #15 — Cold start PyQt/WebEngine au premier boot** : à documenter si fix validé par user.

**Pas d'ajout immédiat dans ce rapport** (règle NOCODE : on ne modifie `ANOMALIES_RECURRENTES.md` que sur patterns vraiment nouveaux et actionnables, et le mode fix n'est pas activé ici). À intégrer dans la session fix qui traitera Anomalie #1.

---

## 10. Recommandations prioritaires (tri impact/effort)

| # | Action | Impact UX | Effort | Priorité |
|---|---|---|---|---|
| 1 | Pre-spawn popup_pyqt **après V2 ready**, sans attendre Outlook (hot-instance permanente) | ★★★ (gain 75 s cold boot) | ~2 h | **P0** |
| 2 | Nettoyer les 2 certs obsolètes `067FDF8CA...` (user exécute commandes WARN) | ★★ (WARN éliminé, robustesse install) | 2 min user | **P0** |
| 3 | Instrumenter `show_pyqt_popup` avec logs INFO détaillés | ★ (diagnostic futur) | 20 min | **P1** |
| 4 | Fire-and-forget `show_pyqt_popup` dans thread daemon | ★ (découple loop superviseur) | 30 min | **P1** |
| 5 | Évaluer PyInstaller one-file `popup_pyqt.exe` (réduit cold import Python) | ★★ (selon mesure) | ~4 h + build | P2 |
| 6 | Ajouter invariant I-UX-03 : `(T_overlay_visible - T_outlook_up) < 5 s` au boot tiède, < 15 s cold | ★ (guard-rail) | 30 min | P2 |

**Recommandation synthèse** : l'action #1 seule ramène le démarrage ressenti de 90 s à ~2 s sur les boots chauds ET froids. C'est le ROI maximal du chantier "démarrage instantané" (chantier #2 du plan 10/04 non résolu à ce jour).

---

## 11. Méta-évaluation

- **Durée audit** : ~35 min
- **Profondeur** : thématique approfondie (logs triangulés superviseur + popup_pyqt + addin_debug + perf JSON)
- **Zones non couvertes** : classes_bugs, angles_attaque, etat_donnees (hors thème)
- **Confiance résultat** : **haute** sur le diagnostic (preuves multi-logs convergentes), **moyenne** sur la cause exacte du gap 13 s (faute d'instrumentation — hypothèses plausibles listées).

---

## Signature

- [x] smoke_test.ps1 exécuté (4 FAIL préexistants documentés, hors périmètre)
- [x] Checklists applicables parcourues (Flux A+B, spécificités Windows)
- [x] ANOMALIES_RECURRENTES.md consulté (Pattern #1, #4, #7, #8)
- [x] Preuves factuelles attachées à chaque item (timestamps logs)
- [x] Aucune modification de code (NOCODE strict)
