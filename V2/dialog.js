/**
 * EasyMail V1 Outlook — Dialog Logic (12f)
 *
 * Gère :
 * - Lecture des données mail depuis URL params
 * - Chargement du body via backend (/api/email_body) en Mode Standard
 * - Body transmis par le taskpane via messageParent en Mode Perf. Réduite
 * - Onglets mail reçu / PJ
 * - Champs destinataires pré-remplis selon le mode (reply/reply_all/forward/new)
 * - Importance R/S/H
 * - Génération via /generate_reply (SSE streaming) — squelette 12f, complété en 12g
 * - Refinement via /refine_reply (SSE streaming) — squelette 12f, complété en 12g
 * - Envoi via /send_reply ou messageParent (Mode Perf. Réduite) — squelette 12f, complété en 12h
 * - Communication dialog → taskpane via Office.context.ui.messageParent()
 */

// =============================================================================
// ÉTAT
// =============================================================================

var _params = new URLSearchParams(window.location.search);
// Audit B1 : URL de base du backend (robuste meme si le dialog est ouvert depuis un autre domaine)
var _backendUrl = window.location.origin || 'https://localhost:3443';

// Étape 7 finale (29/04/2026 PM) — Auth Token Bearer JWT reçu du shared
// runtime via DialogParentMessageReceived (action: 'auth_token').
// Stocké en mémoire JS pour injection dans Authorization: Bearer XXX.
// Activation Phase 4 (future) : remplacer fetch() par _fetchWithBearer()
// dans les routes critiques (instant_reply, dialog_init, etc.).
var _bmAuthToken = '';
var _bmAuthTokenTs = 0;
var _bmAuthTokenTtl = 900;

function _fetchWithBearer(url, opts) {
    /* Wrapper fetch qui injecte Authorization: Bearer si token disponible.
       Compatible avec le code fetch() existant : si token absent, équivalent
       à fetch() classique (rétrocompat). */
    opts = opts || {};
    opts.headers = opts.headers || {};
    if (_bmAuthToken) {
        opts.headers['Authorization'] = 'Bearer ' + _bmAuthToken;
    }
    return fetch(url, opts);
}
var _mode = _params.get('mode') || 'reply';          // reply, reply_all, forward, new
var _messageId = _params.get('messageId') || '';
var _fromName = _params.get('fromName') || _params.get('from') || '';
var _fromEmail = _params.get('fromEmail') || _params.get('from') || '';
var _toEmail = _params.get('to') || '';
var _ccEmail = _params.get('cc') || '';
var _subject = _params.get('subject') || '';
var _hasAttachments = _params.get('hasAttachments') === '1';

// 02/05/2026 — Section « Connexion Outlook » dans Profil : on capture la
// platform Outlook depuis l'URL (ajoutée par le shared runtime Office.js)
// et on la sauve en setting OVH pour que la page Profil l'affiche même
// quand le companion local n'est pas disponible (cas Outlook Web).
(function _saveOutlookPlatform() {
    try {
        var platform = (_params.get('platform') || '').trim();
        // Valeurs attendues : newOutlook, classicOutlook, outlookWeb
        if (!platform) return;
        fetch(_backendUrl + '/api/save_setting', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key: 'last_outlook_platform', value: platform }),
        }).catch(function () {});
    } catch (e) {}
})();

var _importance = 'S';
var _undoStack = [];
var _maxUndo = 10;
var _versionStack = [];       // Pile de versions pour "Essayer une autre réponse" / "Version précédente"
var _isGenerating = false;
var _isStandardMode = false;  // Détecté via /api/status au chargement
var _sendStartTime = 0;       // Timestamp pour métrique duration
var _receivedBody = '';        // Body du mail reçu (pour sauvegarde DB post-envoi + génération)
var _mailBodyForGeneration = ''; // Body complet pour la génération IA
var _summaryStatus = 'unknown';  // #16 'unknown' | 'success' | 'empty_body' | 'error' — drive le wording quand 0 points
// _contactsCache supprime 27/04 PM — autocomplete passe par /api/contact_search debounced (cf _initAutocomplete)

// (Phase 3) Mode standalone : ouvert dans QWebEngineView (PyQt) ou window.open (extension)
var _isStandaloneMode = _params.has('standalone');
var _isOfficeContext = false;
try {
    _isOfficeContext = (typeof Office !== 'undefined' && Office.context &&
                        Office.context.ui && typeof Office.context.ui.messageParent === 'function');
} catch(e) { _isOfficeContext = false; }

// STAND-BY S2 (déclarés en TOP — fix incident 30/04 PM "Cannot read properties
// of undefined reading 'push'") — registry global des autocomplete pour partager
// UN SEUL handler click document, au lieu d'un handler PAR input. Le hoisting
// var de _autocompleteRegistrations en bas de fichier (commit 0b910c1) le
// laissait à undefined au moment où _initAutocomplete() est appelée pendant
// l'init du dialog (ligne ~364), avant que l'assignation `= []` ne soit
// exécutée. Solution : déclarer + initialiser en TOP, avant tout usage.
var _autocompleteRegistrations = [];
var _autocompleteGlobalHandlerBound = false;


// =============================================================================
// SAFETY NET GLOBAL (21/04 — P3)
// =============================================================================

/** Affiche un toast discret en bas-droit. Auto-disparaît après 5 s. */
function _showErrorToast(msg) {
    try {
        var t = document.getElementById('em-error-toast');
        if (!t) {
            t = document.createElement('div');
            t.id = 'em-error-toast';
            t.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:99999;' +
                'background:#c00;color:#fff;padding:10px 14px;border-radius:6px;' +
                'font:12px "Segoe UI",sans-serif;box-shadow:0 3px 12px rgba(0,0,0,0.3);' +
                'max-width:320px;';
            document.body.appendChild(t);
        }
        t.textContent = msg;
        t.style.display = 'block';
        setTimeout(function() { t.style.display = 'none'; }, 5000);
    } catch(_){}
}

/** Intercepte toute exception JS non catchée + toute rejection de Promise.
 *  Fix 27/04 PM — filtre les "Script error." génériques cross-origin
 *  (Office.js CDN Microsoft sans CORS-anonymous). Ces erreurs n'ont aucune
 *  info actionable (msg vide, line=0, col=0, filename=""), elles sont
 *  systematiquement masquees par le browser pour des raisons de securite.
 *  Inutile de polluer l'UX user avec un toast rouge alarmant pour ca. */
function _isCrossOriginErrorWithoutDetails(ev) {
    var msg = (ev.error && ev.error.message) || ev.message || '';
    var src = ev.filename || '';
    // Pattern type Chromium : "Script error." + filename vide + line=0
    return msg === 'Script error.' && !src && (ev.lineno === 0 || !ev.lineno);
}

window.addEventListener('error', function(ev) {
    try {
        var msg = (ev.error && ev.error.message) || ev.message || 'Erreur JS';
        var src = (ev.filename || '').split('/').pop();
        // Toast UX : masquer les Script error cross-origin sans details (Office.js CDN)
        if (!_isCrossOriginErrorWithoutDetails(ev)) {
            _showErrorToast('BoosterMail : ' + msg.substring(0, 80));
        }
        // POST diagnostic toujours envoye (utile pour debugger meme sans details visibles)
        fetch(_backendUrl + '/api/debug_addin_log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                event: 'dialog_js_error',
                details: {
                    msg: msg, src: src, line: ev.lineno, col: ev.colno,
                    cross_origin: _isCrossOriginErrorWithoutDetails(ev)
                }
            }),
            keepalive: true
        }).catch(function(){});
    } catch(_){}
});
window.addEventListener('unhandledrejection', function(ev) {
    try {
        var reason = (ev.reason && ev.reason.message) || String(ev.reason);
        // Skip les "Script error." sans details (idem au handler error ci-dessus)
        if (reason !== 'Script error.') {
            _showErrorToast('BoosterMail : ' + reason.substring(0, 80));
        }
    } catch(_){}
});


// =============================================================================
// PERF MONITOR (22/04 Phase A — instrumentation "dialog 80% complétude")
//
// Mesure la latence perceptive de chaque bloc du dialog, de l'ouverture au
// rendu complet. Le client envoie un snapshot au backend quand tous les marks
// attendus sont arrivés OU après 10 s (timeout pour les cas où un bloc
// échoue). Le backend écrit un JSON par run dans logs/perf_<iso>.json.
//
// Marks attendus (ordre logique) :
//   T0_script_start       → script parsé, variables init
//   T1_init_end           → IIFE init() terminé, 1er paint possible
//   T2_header_rendered    → From/Subject/Date/To/Cc rendus
//   T3_body_rendered      → body HTML affiché (cache ou Graph)
//   T3_body_source        → "cache" | "graph" | "standalone" | "perfreduce"
//   T4_summary_first_point → 1er point résumé visible (cache instant OU stream)
//   T4_summary_done       → résumé complet (points + actions)
//   T4_summary_source     → "cache" | "stream"
//   T5_reply_first_chunk  → 1er texte réponse Claude visible (template/cache/stream)
//   T5_reply_done         → réponse complète
//   T5_reply_source       → "cache" | "template" | "stream" | "draft"
//   T6_contact_profile    → tags confiance/registre rendus
//   T7_pj_rendered        → liste PJ rendue (si applicable)
//
// Chaque mark stocke `performance.now()` ET un delta vs T0. Pas d'envoi
// backend si T0 manque (dialog ouvert hors init normal → bruit).
// =============================================================================

var _perfMonitor = (function() {
    var _marks = {};
    var _sent = false;
    var _expectedMarks = [
        'T1_init_end', 'T2_header_rendered', 'T3_body_rendered',
        'T4_summary_done', 'T5_reply_first_chunk',
    ];
    var _completenessTimer = null;

    function mark(name, meta) {
        if (_marks[name]) return;   // premier seulement (immutable)
        _marks[name] = {
            t: performance.now(),
            meta: meta || null,
        };
        // Check complétude dès qu'un nouveau mark arrive
        _scheduleSend();
    }

    function _scheduleSend() {
        if (_sent || _completenessTimer) return;
        // Attendre 500 ms sans nouveau mark avant d'envoyer (batch)
        _completenessTimer = setTimeout(function() {
            _completenessTimer = null;
            var allPresent = _expectedMarks.every(function(n) {
                return !!_marks[n];
            });
            // Si tous les marks attendus sont là OU 10 s écoulées, on send
            var elapsed = _marks['T0_script_start'] ?
                (performance.now() - _marks['T0_script_start'].t) : 0;
            if (allPresent || elapsed >= 10000) {
                _send();
            } else {
                _scheduleSend();   // retente dans 500 ms
            }
        }, 500);
    }

    function _send() {
        if (_sent) return;
        _sent = true;
        try {
            var t0 = _marks['T0_script_start'] ? _marks['T0_script_start'].t : 0;
            var normalized = {};
            Object.keys(_marks).forEach(function(k) {
                normalized[k] = {
                    ms: Math.round((_marks[k].t - t0) * 100) / 100,
                    meta: _marks[k].meta,
                };
            });
            var payload = {
                message_id: _messageId || null,
                mode: _mode,
                standalone: _isStandaloneMode,
                marks: normalized,
                user_agent: navigator.userAgent.substring(0, 200),
                ts: new Date().toISOString(),
            };
            fetch(_backendUrl + '/api/perf_log', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                keepalive: true,
            }).catch(function(){});
        } catch(e) { /* silent */ }
    }

    // Envoi forcé avant fermeture du dialog (capture même les runs incomplets)
    window.addEventListener('beforeunload', function() {
        if (!_sent) _send();
    });

    return { mark: mark };
})();

// Mark très précoce : script parsé
_perfMonitor.mark('T0_script_start');


// =============================================================================
// CHEF SORTANT (23/04) — Cleanup des streams à la fermeture du dialog
//
// Problème diagnostiqué : quand le dialog 80% se ferme (user clique Retour
// Outlook ou change de mail), les streams SSE en cours (résumé Haiku, réponse
// Claude) restaient actifs côté serveur. Chromium n'envoyait pas de FIN_TCP
// immédiat → V2 conservait les threads occupés → saturation du pool pour
// quelques secondes → le CLIC SUIVANT mettait 5 s à atteindre le backend.
//
// Fix : registre d'objets "fermables" (_activeStreams). Chaque création de
// stream SSE ou fetch streamé s'y enregistre. À beforeunload, on parcourt et
// on close/abort/cancel TOUT → les threads V2 se libèrent instantanément.
// =============================================================================

var _activeStreams = [];

/** Enregistre un objet fermable (EventSource, AbortController, Reader). */
function _registerStream(obj) {
    if (!obj) return obj;
    _activeStreams.push(obj);
    return obj;
}

/** Ferme TOUS les streams actifs. Appelé à beforeunload. Idempotent. */
function _cleanupAllStreams() {
    for (var i = 0; i < _activeStreams.length; i++) {
        var s = _activeStreams[i];
        if (!s) continue;
        try {
            if (typeof s.close === 'function') s.close();          // EventSource
            else if (typeof s.abort === 'function') s.abort();     // AbortController
            else if (typeof s.cancel === 'function') s.cancel();   // Reader
        } catch(_) { /* silent */ }
    }
    _activeStreams = [];
}

// Wire au beforeunload — le "chef sortant" qui libère les portes
window.addEventListener('beforeunload', _cleanupAllStreams);

// =============================================================================
// STAND-BY S9 — Registre des cleanups DOM (listeners document/window)
//
// Pattern pour les listeners attachés à document/window qui ne meurent pas
// automatiquement quand le dialog se ferme (ex: autocomplete global click,
// global drag handlers). Ceux attachés aux éléments DOM internes du dialog
// sont nettoyés automatiquement par le navigateur quand l'iframe meurt.
//
// Usage : `_registerCleanup(function() { document.removeEventListener(...); });`
// =============================================================================

var _domCleanupCallbacks = [];

/** Enregistre un callback de cleanup DOM (exécuté au beforeunload). */
function _registerCleanup(fn) {
    if (typeof fn === 'function') _domCleanupCallbacks.push(fn);
}

function _runDomCleanups() {
    for (var i = 0; i < _domCleanupCallbacks.length; i++) {
        try { _domCleanupCallbacks[i](); } catch(_) { /* silent */ }
    }
    _domCleanupCallbacks = [];
}

window.addEventListener('beforeunload', _runDomCleanups);


// =============================================================================
// INITIALISATION
// =============================================================================

(function init() {
    // Header
    _updateHeader();

    // Champs destinataires pré-remplis
    _prefillFields();

    // Charger le body du mail
    _loadMailBody();

    // Onglets
    _initTabs();

    // Placeholder brief adapté au mode
    var briefField = document.getElementById('fieldBrief');
    if (_mode === 'new') {
        briefField.placeholder = 'Decrivez votre mail en quelques mots (obligatoire)';
    } else {
        briefField.placeholder = 'Instructions (optionnel)';
    }

    // Boutons mode : highlight le bon, masquer en mode new
    var modeRow = document.getElementById('modeRow');
    if (modeRow) {
        if (_mode === 'new') {
            modeRow.style.display = 'none';
        } else {
            document.querySelectorAll('.em-mode-btn').forEach(function(btn) {
                btn.classList.toggle('active', btn.getAttribute('data-mode') === _mode);
            });
        }
    }

    // Auto-détection importance (mots-clés sensibles → H, comme le proto)
    _autoDetectImportance();

    // Détecter le mode (Standard vs Perf. Réduite) et adapter le bouton envoi
    _detectMode();

    // Autocomplete contacts : fetch debounced /api/contact_search a la frappe
    // (plus de pre-load 187 KB upfront — cf optim Workflow 3 du 27/04 PM)
    _initAutocomplete('fieldTo', 'acTo');
    _initAutocomplete('fieldCc', 'acCc');

    // Écouter les messages du parent (taskpane/commands)
    // En Mode Perf. Réduite, le body du mail arrive via messageChild()
    if (!_isStandaloneMode) {
        _listenParentMessages();
    }

    // Plan 2 Phase 5 — Pipeline unifié "réponse instantanée" à l'ouverture du dialog
    // Priorité : brouillon user > préemptif BG > template > rien
    // Remplace les appels séparés _checkSpeculativeCache / _restoreDraft / _tryTemplateMatch.
    //
    // Phase C audit 22/04 : délai réduit 250 → 60 ms (body arrive maintenant via
    // /api/dialog_init bundle, beaucoup plus vite qu'avant). Gain perceptif ~200 ms.
    // _tryInstantReply tolère un body vide (cache draft/preemptive/template
    // indépendants du body), on évite de bloquer le pipeline de réponse.
    if (!_isStandaloneMode) {
        setTimeout(_tryInstantReply, 60);
    }

    // Plan 2 Phase 2.A — Auto-save brouillon en édition (debounced)
    _setupDraftAutoSave();

    // Bouton fermer
    document.getElementById('btnClose').addEventListener('click', function() {
        _closeDialog();
    });

    // Fix UX 22/04 : bouton "Reduire" (btnMinimizeDialog) supprime du HTML.
    // Plus besoin du handler ici — le bouton Retour Outlook (btnClose) gere
    // tout via le handler existant ligne ~119 (easymail://close-dialog).

    // Drag du dialog 80% via le header — Qt Frameless ne fournit pas de drag
    // natif, on envoie les coordonnees screen a PyQt via easymail:// intercepte
    // sans navigation reelle. Ameliore 22/04 :
    //  - throttle 60fps (evite spam WebView2)
    //  - iframe hidden pour nav (comme popup.js, plus robuste que location.href)
    //  - cursor: move + user-select: none sur le header
    if (_isStandaloneMode) {
        (function _initDialogDrag() {
            var header = document.querySelector('.em-header');
            if (!header) return;

            // CSS drag : curseur move + pas de selection texte
            header.style.userSelect = 'none';
            header.style.cursor = 'move';

            // IFRAME hidden pour nav easymail:// (pas de page reload)
            var _dragFrame = document.createElement('iframe');
            _dragFrame.style.display = 'none';
            document.body.appendChild(_dragFrame);
            function _nav(action, x, y) {
                var url = 'easymail://' + action + '/';
                if (typeof x === 'number' && typeof y === 'number') {
                    url += x + ',' + y;
                }
                _dragFrame.src = url;
            }

            var dragging = false;
            var lastMove = 0;

            header.addEventListener('mousedown', function(e) {
                if (e.target.closest('.em-hdr-btn')) return;
                if (e.button !== 0) return;
                dragging = true;
                e.preventDefault();
                _nav('drag-start', e.screenX, e.screenY);
            });
            document.addEventListener('mousemove', function(e) {
                if (!dragging) return;
                var now = Date.now();
                if (now - lastMove < 16) return;  // throttle ~60 fps
                lastMove = now;
                _nav('drag-move', e.screenX, e.screenY);
            });
            document.addEventListener('mouseup', function() {
                if (!dragging) return;
                dragging = false;
                _nav('drag-end');
            });
            // Safety : curseur quitte fenetre pendant drag
            document.addEventListener('mouseleave', function() {
                if (dragging) {
                    dragging = false;
                    _nav('drag-end');
                }
            });
        })();
    }

    // Garde forward : bouton Générer grisé si champ À vide en mode forward
    _applyForwardGuard();

    // Perf : fin de l'IIFE init → 1er paint possible
    _perfMonitor.mark('T1_init_end');

})();

// Garde forward extraite en fonction pour pouvoir être ré-attachée sur rebind
function _applyForwardGuard() {
    var fieldTo = document.getElementById('fieldTo');
    var btnGen = document.getElementById('btnGenerate');
    if (!fieldTo || !btnGen) return;
    if (_mode === 'forward') {
        btnGen.disabled = !fieldTo.value.trim();
        if (!fieldTo.__fwGuardBound) {
            fieldTo.addEventListener('input', function() {
                if (_mode === 'forward') btnGen.disabled = !fieldTo.value.trim();
            });
            fieldTo.__fwGuardBound = true;
        }
    } else {
        btnGen.disabled = false;
    }
}

// =============================================================================
// HEADER
// =============================================================================

function _updateHeader() {
    var label = document.getElementById('headerReplyLabel');
    if (_mode === 'reply') {
        label.innerHTML = 'Repondre a <strong>' + _escapeHtml(_fromName || _fromEmail) + '</strong>';
    } else if (_mode === 'reply_all') {
        label.innerHTML = 'Repondre a tous — <strong>' + _escapeHtml(_fromName || _fromEmail) + '</strong>';
    } else if (_mode === 'forward') {
        label.innerHTML = 'Transferer — <strong>' + _escapeHtml(_subject) + '</strong>';
    } else if (_mode === 'new') {
        label.innerHTML = 'Nouveau mail';
    }
    _perfMonitor.mark('T2_header_rendered');
}

function _loadContactTags() {
    // Fix audit 22/04 bis : le dialog standalone (PyQt) n'utilise PAS le
    // bundle /api/dialog_init côté consommation — _loadDialogBundle ne fire
    // qu'en mode Office.js natif (jamais atteint en pratique). Le bundle
    // backend tourne quand même (pré-chauffe des caches) mais les tags DOIVENT
    // être fetchés directement pour apparaître. Architecture 3 portes : chaque
    // livreur a sa porte dédiée, celle-ci est celle du livreur "fiche contact".
    if (!_fromEmail) return;
    fetch(_backendUrl + '/api/contact_profile/' + encodeURIComponent(_fromEmail))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data && data.profile) _applyContactProfile(data.profile);
        })
        .catch(function() {});
}


// =============================================================================
// PRÉ-REMPLISSAGE CHAMPS
// =============================================================================

function _prefillFields() {
    var fieldTo = document.getElementById('fieldTo');
    var fieldCc = document.getElementById('fieldCc');
    var fieldSubject = document.getElementById('fieldSubject');
    var rowCc = document.getElementById('rowCc');

    switch (_mode) {
        case 'reply':
            fieldTo.value = _fromEmail;
            fieldSubject.value = _subject.match(/^Re:/i) ? _subject : 'Re: ' + _subject;
            break;

        case 'reply_all':
            fieldTo.value = _fromEmail;
            fieldSubject.value = _subject.match(/^Re:/i) ? _subject : 'Re: ' + _subject;
            if (_ccEmail) {
                rowCc.style.display = 'flex';
                fieldCc.value = _ccEmail;
            }
            break;

        case 'forward':
            fieldTo.value = '';  // L'utilisateur saisit le destinataire
            fieldSubject.value = _subject.match(/^Fw:|^Fwd:/i) ? _subject : 'Fw: ' + _subject;
            break;

        case 'new':
            fieldTo.value = _toEmail;
            fieldSubject.value = '';
            break;
    }
}


// =============================================================================
// MODE SWITCHING (reply / reply_all / forward) — comme le proto
// =============================================================================

var _originalFromEmail = _fromEmail;  // Sauvegarde pour mode switching
var _originalToEmail = _toEmail;
var _originalCcEmail = _ccEmail;
var _originalSubject = _subject;
var _pjChoiceMade = false;
var _pjSelectedIndices = [];
var _extractedPjContext = '';
var _fwdPjChoiceMade = false;
var _fwdSelectedIndexes = [];
var _attachmentsList = [];  // PJ du mail (rempli par _renderAttachments)
var _smartPaperclipFolder = '';

function _autoDetectImportance() {
    // Mots-clés sensibles dans le sujet → auto-passage en H (comme le proto)
    var sensitiveKeywords = /litige|bail|notaire|contentieux|tribunal|huissier|mise en demeure/i;
    if (sensitiveKeywords.test(_subject)) {
        _importance = 'H';
        document.querySelectorAll('.em-imp-chip').forEach(function(c) {
            c.classList.remove('active');
            if (c.getAttribute('data-imp') === 'H') c.classList.add('active');
        });
    }
}

function setReplyMode(mode) {
    if (mode === _mode) return;

    // Reset état PJ
    _pjChoiceMade = false;
    _pjSelectedIndices = [];
    _extractedPjContext = '';
    _fwdPjChoiceMade = false;
    _fwdSelectedIndexes = [];

    _mode = mode;

    // Mettre à jour les boutons mode
    document.querySelectorAll('.em-mode-btn').forEach(function(btn) {
        btn.classList.toggle('active', btn.getAttribute('data-mode') === mode);
    });

    // Recalculer les champs
    _computeModalFields();

    // Mettre à jour le header
    _updateHeader();

    // Garde forward : bouton Générer grisé si champ À vide
    // Fix audit 21/04 : utiliser le flag __fwGuardBound (même pattern que
    // _applyForwardGuard ligne 222) pour éviter d'accumuler N handlers à
    // chaque clic sur le bouton Transférer.
    var btnGen = document.getElementById('btnGenerate');
    var fieldTo = document.getElementById('fieldTo');
    if (mode === 'forward') {
        btnGen.disabled = !fieldTo.value.trim();
        if (!fieldTo.__fwGuardBound) {
            fieldTo.addEventListener('input', function _fwdGuard() {
                btnGen.disabled = !fieldTo.value.trim();
            });
            fieldTo.__fwGuardBound = true;
        }
    } else {
        btnGen.disabled = false;
    }

    // Masquer les boutons mode en mode new (pas de switching)
    var modeRow = document.getElementById('modeRow');
    if (modeRow) modeRow.style.display = (mode === 'new') ? 'none' : 'flex';

    // Brief placeholder adapté
    var briefField = document.getElementById('fieldBrief');
    if (mode === 'new') {
        briefField.placeholder = 'Decrivez votre mail en quelques mots (obligatoire)';
    } else if (mode === 'forward') {
        briefField.placeholder = 'Instructions pour le transfert (optionnel)';
    } else {
        briefField.placeholder = 'Instructions (optionnel)';
    }
}

function _computeModalFields() {
    var fieldTo = document.getElementById('fieldTo');
    var fieldCc = document.getElementById('fieldCc');
    var fieldSubject = document.getElementById('fieldSubject');
    var rowCc = document.getElementById('rowCc');

    // Nettoyer le préfixe existant du sujet
    var cleanSubject = _originalSubject.replace(/^(Re:\s*|Fw:\s*|Fwd:\s*)+/gi, '').trim();

    switch (_mode) {
        case 'reply':
            fieldTo.value = _originalFromEmail;
            fieldSubject.value = 'Re: ' + cleanSubject;
            rowCc.style.display = 'none';
            fieldCc.value = '';
            break;

        case 'reply_all':
            fieldTo.value = _originalFromEmail;
            fieldSubject.value = 'Re: ' + cleanSubject;
            // Cc = tous les To + Cc sauf moi et l'expéditeur (auto-calculé)
            var allCc = [];
            if (_originalToEmail) {
                _originalToEmail.split(/[;,]/).forEach(function(e) {
                    var trimmed = e.trim();
                    if (trimmed && trimmed !== _originalFromEmail) allCc.push(trimmed);
                });
            }
            if (_originalCcEmail) {
                _originalCcEmail.split(/[;,]/).forEach(function(e) {
                    var trimmed = e.trim();
                    if (trimmed && trimmed !== _originalFromEmail && allCc.indexOf(trimmed) === -1) allCc.push(trimmed);
                });
            }
            if (allCc.length > 0) {
                rowCc.style.display = 'flex';
                fieldCc.value = allCc.join('; ');
            } else {
                rowCc.style.display = 'none';
            }
            break;

        case 'forward':
            fieldTo.value = '';  // L'utilisateur saisit le destinataire
            fieldSubject.value = 'Fw: ' + cleanSubject;
            rowCc.style.display = 'none';
            fieldCc.value = '';
            break;
    }
}


// =============================================================================
// PJ ANALYSIS POPUP (avant génération — comme le proto)
// =============================================================================

function _shouldShowPjPopup() {
    // Si des PJ existent et qu'on n'a pas encore fait le choix
    return _hasAttachments && !_pjChoiceMade && _attachmentsList.length > 0;
}

/** Helper 02/05/2026 — éditeur a-t-il un contenu réel non placeholder ?
 * Utilisé par les handlers de la popup PJ pour décider s'il faut regénérer
 * (cache miss → oui) ou laisser la réponse cachée affichée (cache HIT → non,
 * la réponse cachée intègre déjà l'analyse PJ côté backend). */
function _editorHasRealContent() {
    var editor = document.getElementById('editor');
    if (!editor) return false;
    // Placeholder actif → pas de contenu réel
    if (_progressPlaceholderActive && document.getElementById('progressPlaceholder')) {
        return false;
    }
    var text = (editor.innerText || '').trim();
    return text.length > 0;
}

function _showPjAnalysisPopup() {
    var list = document.getElementById('pjAnalysisList');
    list.innerHTML = '';
    _attachmentsList.forEach(function(att, i) {
        if (att.is_inline) return;
        var isImage = /\.(png|jpg|jpeg|gif|bmp|ico|svg|webp)$/i.test(att.name);
        var div = document.createElement('div');
        div.style.cssText = 'display:flex;align-items:center;gap:8px;padding:4px 0;';
        div.innerHTML = '<input type="checkbox" class="pj-analysis-cb" data-index="' + i + '"' +
            (isImage ? '' : ' checked') + '>' +
            '<span style="font-size:11px;">\uD83D\uDCC4 ' + _escapeHtml(att.name) +
            (att.size ? ' <span style="color:#aaa;">(' + _formatSize(att.size) + ')</span>' : '') +
            '</span>';
        list.appendChild(div);
    });
    document.getElementById('popupPjAnalysis').classList.add('active');
}

function pjSelectAll(state) {
    document.querySelectorAll('.pj-analysis-cb').forEach(function(cb) {
        cb.checked = state;
    });
}

function _closePjOverlay() {
    /** Helper portage proto 29/04 PM — reset des 2 phases avant fermeture. */
    document.getElementById('popupPjAnalysis').classList.remove('active');
    document.getElementById('pj-phase-select').style.display = 'block';
    document.getElementById('pj-phase-loading').style.display = 'none';
    var _residualRow = document.getElementById('pj-validate-row');
    if (_residualRow) _residualRow.remove();
}

function skipPjAnalysis() {
    _pjChoiceMade = true;
    _extractedPjContext = '';
    _closePjOverlay();
    // Décision Yvan 02/05/2026 : si une réponse cachée est déjà affichée
    // (instant_reply HIT déclenché en parallèle de la popup PJ proactive),
    // on ne regénère PAS. La réponse cachée intègre déjà l'analyse PJ
    // côté backend.
    if (_editorHasRealContent()) return;
    // Sinon (cache miss) : continuer le flow normal de génération
    generateReply();
}

async function acceptPjAnalysis() {
    /** Portage exact proto 29/04 PM (Écart 4 PLUS_TARD_VF) — barre de
     * progression PJ par PJ avec spinner / OK / erreur, batch de 3
     * extractions parallèles, alerte si PJ trop volumineuse, bouton
     * « Valider et générer » à la fin. */
    _pjChoiceMade = true;
    var selected = [];
    document.querySelectorAll('.pj-analysis-cb:checked').forEach(function(cb) {
        var idx = parseInt(cb.getAttribute('data-index'), 10);
        var att = _attachmentsList[idx] || {};
        selected.push({ index: idx, name: att.name || 'PJ' });
    });
    _pjSelectedIndices = selected.map(function(s) { return s.index; });

    if (selected.length === 0) {
        _closePjOverlay();
        // Décision Yvan 02/05/2026 : idem skipPjAnalysis (cf. helper ci-dessous).
        if (_editorHasRealContent()) return;
        generateReply();
        return;
    }

    // Phase 2 : switcher la popup vers la barre de progression
    document.getElementById('pj-phase-select').style.display = 'none';
    document.getElementById('pj-phase-loading').style.display = 'block';
    var progressList = document.getElementById('pj-progress-list');
    progressList.innerHTML = '';
    selected.forEach(function(s) {
        progressList.innerHTML += '<div id="pj-item-' + s.index + '" style="display:flex;align-items:center;gap:8px;padding:5px 8px;margin-bottom:4px;border-radius:6px;font-size:12px;color:#999;background:#f8f8f8;">'
            + '<span class="pj-status-icon" style="font-size:14px;">⏳</span>'
            + '<span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + _escapeHtml(s.name) + '</span>'
            + '</div>';
    });
    document.getElementById('pj-progress-bar').style.width = '0%';
    document.getElementById('pj-progress-pct').textContent = '0 / ' + selected.length;

    var allContexts = [];
    var _failedPjNames = [];
    var _doneCount = 0;
    var BATCH_SIZE = 3;

    function _markPjSpinning(s) {
        var itemEl = document.getElementById('pj-item-' + s.index);
        if (!itemEl) return;
        itemEl.style.color = '#333';
        itemEl.style.background = '#e8f4fd';
        var icon = itemEl.querySelector('.pj-status-icon');
        if (icon) icon.innerHTML = '<div style="width:12px;height:12px;border:2px solid #e0e0e0;border-top-color:#0078d4;border-radius:50%;animation:pj-spin 0.6s linear infinite;display:inline-block;"></div>';
    }
    function _updatePjBar() {
        _doneCount++;
        var pct = Math.round((_doneCount / selected.length) * 100);
        document.getElementById('pj-progress-bar').style.width = pct + '%';
        document.getElementById('pj-progress-pct').textContent = _doneCount + ' / ' + selected.length;
    }
    async function _extractOnePj(s) {
        _markPjSpinning(s);
        var itemEl = document.getElementById('pj-item-' + s.index);
        try {
            var res = await fetch(_backendUrl + '/api/extract_attachments/' + encodeURIComponent(_messageId), {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ indices: [s.index] }),
            });
            var data = await res.json();
            if (data.ok && data.pj_context) {
                allContexts.push(data.pj_context);
                if (itemEl) {
                    itemEl.style.color = '#2e7d32';
                    itemEl.style.background = '#e8f5e9';
                    var icon = itemEl.querySelector('.pj-status-icon');
                    if (icon) icon.textContent = '✅';
                    if (data.warnings && data.warnings.length > 0) {
                        data.warnings.forEach(function(w) {
                            itemEl.insertAdjacentHTML('afterend', '<div style="font-size:10px;color:#e65100;background:#fff3e0;padding:3px 8px;border-radius:4px;margin:2px 0 4px 24px;">' + _escapeHtml(w) + '</div>');
                        });
                    }
                }
            } else {
                _failedPjNames.push(s.name);
                var _ext = (s.name.split('.').pop() || '').toLowerCase();
                var _reason = 'contenu non extractible';
                if (['png','jpg','jpeg','gif','bmp','svg','webp'].indexOf(_ext) >= 0) _reason = 'format image non analysable';
                else if (_ext === 'pdf') _reason = 'PDF scanné (sans texte exploitable)';
                else if (['zip','rar','7z'].indexOf(_ext) >= 0) _reason = 'archive non analysable';
                if (itemEl) {
                    itemEl.style.color = '#999';
                    itemEl.style.background = '#f5f5f5';
                    var icon = itemEl.querySelector('.pj-status-icon');
                    if (icon) icon.textContent = '⚠️';
                    itemEl.insertAdjacentHTML('beforeend', '<span style="font-size:10px;color:#c57600;margin-left:4px;">— ' + _escapeHtml(_reason) + '</span>');
                }
            }
        } catch(e) {
            _failedPjNames.push(s.name);
            if (itemEl) {
                itemEl.style.color = '#c62828';
                itemEl.style.background = '#ffebee';
                var icon = itemEl.querySelector('.pj-status-icon');
                if (icon) icon.textContent = '❌';
                itemEl.insertAdjacentHTML('beforeend', '<span style="font-size:10px;color:#c62828;margin-left:4px;">— erreur d\'extraction</span>');
            }
        }
        _updatePjBar();
    }

    // Lancer par batch de BATCH_SIZE en parallèle
    for (var bStart = 0; bStart < selected.length; bStart += BATCH_SIZE) {
        var batch = selected.slice(bStart, bStart + BATCH_SIZE);
        await Promise.all(batch.map(function(s) { return _extractOnePj(s); }));
    }

    _extractedPjContext = allContexts.join('\n\n');

    // Note interne pour Claude : ignorer les PJ qui ont échoué
    if (_failedPjNames.length > 0 && allContexts.length > 0) {
        _extractedPjContext += '\n\n[NOTE INTERNE : Certaines pieces jointes n\'ont pas pu etre analysees automatiquement (' + _failedPjNames.join(', ') + '). NE PAS mentionner ce probleme dans le mail. NE PAS dire que tu n\'as pas pu consulter ou analyser un document. L\'utilisateur les a consultees lui-meme. Concentre-toi uniquement sur les PJ analysees ci-dessus.]';
    } else if (_failedPjNames.length > 0 && allContexts.length === 0) {
        _extractedPjContext = '';
    }

    // Résumé + bouton « Valider et générer »
    var summaryText = allContexts.length + ' PJ analysee(s) avec succes';
    if (_failedPjNames.length > 0) summaryText += ' — ' + _failedPjNames.length + ' non analysable(s)';
    document.getElementById('pj-progress-pct').textContent = summaryText;
    var _oldValidateRow = document.getElementById('pj-validate-row');
    if (_oldValidateRow) _oldValidateRow.remove();
    document.getElementById('pj-progress-pct').insertAdjacentHTML('afterend',
        '<div id="pj-validate-row" style="text-align:center;margin-top:12px;">'
        + '<button id="btn-pj-validate" onclick="_onPjValidate()" class="em-popup-btn primary">Valider et generer la reponse</button>'
        + '</div>');
}

function _onPjValidate() {
    /** Clic « Valider et générer » : ferme la popup et lance generate.
     * Décision Yvan 02/05/2026 : si une réponse cachée est déjà affichée
     * (instant_reply HIT pendant l'extraction PJ), on ne regénère PAS —
     * la réponse cachée intègre déjà l'analyse PJ côté backend. */
    var validateRow = document.getElementById('pj-validate-row');
    if (validateRow) validateRow.remove();
    _closePjOverlay();
    if (_editorHasRealContent()) return;
    generateReply();
}


// =============================================================================
// FORWARD PJ POPUP (inclure PJ originales — comme le proto)
// =============================================================================

function _shouldShowFwdPjPopup() {
    return _mode === 'forward' && _hasAttachments && !_fwdPjChoiceMade && _attachmentsList.length > 0;
}

function _showFwdPjPopup() {
    var list = document.getElementById('fwdPjList');
    list.innerHTML = '';
    _attachmentsList.forEach(function(att, i) {
        if (att.is_inline) return;
        var div = document.createElement('div');
        div.style.cssText = 'display:flex;align-items:center;gap:8px;padding:4px 0;';
        div.innerHTML = '<input type="checkbox" class="fwd-pj-cb" data-index="' + i + '" checked>' +
            '<span style="font-size:11px;">\uD83D\uDCC4 ' + _escapeHtml(att.name) +
            (att.size ? ' <span style="color:#aaa;">(' + _formatSize(att.size) + ')</span>' : '') +
            '</span>';
        list.appendChild(div);
    });
    document.getElementById('popupFwdPj').classList.add('active');
}

function fwdPjSelectAll(state) {
    document.querySelectorAll('.fwd-pj-cb').forEach(function(cb) {
        cb.checked = state;
    });
}

function skipFwdAttachments() {
    _fwdPjChoiceMade = true;
    _fwdSelectedIndexes = [];
    document.getElementById('popupFwdPj').classList.remove('active');
}

function includeSelectedFwdAttachments() {
    _fwdPjChoiceMade = true;
    _fwdSelectedIndexes = [];
    document.querySelectorAll('.fwd-pj-cb:checked').forEach(function(cb) {
        _fwdSelectedIndexes.push(parseInt(cb.getAttribute('data-index'), 10));
    });
    document.getElementById('popupFwdPj').classList.remove('active');

    // Note audit 21/04 : la route /api/save_original_attachments n'existe pas
    // côté V2 backend (appel produisait 404 silencieux). Le forward côté
    // Graph inclut automatiquement TOUTES les PJ du mail source — le filtrage
    // côté utilisateur n'est donc pas respecté en pratique. La variable
    // `_fwdSelectedIndexes` reste pour un usage futur (quand on voudra filtrer
    // via createForward + DELETE attachments spécifiques).
}


// =============================================================================
// SMART PAPERCLIP (trombone intelligent — comme le proto)
// =============================================================================

function smartPaperclip() {
    if (!_fromEmail) {
        alert('Aucun correspondant detecte.');
        return;
    }
    fetch(_backendUrl + '/api/smart_paperclip?email=' + encodeURIComponent(_fromEmail) +
          '&subject=' + encodeURIComponent(_subject))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.folder) {
                _smartPaperclipFolder = data.folder;
                document.getElementById('smartPaperclipFolder').textContent = '\uD83D\uDCC1 ' + data.folder;
                document.getElementById('popupSmartPaperclip').classList.add('active');
            } else {
                // Pas de suggestion → fallback upload classique
                alert('Aucune suggestion de dossier pour ce correspondant.');
            }
        })
        .catch(function() {
            alert('Erreur de connexion au backend.');
        });
}

function openSuggestedFolder() {
    if (!_smartPaperclipFolder) return;
    fetch(_backendUrl + '/api/open_windows_folder?path=' + encodeURIComponent(_smartPaperclipFolder))
        .catch(function() {});
    closeSmartPaperclip();
}

function closeSmartPaperclip() {
    document.getElementById('popupSmartPaperclip').classList.remove('active');
}


// =============================================================================
// CHARGEMENT BODY MAIL (panneau gauche)
// =============================================================================

function _loadMailBody() {
    // Infos de base depuis les URL params — panneau Mail reçu
    document.getElementById('mailFrom').textContent = _fromName
        ? _fromName + ' <' + _fromEmail + '>'
        : _fromEmail || '—';
    document.getElementById('mailSubject').textContent = _subject || '—';

    // Meta : destinataires
    var metaParts = [];
    if (_toEmail) metaParts.push('A : ' + _toEmail);
    if (_ccEmail) metaParts.push('Cc : ' + _ccEmail);
    var metaEl = document.getElementById('mailMeta');
    if (metaEl) metaEl.textContent = metaParts.join(' | ') || '—';

    // Panneau Résumé — from + sujet
    var resumeFrom = document.getElementById('resumeFrom');
    if (resumeFrom) resumeFrom.textContent = _fromName ? _fromName + ' — ' + (_fromEmail || '') : _fromEmail || '—';
    var resumeSubject = document.getElementById('resumeSubject');
    if (resumeSubject) resumeSubject.textContent = _subject || '—';

    // Tags vouvoiement/confiance dans le header
    _loadContactTags();

    // PJ dans le résumé
    if (_hasAttachments) {
        var resumePJ = document.getElementById('resumePJ');
        if (resumePJ) resumePJ.style.display = 'block';
    }

    if (!_messageId && !_isStandaloneMode) {
        // Mode new mail : pas de mail reçu
        document.getElementById('mailBody').innerHTML =
            '<p style="color:#999; font-size:11px;">Nouveau mail — pas de mail source.</p>';
        var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');
        return;
    }

    // (Phase 3) Mode standalone : charger les données depuis /api/current_mail
    if (_isStandaloneMode) {
        _loadMailBodyStandalone();
        return;
    }

    // Phase C audit 22/04 — route bundle : 1 seul round-trip pour
    // body + résumé + profil contact (élimine 3 TLS handshakes successifs).
    // Fallback individuel si /api/dialog_init échoue.
    _loadDialogBundle();
}

/**
 * Phase C — charge body + résumé + profil contact en 1 seul fetch bundle.
 * Fallback gracieux : si la route bundle KO, on retombe sur les fetches
 * individuels existants (compat arrière garantie).
 *
 * Eager fetch : si `window.__bundlePromise` est déjà en cours (déclenché par
 * le <script> inline de dialog.html AVANT le parse dialog.js), on consomme
 * cette promesse → gain ~100-300 ms sur le cold start.
 */
function _loadDialogBundle() {
    var _bs = function() { var el = document.getElementById('bodySpinner'); if (el) el.classList.remove('active'); };
    // Prioriser la promesse pré-déclenchée par dialog.html (eager fetch)
    var bundlePromise;
    if (window.__bundlePromise) {
        bundlePromise = window.__bundlePromise;
        if (window.__bundleTriggeredAt) {
            var eagerMs = Math.round((performance.now() - window.__bundleTriggeredAt) * 10) / 10;
            console.info('[dialog] bundle consommé depuis eager fetch (age=' + eagerMs + 'ms)');
        }
    } else {
        var url = _backendUrl + '/api/dialog_init?message_id=' + encodeURIComponent(_messageId)
                  + (_fromEmail ? '&from_email=' + encodeURIComponent(_fromEmail) : '');
        bundlePromise = fetch(url).then(function(r) { return r.ok ? r.json() : null; });
    }
    bundlePromise
        .then(function(bundle) {
            if (!bundle) {
                // Fallback : ancienne logique (3 fetches)
                _legacyFetchBody();
                _legacyFetchContactTags();
                if (_messageId) _fetchMailSummary();
                return;
            }
            // --- Email body ---
            var email = bundle.email;
            if (email && email.error === 'auth_required') {
                document.getElementById('mailBody').innerHTML =
                    '<p style="color:#999; font-size:11px;">Reconnexion Microsoft requise.</p>';
                // #15 bandeau in-dialog avec bouton Se reconnecter
                _showReauthBanner('Session Microsoft expirée. Reconnectez-vous pour charger le mail.');
                _bs();
            } else if (email) {
                _renderMailBody(email);
                if (email.attachments && email.attachments.length > 0) {
                    _renderAttachments(email.attachments);
                }
            } else {
                // Mode Dégradé ou pas de email_body dispo — fallback
                _legacyFetchBody();
            }
            // --- Résumé ---
            var summary = bundle.summary;
            if (summary && summary.status === 'done') {
                _renderSummaryInstant(summary.points || [], summary.actions || []);
            } else {
                // MISS → fallback SSE stream
                _fetchMailSummary();
            }
            // --- Profil contact ---
            var profile = bundle.contact_profile;
            if (profile) {
                _applyContactProfile(profile);
            }
            // --- Preview (échéance + classement + PJ) — Phase 3 (25/04 soir) ---
            // 3 portes séparées en parallèle au lieu d'1 porte commune.
            // Chaque plat arrive dès qu'il est prêt → service progressif.
            var preview = bundle.preview;
            if (preview) {
                // Bundle déjà fourni → applique immédiatement (cas warm).
                _applyMailPreview(preview);
            } else {
                _applyMailPreview(null);  // "—" en attendant
            }
            // Toujours lancer les 3 portes en parallèle (refresh + couvre miss
            // bundle). Si déjà cached → instant ; sinon le BG génère et on poll.
            _fetchSinglePreviewPlates();
        })
        .catch(function(e) {
            console.warn('[dialog] dialog_init bundle échec, fallback:', e);
            _legacyFetchBody();
            _legacyFetchContactTags();
            if (_messageId) _fetchMailSummary();
        });
}

/** Sanitize email HTML (Word/Outlook) avant injection dans #mailBody.
 *
 * Fix 02/05/2026 (signal Yvan : mise en page mail reçu Stéphane Dufau
 * avec lignes collées « Stephane DufauChef de projetsTél. ») :
 * Microsoft Word génère un <style> avec `p.MsoNormal { margin:0cm }`
 * qui, injecté via innerHTML, fuit vers toute la page et écrase les
 * marges par défaut des paragraphes → toute la signature et les
 * headers cités se collent sans saut de ligne. Pire, `a:link {color:blue}`
 * du mail fuit vers les liens de l'app.
 *
 * Solution : extraire le <body> du HTML (si présent) et stripper les
 * éléments qui transportent du CSS global (style, head, meta, link).
 * Le navigateur applique alors les marges par défaut sur les <p> →
 * rendu propre.
 */
function _sanitizeEmailHtml(html) {
    if (!html) return '';
    // 1. Extraire le contenu du <body> si présent (sinon prendre tout)
    var bodyMatch = html.match(/<body\b[^>]*>([\s\S]*?)<\/body>/i);
    var content = bodyMatch ? bodyMatch[1] : html;
    // 2. Strip les éléments qui injectent du CSS global ou exécutent du code
    content = content
        .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, '')
        .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
        .replace(/<head\b[^<]*(?:(?!<\/head>)<[^<]*)*<\/head>/gi, '')
        .replace(/<meta\b[^>]*\/?>/gi, '')
        .replace(/<link\b[^>]*\/?>/gi, '')
        .replace(/<iframe\b[^>]*>/gi, '<!-- blocked -->')
        .replace(/<object\b[^>]*>/gi, '<!-- blocked -->')
        .replace(/<embed\b[^>]*>/gi, '<!-- blocked -->')
        .replace(/on\w+\s*=/gi, 'data-blocked=');
    return content;
}

/** Rendu body (extrait de _loadMailBody pour réutilisation dans bundle) */
function _renderMailBody(data) {
    var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');
    var _bodyCached = !!(data && data.cached);
    var _mailBodyEl = document.getElementById('mailBody');
    if (data.html_body) {
        var sanitized = _sanitizeEmailHtml(data.html_body);
        if (!_bodyCached && _mailBodyEl) {
            _mailBodyEl.style.opacity = '0';
            _mailBodyEl.style.transition = 'opacity 0.25s ease-in';
        }
        _mailBodyEl.innerHTML = sanitized;
        if (!_bodyCached) {
            requestAnimationFrame(function() { if (_mailBodyEl) _mailBodyEl.style.opacity = '1'; });
        }
        _receivedBody = data.body || data.html_body || '';
        _mailBodyForGeneration = data.body || data.html_body || '';
    } else if (data.body) {
        var bodyHtml = data.body.split(/\n\n+/).map(function(p) {
            return '<p>' + _escapeHtml(p).replace(/\n/g, '<br>') + '</p>';
        }).join('');
        if (!_bodyCached && _mailBodyEl) {
            _mailBodyEl.style.opacity = '0';
            _mailBodyEl.style.transition = 'opacity 0.25s ease-in';
        }
        _mailBodyEl.innerHTML = bodyHtml;
        if (!_bodyCached) {
            requestAnimationFrame(function() { if (_mailBodyEl) _mailBodyEl.style.opacity = '1'; });
        }
        _mailBodyForGeneration = data.body || '';
    } else {
        _mailBodyEl.innerHTML = '<p style="color:#999;">Contenu non disponible.</p>';
    }
    _perfMonitor.mark('T3_body_rendered', _bodyCached ? 'cache' : 'graph');
    // Meta
    // Fix 02/05/2026 (signal Yvan : « A : [object Object] » sur screenshot
    // mail Dufau) : data.to/data.cc peuvent être des listes [{name, address}]
    // ou dict {name, address} renvoyés par Graph API (pas toujours stringifié
    // côté backend, cf. mémoire « Graph API types list vs str »). On
    // normalise en string lisible avant concaténation.
    if (data.date || data.to) {
        var metaParts2 = [];
        var _toStr = _formatRecipients(data.to) || _toEmail || '';
        if (_toStr) metaParts2.push('A : ' + _toStr);
        var _ccStr = _formatRecipients(data.cc) || _ccEmail || '';
        if (_ccStr) metaParts2.push('Cc : ' + _ccStr);
        if (data.date) metaParts2.push(new Date(data.date).toLocaleString('fr-FR'));
        document.getElementById('mailMeta').textContent = metaParts2.join(' | ') || '—';
    }
}

/** Normalise un champ recipient (to/cc) qui peut arriver sous 4 formes :
 *   - string (cas nominal) : « Yvan BOSSER <yvan.bosser@...> »
 *   - dict {name, address} (Graph API single recipient)
 *   - list[dict] (Graph API multi recipients)
 *   - list[string] (backend qui a déjà serialize)
 * Renvoie une string lisible ou '' si rien d'exploitable. */
function _formatRecipients(field) {
    if (!field) return '';
    if (typeof field === 'string') return field;
    if (Array.isArray(field)) {
        return field.map(_formatRecipients).filter(Boolean).join(', ');
    }
    if (typeof field === 'object') {
        // Graph format : {emailAddress: {name, address}} ou {name, address} direct
        var src = field.emailAddress || field;
        var name = src.name || '';
        var addr = src.address || src.email || '';
        if (name && addr) return name + ' <' + addr + '>';
        return name || addr || '';
    }
    return '';
}

/** Phase 2.A (24/04) — Applique le preview mail pré-chauffé (échéance + classement)
 * aux cards `infoEcheance` et `infoClassement` du dialog 80%.
 * Si preview null ou données vides → "Néant" (demande user : ne pas laisser vide).
 * Si status === 'running' → "Analyse en cours..." + auto-poll 2s.
 */
function _applyMailPreview(preview) {
    var echEl = document.getElementById('infoEcheanceContent');
    var clsEl = document.getElementById('infoClassementContent');

    // Échéance
    if (echEl) {
        if (!preview || !preview.echeance) {
            echEl.textContent = 'Néant';
        } else {
            var echStatus = preview.echeance.status;
            var echData = preview.echeance.data;
            if (echStatus === 'running' || echStatus === 'miss') {
                echEl.textContent = 'Analyse en cours…';
            } else if (echStatus === 'error') {
                echEl.textContent = 'Néant';  // fallback en cas d'erreur scan
            } else if (Array.isArray(echData) && echData.length > 0) {
                // Afficher la première échéance (plus récente / plus importante)
                var e = echData[0];
                var txt = '';
                if (e.description) txt += e.description;
                if (e.date_echeance) txt += (txt ? ' — ' : '') + e.date_echeance;
                echEl.textContent = txt || 'Échéance détectée';
            } else {
                echEl.textContent = 'Néant';
            }
        }
    }

    // Classement
    if (clsEl) {
        if (!preview || !preview.classement) {
            clsEl.textContent = 'Néant';
            _classementCacheData = null;
            _setClassementFieldClickable(false);
        } else {
            var clsStatus = preview.classement.status;
            var clsData = preview.classement.data;
            if (clsStatus === 'running' || clsStatus === 'miss') {
                clsEl.textContent = 'Analyse en cours…';
                _setClassementFieldClickable(false);
            } else if (clsData && clsData.suggestion) {
                var sugg = clsData.suggestion;
                var folderPath = sugg.folder_path || sugg.folder_name || sugg.folder_id || 'Dossier suggéré';
                clsEl.textContent = folderPath;
                // Étape 4' (02/05 PM) — Stocker pour popup pré-envoi cliquable
                _classementCacheData = clsData;
                _setClassementFieldClickable(true);
            } else {
                // Sujet PLUS_TARD_VF #4 (28/04) — wording transparent selon
                // la raison pour laquelle aucune suggestion n'est proposée.
                // 'source' arrive du backend (mail_classement_cache.source) :
                //   - 'none_auto_email'     : noreply / mailer-daemon
                //   - 'none_new_sender'     : contact jamais vu (mais domaine connu)
                //   - 'none_unknown_domain' : domaine + contact inconnus
                //   - 'none_low_signal'     : signal trop faible (mail trop court)
                //   - 'none' (fallback)     : pas de raison classifiée
                //   - 'self'                : mail à soi-même
                var clsSrc = (clsData && clsData.source) || 'none';
                var clsMsgs = {
                    'none_auto_email':     'Mail automatique — pas de dossier métier évident.',
                    'none_new_sender':     "Premier mail de ce contact — je m'inspirerai de ton classement.",
                    'none_unknown_domain': 'Domaine que je découvre — apprends-moi en classant.',
                    'none_low_signal':     'Mail trop court pour suggérer un dossier.',
                    'self':                'Mail envoyé à toi-même.',
                };
                clsEl.textContent = clsMsgs[clsSrc] || 'Néant';
                // Étape 4' fix (02/05 PM signal Yvan) — Champ cliquable AUSSI
                // sans suggestion BG (cas 'none' / 'none_*' / 'self') pour
                // permettre classement manuel via arbo + saisie path. La popup
                // s'ouvre alors sans bandeau bleu, juste arbo + manuel.
                _classementCacheData = clsData || { suggestion: null, suggestions: [], source: clsSrc };
                _setClassementFieldClickable(true);
            }
        }
    }

    // Classement PJ (Phase 2 - 24/04 + étape 4'' 02/05 PM clickable)
    var pjEl = document.getElementById('infoClassementPJContent');
    if (pjEl) {
        if (!preview || !preview.pj_classement) {
            pjEl.textContent = 'Néant';
            _classementPJCacheData = null;
            _setClassementPJFieldClickable(false);
        } else {
            var pjStatus = preview.pj_classement.status;
            var pjData = preview.pj_classement.data;
            if (pjStatus === 'running' || pjStatus === 'miss') {
                pjEl.textContent = 'Analyse en cours…';
                _setClassementPJFieldClickable(false);
            } else if (pjData && pjData.source === 'no_pj') {
                pjEl.textContent = 'Néant';  // Fix Néant (25/04) — "Pas de PJ" → "Néant" (demande user)
                _classementPJCacheData = null;
                _setClassementPJFieldClickable(false);
            } else if (pjData && pjData.suggestion) {
                var pjSugg = pjData.suggestion;
                var pjPath = pjSugg.folder_path || pjSugg.dest_folder || pjSugg.folder_name || 'Dossier suggéré';
                pjEl.textContent = pjPath;
                // Étape 4'' (02/05 PM) — Stocker pour popup pré-envoi PJ
                _classementPJCacheData = pjData;
                _setClassementPJFieldClickable(true);
            } else {
                pjEl.textContent = 'Néant';
                // Étape 4'' (02/05 PM) — Cliquable même sans suggestion BG
                // (cohérent avec fix mail) pour permettre classement manuel
                _classementPJCacheData = pjData || { suggestion: null, suggestions: [], source: 'none' };
                _setClassementPJFieldClickable(true);
            }
        }
    }

    // Auto-poll si status running (pour éviter "Analyse en cours" figé)
    var needsPoll = preview && ((preview.echeance && preview.echeance.status === 'running')
                              || (preview.classement && preview.classement.status === 'running')
                              || (preview.pj_classement && preview.pj_classement.status === 'running')
                              || (preview.echeance && preview.echeance.status === 'miss')
                              || (preview.classement && preview.classement.status === 'miss')
                              || (preview.pj_classement && preview.pj_classement.status === 'miss'));
    if (needsPoll && !window.__mailPreviewPolling && _messageId) {
        // Fix 27/04 (Pattern #17 audit) : snapshot _messageId pour le poll.
        // Sans ça, si l'user navigue pendant les 20s du poll, on
        // afficherait les données de l'ancien mail dans le dialog courant.
        var pollMid = _messageId;
        window.__mailPreviewPolling = true;
        var pollCount = 0;
        var poll = function() {
            pollCount++;
            if (pollCount > 10) {  // stop après 20s (10 × 2s)
                window.__mailPreviewPolling = false;
                return;
            }
            // Garde : abort si user a navigué vers un autre mail
            if (_messageId !== pollMid) {
                window.__mailPreviewPolling = false;
                return;
            }
            fetch(_backendUrl + '/api/mail_preview/' + encodeURIComponent(pollMid))
                .then(function(r) { return r.ok ? r.json() : null; })
                .then(function(newPreview) {
                    if (!newPreview) { window.__mailPreviewPolling = false; return; }
                    // Re-vérifier après le fetch
                    if (_messageId !== pollMid) {
                        window.__mailPreviewPolling = false;
                        return;
                    }
                    _applyMailPreview(newPreview);
                    var stillRunning = (newPreview.echeance && newPreview.echeance.status === 'running')
                                     || (newPreview.classement && newPreview.classement.status === 'running')
                                     || (newPreview.pj_classement && newPreview.pj_classement.status === 'running');
                    if (stillRunning) {
                        setTimeout(poll, 2000);
                    } else {
                        window.__mailPreviewPolling = false;
                    }
                })
                .catch(function() { window.__mailPreviewPolling = false; });
        };
        setTimeout(poll, 2000);
    }
}

/** Phase 3 (25/04 soir) — 3 portes séparées en parallèle.
 * Chaque plat (échéance, classement mail, classement PJ) a sa porte dédiée.
 * Service progressif : le rapide arrive avant le lent.
 * Polling indépendant par plat — l'un peut continuer pendant que l'autre est fini.
 */
function _fetchSinglePreviewPlates() {
    if (!_messageId) return;
    // Fix 27/04 (Pattern #17 audit) : snapshot _messageId pour les 3 plats.
    // Si l'user navigue vers un autre mail pendant les retries (24s max),
    // on évite d'afficher les données du mauvais mail dans le dialog courant.
    var mid = _messageId;
    _fetchSinglePlate('echeance', '/api/echeance/', mid);
    _fetchSinglePlate('classement', '/api/classement_mail/', mid);
    _fetchSinglePlate('pj_classement', '/api/classement_pj/', mid);
}

function _fetchSinglePlate(plateName, urlPrefix, messageId, attempt) {
    attempt = attempt || 0;
    var maxAttempts = 12;  // 24s max (12 × 2s)
    // Garde Pattern #17 : si l'user a navigué vers un autre mail, abort
    // (on n'écrira pas les données de l'ancien mail dans le DOM courant).
    if (_messageId !== messageId) return;
    fetch(_backendUrl + urlPrefix + encodeURIComponent(messageId))
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(res) {
            if (!res) return;
            // Re-vérifier après le fetch (peut prendre 100ms-2s)
            if (_messageId !== messageId) return;
            // Appliquer SEULEMENT ce plat (les autres conservent leur valeur actuelle)
            _applySinglePlate(plateName, res);
            // Si still running/miss, repolll dans 2s (max 12 tentatives = 24s)
            if ((res.status === 'running' || res.status === 'miss') && attempt < maxAttempts) {
                setTimeout(function() {
                    _fetchSinglePlate(plateName, urlPrefix, messageId, attempt + 1);
                }, 2000);
            }
        })
        .catch(function(e) {
            console.warn('[dialog] _fetchSinglePlate ' + plateName + ' failed:', e);
        });
}

function _applySinglePlate(plateName, res) {
    // Appliquer 1 seul plat sans toucher aux 2 autres.
    if (plateName === 'echeance') {
        var echEl = document.getElementById('infoEcheanceContent');
        if (!echEl) return;
        if (res.status === 'running' || res.status === 'miss') {
            echEl.textContent = 'Analyse en cours…';
        } else if (res.status === 'error') {
            echEl.textContent = 'Néant';
        } else if (Array.isArray(res.data) && res.data.length > 0) {
            var e = res.data[0];
            var txt = '';
            if (e.description) txt += e.description;
            if (e.date_echeance) txt += (txt ? ' — ' : '') + e.date_echeance;
            echEl.textContent = txt || 'Échéance détectée';
        } else {
            echEl.textContent = 'Néant';
        }
    } else if (plateName === 'classement') {
        var clsEl = document.getElementById('infoClassementContent');
        if (!clsEl) return;
        if (res.status === 'running' || res.status === 'miss') {
            clsEl.textContent = 'Analyse en cours…';
            _setClassementFieldClickable(false);
        } else if (res.data && res.data.suggestion) {
            var sugg = res.data.suggestion;
            var folderPath = sugg.folder_path || sugg.folder_name || sugg.folder_id || 'Dossier suggéré';
            clsEl.textContent = folderPath;
            // Étape 4' (02/05 PM) — Stocker données pour popup pré-envoi cliquable
            _classementCacheData = res.data;
            _setClassementFieldClickable(true);
        } else {
            // Étape 4' fix (02/05 PM signal Yvan) — Wording « Néant » +
            // messages contextuels MAIS champ cliquable (cas 'none'/'self'/
            // 'none_*') pour permettre classement manuel via arbo + saisie
            // path. Avant : champ désactivé → l'user ne pouvait pas classer
            // manuellement quand BoosterMail n'avait rien à proposer.
            var clsSrc2 = (res.data && res.data.source) || 'none';
            var clsMsgs2 = {
                'none_auto_email':     'Mail automatique — pas de dossier métier évident.',
                'none_new_sender':     "Premier mail de ce contact — je m'inspirerai de ton classement.",
                'none_unknown_domain': 'Domaine que je découvre — apprends-moi en classant.',
                'none_low_signal':     'Mail trop court pour suggérer un dossier.',
                'self':                'Mail envoyé à toi-même.',
            };
            clsEl.textContent = clsMsgs2[clsSrc2] || 'Néant';
            _classementCacheData = res.data || { suggestion: null, suggestions: [], source: clsSrc2 };
            _setClassementFieldClickable(true);
        }
    } else if (plateName === 'pj_classement') {
        var pjEl = document.getElementById('infoClassementPJContent');
        if (!pjEl) return;
        if (res.status === 'running' || res.status === 'miss') {
            pjEl.textContent = 'Analyse en cours…';
            _setClassementPJFieldClickable(false);
        } else if (res.data && res.data.source === 'no_pj') {
            pjEl.textContent = 'Néant';
            _classementPJCacheData = null;
            _setClassementPJFieldClickable(false);
        } else if (res.data && res.data.suggestion) {
            var pjSugg = res.data.suggestion;
            var pjPath = pjSugg.folder_path || pjSugg.dest_folder || pjSugg.folder_name || 'Dossier suggéré';
            pjEl.textContent = pjPath;
            // Étape 4'' (02/05 PM) — Stocker pour popup pré-envoi PJ
            _classementPJCacheData = res.data;
            _setClassementPJFieldClickable(true);
        } else {
            pjEl.textContent = 'Néant';
            // Étape 4'' (02/05 PM) — Cliquable sans suggestion (cohérent fix mail)
            _classementPJCacheData = res.data || { suggestion: null, suggestions: [], source: 'none' };
            _setClassementPJFieldClickable(true);
        }
    }
}

/** Application tags contact (extrait de _loadContactTags) */
function _applyContactProfile(p) {
    if (!p) return;
    var tagReg = document.getElementById('tagRegister');
    if (tagReg && p.register) { tagReg.textContent = p.register; tagReg.style.display = ''; }
    var tagConf = document.getElementById('tagConfidence');
    if (tagConf && p.confidence !== undefined) {
        // Fix 01/05/2026 (signal Yvan : Stephane Dufau affichait 1% au lieu
        // de 100%) : la confidence en DB est sur l'échelle 0-1 (float). Il
        // faut la multiplier par 100 pour avoir le pourcentage. Cohérent
        // avec d'autres sites qui font Math.round(confidence * 100) + '%'.
        var pct = (p.confidence > 1) ? p.confidence : Math.round(p.confidence * 100);
        tagConf.textContent = 'confiance ' + pct + '%';
        tagConf.style.display = '';
    }
    _perfMonitor.mark('T6_contact_profile');
}

/** Rendu instant résumé depuis bundle cache DB */
function _renderSummaryInstant(points, actions) {
    var pointsBox = document.getElementById('resumePoints');
    var actionsBox = document.getElementById('resumeActionsList');
    var spinner = document.getElementById('resumeSpinner');
    _summaryStatus = 'success';  // #16 résumé reçu depuis cache DB (même si 0 points)
    _perfMonitor.mark('T4_summary_first_point', 'cache');
    if (pointsBox) {
        var title = pointsBox.querySelector('.resume-section-title');
        pointsBox.innerHTML = '';
        if (title) pointsBox.appendChild(title);
        if (points.length === 0) {
            var empty = document.createElement('div');
            empty.style.cssText = 'color:#999;font-size:10px;';
            empty.textContent = _getEmptyPointsMessage();  // #16 wording contextualisé
            pointsBox.appendChild(empty);
        } else {
            var ul = document.createElement('ul');
            ul.style.cssText = 'margin:0;padding-left:16px;font-size:11px;line-height:1.5;';
            points.forEach(function(p) {
                var li = document.createElement('li');
                li.textContent = p;
                ul.appendChild(li);
            });
            pointsBox.appendChild(ul);
        }
    }
    if (actionsBox) {
        actionsBox.innerHTML = '';
        if (actions.length === 0) {
            var emptyA = document.createElement('span');
            emptyA.style.cssText = 'color:#999;font-size:10px;';
            emptyA.textContent = 'Aucune action explicite.';
            actionsBox.appendChild(emptyA);
        } else {
            var ulA = document.createElement('ul');
            ulA.style.cssText = 'margin:0;padding-left:16px;font-size:11px;line-height:1.5;';
            actions.forEach(function(a) {
                var li = document.createElement('li');
                li.textContent = a;
                ulA.appendChild(li);
            });
            actionsBox.appendChild(ulA);
        }
    }
    if (spinner) spinner.classList.remove('active');
    _perfMonitor.mark('T4_summary_done', 'cache');
    _perfMonitor.mark('T4_summary_source', 'cache');
}

/** Fallback body : ancien /api/email_body (si bundle KO) */
function _legacyFetchBody() {
    fetch(_backendUrl + '/api/email_body?messageId=' + encodeURIComponent(_messageId))
        .then(function(r) {
            if (r.status === 403) {
                document.getElementById('mailBody').innerHTML =
                    '<p style="color:#999; font-size:11px;">Body disponible apres generation (Mode Perf. Reduite).</p>';
                var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');
                return null;
            }
            return r.json();
        })
        .then(function(data) {
            if (!data) return;
            _renderMailBody(data);
            if (data.attachments && data.attachments.length > 0) {
                _renderAttachments(data.attachments);
            }
        })
        .catch(function(err) {
            var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');
            document.getElementById('mailBody').innerHTML =
                '<p style="color:#c00; font-size:11px;">Erreur chargement : ' + _escapeHtml(err.message) + '</p>';
        });
}

/** Fallback tags contact : ancien /api/contact_profile/<email> (si bundle KO) */
function _legacyFetchContactTags() {
    if (!_fromEmail) return;
    fetch(_backendUrl + '/api/contact_profile/' + encodeURIComponent(_fromEmail))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data && data.profile) _applyContactProfile(data.profile);
        })
        .catch(function() {});
}


function _renderAttachments(attachments) {
    _attachmentsList = attachments;  // Sauvegarder pour les popups PJ
    var pjList = document.getElementById('pjList');
    pjList.innerHTML = '';
    attachments.forEach(function(att) {
        if (att.is_inline) return;  // Skip images inline
        var chip = document.createElement('span');
        chip.className = 'pj-chip';
        chip.innerHTML = '&#x1f4c4; ' + _escapeHtml(att.name) +
            (att.size ? ' <span style="color:#aaa;">(' + _formatSize(att.size) + ')</span>' : '');
        pjList.appendChild(chip);
    });
    if (pjList.children.length === 0) {
        pjList.innerHTML = '<span style="color:#999; font-size:11px;">Aucune piece jointe</span>';
    }
    _perfMonitor.mark('T7_pj_rendered', attachments.length);

    // Mettre à jour le badge PJ dans l'onglet
    var pjTab = document.querySelector('[data-tab="pj"]');
    if (pjTab) {
        pjTab.textContent = '\uD83D\uDCCE PJ (' + pjList.children.length + ')';
    }

    // Mettre à jour les PJ dans l'onglet Résumé (mockup v14)
    var resumePJList = document.getElementById('resumePJList');
    var resumePJ = document.getElementById('resumePJ');
    if (resumePJList && resumePJ) {
        resumePJList.innerHTML = '';
        var hasPJ = false;
        attachments.forEach(function(att) {
            if (att.is_inline) return;
            hasPJ = true;
            var chip = document.createElement('span');
            chip.className = 'resume-att-chip';
            chip.textContent = '\uD83D\uDCC4 ' + att.name;
            resumePJList.appendChild(chip);
        });
        resumePJ.style.display = hasPJ ? 'block' : 'none';
    }

    // D\u00E9cision Yvan 02/05/2026 : afficher la popup PJ proactivement \u00E0
    // l'ouverture du dialog d\u00E8s que les attachments sont charg\u00E9s, M\u00CAME si
    // la r\u00E9ponse a \u00E9t\u00E9 servie depuis le cache (instant_reply HIT).
    // Objectif UX : informer l'user que BoosterMail a d\u00E9tect\u00E9 les PJ et
    // qu'il peut les analyser \u2014 montre la puissance du produit. Quel que
    // soit le clic Oui/Non, la r\u00E9ponse cach\u00E9e s'affiche derri\u00E8re (elle
    // int\u00E8gre d\u00E9j\u00E0 l'analyse PJ c\u00F4t\u00E9 backend).
    // Conditions : mode reply (forward a sa propre popup), pas encore
    // choisi, au moins une PJ non-inline visible.
    if (_mode === 'reply' && !_pjChoiceMade && pjList.children.length > 0) {
        _showPjAnalysisPopup();
    }
}


// =============================================================================
// ONGLETS (Mail reçu / PJ)
// =============================================================================

function _initTabs() {
    var tabs = document.querySelectorAll('.mail-tab');
    tabs.forEach(function(tab) {
        tab.addEventListener('click', function() {
            var target = tab.getAttribute('data-tab');
            // Désactiver tous les onglets
            tabs.forEach(function(t) { t.classList.remove('active'); });
            document.querySelectorAll('.tab-pane').forEach(function(p) { p.classList.remove('active'); });
            // Activer l'onglet cliqué
            tab.classList.add('active');
            var pane = document.getElementById('tab-' + target);
            if (pane) pane.classList.add('active');
        });
    });
}


// =============================================================================
// IMPORTANCE R/S/H
// =============================================================================

function selectImportance(el) {
    document.querySelectorAll('.em-imp-chip').forEach(function(c) {
        c.classList.remove('active');
    });
    el.classList.add('active');
    _importance = el.getAttribute('data-imp');
}


// =============================================================================
// FORMATAGE RICH TEXT
// =============================================================================

function execFmt(cmd, value) {
    document.execCommand(cmd, false, value || null);
    document.getElementById('editor').focus();
}

// Appliquer taille de police (combobox custom)
function applyFontSize(val) {
    var size = parseInt(val, 10);
    if (isNaN(size) || size < 1) return;
    // execCommand fontSize n'accepte que 1-7, on utilise une approche CSS pour les tailles custom
    var fontSize;
    if (size <= 8) fontSize = 1;
    else if (size <= 10) fontSize = 2;
    else if (size <= 12) fontSize = 3;
    else if (size <= 14) fontSize = 4;
    else if (size <= 18) fontSize = 5;
    else if (size <= 24) fontSize = 6;
    else fontSize = 7;
    document.execCommand('fontSize', false, fontSize);
    document.getElementById('editor').focus();
}

// Toggle dropdown surlignage
function toggleHiliteDropdown() {
    var dd = document.getElementById('hiliteDropdown');
    dd.classList.toggle('active');
}

// Appliquer couleur surlignage
function applyHilite(color) {
    if (color === 'transparent') {
        document.execCommand('removeFormat', false, null);
    } else {
        document.execCommand('hiliteColor', false, color);
    }
    document.getElementById('hiliteDropdown').classList.remove('active');
    document.getElementById('editor').focus();
}

// Fermer le dropdown surlignage au clic extérieur
document.addEventListener('click', function(e) {
    var dd = document.getElementById('hiliteDropdown');
    if (dd && dd.classList.contains('active')) {
        var btn = document.getElementById('btnHilite');
        if (!dd.contains(e.target) && e.target !== btn) {
            dd.classList.remove('active');
        }
    }
});


// =============================================================================
// GÉNÉRATION IA (SSE Streaming) — squelette 12f, complété en 12g
// =============================================================================

function generateReply() {
    if (_isGenerating) return;

    // Popup PJ forward (si forward avec PJ et pas encore choisi)
    if (_shouldShowFwdPjPopup()) {
        _showFwdPjPopup();
        return;  // La popup appellera includeSelectedFwdAttachments/skipFwdAttachments
    }

    // Popup analyse PJ (si PJ et pas encore choisi)
    if (_shouldShowPjPopup()) {
        _showPjAnalysisPopup();
        return;  // acceptPjAnalysis/skipPjAnalysis rappellera generateReply()
    }

    var brief = document.getElementById('fieldBrief').value.trim();
    var editor = document.getElementById('editor');
    var spinner = document.getElementById('genSpinner');
    var btnGen = document.getElementById('btnGenerate');

    // Brief obligatoire en mode nouveau mail
    if (_mode === 'new' && !brief) {
        alert('Le brief est obligatoire pour un nouveau mail.');
        document.getElementById('fieldBrief').focus();
        return;
    }

    // Destinataire obligatoire en mode nouveau mail
    if (_mode === 'new' && !document.getElementById('fieldTo').value.trim()) {
        alert('Le champ À est obligatoire pour un nouveau mail.');
        document.getElementById('fieldTo').focus();
        return;
    }

    // Sauvegarder l'état actuel pour undo
    if (editor.innerHTML.trim()) {
        _pushUndo(editor.innerHTML);
    }

    // UI : mode génération
    _isGenerating = true;
    btnGen.disabled = true;
    spinner.classList.add('active');
    // Phase 2/3 progression : force l'affichage (remplace le texte user
    // comme le faisait le editor.innerHTML = '' d'origine).
    _showProgressPlaceholder(_mailBodyForGeneration ? 'writing' : 'context', true);
    document.getElementById('headerStatus').textContent = 'Lecture du contexte...';
    _sendStartTime = Date.now();

    // SAFETY : si le body n'est pas encore chargé (click rapide avant fin du fetch async),
    // le récupérer synchroniquement avant d'appeler Claude (sinon réponse vide/non pertinente)
    var _proceedWithGeneration = function() {
        console.log('[dialog] generateReply: body length =', (_mailBodyForGeneration || '').length);
        var body = JSON.stringify({
            message_id: _messageId,
            brief: brief,
            importance: _importance,
            mode: _mode,
            to: document.getElementById('fieldTo').value,
            subject: document.getElementById('fieldSubject').value,
            from_email: _fromEmail,
            from_name: _fromName,
            body: _mailBodyForGeneration,
            pj_context: _extractedPjContext || '',
            fwd_pj_indices: _fwdSelectedIndexes.length > 0 ? _fwdSelectedIndexes : undefined,
        });
        // Placeholder final : "Rédaction en cours..." (avant le stream SSE).
        // Si le template matche, _tryTemplateMatch écrase l'éditeur avec le
        // template → placeholder remplacé proprement.
        if (_progressPlaceholderActive) _showProgressPlaceholder('writing');

        // Plan 2 Phase 1 — tenter un template ($0, <100 ms) avant Claude
        // Sauf si l'user vient de cliquer "Autre réponse" → skip template
        if (_skipTemplateMatch) {
            _skipTemplateMatch = false;
            _fetchGenerateReply(body);
            return;
        }
        _tryTemplateMatch(brief, function(matched) {
            if (!matched) _fetchGenerateReply(body);
        });
    };

    if (!_mailBodyForGeneration && _messageId && _mode !== 'new') {
        // Récupérer le body manquant avant génération
        document.getElementById('headerStatus').textContent = 'Chargement du mail...';
        fetch(_backendUrl + '/api/email_body?messageId=' + encodeURIComponent(_messageId))
            .then(function(r) { return r.json(); })
            .then(function(ebody) {
                if (ebody && (ebody.body || ebody.html_body)) {
                    _mailBodyForGeneration = ebody.body || ebody.html_body || '';
                    _receivedBody = _mailBodyForGeneration;
                }
                _proceedWithGeneration();
            })
            .catch(function() { _proceedWithGeneration(); });
        return;
    }

    _proceedWithGeneration();
}

/**
 * Plan 2 Phase 1 — Tente un template (fixe ou appris) AVANT d'appeler Claude.
 * Si match avec confiance >= 0.75 : affiche le template directement, badge "Réponse rapide",
 * callback(true). Sinon : callback(false) pour que le caller lance la génération IA.
 *
 * Coût $0, temps <100 ms (pas de streaming SSE, affichage instantané).
 */
function _tryTemplateMatch(brief, callback) {
    var editor = document.getElementById('editor');
    var spinner = document.getElementById('genSpinner');
    var btnGen = document.getElementById('btnGenerate');

    var payload = JSON.stringify({
        email_body: _mailBodyForGeneration || '',
        subject: document.getElementById('fieldSubject').value || '',
        brief: brief || '',
        reply_mode: _mode,
        importance: _importance,
        current_draft: (editor.innerText || '').trim(),
        from_email: _fromEmail || '',
    });

    document.getElementById('headerStatus').textContent = 'Vérification template...';

    fetch(_backendUrl + '/api/match_template', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
    })
    .then(function(r) { return r.json(); })
    .then(function(result) {
        if (!result || !result.match || !result.threshold_passed) {
            callback(false);
            return;
        }
        // MATCH — afficher le template en remplaçant le contenu éditeur
        console.log('[dialog] Template match', result.template_name,
                    'conf=' + result.confidence, 'src=' + result.source);
        // Fix XSS audit 21/04 : escape le template avant innerHTML. Les templates
        // appris (learned_templates) peuvent contenir du texte user copié avec
        // potentiels caractères HTML. Escape = défense en profondeur.
        var html = _escapeHtml(result.template || '').replace(/\n/g, '<br>');
        editor.innerHTML = html;
        _isGenerating = false;
        btnGen.disabled = false;
        spinner.classList.remove('active');
        _showTemplateBadge(result);
        document.getElementById('headerStatus').textContent = 'Réponse rapide (template)';
        // Mémoriser pour le learning loop côté serveur à l'envoi
        _lastTemplateMatch = {
            id: result.template_id, name: result.template_name,
            source: result.source, confidence: result.confidence,
        };
        _perfMonitor.mark('T5_reply_first_chunk', 'template');
        _perfMonitor.mark('T5_reply_done', 'template');
        _perfMonitor.mark('T5_reply_source', 'template');
        callback(true);
    })
    .catch(function(e) {
        console.warn('[dialog] match_template erreur, fallback génération:', e);
        callback(false);
    });
}

/** Affiche un badge discret "Réponse rapide · template" près de l'éditeur. */
function _showTemplateBadge(result) {
    var existing = document.getElementById('tplBadge');
    if (existing) existing.remove();
    var badge = document.createElement('div');
    badge.id = 'tplBadge';
    badge.className = 'tpl-badge';
    var label = result.source === 'learned' ? 'Réponse apprise' : 'Réponse rapide';
    badge.innerHTML = '<span class="tpl-badge-dot">●</span> ' + label +
                      ' · ' + (result.template_name || 'template') +
                      ' <span class="tpl-badge-conf">' +
                      Math.round((result.confidence || 0) * 100) + '%</span>';
    var editor = document.getElementById('editor');
    editor.parentNode.insertBefore(badge, editor);
}

var _lastTemplateMatch = null;


// =============================================================================
// Plan 2 Phase 5 — Pipeline unifié "réponse instantanée" à l'ouverture
// =============================================================================

function _tryInstantReply() {
    if (!_messageId) return;
    var editor = document.getElementById('editor');
    // Ne pas écraser si l'user a déjà commencé à taper.
    // Fix 23/04 : ignorer notre propre placeholder "Recherche de l'historique..."
    // qui, avant ce fix, bloquait tout le flow (pas d'instant_reply, pas
    // d'auto_generate → réponse jamais rendue en mode standalone).
    if (!_progressPlaceholderActive
        && editor.innerText && editor.innerText.trim()) return;

    var payload = JSON.stringify({
        message_id: _messageId,
        email_body: _mailBodyForGeneration || '',
        subject: document.getElementById('fieldSubject').value || '',
        brief: document.getElementById('fieldBrief').value || '',
        reply_mode: _mode,
        importance: _importance,
        current_draft: (editor.innerText || '').trim(),
        from_email: _fromEmail || '',
    });

    fetch(_backendUrl + '/api/instant_reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
    })
    .then(function(r) { return r.json(); })
    .then(function(res) {
        if (!res || res.source === 'none') {
            console.log('[dialog] instant_reply: aucun hit → déclenchement auto generateReply()');
            // Test 21/04 — Génération automatique si pas de cache hit.
            _triggerAutoGenerate();
            return;
        }
        console.log('[dialog] instant_reply HIT', res.source, res.badge || '');
        // P0.5 (24/04) : si le serveur marque res.html === true, le texte est
        // déjà en HTML propre (normalise côté backend _normalize_reply_to_html).
        // Affichage direct via innerHTML, aucun travail de mise en forme ici.
        // Sinon fallback legacy : escape + \n→<br> (cache pré-P0.5 ou draft
        // user plain text).
        if (res.html === true) {
            editor.innerHTML = res.text || '';
        } else {
            editor.innerHTML = _escapeHtml(res.text || '').replace(/\n/g, '<br>');
        }
        _showInstantReplyBadge(res);
        if (res.source === 'template') {
            _lastTemplateMatch = {
                id: res.template_id, name: res.template_name,
                source: res.template_source, confidence: res.confidence,
            };
        }
        // Fix 28/04 PM : btnSend reste disabled sur New Outlook desktop si on
        // n'active pas explicitement apres un cache HIT instant_reply. Le path
        // streaming Claude passe par _onGenerationDone() qui active le bouton
        // (l. 2040), mais le path cache HIT (ce bloc) ne passait pas par la.
        // Sur Outlook Web, un effet de bord du browser (re-render via assignation
        // innerHTML) reactivait accidentellement le bouton, mais ce n'est pas
        // fiable cross-platform — sur New Outlook desktop (WebView2) le bouton
        // restait grise. Activation explicite ici = comportement uniforme.
        var _btnSendInstant = document.getElementById('btnSend');
        if (_btnSendInstant) _btnSendInstant.disabled = false;
        // Perf : réponse affichée en instant via cache (draft / préemptif / template)
        _perfMonitor.mark('T5_reply_first_chunk', res.source || 'cache');
        _perfMonitor.mark('T5_reply_done', res.source || 'cache');
        _perfMonitor.mark('T5_reply_source', res.source || 'cache');
    })
    .catch(function(e) { console.warn('[dialog] instant_reply erreur', e); });
}

/**
 * Test 21/04 — Déclenche generateReply() automatiquement avec garde-fous :
 *   - Skip si mode='new' (brief obligatoire)
 *   - Skip si user a déjà tapé
 *   - Skip si _isGenerating (protection double trigger avec _checkSpeculativeCache)
 *   - ATTEND que _mailBodyForGeneration soit peuplé (sinon generateReply
 *     envoie body vide → réponse dégradée). Retry jusqu'à 3 s max.
 */
var _autoGeneratePending = false;

function _triggerAutoGenerate() {
    if (_autoGeneratePending) return;       // Garde double déclenchement
    if (_isGenerating) return;               // Déjà en cours (via _checkSpeculativeCache)
    if (_mode === 'new') return;             // Brief obligatoire
    var editor = document.getElementById('editor');
    // Fix 23/04 : le check "user a tapé" ne doit PAS matcher notre placeholder
    // "🔍 Recherche de l'historique..." (sinon la génération est bloquée en
    // standalone car _loadMailBodyStandalone active un placeholder AVANT que
    // _triggerAutoGenerate ne soit appelé). On consulte la variable globale
    // _progressPlaceholderActive qui indique si le texte vient de nous.
    if (!_progressPlaceholderActive
        && editor && editor.innerText && editor.innerText.trim()) return;

    _autoGeneratePending = true;
    var _t0 = Date.now();
    var _waitBodyAndGen = function() {
        // Si user a commencé à taper entre-temps → on abandonne
        var ed = document.getElementById('editor');
        // Même garde anti-placeholder dans la boucle d'attente
        if (!_progressPlaceholderActive
            && ed && ed.innerText && ed.innerText.trim()) {
            _autoGeneratePending = false;
            return;
        }
        // Si autre flow a lancé une génération entre-temps (ex: _checkSpeculativeCache) → abandon
        if (_isGenerating) {
            _autoGeneratePending = false;
            return;
        }
        // Body prêt OU mode sans body OU timeout 3 s → lancer
        if (_mailBodyForGeneration || _mode === 'forward' || (Date.now() - _t0) > 3000) {
            _autoGeneratePending = false;
            if (typeof generateReply === 'function') {
                console.log('[dialog] auto-generateReply() déclenchée après ' +
                            (Date.now() - _t0) + 'ms, body_len=' +
                            (_mailBodyForGeneration || '').length);
                generateReply();
            }
            return;
        }
        // Retry 150 ms plus tard
        setTimeout(_waitBodyAndGen, 150);
    };
    setTimeout(_waitBodyAndGen, 150);
}

function _showInstantReplyBadge(res) {
    // Refonte 28/04/2026 — Option A : suppression complete du badge instant
    // reply ("Pre-generee il y a X j" / "Reponse depuis brouillon" / template
    // confidence %). Decision Yvan post-test Outlook Web : info non pertinente
    // pour l'usage quotidien (sur-mesure pret, peu importe quand) et rognait
    // ~26 px d'editeur. Si plus tard on veut reafficher la confidence sur les
    // templates pour les beta-testeurs, restaurer le bloc complet depuis git
    // history (commit precedent). Cleanup d'un eventuel badge orphelin garde
    // par securite (au cas ou la fonction serait appelee plusieurs fois dans
    // le meme runtime — ne devrait pas arriver mais sans risque).
    var existing = document.getElementById('tplBadge') || document.getElementById('draftBadge');
    if (existing) existing.remove();
}


// =============================================================================
// Plan 2 Phase 2.A — Cache brouillon unifié (ex-drafts_v2 + _preemptive_cache)
// =============================================================================

var _draftSaveTimer = null;

function _restoreDraft() {
    if (!_messageId) return;
    fetch(_backendUrl + '/api/get_draft?message_id=' + encodeURIComponent(_messageId))
        .then(function(r) { return r.json(); })
        .then(function(res) {
            if (!res || !res.found) return;
            var editor = document.getElementById('editor');
            // Ne pas écraser si l'user a déjà commencé à taper (mais OK si
            // c'est juste notre placeholder de progression).
            if (!_progressPlaceholderActive
                && editor.innerText && editor.innerText.trim()) return;
            // Fix XSS audit 21/04 : escape avant innerHTML (res.text = draft DB)
            editor.innerHTML = _escapeHtml(res.text || '').replace(/\n/g, '<br>');
            _showDraftBadge(res.timestamp);
            console.log('[dialog] Brouillon restauré pour', _messageId.substring(0, 20));
        })
        .catch(function() {});
}

function _showDraftBadge(timestamp) {
    var existing = document.getElementById('draftBadge');
    if (existing) existing.remove();
    var badge = document.createElement('div');
    badge.id = 'draftBadge';
    badge.className = 'tpl-badge';  // réutilise le même style que le template badge
    var ageText = '';
    if (timestamp) {
        var delta = Math.round((Date.now() / 1000 - timestamp) / 60);
        if (delta < 60) ageText = ' il y a ' + delta + ' min';
        else if (delta < 1440) ageText = ' il y a ' + Math.round(delta / 60) + ' h';
        else ageText = ' il y a ' + Math.round(delta / 1440) + ' j';
    }
    badge.innerHTML = '<span class="tpl-badge-dot">●</span> Brouillon sauvegardé' + ageText;
    var editor = document.getElementById('editor');
    editor.parentNode.insertBefore(badge, editor);
}

// Fix 23/04 (bug brouillon fantôme) : flag qui distingue vrai édit user vs
// simple affichage programmatique (innerHTML = ...) d'un préemptif Claude.
// L'event 'input' fire UNIQUEMENT sur frappe clavier / coller / drop — pas
// sur innerHTML ni insertAdjacentText. Donc c'est un signal fiable de
// "l'user a tapé au moins une touche".
// Sans ce flag, _saveDraftNow() au beforeunload sauvegardait le préemptif
// Claude affiché comme si c'était un brouillon user → au clic BM suivant,
// affichage trompeur "Brouillon sauvegardé il y a 3h" pour une réponse
// que l'user n'a jamais touchée.
var _userHasTypedSomething = false;

/**
 * Sauvegarde un brouillon avec un message_id snapshot (capturé au schedule).
 * Fix 27/04 (BUG CRITIQUE Vincent Hubert ↔ Ombeline) : le timer 2s du debounce
 * ne doit PAS lire _messageId/_fromEmail au moment du fire car ces variables
 * globales peuvent avoir changé si l'user a navigué vers un autre mail entre
 * la frappe et le fire. Symptôme observé 26/04 : draft Ombeline sauvegardé
 * sous l'IMID Vincent Hubert → au prochain clic V.Hubert, instant_reply
 * step 1 (draft user_edit, prio absolue) retourne le mauvais texte.
 */
function _saveDraftFor(messageId, fromEmail, importance) {
    if (!messageId) return;
    if (!_userHasTypedSomething) return;
    var editor = document.getElementById('editor');
    if (!editor) return;
    var text = (editor.innerText || '').trim();
    if (!text) return;  // n'écrase pas avec un éditeur vide
    fetch(_backendUrl + '/api/save_draft', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        keepalive: true,  // survit au beforeunload
        body: JSON.stringify({
            message_id: messageId,
            text: text,
            from_email: fromEmail || '',
            importance: importance || '',
        }),
    }).catch(function() {});
}

/**
 * Sauvegarde immédiate avec les valeurs courantes.
 * Utilisée par beforeunload (au moment du unload, _messageId est encore
 * l'ancien — l'unload fire AVANT le changement de page).
 */
function _saveDraftNow() {
    _saveDraftFor(_messageId, _fromEmail, _importance);
}

function _setupDraftAutoSave() {
    var editor = document.getElementById('editor');
    if (!editor) return;
    // Debounce 2 s après la dernière frappe.
    // Fix 27/04 : SNAPSHOT _messageId, _fromEmail, _importance au moment de
    // la frappe. Sans ça, race condition si l'user navigue vers un autre
    // mail pendant les 2s du debounce → save text Ombeline sous IMID
    // Vincent Hubert (bug observé 26/04 21:11).
    var schedule = function() {
        _userHasTypedSomething = true;  // fix 23/04 : seul signal fiable
        var capturedMid = _messageId;
        var capturedFrom = _fromEmail;
        var capturedImp = _importance;
        if (_draftSaveTimer) clearTimeout(_draftSaveTimer);
        _draftSaveTimer = setTimeout(function() {
            _saveDraftFor(capturedMid, capturedFrom, capturedImp);
        }, 2000);
    };
    editor.addEventListener('input', schedule);
    // Sauvegarde explicite si l'user ferme / quitte l'onglet
    window.addEventListener('beforeunload', _saveDraftNow);
}


function _fetchGenerateReply(body) {
    var editor = document.getElementById('editor');
    var spinner = document.getElementById('genSpinner');
    var btnGen = document.getElementById('btnGenerate');
    // Chef sortant : AbortController enregistré → abort au beforeunload.
    var _genAbort = _registerStream(
        (typeof AbortController !== 'undefined') ? new AbortController() : null
    );
    // SSE streaming
    fetch(_backendUrl + '/generate_reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body,
        signal: _genAbort ? _genAbort.signal : undefined,
    }).then(function(response) {
        /* #14 : verifier que la reponse est OK */
        if (!response.ok) {
            response.json().then(function(errData) {
                var msg = (errData && errData.error) ? errData.error : ('Erreur serveur (' + response.status + ')');
                document.getElementById('headerStatus').textContent = msg;
            }).catch(function() {
                document.getElementById('headerStatus').textContent = 'Erreur serveur (' + response.status + ')';
            });
            _onGenerationDone();
            return;
        }
        var reader = _registerStream(response.body.getReader());
        var decoder = new TextDecoder();
        var _lineBuffer = '';   // Buffer anti-fragmentation SSE
        var streamedText = '';  // Texte brut accumulé pendant le stream (préserve \n)

        function read() {
            reader.read().then(function(result) {
                if (result.done) {
                    // Vider le buffer restant (dernier chunk sans \n final)
                    if (_lineBuffer.startsWith('data: ')) {
                        try {
                            var last = JSON.parse(_lineBuffer.substring(6));
                            if (last.chunk) {
                                if (_progressPlaceholderActive) _clearProgressPlaceholder();
                                // Fix 30/04 PM — même garde anti-doublon que dans
                                // le path read() normal (cas SSE court qui termine
                                // entièrement en 1 read).
                                if (streamedText === '') {
                                    editor.innerHTML = '';
                                    _progressPlaceholderActive = false;
                                }
                                editor.insertAdjacentText('beforeend', last.chunk);
                                streamedText += last.chunk;
                            }
                        } catch(e) {}
                    }
                    // Safety : si aucun chunk n'est arrivé (erreur silencieuse), vider le placeholder
                    if (_progressPlaceholderActive) _clearProgressPlaceholder();
                    _onGenerationDone(streamedText);
                    return;
                }
                _lineBuffer += decoder.decode(result.value, { stream: true });
                var lines = _lineBuffer.split('\n');
                _lineBuffer = lines.pop();
                lines.forEach(function(line) {
                    if (line.startsWith('data: ')) {
                        try {
                            var data = JSON.parse(line.substring(6));
                            if (data.chunk) {
                                // Placeholder → supprimé juste avant le 1er chunk
                                if (_progressPlaceholderActive) _clearProgressPlaceholder();
                                // Fix 30/04 PM (signal Yvan : doublon "Bonjour Stéphane"
                                // + signature 2× quand re-génération sur mail avec draft
                                // user_edit existant). Garde anti-doublon : au 1er chunk
                                // de la génération, on s'assure que l'editor est vide
                                // (clear hard, indépendant du placeholder flag). Couvre
                                // les cas où instant_reply a pré-rempli l'editor avec
                                // un draft, où le placeholder a été remplacé hors flow,
                                // ou toute race DOM/flag non détectée.
                                if (streamedText === '') {
                                    editor.innerHTML = '';
                                    _progressPlaceholderActive = false;
                                }
                                spinner.classList.remove('active');
                                document.getElementById('headerStatus').textContent = 'Generation en cours...';
                                editor.insertAdjacentText('beforeend', data.chunk);
                                streamedText += data.chunk;
                                if (!streamedText || streamedText.length === data.chunk.length) {
                                    _perfMonitor.mark('T5_reply_first_chunk', 'stream');
                                    _perfMonitor.mark('T5_reply_source', 'stream');
                                }
                            }
                            // Fix 24/04 (P1) — replace_body : le serveur a
                            // détecté que Claude avait généré du HTML brut
                            // (<p>...</p>) et envoie la version plain text
                            // propre pour swap éditeur. Évite les balises
                            // visibles comme texte dans l'éditeur.
                            if (data.replace_body) {
                                editor.innerText = data.replace_body;
                                streamedText = data.replace_body;
                            }
                            // data.done (événement applicatif) : on n'agit PAS ici.
                            // Le reformatage final se fait UNE fois dans result.done
                            // (vrai end-of-stream, après tous les chunks résiduels).
                            if (data.error) {
                                if (_progressPlaceholderActive) _clearProgressPlaceholder();
                                spinner.classList.remove('active');
                                // Fix 27/04 PM (Workflow 4 #9) — message specifique
                                // pour quota_exceeded (data.message), sinon data.error brut.
                                var _errMsg = (data.error === 'quota_exceeded' && data.message)
                                    ? data.message : data.error;
                                editor.innerHTML = '<p style="color:#c00;">' + _escapeHtml(_errMsg) + '</p>';
                                if (data.auth_required) {
                                    document.getElementById('headerStatus').textContent = 'Session expiree — reconnectez-vous';
                                    // #15 bandeau in-dialog avec bouton Se reconnecter
                                    _showReauthBanner('Session Microsoft expirée. Reconnectez-vous pour générer la réponse.');
                                } else if (data.error === 'quota_exceeded') {
                                    document.getElementById('headerStatus').textContent = 'Quota quotidien atteint';
                                }
                                _onGenerationDone();
                                return;
                            }
                        } catch (e) {}
                    }
                });
                read();
            });
        }
        read();
    }).catch(function(err) {
        if (_progressPlaceholderActive) _clearProgressPlaceholder();
        spinner.classList.remove('active');
        editor.innerHTML = '<p style="color:#c00;">Erreur : ' + _escapeHtml(err.message) + '</p>';
        _onGenerationDone();
    });
}

/**
 * Finalise la génération / modification :
 *   - réinitialise l'UI (spinner, status, boutons)
 *   - si streamedText fourni, convertit le texte brut en <p>/<br> HTML propre
 *
 * streamedText (optionnel) : texte accumulé pendant le streaming SSE.
 * Le contenteditable Chromium perd les \n via textContent/innerText, donc
 * on s'appuie sur cette variable accumulée à la source.
 */
function _onGenerationDone(streamedText) {
    _isGenerating = false;
    document.getElementById('btnGenerate').disabled = (_mode === 'forward' && !document.getElementById('fieldTo').value.trim());
    document.getElementById('genSpinner').classList.remove('active');

    var elapsed = _sendStartTime ? ((Date.now() - _sendStartTime) / 1000).toFixed(1) : '?';
    document.getElementById('headerStatus').textContent = 'Reponse prete \u2022 ' + elapsed + 's';

    // Structurer le texte streamé en paragraphes HTML pour l'envoi ET le rendu final.
    // Fix XSS audit 21/04 : escape HTML avant injection — protection contre
    // prompt injection qui ferait générer du <script> ou <img onerror=…> par
    // Claude (ex: mail malveillant qui demande à Claude d'inclure un payload).
    var editor = document.getElementById('editor');
    if (streamedText && !editor.querySelector('p')) {
        var paragraphs = streamedText.split(/\n\n+/).map(function(p) {
            return '<p>' + _escapeHtml(p).replace(/\n/g, '<br>') + '</p>';
        }).join('');
        editor.innerHTML = paragraphs;
    }

    // #11 Garde défensive : si dialog fermé pendant le streaming, ces éléments
    // peuvent être détachés du DOM.
    var _btnUndo = document.getElementById('btnUndo');
    if (_btnUndo) _btnUndo.style.display = _undoStack.length > 0 ? '' : 'none';
    _safeSetSendBtn({ disabled: false });
    var btnRestore = document.getElementById('btnRestore');
    if (btnRestore) btnRestore.style.display = _versionStack.length > 0 ? '' : 'none';
    _perfMonitor.mark('T5_reply_done');
}


// =============================================================================
// REFINEMENT — squelette 12f, complété en 12g
// =============================================================================

function refineReply() {
    var instruction = document.getElementById('refineInput').value.trim();
    if (!instruction || _isGenerating) return;

    var editor = document.getElementById('editor');
    var currentReply = editor.innerText;
    _pushUndo(editor.innerHTML);

    _isGenerating = true;
    _sendStartTime = Date.now();
    document.getElementById('btnGenerate').disabled = true;
    document.getElementById('genSpinner').textContent = 'Modification en cours...';
    document.getElementById('genSpinner').classList.add('active');
    document.getElementById('headerStatus').textContent = 'Modification en cours...';
    // Placeholder "Rédaction en cours" aussi pour la modif (force : écrase le contenu existant)
    _showProgressPlaceholder('writing', true);

    // Chef sortant : AbortController enregistré
    var _refAbort = _registerStream(
        (typeof AbortController !== 'undefined') ? new AbortController() : null
    );
    fetch(_backendUrl + '/refine_reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            current_reply: currentReply,
            instruction: instruction,
            message_id: _messageId,
            from_email: _fromEmail,
            from_name: _fromName,
            subject: _subject,
            mode: _mode,
            to_email: document.getElementById('fieldTo').value.trim(),
            body: _mailBodyForGeneration,
        }),
        signal: _refAbort ? _refAbort.signal : undefined,
    }).then(function(response) {
        /* #14 : verifier que la reponse est OK */
        if (!response.ok) {
            response.json().then(function(errData) {
                var msg = (errData && errData.error) ? errData.error : ('Erreur serveur (' + response.status + ')');
                document.getElementById('headerStatus').textContent = msg;
            }).catch(function() {
                document.getElementById('headerStatus').textContent = 'Erreur serveur (' + response.status + ')';
            });
            _onGenerationDone();
            return;
        }
        var reader = _registerStream(response.body.getReader());
        var decoder = new TextDecoder();
        var _lineBufferRefine = '';
        var streamedText = '';   // Texte brut accumulé pendant le stream (préserve \n)

        function read() {
            reader.read().then(function(result) {
                if (result.done) {
                    if (_lineBufferRefine.startsWith('data: ')) {
                        try {
                            var last = JSON.parse(_lineBufferRefine.substring(6));
                            if (last.chunk) {
                                if (_progressPlaceholderActive) _clearProgressPlaceholder();
                                // Fix 02/05/2026 (signal Yvan : doublon Bonjour/Cdlt sur
                                // refine d'un mail déjà en cache) : même garde anti-doublon
                                // que dans _fetchGenerateReply (cas SSE court terminé en
                                // 1 read, current_reply non vidé).
                                if (streamedText === '') {
                                    editor.innerHTML = '';
                                    _progressPlaceholderActive = false;
                                }
                                editor.insertAdjacentText('beforeend', last.chunk);
                                streamedText += last.chunk;
                            }
                        } catch(e) {}
                    }
                    if (_progressPlaceholderActive) _clearProgressPlaceholder();
                    _onGenerationDone(streamedText);
                    document.getElementById('refineInput').value = '';
                    return;
                }
                _lineBufferRefine += decoder.decode(result.value, { stream: true });
                var lines = _lineBufferRefine.split('\n');
                _lineBufferRefine = lines.pop();
                lines.forEach(function(line) {
                    if (line.startsWith('data: ')) {
                        try {
                            var data = JSON.parse(line.substring(6));
                            if (data.chunk) {
                                if (_progressPlaceholderActive) _clearProgressPlaceholder();
                                document.getElementById('genSpinner').classList.remove('active');
                                // Fix 02/05/2026 (signal Yvan : doublon Bonjour/Cdlt sur
                                // refine d'un mail déjà en cache) : au 1er chunk, garantir
                                // un editor vide indépendamment du flag placeholder. Le
                                // backend renvoie une réponse COMPLÈTE (pas un diff),
                                // donc l'editor doit partir d'un état propre. Symétrique
                                // au fix _fetchGenerateReply (30/04 PM).
                                if (streamedText === '') {
                                    editor.innerHTML = '';
                                    _progressPlaceholderActive = false;
                                }
                                editor.insertAdjacentText('beforeend', data.chunk);
                                streamedText += data.chunk;
                            }
                            // Idem generate : on n'agit pas sur data.done — tout
                            // se passe au vrai end-of-stream (result.done ci-dessus).
                            if (data.error) {
                                if (_progressPlaceholderActive) _clearProgressPlaceholder();
                                document.getElementById('genSpinner').classList.remove('active');
                                // Fix 27/04 PM (Workflow 4 #9) — message clair quota_exceeded
                                var _errMsg2 = (data.error === 'quota_exceeded' && data.message)
                                    ? data.message : data.error;
                                editor.innerHTML = '<p style="color:#c00;">' + _escapeHtml(_errMsg2) + '</p>';
                                if (data.error === 'quota_exceeded') {
                                    document.getElementById('headerStatus').textContent = 'Quota quotidien atteint';
                                }
                                _onGenerationDone();
                                return;
                            }
                        } catch (e) {}
                    }
                });
                read();
            });
        }
        read();
    }).catch(function(err) {
        if (_progressPlaceholderActive) _clearProgressPlaceholder();
        document.getElementById('genSpinner').classList.remove('active');
        editor.innerHTML = '<p style="color:#c00;">Erreur : ' + _escapeHtml(err.message) + '</p>';
        _onGenerationDone();
    });
}


// =============================================================================
// RÉGÉNÉRATION
// =============================================================================

function regenReply() {
    if (_isGenerating) return;
    // Sauvegarder la version actuelle dans le versionStack (comme le proto)
    var editor = document.getElementById('editor');
    var currentHtml = editor.innerHTML;
    if (currentHtml && currentHtml.trim()) {
        _versionStack.push(currentHtml);
    }
    // Plan 2 Phase 1 : si l'user clique "Autre réponse", il rejette le template
    // (s'il y en avait un). On skippe le match template et on feedback au backend.
    if (_lastTemplateMatch) {
        _sendTemplateFeedback(_lastTemplateMatch, 'reject');
        _lastTemplateMatch = null;
    }
    var badge = document.getElementById('tplBadge');
    if (badge) badge.remove();
    _skipTemplateMatch = true;
    generateReply();
}

var _skipTemplateMatch = false;

/** Envoie un feedback success/reject au backend pour la learning loop. */
function _sendTemplateFeedback(match, feedback) {
    try {
        fetch(_backendUrl + '/api/template_feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                template_id: match.id, source: match.source, feedback: feedback,
            }),
        }).catch(function() {});
    } catch (e) {}
}

function restorePreviousVersion() {
    if (_versionStack.length === 0) return;
    var prev = _versionStack.pop();
    var editor = document.getElementById('editor');
    // Sauvegarder la version courante dans l'undo
    _pushUndo(editor.innerHTML);
    editor.innerHTML = prev;
    // Mettre à jour la visibilité du bouton
    var btnRestore = document.getElementById('btnRestore');
    if (btnRestore) btnRestore.style.display = _versionStack.length > 0 ? '' : 'none';
    document.getElementById('btnUndo').style.display = _undoStack.length > 0 ? '' : 'none';
}

function regenWithImportance(delta) {
    // Plus court (delta=-1) ou Plus travaillé (delta=+1)
    // Ajuste l'importance avant de régénérer
    if (_isGenerating) return;

    // Décision Yvan 01/05/2026 : la flèche « Version précédente » (btnRestore)
    // doit apparaître après un clic Plus court / Plus travaillé aussi (pas
    // seulement après Essayer une autre réponse). Push de la version courante
    // dans _versionStack comme dans regenReply().
    var editor = document.getElementById('editor');
    var currentHtml = editor.innerHTML;
    if (currentHtml && currentHtml.trim()) {
        _versionStack.push(currentHtml);
    }
    // Affiche la flèche restore (btnRestore) immédiatement, sans attendre la
    // fin du streaming — feedback visuel direct.
    var btnRestore = document.getElementById('btnRestore');
    if (btnRestore) btnRestore.style.display = '';

    var impMap = {'R': 0, 'S': 1, 'H': 2};
    var impReverse = ['R', 'S', 'H'];
    var currentIdx = impMap[_importance] || 1;
    var newIdx = Math.max(0, Math.min(2, currentIdx + delta));
    var newImp = impReverse[newIdx];

    // Mettre à jour l'UI
    document.querySelectorAll('.em-imp-chip').forEach(function(c) {
        c.classList.remove('active');
        if (c.getAttribute('data-imp') === newImp) c.classList.add('active');
    });
    _importance = newImp;

    // Régénérer
    generateReply();
}


// =============================================================================
// UNDO
// =============================================================================

function _pushUndo(html) {
    _undoStack.push(html);
    if (_undoStack.length > _maxUndo) _undoStack.shift();
}

function undoReply() {
    if (_undoStack.length === 0) return;
    var prev = _undoStack.pop();
    document.getElementById('editor').innerHTML = prev;
    document.getElementById('btnUndo').style.display = _undoStack.length > 0 ? '' : 'none';
}


// =============================================================================
// DÉTECTION MODE (Standard vs Perf. Réduite)
// =============================================================================

function _detectMode() {
    // Fix 2 (20/04) — cache localStorage avec TTL 1 h.
    // /api/status change rarement (seul connexion/deconnexion Microsoft le fait).
    // Si on a un cache frais, on l'utilise instantanément + on revalide en BG.
    var _applyStatus = function(data) {
        _isStandardMode = data.authenticated && data.mode === 'standard';
        var btnSend = document.getElementById('btnSend');
        if (btnSend) {
            btnSend.innerHTML = _isStandardMode
                ? '&#x1f4e4; Relire et envoyer'
                : '&#x2709; Valider et envoyer';
        }
        _sendStartTime = Date.now();
    };
    try {
        var cached = JSON.parse(localStorage.getItem('em_status_v1') || 'null');
        if (cached && (Date.now() - cached.ts) < 3600000) {
            _applyStatus(cached.data);   // 0 ms — appliqué instantanément
        }
    } catch(e) {
        // Fix D5 (21/04 audit) : cache corrompu → fallback safe + purge
        _isStandardMode = false;
        try { localStorage.removeItem('em_status_v1'); } catch(_){}
    }

    // Revalidation réseau en arrière-plan (met à jour le cache si changé)
    fetch(_backendUrl + '/api/status')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            _applyStatus(data);
            try {
                localStorage.setItem('em_status_v1', JSON.stringify({ ts: Date.now(), data: data }));
            } catch(e) {}
        })
        .catch(function() {
            if (!_sendStartTime) {
                _isStandardMode = false;
                _sendStartTime = Date.now();
                var hs = document.getElementById('headerStatus');
                if (hs) hs.textContent = 'Backend indisponible';
            }
        });
}


// =============================================================================
// ENVOI (12h)
// =============================================================================

function sendReply() {
    if (_isGenerating) return;

    var btnSend = document.getElementById('btnSend');
    if (btnSend.disabled) return;  // Garde double-clic

    var editor = document.getElementById('editor');
    var body = editor.innerHTML;
    var to = document.getElementById('fieldTo').value.trim();
    var cc = document.getElementById('fieldCc') ? document.getElementById('fieldCc').value.trim() : '';
    var subject = document.getElementById('fieldSubject').value.trim();

    if (!body.trim()) {
        alert('Le mail est vide.');
        return;
    }

    // Validation destinataire selon le mode
    if (_mode === 'forward' && !to) {
        alert('Le destinataire est obligatoire en mode transfert.');
        document.getElementById('fieldTo').focus();
        return;
    }
    if (_mode === 'new' && !to) {
        alert('Le destinataire est obligatoire.');
        document.getElementById('fieldTo').focus();
        return;
    }

    // Désactiver immédiatement (anti double-clic)
    btnSend.disabled = true;

    // La signature marketing est ajoutée côté BACKEND (pas ici)
    // Le body est envoyé tel quel (contenu de l'éditeur)

    if (_isStandardMode) {
        _sendViaGraph(body, to, cc, subject);
    } else {
        _sendViaOutlook(body, to, cc, subject);
    }
}

function _sendViaGraph(body, to, cc, subject) {
    var btnSend = document.getElementById('btnSend');
    btnSend.disabled = true;
    btnSend.innerHTML = '&#x23F3; Envoi en cours...';

    // Idempotence (21/04) : UUID unique au click, évite double envoi sur retry
    var clientReqId = '';
    try {
        clientReqId = (window.crypto && typeof window.crypto.randomUUID === 'function')
            ? window.crypto.randomUUID()
            : ('c_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10));
    } catch(_) {
        clientReqId = 'c_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10);
    }

    // #10 AbortController timeout 30s — protège contre micro-cuts réseau
    // ou serveur Graph qui ne répond pas (sinon spinner infini côté user).
    _fetchTimeout(_backendUrl + '/send_reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            mode: _mode,
            message_id: _messageId,
            body: body,
            to: to,
            cc: cc,
            subject: subject,
            client_request_id: clientReqId,
        }),
    }, 30000).then(function(r) {
        if (!r.ok && r.status !== 403) {
            throw new Error('Erreur serveur (' + r.status + ')');
        }
        return r.json();
    })
    .then(function(data) {
        if (data.success) {
            // Plan 2 Phase 1 : le user a envoyé → si un template a été accepté, on feedback
            if (_lastTemplateMatch) {
                _sendTemplateFeedback(_lastTemplateMatch, 'success');
                _lastTemplateMatch = null;
            }
            // Succès → post-envoi
            // #11 Garde défensive : headerStatus + btnSend peuvent être détachés
            // du DOM si dialog fermé entre le clic et l'arrivée de la réponse Graph.
            var _hdr = document.getElementById('headerStatus');
            if (_hdr) _hdr.textContent = 'Mail envoye !';
            _safeSetSendBtn({ html: '&#x2705; Envoye' });
            _postSend(body, to, cc, subject);
        } else if (data.auth_required) {
            // Token expiré
            // #15 bandeau in-dialog avec bouton Se reconnecter (vs alert + nav manuelle)
            _showReauthBanner('Session Microsoft expir\u00e9e. Reconnectez-vous pour envoyer.');
            _safeSetSendBtn({ html: '&#x1f4e4; Relire et envoyer', disabled: false });
        } else {
            alert('Erreur envoi : ' + (data.error || 'inconnue'));
            _safeSetSendBtn({ html: '&#x1f4e4; Relire et envoyer', disabled: false });
        }
    })
    .catch(function(err) {
        // #10 D\u00e9tection AbortError = timeout 30s explicite (sinon msg "user aborted" cryptique)
        var msg = (err && err.name === 'AbortError')
            ? 'D\u00e9lai d\'envoi d\u00e9pass\u00e9 (30s). R\u00e9seau lent ou serveur indisponible. R\u00e9essayez.'
            : 'Erreur r\u00e9seau : ' + (err && err.message ? err.message : 'inconnue');
        alert(msg);
        // #11 Garde d\u00e9fensive : btnSend peut \u00eatre d\u00e9tach\u00e9 du DOM
        _safeSetSendBtn({ html: '&#x1f4e4; Relire et envoyer', disabled: false });
    });
}

function _sendViaOutlook(body, to, cc, subject) {
    // (P18) Mode standalone : utiliser le Companion /inject_reply au lieu de messageParent
    if (_isStandaloneMode) {
        _sendViaCompanion(body, to, cc, subject);
        return;
    }

    // Mode Office.js : envoyer via messageParent → taskpane.js/commands.js → displayReplyForm
    var sent = _messageParent({
        action: 'send_via_outlook',
        htmlBody: body,
        to: to,
        cc: cc,
        subject: subject,
        mode: _mode,
    });
    if (sent) {
        document.getElementById('headerStatus').textContent = 'Ouverture Outlook...';
        document.getElementById('btnSend').innerHTML = '&#x2705; Transmis a Outlook';
        _postSend(body, to, cc, subject);
    } else {
        alert('Envoi via Outlook non disponible en mode navigateur.');
        document.getElementById('btnSend').disabled = false;
    }
}


// =============================================================================
// POST-ENVOI (12h) — Sauvegarde thread, métriques, apprentissage
// =============================================================================

function _postSend(body, to, cc, subject) {
    var duration = Date.now() - _sendStartTime;
    var editor = document.getElementById('editor');
    var finalReply = editor.innerHTML;

    // Appeler le backend pour sauvegarder
    // #10 AbortController timeout 15s — non-bloquant : si timeout, le workflow
    // post-send continue gracieusement via le .catch (_finalClose appelé).
    _fetchTimeout(_backendUrl + '/api/post_send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message_id: _messageId,
            mode: _mode,
            to: to,
            cc: cc,
            subject: subject,
            body: body,
            final_reply: finalReply,
            received_body: _receivedBody,
            importance: _importance,
            duration_ms: duration,
            from_email: _fromEmail,
            from_name: _fromName,
        }),
    }, 15000).then(function(r) {
        if (!r.ok) console.log('[dialog] post_send HTTP ' + r.status);
        return r.json();
    })
    .then(function(data) {
        // Lancer les workflows post-envoi (échéances → classement → PJ → fermeture)
        _runPostSendWorkflows();
    })
    .catch(function(err) {
        console.log('[dialog] Erreur post-envoi (non bloquant):', err.message);
        // Fermer malgré l'erreur
        _finalClose();
    });
}


// =============================================================================
// WORKFLOWS POST-ENVOI (12i) — Échéances → Classement mail → Classement PJ
// =============================================================================

var _selectedFolderId = '';
var _postSendEcheances = [];
var _postSendPJData = null;

// Étape 4'/4' (02/05 PM, vision Yvan) — popup classement pré-envoi cliquable.
// Le champ #infoClassement en bas du dialog devient cliquable dès que le BG
// a calculé une suggestion. Au clic → popup classement s'ouvre en mode 'pre'
// (boutons « Annuler » / « Confirmer »). L'user peut modifier, son choix est
// mémorisé, puis la popup post-envoi le réutilise comme défaut.
var _classementCacheData = null;       // {suggestion, suggestions, source} reçu du polling
var _classementFoldersCache = null;    // folders Graph fetché lazy au 1er clic pré-envoi
var _classMailMode = 'post';           // 'pre' ou 'post' — détermine boutons popup
var _preSendFolderId = '';             // choix user pré-envoi (folder_id depuis arbo/sugg)
var _preSendFolderPath = '';           // path lisible (pour affichage card + manuel)
var _preSendIsManual = false;          // true si user a tapé un path manuel pré-envoi

// Étape 1''-4''/4'' (02/05 PM, vision Yvan) — équivalents pour CLASSEMENT PJ.
// Folders Windows (path/name/depth) lus depuis user_windows_folders OVH
// (poussés par Companion local). Saisie manuelle path → Companion local
// crée le dossier sous pj_root_folder.
var _selectedPJFolderPath = '';            // path Windows sélectionné (arbo ou suggestion)
var _selectedPJFolderManualPath = '';      // path manuel tapé par user (Q2=OUI)
var _classementPJCacheData = null;         // {suggestion, suggestions, source, attachments, folders}
var _classMailPJMode = 'post';             // 'pre' ou 'post'
var _preSendPJFolderPath = '';             // choix user pré-envoi PJ
var _preSendPJIsManual = false;            // true si manual

function _runPostSendWorkflows() {
    /** Chaîne les 3 workflows : échéances → classement mail → classement PJ → fermeture. */
    if (!_messageId) {
        _finalClose();
        return;
    }
    // Étape 1 : Scanner les échéances
    _pollEcheances(0);
}

// --- Étape 1 : Échéances ---

function _pollEcheances(attempt) {
    if (attempt >= 8) { _startClassMail(); return; }  // Timeout 4s (8 × 500ms)

    fetch(_backendUrl + '/api/echeances/post_send/' + encodeURIComponent(_messageId))
        .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function(data) {
            if (data.status === 'scanning') {
                setTimeout(function() { _pollEcheances(attempt + 1); }, 500);
            } else if (data.status === 'done' && data.echeances && data.echeances.length > 0) {
                _postSendEcheances = data.echeances;
                _showEcheancePopup(data.echeances);
            } else {
                _startClassMail();  // Pas d'échéance → passer au classement
            }
        })
        .catch(function() { _startClassMail(); });
}

function _showEcheancePopup(echeances) {
    var html = '';
    echeances.forEach(function(ech) {
        html += '<div class="em-ech-card">'
            + '<div class="ech-desc">' + _escapeHtml(ech.description || ech.titre || '') + '</div>'
            + '<div class="ech-date">' + _escapeHtml(ech.date_echeance || '') + '</div>'
            + '</div>';
    });
    document.getElementById('echeancesBody').innerHTML = html;
    document.getElementById('popupEcheances').classList.add('active');
}

function confirmEcheance() {
    document.getElementById('popupEcheances').classList.remove('active');
    _startClassMail();
}

function dismissEcheance() {
    document.getElementById('popupEcheances').classList.remove('active');
    _startClassMail();
}

// --- Étape 2 : Classement Mail (Mode Standard uniquement) ---

function _startClassMail() {
    if (!_isStandardMode) { _startClassPJ(); return; }

    fetch(_backendUrl + '/api/classification/post_send/' + encodeURIComponent(_messageId))
        .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function(data) {
            if (data.status === 'scanning') {
                // Poll 1 fois de plus
                setTimeout(function() {
                    fetch(_backendUrl + '/api/classification/post_send/' + encodeURIComponent(_messageId))
                        .then(function(r) { return r.json(); })
                        .then(function(data2) {
                            if (data2.status === 'done' && data2.suggestion) {
                                _showClassMailPopup(data2.suggestion, data2.suggestion.folders || []);
                            } else { _startClassPJ(); }
                        }).catch(function() { _startClassPJ(); });
                }, 1500);
            } else if (data.status === 'done' && data.suggestion) {
                _showClassMailPopup(data.suggestion, data.suggestion.folders || []);
            } else {
                _startClassPJ();
            }
        })
        .catch(function() { _startClassPJ(); });
}

function _showClassMailPopup(suggestion, folders, mode) {
    // Étape 2' (02/05 PM, vision Yvan) — Top 3 suggestions au lieu de #1.
    // suggestion.suggestions = array (top 3 calculé par BG prewarm) ; fallback
    // [#1] si BG ancien ou source != rule/ai. Backend exposé via étape 1'.
    // Affichage : 1 principale (sélectionnée par défaut, gros bandeau bleu)
    // + jusqu'à 2 alternatives (boulettes discrètes ●).
    //
    // Étape 4' (02/05 PM) — Param `mode` ∈ {'pre', 'post'} (default 'post').
    //   Mode 'pre'  = popup ouverte au clic #infoClassement avant envoi.
    //                 Boutons « Annuler » / « Confirmer ». Confirm mémorise
    //                 dans _preSendFolderId/Path sans déclencher classement.
    //   Mode 'post' = popup ouverte après envoi (workflow standard).
    //                 Boutons « Pas maintenant » / « Classer ici ».
    //                 Si _preSendFolderId/Path existe (modif user pré-envoi)
    //                 → pré-sélection de ce choix au lieu de la suggestion BG.
    mode = mode || 'post';
    _classMailMode = mode;

    var suggestions = (suggestion && suggestion.suggestions && suggestion.suggestions.length)
        ? suggestion.suggestions
        : (suggestion && suggestion.suggestion ? [suggestion.suggestion] : []);

    // Sélection initiale (priorité au choix pré-envoi user en mode 'post')
    var initialSelectedId = (suggestions.length > 0 && suggestions[0]) ? (suggestions[0].folder_id || '') : '';
    var initialManualPath = '';
    if (mode === 'post') {
        if (_preSendIsManual && _preSendFolderPath) {
            initialManualPath = _preSendFolderPath;
            initialSelectedId = '';
        } else if (_preSendFolderId) {
            initialSelectedId = _preSendFolderId;
        }
    }

    var sugHtml = '';
    if (suggestions.length > 0) {
        // Suggestion principale (top 1)
        var main = suggestions[0];
        var mainId = main.folder_id || '';
        var mainPath = main.folder_path || main.folder_name || mainId || 'Dossier suggéré';
        var mainReason = main.reason || '';
        var mainPrefix = (suggestion.source === 'ai') ? 'Suggestion IA : ' : '';
        var mainSelected = (mainId === initialSelectedId) ? ' selected' : '';
        sugHtml += '<div class="em-folder-suggestion' + mainSelected + '" '
            + 'onclick="_selectFolder(\'' + _escapeAttr(mainId) + '\', this)">'
            + '&#x1f4c1; ' + _escapeHtml(mainPrefix + mainPath)
            + (mainReason ? '<span class="em-suggestion-reason">— ' + _escapeHtml(mainReason) + '</span>' : '')
            + '</div>';
        _selectedFolderId = initialSelectedId;
        document.getElementById('btnClassMail').disabled = !(initialSelectedId || initialManualPath);

        // Alternatives top 2/3 — boulettes discrètes (max 2)
        var alts = suggestions.slice(1, 3);
        if (alts.length > 0) {
            sugHtml += '<div class="em-folder-alternatives">';
            alts.forEach(function(s) {
                var altId = s.folder_id || '';
                var altPath = s.folder_path || s.folder_name || altId || 'Dossier suggéré';
                var altReason = s.reason || '';
                var altSelected = (altId === initialSelectedId) ? ' selected' : '';
                sugHtml += '<div class="em-folder-alternative' + altSelected + '" '
                    + 'onclick="_selectFolder(\'' + _escapeAttr(altId) + '\', this)">'
                    + '<span class="em-folder-alt-bullet">&#x25cf;</span>'
                    + '<span>' + _escapeHtml(altPath)
                    + (altReason ? '<span class="em-suggestion-reason">— ' + _escapeHtml(altReason) + '</span>' : '')
                    + '</span></div>';
            });
            sugHtml += '</div>';
        }
    }
    document.getElementById('classMailSuggestion').innerHTML = sugHtml;

    // Arborescence dossiers — affichage type Outlook avec chevrons ▼/▶
    // (signal Yvan 02/05/2026 : « rajoute des flèches > vers le haut et le
    // bas pour simuler l'arborescence Outlook »).
    // Algorithme :
    //   - Folders sont déjà triés par hiérarchie (parent avant enfants)
    //   - Un folder a des enfants si le SUIVANT a un depth > au sien
    //   - Au clic sur chevron : toggle visibilité de tous les descendants
    //     (lignes consécutives avec depth > depth_courant)
    if (folders && folders.length > 0) {
        var treeHtml = '';
        folders.forEach(function(f, i) {
            var depth = f.depth || 0;
            var next = folders[i + 1];
            var hasChildren = next && (next.depth || 0) > depth;
            var indent = depth * 14; // 14px par niveau
            var chevron = hasChildren
                ? '<span class="em-folder-chevron expanded" onclick="_toggleFolderChildren(event, this.parentElement)">▼</span>'
                : '<span class="em-folder-chevron-spacer"></span>';
            treeHtml += '<div class="em-folder-item" '
                + 'data-folder-id="' + _escapeAttr(f.id) + '" '
                + 'data-depth="' + depth + '" '
                + 'style="padding-left:' + indent + 'px;display:flex;align-items:center;gap:4px;" '
                + 'onclick="_selectFolderFromRow(event, this)">'
                + chevron
                + '<span class="em-folder-name">' + _escapeHtml(f.name) + '</span>'
                + '</div>';
        });
        document.getElementById('classMailTree').innerHTML = treeHtml;

        // Étape 3' (02/05 PM, vision Yvan) — « L'arborescence débute au
        // niveau de la proposition principale de BoosterMail ». Au load :
        // - Highlight la row de la suggestion principale (cohérent avec
        //   le bandeau bleu en haut .em-folder-suggestion.selected)
        // - Scroll automatique vers cette row (block: center)
        // L'algo depth-based d'Yvan laisse tout déplié par défaut, donc
        // la row est forcément visible dans le DOM (on doit juste scroller).
        try {
            if (_selectedFolderId) {
                var rows = document.querySelectorAll('#classMailTree .em-folder-item');
                for (var ri = 0; ri < rows.length; ri++) {
                    if (rows[ri].getAttribute('data-folder-id') === _selectedFolderId) {
                        rows[ri].classList.add('selected');
                        if (rows[ri].scrollIntoView) {
                            rows[ri].scrollIntoView({ block: 'center', behavior: 'auto' });
                        }
                        break;
                    }
                }
            }
        } catch (e) { /* scroll non critique, ne pas bloquer le rendu */ }
    }

    // Phase 3 (30/04 PM) — brancher l'input de saisie manuelle.
    // Étape 4' (02/05 PM) : pré-remplir si l'user avait tapé un path manuel
    // en mode pré-envoi (cohérence post-envoi avec choix pré-envoi).
    var manualInput = document.getElementById('classMailManualPath');
    if (manualInput) {
        manualInput.value = initialManualPath || '';
        if (initialManualPath) {
            _selectedFolderManualPath = initialManualPath;
        }
        manualInput.removeEventListener('input', _onManualPathInput);
        manualInput.addEventListener('input', _onManualPathInput);
    }

    // Étape 4' (02/05 PM) — Adapter libellés des boutons selon le mode.
    // skipClassMail() / doClassMail() inspectent _classMailMode et
    // redirigent vers _cancelPreSendChoice() / _confirmPreSendChoice() en
    // mode 'pre'.
    var btnSkip = document.querySelector('#popupClassMail .em-popup-btn:not(.primary)');
    var btnPrimary = document.getElementById('btnClassMail');
    if (mode === 'pre') {
        if (btnSkip) btnSkip.textContent = 'Annuler';
        if (btnPrimary) btnPrimary.textContent = 'Confirmer';
    } else {
        if (btnSkip) btnSkip.textContent = 'Pas maintenant';
        if (btnPrimary) btnPrimary.textContent = 'Classer ici';
    }

    document.getElementById('popupClassMail').classList.add('active');
}

// Phase 3 (30/04 PM) — Handler input saisie manuelle de path dossier.
// Si l'user tape : on annule la sélection arborescence/suggestion et on
// active le bouton "Classer ici" qui passera en mode manual_classify.
var _selectedFolderManualPath = '';

function _onManualPathInput(e) {
    var val = (e && e.target && e.target.value || '').trim();
    var btn = document.getElementById('btnClassMail');
    if (val.length > 0) {
        _selectedFolderManualPath = val;
        _selectedFolderId = '';  // mode manual prend le pas
        // Highlight off (arbo/suggestion/alternative neutralisées) — étape 2'
        document.querySelectorAll('.em-folder-item, .em-folder-suggestion, .em-folder-alternative').forEach(function(el) {
            el.classList.remove('selected');
        });
        if (btn) btn.disabled = false;
    } else {
        _selectedFolderManualPath = '';
        if (btn) btn.disabled = (_selectedFolderId ? false : true);
    }
}

function _selectFolder(folderId, element) {
    _selectedFolderId = folderId;
    _selectedFolderManualPath = '';  // user re-sélectionne via arbo → reset manual
    var manualInput = document.getElementById('classMailManualPath');
    if (manualInput) manualInput.value = '';
    document.getElementById('btnClassMail').disabled = false;
    // Highlight — étape 2' (02/05 PM) : ajout em-folder-alternative au reset
    // selector pour cohérence avec les boulettes top 2/3.
    document.querySelectorAll('.em-folder-item, .em-folder-suggestion, .em-folder-alternative').forEach(function(el) {
        el.classList.remove('selected');
    });
    if (element && element.classList) {
        element.classList.add('selected');
    }
}

// 02/05/2026 — Wrapper qui distingue clic chevron (toggle) vs clic ligne
// (sélection). Utilisé par le rendu arbre Outlook avec chevrons ▼/▶.
function _selectFolderFromRow(event, rowEl) {
    // Si le clic vient du chevron, on ne sélectionne pas (le chevron a son
    // propre handler avec stopPropagation, mais double sécurité ici).
    if (event && event.target && event.target.classList &&
        event.target.classList.contains('em-folder-chevron')) {
        return;
    }
    var folderId = rowEl.getAttribute('data-folder-id');
    _selectFolder(folderId, rowEl);
}

// 02/05/2026 — Toggle l'affichage des sous-dossiers d'un dossier parent
// dans la popup de classement. Reproduit le comportement Outlook (chevron
// ▼ ouvert / ▶ fermé). On masque/montre tous les frères suivants jusqu'à
// trouver un élément avec depth ≤ depth_courant.
function _toggleFolderChildren(event, parentRow) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    var depth = parseInt(parentRow.getAttribute('data-depth'), 10);
    if (isNaN(depth)) return;
    var chevron = parentRow.querySelector('.em-folder-chevron');
    var collapsing = chevron && chevron.classList.contains('expanded');
    if (chevron) {
        chevron.classList.toggle('expanded', !collapsing);
        chevron.classList.toggle('collapsed', collapsing);
        chevron.textContent = collapsing ? '▶' : '▼'; // ▶ ou ▼
    }
    // Parcourt les frères suivants : tant que depth > depth_courant, on toggle
    var sibling = parentRow.nextElementSibling;
    while (sibling) {
        var sd = parseInt(sibling.getAttribute('data-depth'), 10);
        if (isNaN(sd) || sd <= depth) break;
        if (collapsing) {
            sibling.style.display = 'none';
        } else {
            // Pour ne pas re-déplier des sous-dossiers qui étaient repliés
            // manuellement, on ne montre que ceux du niveau immédiat (depth+1).
            if (sd === depth + 1) {
                sibling.style.display = '';
            } else {
                // Vérifie si l'ancêtre direct (depth+1) est expanded
                var anc = sibling.previousElementSibling;
                while (anc) {
                    var ad = parseInt(anc.getAttribute('data-depth'), 10);
                    if (!isNaN(ad) && ad === depth + 1) {
                        var ancChev = anc.querySelector('.em-folder-chevron');
                        var ancExpanded = ancChev && ancChev.classList.contains('expanded');
                        sibling.style.display = ancExpanded ? '' : 'none';
                        break;
                    }
                    anc = anc.previousElementSibling;
                }
            }
        }
        sibling = sibling.nextElementSibling;
    }
}

// Étape 4'/4' (02/05 PM) — Active/désactive le clic sur la card #infoClassement.
// Le champ devient cliquable dès qu'une suggestion est calculée par le BG.
function _setClassementFieldClickable(clickable) {
    var card = document.getElementById('infoClassement');
    if (!card) return;
    if (clickable) {
        card.classList.add('clickable');
        if (!card.dataset.clickHandlerAdded) {
            card.addEventListener('click', _openPreSendClassPopup);
            card.dataset.clickHandlerAdded = '1';
        }
    } else {
        card.classList.remove('clickable');
    }
}

// Étape 4'/4' (02/05 PM) — Ouvre la popup classement EN MODE PRÉ-ENVOI au clic
// sur le champ #infoClassement. Les données top 3 viennent de
// _classementCacheData (peuplé par _applyMailPreview / _applySinglePlate). Les
// folders Graph sont fetchés lazy au 1er clic via /api/folders puis cachés.
// L'user peut modifier la sélection ou taper un path manuel — son choix est
// mémorisé dans _preSendFolderId / _preSendFolderPath / _preSendIsManual.
function _openPreSendClassPopup() {
    // Étape 4' fix (02/05 PM signal Yvan) — Permettre l'ouverture même sans
    // suggestion BG (cas 'none' / 'self' / 'none_*'). La popup s'ouvre alors
    // avec juste l'arborescence + saisie manuelle (pas de bandeau bleu).
    if (!_classementCacheData) {
        _classementCacheData = { suggestion: null, suggestions: [], source: 'none' };
    }

    var openWithFolders = function(folders) {
        _classMailMode = 'pre';
        var suggestionsArr = _classementCacheData.suggestions
            || (_classementCacheData.suggestion ? [_classementCacheData.suggestion] : []);
        _showClassMailPopup({
            suggestion: _classementCacheData.suggestion,
            suggestions: suggestionsArr,
            source: _classementCacheData.source,
        }, folders, 'pre');
    };

    if (_classementFoldersCache && _classementFoldersCache.length) {
        openWithFolders(_classementFoldersCache);
    } else {
        fetch(_backendUrl + '/api/folders')
            .then(function(r) { return r.ok ? r.json() : null; })
            .then(function(data) {
                _classementFoldersCache = (data && data.folders) || [];
                openWithFolders(_classementFoldersCache);
            })
            .catch(function() {
                openWithFolders([]);
            });
    }
}

// Étape 4'/4' (02/05 PM) — Confirme le choix pré-envoi (au clic « Confirmer »).
// Mémorise dans _preSendFolderId / _preSendFolderPath / _preSendIsManual et
// MAJ le champ #infoClassement pour afficher le choix retenu.
function _confirmPreSendChoice() {
    if (_selectedFolderManualPath) {
        _preSendFolderId = '';
        _preSendFolderPath = _selectedFolderManualPath;
        _preSendIsManual = true;
    } else if (_selectedFolderId) {
        _preSendFolderId = _selectedFolderId;
        _preSendIsManual = false;
        // Path lisible : on cherche dans _classementFoldersCache, sinon dans
        // les suggestions (folder_path déjà présent).
        var found = null;
        if (_classementFoldersCache) {
            for (var i = 0; i < _classementFoldersCache.length; i++) {
                if (_classementFoldersCache[i].id === _selectedFolderId) {
                    found = _classementFoldersCache[i];
                    break;
                }
            }
        }
        if (!found && _classementCacheData && _classementCacheData.suggestions) {
            for (var j = 0; j < _classementCacheData.suggestions.length; j++) {
                var s = _classementCacheData.suggestions[j];
                if (s && s.folder_id === _selectedFolderId) {
                    _preSendFolderPath = s.folder_path || s.folder_name || _selectedFolderId;
                    break;
                }
            }
        } else if (found) {
            _preSendFolderPath = found.name || _selectedFolderId;
        } else {
            _preSendFolderPath = _selectedFolderId;
        }
    }
    var clsEl = document.getElementById('infoClassementContent');
    if (clsEl && _preSendFolderPath) {
        clsEl.textContent = _preSendFolderPath + ' ✓';
    }
    _classMailMode = 'post';
    document.getElementById('popupClassMail').classList.remove('active');
}

// Étape 4'/4' (02/05 PM) — Annule le choix pré-envoi (au clic « Annuler »).
// La popup ferme sans rien sauvegarder. Le champ #infoClassement garde la
// suggestion BG d'origine.
function _cancelPreSendChoice() {
    _classMailMode = 'post';
    document.getElementById('popupClassMail').classList.remove('active');
}

// =============================================================================
// Étape 4''/4'' (02/05 PM) — Helpers POPUP CLASSEMENT PJ PRÉ-ENVOI
// Parallèles aux helpers mail. Le champ #infoClassementPJ devient cliquable
// dès qu'une suggestion ou catégorisation a été calculée par le BG. Au clic →
// popup classement PJ s'ouvre en mode 'pre'. L'user peut modifier (top 3 +
// arbo Windows + saisie manuelle), son choix est mémorisé dans
// _preSendPJFolderPath / _preSendPJIsManual, puis la popup post-envoi le
// réutilise comme défaut.
// =============================================================================

function _setClassementPJFieldClickable(clickable) {
    var card = document.getElementById('infoClassementPJ');
    if (!card) return;
    if (clickable) {
        card.classList.add('clickable');
        if (!card.dataset.clickHandlerAdded) {
            card.addEventListener('click', _openPreSendClassPJPopup);
            card.dataset.clickHandlerAdded = '1';
        }
    } else {
        card.classList.remove('clickable');
    }
}

function _openPreSendClassPJPopup() {
    // Permettre l'ouverture même sans suggestion BG (cas 'none' générique).
    if (!_classementPJCacheData) {
        _classementPJCacheData = { suggestion: null, suggestions: [], source: 'none' };
    }
    if (!_messageId) return;

    // Fetch via /api/pj_classification/post_send qui retourne en 1 appel :
    // attachments + suggestion + suggestions (top 3) + source + folders
    // (étape 1'' backend exposé). Bénéfice : 1 seul round-trip + données
    // toujours fraîches (pas d'incohérence vs cache RAM front).
    fetch(_backendUrl + '/api/pj_classification/post_send/' + encodeURIComponent(_messageId))
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(data) {
            var pjs = (data && data.pj_suggestions) || {};
            // Si rien à classer (pas de PJ ou no_pj source), avertir l'user
            if (!pjs.attachments || pjs.attachments.length === 0) {
                alert('Pas de pièce jointe à classer pour ce mail.');
                return;
            }
            _classMailPJMode = 'pre';
            // Mettre à jour le cache RAM avec les données fraîches
            _classementPJCacheData = pjs;
            _showClassPJPopup(pjs, 'pre');
        })
        .catch(function(e) {
            console.warn('[dialog] _openPreSendClassPJPopup failed:', e);
        });
}

function _confirmPreSendPJChoice() {
    if (_selectedPJFolderManualPath) {
        _preSendPJFolderPath = _selectedPJFolderManualPath;
        _preSendPJIsManual = true;
    } else if (_selectedPJFolderPath) {
        _preSendPJFolderPath = _selectedPJFolderPath;
        _preSendPJIsManual = false;
    }
    var pjEl = document.getElementById('infoClassementPJContent');
    if (pjEl && _preSendPJFolderPath) {
        pjEl.textContent = _preSendPJFolderPath + ' ✓';
    }
    _classMailPJMode = 'post';
    document.getElementById('popupClassPJ').classList.remove('active');
}

function _cancelPreSendPJChoice() {
    _classMailPJMode = 'post';
    document.getElementById('popupClassPJ').classList.remove('active');
}

function doClassMail() {
    // Étape 4' (02/05 PM) — En mode pré-envoi : mémoriser le choix sans
    // déclencher l'API. La popup post-envoi le réutilisera comme défaut.
    if (_classMailMode === 'pre') {
        _confirmPreSendChoice();
        return;
    }
    // Phase 3 (30/04 PM) : si l'user a tapé un path manuel, on route vers
    // /api/classify_email_manual qui crée récursivement les dossiers manquants.
    // Sinon : path classique (folder_id sélectionné dans l'arborescence/suggestion).
    if (_selectedFolderManualPath) {
        _doClassMailManual(_selectedFolderManualPath);
        return;
    }
    if (!_selectedFolderId) return;
    document.getElementById('btnClassMail').disabled = true;
    document.getElementById('btnClassMail').textContent = 'Classement...';

    // #10 AbortController timeout 10s — fallback gracieux vers _startClassPJ
    // si timeout (workflow non-bloquant, le mail est déjà envoyé).
    _fetchTimeout(_backendUrl + '/api/classify_email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message_id: _messageId,
            folder_id: _selectedFolderId,
        }),
    }, 10000).then(function(r) { return r.json(); })
    .then(function(data) {
        document.getElementById('popupClassMail').classList.remove('active');
        _startClassPJ();
    })
    .catch(function() {
        document.getElementById('popupClassMail').classList.remove('active');
        _startClassPJ();
    });
}

// Phase 3 (30/04 PM) — Classement par saisie manuelle d'un path texte.
// Le backend (`/api/classify_email_manual`) crée récursivement les dossiers
// manquants via Graph API si le path n'existe pas (max 5 niveaux de
// profondeur, max 100 chars/segment).
function _doClassMailManual(path) {
    var btn = document.getElementById('btnClassMail');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Création + classement...';
    }

    _fetchTimeout(_backendUrl + '/api/classify_email_manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message_id: _messageId,
            path: path,
        }),
    }, 15000)  // 15s : création récursive + move peut être plus long que classify simple
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data && data.status === 'ok') {
            // Pas d'alert : workflow non-bloquant, on passe au classement PJ
            document.getElementById('popupClassMail').classList.remove('active');
            _startClassPJ();
        } else {
            // Erreur : afficher dans le bouton et rester sur la popup pour retry
            if (btn) {
                btn.textContent = 'Erreur : ' + (data && data.detail || data && data.error || 'inconnue');
                setTimeout(function() {
                    btn.textContent = 'Classer ici';
                    btn.disabled = false;
                }, 3000);
            }
        }
    })
    .catch(function(err) {
        if (btn) {
            btn.textContent = 'Erreur réseau';
            setTimeout(function() {
                btn.textContent = 'Classer ici';
                btn.disabled = false;
            }, 2500);
        }
    });
}

function skipClassMail() {
    // Étape 4' (02/05 PM) — En mode pré-envoi : « Annuler » ferme sans
    // sauvegarder. _startClassPJ ne doit PAS être appelé (workflow post-envoi
    // pas encore lancé).
    if (_classMailMode === 'pre') {
        _cancelPreSendChoice();
        return;
    }
    document.getElementById('popupClassMail').classList.remove('active');
    _startClassPJ();
}

// --- Étape 3 : Classement PJ ---

function _startClassPJ() {
    if (!_messageId) { _finalClose(); return; }

    // #10 AbortController timeout 10s — workflow non-bloquant, fallback _finalClose si timeout.
    _fetchTimeout(_backendUrl + '/api/pj_classification/post_send/' + encodeURIComponent(_messageId), null, 10000)
        .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function(data) {
            if (data.status === 'scanning') {
                setTimeout(function() {
                    // #10 timeout 10s aussi sur le retry
                    _fetchTimeout(_backendUrl + '/api/pj_classification/post_send/' + encodeURIComponent(_messageId), null, 10000)
                        .then(function(r) { return r.json(); })
                        .then(function(data2) {
                            if (data2.status === 'done' && data2.pj_suggestions && data2.pj_suggestions.attachments && data2.pj_suggestions.attachments.length > 0) {
                                _postSendPJData = data2.pj_suggestions;
                                _showClassPJPopup(data2.pj_suggestions);
                            } else { _finalClose(); }
                        }).catch(function() { _finalClose(); });
                }, 1500);
            } else if (data.status === 'done' && data.pj_suggestions && data.pj_suggestions.attachments && data.pj_suggestions.attachments.length > 0) {
                _postSendPJData = data.pj_suggestions;
                _showClassPJPopup(data.pj_suggestions);
            } else {
                _finalClose();
            }
        })
        .catch(function() { _finalClose(); });
}

function _showClassPJPopup(pjData, mode) {
    // Étape 2''/4'' (02/05 PM, vision Yvan) — Refonte complète parallèle
    // popup classement mail :
    //   - Liste des PJ (header inchangé)
    //   - Top 3 suggestions (1 principale + 2 boulettes ●) basé sur
    //     pjData.suggestions (exposé par étape 1'' backend)
    //   - Arborescence Windows (chevrons togglables, algo depth-based)
    //     issue de pjData.folders
    //   - Saisie manuelle path (input Q2=OUI)
    //   - Mode 'pre' / 'post' (étape 4'') adapte les boutons
    mode = mode || 'post';
    _classMailPJMode = mode;

    // Liste des PJ à classer (inchangé)
    var listHtml = '<p style="margin-bottom:8px;">Pieces jointes a classer :</p>';
    (pjData.attachments || []).forEach(function(att) {
        listHtml += '<div class="pj-chip" style="margin-bottom:4px;">&#x1f4c4; '
            + _escapeHtml(att.name) + '</div>';
    });
    document.getElementById('classPJList').innerHTML = listHtml;

    // Top 3 suggestions
    var suggestions = (pjData.suggestions && pjData.suggestions.length)
        ? pjData.suggestions
        : (pjData.suggestion ? [pjData.suggestion] : []);

    // Sélection initiale (priorité au choix pré-envoi user en mode 'post')
    var initialSelectedPath = '';
    if (suggestions.length > 0 && suggestions[0]) {
        initialSelectedPath = suggestions[0].folder_path
            || suggestions[0].dest_folder
            || suggestions[0].folder_name || '';
    }
    var initialManualPath = '';
    if (mode === 'post') {
        if (_preSendPJIsManual && _preSendPJFolderPath) {
            initialManualPath = _preSendPJFolderPath;
            initialSelectedPath = '';
        } else if (_preSendPJFolderPath) {
            initialSelectedPath = _preSendPJFolderPath;
        }
    }

    var sugHtml = '';
    if (suggestions.length > 0) {
        var main = suggestions[0];
        var mainPath = main.folder_path || main.dest_folder || main.folder_name || 'Dossier suggéré';
        var mainReason = main.reason || '';
        var mainPrefix = (pjData.source === 'ai') ? 'Suggestion IA : ' : '';
        var mainSelected = (mainPath === initialSelectedPath) ? ' selected' : '';
        sugHtml += '<div class="em-folder-suggestion' + mainSelected + '" '
            + 'onclick="_selectPJFolder(\'' + _escapeAttr(mainPath) + '\', this)">'
            + '&#x1f4c1; ' + _escapeHtml(mainPrefix + mainPath)
            + (mainReason ? '<span class="em-suggestion-reason">— ' + _escapeHtml(mainReason) + '</span>' : '')
            + '</div>';
        _selectedPJFolderPath = initialSelectedPath;
        document.getElementById('btnClassPJ').disabled = !(initialSelectedPath || initialManualPath);

        // Alternatives top 2/3 — boulettes (max 2)
        var alts = suggestions.slice(1, 3);
        if (alts.length > 0) {
            sugHtml += '<div class="em-folder-alternatives">';
            alts.forEach(function(s) {
                var altPath = s.folder_path || s.dest_folder || s.folder_name || 'Dossier suggéré';
                var altReason = s.reason || '';
                var altSelected = (altPath === initialSelectedPath) ? ' selected' : '';
                sugHtml += '<div class="em-folder-alternative' + altSelected + '" '
                    + 'onclick="_selectPJFolder(\'' + _escapeAttr(altPath) + '\', this)">'
                    + '<span class="em-folder-alt-bullet">&#x25cf;</span>'
                    + '<span>' + _escapeHtml(altPath)
                    + (altReason ? '<span class="em-suggestion-reason">— ' + _escapeHtml(altReason) + '</span>' : '')
                    + '</span></div>';
            });
            sugHtml += '</div>';
        }
    }
    document.getElementById('classPJSuggestion').innerHTML = sugHtml;

    // Arborescence Windows (algo depth-based comme l'arbo mail d'Yvan)
    var folders = pjData.folders || [];
    if (folders.length > 0) {
        var treeHtml = _buildPJFolderTreeHtml(folders);
        var treeEl = document.getElementById('classPJTree');
        treeEl.innerHTML = treeHtml;

        // Étape 3'' — Scroll auto vers la suggestion (parallèle mail)
        try {
            if (_selectedPJFolderPath) {
                var rows = treeEl.querySelectorAll('.em-folder-item');
                for (var ri = 0; ri < rows.length; ri++) {
                    if (rows[ri].getAttribute('data-folder-path') === _selectedPJFolderPath) {
                        rows[ri].classList.add('selected');
                        if (rows[ri].scrollIntoView) {
                            rows[ri].scrollIntoView({ block: 'center', behavior: 'auto' });
                        }
                        break;
                    }
                }
            }
        } catch (e) { /* scroll non critique */ }
    } else {
        document.getElementById('classPJTree').innerHTML = '';
    }

    // Saisie manuelle (Q2=OUI) — pré-remplir si choix pré-envoi manuel
    var manualInput = document.getElementById('classPJManualPath');
    if (manualInput) {
        manualInput.value = initialManualPath || '';
        if (initialManualPath) {
            _selectedPJFolderManualPath = initialManualPath;
        } else {
            _selectedPJFolderManualPath = '';
        }
        manualInput.removeEventListener('input', _onManualPJPathInput);
        manualInput.addEventListener('input', _onManualPJPathInput);
    }

    // Adapter libellés boutons selon mode (étape 4'')
    var btnSkipPJ = document.querySelector('#popupClassPJ .em-popup-btn:not(.primary)');
    var btnPrimaryPJ = document.getElementById('btnClassPJ');
    if (mode === 'pre') {
        if (btnSkipPJ) btnSkipPJ.textContent = 'Annuler';
        if (btnPrimaryPJ) btnPrimaryPJ.textContent = 'Confirmer';
    } else {
        if (btnSkipPJ) btnSkipPJ.textContent = 'Pas maintenant';
        if (btnPrimaryPJ) btnPrimaryPJ.textContent = 'Classer ici';
    }

    document.getElementById('popupClassPJ').classList.add('active');
}

// Étape 2''/4'' (02/05 PM) — Construit l'arbo Windows à partir d'une liste
// plate {path, name, depth} (poussée par Companion). Algo depth-based
// identique à l'arbo mail d'Yvan, mais identifie par data-folder-path
// (les dossiers Windows n'ont pas d'id, juste un path).
function _buildPJFolderTreeHtml(folders) {
    if (!folders || !folders.length) return '';
    var html = '';
    folders.forEach(function(f, i) {
        var depth = f.depth || 0;
        var next = folders[i + 1];
        var hasChildren = next && (next.depth || 0) > depth;
        var indent = depth * 14;
        var chevron = hasChildren
            ? '<span class="em-folder-chevron expanded" onclick="_togglePJFolderChildren(event, this.parentElement)">&#x25bc;</span>'
            : '<span class="em-folder-chevron-spacer"></span>';
        html += '<div class="em-folder-item" '
            + 'data-folder-path="' + _escapeAttr(f.path) + '" '
            + 'data-depth="' + depth + '" '
            + 'style="padding-left:' + indent + 'px;display:flex;align-items:center;gap:4px;" '
            + 'onclick="_selectPJFolderFromRow(event, this)">'
            + chevron
            + '<span class="em-folder-name">' + _escapeHtml(f.name) + '</span>'
            + '</div>';
    });
    return html;
}

// Étape 2''/4'' (02/05 PM) — Wrapper distinguant clic chevron vs clic ligne
// pour l'arbo PJ (parallèle _selectFolderFromRow pour mail).
function _selectPJFolderFromRow(event, rowEl) {
    if (event && event.target && event.target.classList &&
        event.target.classList.contains('em-folder-chevron')) {
        return;
    }
    var folderPath = rowEl.getAttribute('data-folder-path');
    _selectPJFolder(folderPath, rowEl);
}

// Étape 2''/4'' (02/05 PM) — Sélectionne un folder PJ (depuis arbo, sugg,
// ou alternative). Reset sélection précédente + saisie manuelle. Identique
// à _selectFolder mais pour PJ (path au lieu de folder_id).
function _selectPJFolder(folderPath, element) {
    _selectedPJFolderPath = folderPath;
    _selectedPJFolderManualPath = '';
    var manualInput = document.getElementById('classPJManualPath');
    if (manualInput) manualInput.value = '';
    document.getElementById('btnClassPJ').disabled = false;
    // Highlight (cible #popupClassPJ uniquement pour ne pas affecter mail)
    document.querySelectorAll('#popupClassPJ .em-folder-item, #popupClassPJ .em-folder-suggestion, #popupClassPJ .em-folder-alternative').forEach(function(el) {
        el.classList.remove('selected');
    });
    if (element && element.classList) {
        element.classList.add('selected');
    }
}

// Étape 2''/4'' (02/05 PM) — Toggle expand/collapse arbo PJ (parallèle
// _toggleFolderChildren mail).
function _togglePJFolderChildren(event, parentRow) {
    if (event) {
        event.stopPropagation();
        event.preventDefault();
    }
    var depth = parseInt(parentRow.getAttribute('data-depth'), 10);
    if (isNaN(depth)) return;
    var chevron = parentRow.querySelector('.em-folder-chevron');
    var collapsing = chevron && chevron.classList.contains('expanded');
    if (chevron) {
        chevron.classList.toggle('expanded', !collapsing);
        chevron.classList.toggle('collapsed', collapsing);
        chevron.textContent = collapsing ? '▶' : '▼';
    }
    var sibling = parentRow.nextElementSibling;
    while (sibling) {
        var sd = parseInt(sibling.getAttribute('data-depth'), 10);
        if (isNaN(sd) || sd <= depth) break;
        if (collapsing) {
            sibling.style.display = 'none';
        } else {
            if (sd === depth + 1) {
                sibling.style.display = '';
            } else {
                var anc = sibling.previousElementSibling;
                while (anc) {
                    var ad = parseInt(anc.getAttribute('data-depth'), 10);
                    if (!isNaN(ad) && ad === depth + 1) {
                        var ancChev = anc.querySelector('.em-folder-chevron');
                        var ancExpanded = ancChev && ancChev.classList.contains('expanded');
                        sibling.style.display = ancExpanded ? '' : 'none';
                        break;
                    }
                    anc = anc.previousElementSibling;
                }
            }
        }
        sibling = sibling.nextElementSibling;
    }
}

// Étape 2''/4'' (02/05 PM) — Handler input saisie manuelle path PJ.
// Désactive sélection arbo/suggestion + active btnClassPJ. Au confirm,
// le Companion local crée le dossier sous pj_root_folder s'il n'existe
// pas (os.makedirs exist_ok=True déjà géré).
function _onManualPJPathInput(e) {
    var val = (e && e.target && e.target.value || '').trim();
    var btn = document.getElementById('btnClassPJ');
    if (val.length > 0) {
        _selectedPJFolderManualPath = val;
        _selectedPJFolderPath = '';  // mode manual prend le pas
        document.querySelectorAll('#popupClassPJ .em-folder-item, #popupClassPJ .em-folder-suggestion, #popupClassPJ .em-folder-alternative').forEach(function(el) {
            el.classList.remove('selected');
        });
        if (btn) btn.disabled = false;
    } else {
        _selectedPJFolderManualPath = '';
        if (btn) btn.disabled = (_selectedPJFolderPath ? false : true);
    }
}

function doClassPJ() {
    // Étape 4''/4'' (02/05 PM) — En mode pré-envoi : mémoriser le choix
    // sans déclencher la copie. La popup post-envoi le réutilisera comme
    // défaut.
    if (_classMailPJMode === 'pre') {
        _confirmPreSendPJChoice();
        return;
    }
    if (!_postSendPJData) return;
    document.getElementById('btnClassPJ').disabled = true;
    document.getElementById('btnClassPJ').textContent = 'Classement...';

    // Étape 2'' (02/05 PM) — Source du dest_folder (ordre de priorité) :
    // 1. Saisie manuelle (Q2=OUI, le Companion crée le dossier si manquant)
    // 2. Sélection arbo / suggestion / boulette (path Windows depuis
    //    user_windows_folders OVH)
    // 3. Fallback : suggestion.folder_path du cache BG (rétro-compat)
    var pjDestFolder = _selectedPJFolderManualPath
        || _selectedPJFolderPath
        || (_postSendPJData.suggestion ? (_postSendPJData.suggestion.folder_path || '') : '');
    if (!pjDestFolder) {
        document.getElementById('popupClassPJ').classList.remove('active');
        _finalClose();
        return;
    }

    // Classer chaque PJ via le backend (qui choisit le niveau automatiquement)
    var promises = [];
    _postSendPJData.attachments.forEach(function(att) {
        promises.push(
            fetch(_backendUrl + '/api/classify_pj', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message_id: _messageId,
                    attachment_id: att.id,
                    dest_folder: pjDestFolder,
                    filename: att.name,
                    contact_email: _fromEmail,
                    level: 0,  // Auto-detect (Companion géré côté dialog si disponible)
                }),
            }).then(function(r) { return r.json(); })
              .then(function(data) {
                  if (data.level === 3) {
                      // Niveau 3 : téléchargement guidé — informer l'utilisateur
                      console.log('[dialog] PJ ' + att.name + ' : classement auto non disponible');
                  }
                  return data;
              })
        );
    });

    Promise.allSettled(promises)
        .then(function(results) {
            var failed = results.filter(function(r) { return r.status === 'rejected'; }).length;
            var level3 = results.filter(function(r) {
                return r.status === 'fulfilled' && r.value && r.value.level === 3;
            }).length;
            if (failed > 0 || level3 > 0) {
                console.log('[dialog] ' + (failed + level3) + ' PJ(s) non classees automatiquement');
            }
            document.getElementById('popupClassPJ').classList.remove('active');
            _finalClose();
        });
}

function skipClassPJ() {
    // Étape 4''/4'' (02/05 PM) — En mode pré-envoi : « Annuler » ferme
    // sans rien sauvegarder. _finalClose ne doit PAS être appelé.
    if (_classMailPJMode === 'pre') {
        _cancelPreSendPJChoice();
        return;
    }
    document.getElementById('popupClassPJ').classList.remove('active');
    _finalClose();
}

// --- Fermeture finale ---

function _finalClose() {
    if (_isStandardMode) {
        _messageParent({ action: 'sent' });
    }
    // Popup succès "Mail envoyé !" (comme le proto)
    _showSuccessOverlay();
    setTimeout(function() { _closeDialog(); }, 2500);
}

function _showSuccessOverlay() {
    var overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.5);z-index:300;display:flex;align-items:center;justify-content:center;';
    var popup = document.createElement('div');
    popup.style.cssText = 'background:#fff;border-radius:12px;padding:32px 48px;text-align:center;box-shadow:0 8px 32px rgba(0,0,0,0.2);';
    popup.innerHTML = '<div style="font-size:48px;margin-bottom:12px;">&#x2705;</div>' +
        '<div style="font-size:16px;font-weight:600;color:#333;margin-bottom:4px;">Mail envoye !</div>' +
        '<div style="font-size:11px;color:#999;">Fermeture automatique...</div>';
    overlay.appendChild(popup);
    document.body.appendChild(overlay);
}


// =============================================================================
// TABLEAU DE BORD — overlay iframe interne (29/04 PM tardif)
// =============================================================================
// Les 3 boutons header (Profil/Contacts/Échéances) ouvrent les pages
// correspondantes en surimpression dans la fenêtre BoosterMail actuelle.
// Le brouillon en cours est préservé (overlay z-index:200 par-dessus).

function _openDashboard(view) {
    /** Affiche le dashboard (Profil/Contacts/Échéances) dans un overlay
     * iframe AU-DESSUS du dialog principal. view ∈ {'profile', 'contacts', 'echeances'}.
     *
     * Décision Yvan 01/05/2026 — REVERT du commit ec6d009 (window.open).
     * L'ancienne implémentation iframe overlay au-dessus du dialog est
     * la bonne UX. Le window.open ouvrait une fenêtre browser détachée,
     * gênante en pratique. */
    var VALID_VIEWS = {'profile': 1, 'contacts': 1, 'echeances': 1};
    if (!VALID_VIEWS[view]) {
        console.warn('[dashboard] view non autorisée :', view);
        return;
    }

    var titles = {
        'profile':   '👤 Profil',
        'contacts':  '📑 Contacts',
        'echeances': '⏰ Échéances',
    };
    var titleEl = document.getElementById('dashboardTitle');
    if (titleEl) titleEl.textContent = titles[view] || 'Tableau de bord';

    var frame = document.getElementById('dashboardFrame');
    var overlay = document.getElementById('dashboardOverlay');
    if (!frame || !overlay) return;

    frame.src = _backendUrl + '/plugin/' + view;
    overlay.style.display = 'block';
}

function _closeDashboard() {
    /** Ferme l'overlay tableau de bord et libère l'iframe. */
    var overlay = document.getElementById('dashboardOverlay');
    var frame = document.getElementById('dashboardFrame');
    if (overlay) overlay.style.display = 'none';
    // Libérer l'iframe pour que le prochain ouvrir reload frais
    if (frame) frame.src = 'about:blank';
}


// =============================================================================
// COMMUNICATION DIALOG ↔ OUTLOOK
// =============================================================================

function _messageParent(msg) {
    /** Wrapper sûr pour Office.context.ui.messageParent(). */
    try {
        if (typeof Office !== 'undefined' && Office.context && Office.context.ui) {
            Office.context.ui.messageParent(JSON.stringify(msg));
            return true;
        }
    } catch (e) {
        console.log('[dialog] messageParent non disponible:', e.message);
    }
    return false;
}

function _closeDialog() {
    // Chef sortant : libérer les portes AVANT de signaler la fermeture.
    // beforeunload tire aussi _cleanupAllStreams mais il arrive parfois trop
    // tard en PyQt (la nav easymail:// est interceptée avant qu'unload ne
    // fire proprement). On appelle explicitement ici pour que V2 voie les
    // TCP close immédiatement → le prochain clic BM trouve le pool vide.
    try { _cleanupAllStreams(); } catch(_) {}

    if (!_messageParent({ action: 'close' })) {
        // (B45) En standalone PyQt, signaler au conteneur de revenir à la popup
        try {
            window.location.href = 'easymail://close-dialog/';
        } catch (e) {}
        // Fallback navigateur : fermer la fenêtre (window.open → window.close)
        try {
            window.close();
        } catch (e) {}
    }
}


// =============================================================================
// ÉCOUTE MESSAGES PARENT — Body du mail en Mode Perf. Réduite
// =============================================================================

function _listenParentMessages() {
    try {
        if (typeof Office !== 'undefined' && Office.context && Office.context.ui) {
            Office.context.ui.addHandlerAsync(
                Office.EventType.DialogParentMessageReceived,
                function(arg) {
                    try {
                        var data = JSON.parse(arg.message);
                        if (data.action === 'mail_body') {
                            // Body reçu du parent (Mode Perf. Réduite)
                            _mailBodyForGeneration = data.body || '';
                            _receivedBody = data.body || '';

                            // Mettre à jour le panneau gauche
                            var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');
                            // Convertir le texte brut en paragraphes pour une meilleure mise en page
                            var bodyHtml = _mailBodyForGeneration.split(/\n\n+/).map(function(p) {
                                return '<p>' + _escapeHtml(p).replace(/\n/g, '<br>') + '</p>';
                            }).join('');
                            document.getElementById('mailBody').innerHTML = bodyHtml || _escapeHtml(_mailBodyForGeneration);

                            // Mettre à jour from si pas encore rempli
                            if (data.from_name && !_fromName) {
                                _fromName = data.from_name;
                                _updateHeader();
                            }
                            if (data.from_email && !_fromEmail) {
                                _fromEmail = data.from_email;
                            }
                            console.log('[dialog] Body recu du parent (' + _mailBodyForGeneration.length + ' chars)');

                        } else if (data.action === 'auth_token') {
                            // Étape 7 finale (29/04 PM) — JWT reçu du shared runtime
                            // Stocké en mémoire JS, disponible pour _fetchWithBearer().
                            // Le token expire dans data.expires_in secondes (typique 900 = 15 min).
                            // Le shared runtime renouvelle toutes les 10 min et nous le re-pousse.
                            _bmAuthToken = data.token || '';
                            _bmAuthTokenTs = data.issued_at_ts || Date.now();
                            _bmAuthTokenTtl = data.expires_in || 900;
                            console.log('[dialog] auth_token recu (len=' + _bmAuthToken.length + ', ttl=' + _bmAuthTokenTtl + 's)');

                        } else if (data.action === 'compose_data') {
                            // Données compose reçues du parent (mode compose ouvert rapidement)
                            if (data.subject) _subject = data.subject;
                            if (data.mode && data.mode !== _mode) {
                                _mode = data.mode;
                                _updateHeader();
                                // Mettre à jour le champ sujet
                                var fSubj = document.getElementById('fieldSubject');
                                if (fSubj && data.subject) fSubj.value = data.subject;
                                // Adapter le placeholder brief
                                var briefField = document.getElementById('fieldBrief');
                                if (briefField) {
                                    briefField.placeholder = (_mode === 'new')
                                        ? 'Decrivez votre mail en quelques mots (obligatoire)'
                                        : 'Instructions (optionnel)';
                                }
                            }
                            // Pré-remplir To/Cc si pas encore remplis
                            var fTo = document.getElementById('fieldTo');
                            if (fTo && data.to && !fTo.value) fTo.value = data.to;
                            var fCc = document.getElementById('fieldCc');
                            if (fCc && data.cc && !fCc.value) fCc.value = data.cc;
                            console.log('[dialog] compose_data recu: mode=' + data.mode + ' subject=' + data.subject);
                        }
                    } catch(e) {
                        console.log('[dialog] Erreur parsing message parent:', e.message);
                    }
                }
            );
        }
    } catch(e) {
        console.log('[dialog] DialogParentMessageReceived non supporte');
    }
}


// =============================================================================
// AUTOCOMPLETE CONTACTS (12o)
// =============================================================================

// Optim 27/04 PM (Workflow 3 audit kit) — remplacement du pre-load
// /api/contact_profiles 187 KB par un fetch debounced /api/contact_search
// a la frappe. Le cache localStorage TTL 1h ne tenait pas dans le contexte
// iframe Office.js (sandboxe par dialog), donc 187 KB telecharges a chaque
// clic. Avec contact_search : ~3 KB par recherche, declenche seulement
// quand l'user tape > 2 chars dans À : ou Cc :.
//
// _loadContacts() et _contactsCache supprimes (plus utilises).

// STAND-BY S2 — déclarations déplacées en TOP du fichier (cf incident 30/04 PM
// "Cannot read properties of undefined reading 'push'"). Le handler ci-dessous
// ne reste ici que pour la cohérence de localisation avec _initAutocomplete.

function _bindGlobalAutocompleteHandler() {
    if (_autocompleteGlobalHandlerBound) return;
    _autocompleteGlobalHandlerBound = true;
    var _autocompleteClickHandler = function(e) {
        for (var i = 0; i < _autocompleteRegistrations.length; i++) {
            var reg = _autocompleteRegistrations[i];
            if (e.target !== reg.input && !reg.dropdown.contains(e.target)) {
                reg.dropdown.classList.remove('active');
            }
        }
    };
    document.addEventListener('click', _autocompleteClickHandler);
    // STAND-BY S9 — cleanup au beforeunload pour libérer le handler document.
    _registerCleanup(function() {
        document.removeEventListener('click', _autocompleteClickHandler);
        _autocompleteRegistrations = [];
        _autocompleteGlobalHandlerBound = false;
    });
}

function _initAutocomplete(inputId, dropdownId) {
    var input = document.getElementById(inputId);
    var dropdown = document.getElementById(dropdownId);
    if (!input || !dropdown) return;

    var selectedIndex = -1;
    var _searchTimer = null;
    var _searchAbortCtrl = null;

    function _renderMatches(matches) {
        if (!matches || !matches.length) {
            dropdown.classList.remove('active');
            return;
        }
        selectedIndex = -1;
        dropdown.innerHTML = matches.map(function(c, i) {
            return '<div class="em-ac-item" data-email="' + _escapeHtml(c.email) + '" data-index="' + i + '">'
                + '<span class="em-ac-name">' + _escapeHtml(c.name) + '</span>'
                + '<span class="em-ac-email">' + _escapeHtml(c.email) + '</span>'
                + (c.org ? '<span class="em-ac-org">' + _escapeHtml(c.org) + '</span>' : '')
                + '</div>';
        }).join('');

        dropdown.classList.add('active');

        // Positionner sous l'input (pas sous la label)
        dropdown.style.left = (input.offsetLeft) + 'px';
        dropdown.style.right = '0';
        dropdown.style.top = input.offsetHeight + 'px';

        // Click handler sur chaque item
        dropdown.querySelectorAll('.em-ac-item').forEach(function(item) {
            item.addEventListener('click', function() {
                input.value = item.getAttribute('data-email');
                input.dispatchEvent(new Event('input'));  // Trigger garde forward
                // Fermer APRÈS le dispatch (sinon le handler input rouvre le dropdown)
                setTimeout(function() { dropdown.classList.remove('active'); }, 50);
            });
        });
    }

    function _doSearch(val) {
        // Annuler le fetch precedent si encore en vol (evite race)
        if (_searchAbortCtrl) {
            try { _searchAbortCtrl.abort(); } catch(_) {}
        }
        _searchAbortCtrl = (typeof AbortController !== 'undefined')
            ? new AbortController() : null;

        var url = _backendUrl + '/api/contact_search?q=' + encodeURIComponent(val);
        var opts = _searchAbortCtrl ? { signal: _searchAbortCtrl.signal } : {};

        fetch(url, opts)
            .then(function(r) { return r.ok ? r.json() : { contacts: [] }; })
            .then(function(data) { _renderMatches(data.contacts || []); })
            .catch(function(err) {
                // AbortError = nouveau fetch parti, normal. Autres = silent.
                if (err && err.name === 'AbortError') return;
            });
    }

    input.addEventListener('input', function() {
        var val = input.value.trim().toLowerCase();
        if (val.length < 2) {
            dropdown.classList.remove('active');
            return;
        }
        // Debounce 150 ms : evite de spammer le serveur a chaque touche
        if (_searchTimer) clearTimeout(_searchTimer);
        _searchTimer = setTimeout(function() {
            _searchTimer = null;
            _doSearch(val);
        }, 150);
    });

    // Navigation clavier
    input.addEventListener('keydown', function(e) {
        var items = dropdown.querySelectorAll('.em-ac-item');
        if (!dropdown.classList.contains('active') || items.length === 0) return;

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
            items.forEach(function(it, i) { it.classList.toggle('selected', i === selectedIndex); });
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            selectedIndex = Math.max(selectedIndex - 1, 0);
            items.forEach(function(it, i) { it.classList.toggle('selected', i === selectedIndex); });
        } else if (e.key === 'Enter' && selectedIndex >= 0) {
            e.preventDefault();
            input.value = items[selectedIndex].getAttribute('data-email');
            dropdown.classList.remove('active');
            input.dispatchEvent(new Event('input'));
        } else if (e.key === 'Escape') {
            dropdown.classList.remove('active');
        }
    });

    // STAND-BY S2 — enregistrer cet autocomplete dans le registry global
    // (handler click document partagé via _bindGlobalAutocompleteHandler).
    _autocompleteRegistrations.push({ input: input, dropdown: dropdown });
    _bindGlobalAutocompleteHandler();
}


// =============================================================================
// UTILITAIRES
// =============================================================================

function _escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

/* #4 audit : echappe pour les attributs onclick inline (guillemets simples) */
function _escapeAttr(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/'/g, '&#39;').replace(/"/g, '&quot;')
              .replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function _formatSize(bytes) {
    if (bytes < 1024) return bytes + ' o';
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' Ko';
    return (bytes / (1024 * 1024)).toFixed(1) + ' Mo';
}


// =============================================================================
// PHASE 3 — MODE STANDALONE (QWebEngineView / window.open)
// =============================================================================

/** Nettoyage HTML (factorisé 21/04 — évite 3 copies identiques) */
function _sanitizeHtml(html) {
    if (!html) return '';
    return html
        .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
        .replace(/<iframe\b[^>]*>/gi, '<!-- blocked -->')
        .replace(/<object\b[^>]*>/gi, '<!-- blocked -->')
        .replace(/<embed\b[^>]*>/gi, '<!-- blocked -->')
        .replace(/on\w+\s*=/gi, 'data-blocked=');
}

function _applyMailMeta() {
    var mf = document.getElementById('mailFrom');
    if (mf) mf.textContent = _fromName ? _fromName + ' <' + _fromEmail + '>' : (_fromEmail || '—');
    var ms = document.getElementById('mailSubject');
    if (ms) ms.textContent = _subject || '—';
    _updateHeader();
    // (O6) Pré-remplir les champs dest / sujet (pas écraser ce qu'a saisi user)
    if (!document.getElementById('fieldTo').value && _fromEmail && (_mode === 'reply' || _mode === 'reply_all')) {
        document.getElementById('fieldTo').value = _fromEmail;
    }
    if (!document.getElementById('fieldSubject').value && _subject) {
        var prefix = _mode === 'forward' ? 'Fw: ' : 'Re: ';
        var subjectClean = _subject.replace(/^(re\s*:|fw\s*:|fwd\s*:|tr\s*:)\s*/i, '');
        document.getElementById('fieldSubject').value = prefix + subjectClean;
    }
}

function _setMailBody(rawBody, isCached) {
    if (!rawBody) return false;
    var mb = document.getElementById('mailBody');
    // Phase 3 audit 22/04 : si !cached → fetch fresh → anim fade-in (feedback
    // visuel). Si cached → instantané (pas d'anim, user voit le texte déjà là).
    if (!isCached && mb) {
        mb.style.opacity = '0';
        mb.style.transition = 'opacity 0.25s ease-in';
    }
    mb.innerHTML = _sanitizeHtml(rawBody);
    if (!isCached && mb) {
        requestAnimationFrame(function() { mb.style.opacity = '1'; });
    }
    _receivedBody = rawBody;
    _mailBodyForGeneration = rawBody;
    var bs = document.getElementById('bodySpinner');
    if (bs) bs.classList.remove('active');
    // Phase 2 progression : body chargé → passage à "Intégration du contexte"
    if (_progressPlaceholderActive) _showProgressPlaceholder('context');
    // Fix 23/04 : T3 mark manquant dans path standalone — sans ça le perf log
    // n'enregistrait jamais le moment où le body devient visible.
    _perfMonitor.mark('T3_body_rendered', isCached ? 'cache' : 'graph');
    return true;
}

// =============================================================================
// Messages de progression dans l'éditeur (21/04) — la popup s'affiche quasi
// instantanément (apparition), mais le CONTENU se construit progressivement.
// On affiche des messages d'attente dans l'éditeur pour donner un feedback
// visuel pendant les ~3-6s que prend la génération Claude.
//
// Phases :
//   1. "Recherche de l'historique..." : au chargement du dialog (fetch body)
//   2. "Intégration du contexte..."   : body chargé, préparation Claude
//   3. "Rédaction en cours..."        : Claude streame (juste avant 1er chunk)
//
// Règles :
//   - JAMAIS écraser du texte utilisateur (si editor non vide sans placeholder)
//   - JAMAIS écraser une vraie réponse (draft / template / préemptif) : ces
//     chemins appellent editor.innerHTML = ... qui supprime le placeholder
//   - Le 1er chunk Claude vide le placeholder avant insertion
// =============================================================================
var _progressPlaceholderActive = false;

function _showProgressPlaceholder(phase, force) {
    var editor = document.getElementById('editor');
    if (!editor) return;
    // Sync DOM ↔ flag : si notre placeholder a été remplacé par du contenu
    // réel (draft/template/préemptif), le flag doit refléter cette réalité
    // pour que le garde "ne pas écraser l'user" redevienne actif.
    if (_progressPlaceholderActive && !document.getElementById('progressPlaceholder')) {
        _progressPlaceholderActive = false;
    }
    // Sans force : si pas de placeholder actif ET l'éditeur contient du
    // texte user → on touche pas. Avec force (click explicite sur "Générer"
    // après que l'user a tapé), on écrase.
    if (!force && !_progressPlaceholderActive) {
        if (editor.innerText && editor.innerText.trim()) return;
    }
    var labels = {
        'history': '🔍 Recherche de l\'historique...',
        'context': '📧 Intégration du contexte...',
        'writing': '✍️ Rédaction en cours...',
    };
    var label = labels[phase] || labels.writing;
    editor.innerHTML = '<p id="progressPlaceholder" style="color:#888;' +
                       'font-style:italic;margin:0;padding:0;">' +
                       label + '</p>';
    _progressPlaceholderActive = true;
}

function _clearProgressPlaceholder() {
    if (!_progressPlaceholderActive) return;
    var editor = document.getElementById('editor');
    if (editor) {
        var ph = document.getElementById('progressPlaceholder');
        if (ph) editor.innerHTML = '';
    }
    _progressPlaceholderActive = false;
}

/**
 * #15 Affiche un bandeau in-dialog "Session expirée" avec bouton intégré
 * « Se reconnecter » qui ouvre la page profil dans une fenêtre détachée.
 *
 * Avant : alert() bloquant + demande de navigation manuelle vers
 * Profil > Mode Standard → friction UX inacceptable, surtout en plein
 * envoi de mail.
 *
 * Après : bandeau orange non-bloquant en haut du dialog avec bouton qui
 * ouvre `/profile` dans une popup (500×600), idempotent (un seul bandeau
 * à la fois — re-appel = remplace le contenu). Garde anti-spam :
 * disparaît au clic « Se reconnecter » et au close manuel via X.
 */
function _showReauthBanner(message) {
    // Idempotent : si bandeau déjà présent, on met à jour le message et on s'arrête
    var existing = document.getElementById('reauthBanner');
    if (existing) {
        var msgEl = existing.querySelector('.reauth-banner-msg');
        if (msgEl) msgEl.textContent = message || 'Session Microsoft expirée.';
        return;
    }
    var banner = document.createElement('div');
    banner.id = 'reauthBanner';
    banner.style.cssText =
        'position:fixed;top:0;left:0;right:0;z-index:9999;' +
        'background:#fff3cd;border-bottom:1px solid #f0c674;' +
        'padding:8px 12px;display:flex;align-items:center;gap:10px;' +
        'font-size:12px;font-family:Segoe UI,Arial,sans-serif;' +
        'box-shadow:0 1px 3px rgba(0,0,0,0.08);';
    var icon = document.createElement('span');
    icon.textContent = '⚠️';
    icon.style.cssText = 'font-size:14px;flex-shrink:0;';
    var msg = document.createElement('span');
    msg.className = 'reauth-banner-msg';
    msg.textContent = message || 'Session Microsoft expirée.';
    msg.style.cssText = 'flex:1;color:#7d5a00;';
    var btnReauth = document.createElement('button');
    btnReauth.textContent = 'Se reconnecter';
    btnReauth.style.cssText =
        'background:#0F6CBD;color:#fff;border:none;padding:5px 12px;' +
        'border-radius:3px;cursor:pointer;font-size:12px;flex-shrink:0;';
    btnReauth.onclick = function() {
        try {
            window.open(_backendUrl + '/profile', 'BoosterMailReauth',
                        'width=520,height=640,resizable=yes,scrollbars=yes');
        } catch(_) {
            // Fallback si popup bloquée : redirige le dialog lui-même
            window.location.href = _backendUrl + '/profile';
        }
        // Le bandeau reste visible — disparaît au refresh ou retry envoi
    };
    var btnClose = document.createElement('button');
    btnClose.textContent = '✕';
    btnClose.title = 'Masquer';
    btnClose.style.cssText =
        'background:transparent;color:#7d5a00;border:none;cursor:pointer;' +
        'font-size:14px;padding:0 4px;flex-shrink:0;';
    btnClose.onclick = function() { try { banner.remove(); } catch(_) {} };
    banner.appendChild(icon);
    banner.appendChild(msg);
    banner.appendChild(btnReauth);
    banner.appendChild(btnClose);
    document.body.appendChild(banner);
}

/**
 * #16 Choix du wording selon le contexte quand `points.length === 0`.
 *
 * Avant : « Pas de points clés identifiés. » dans tous les cas → ambigu pour
 * l'user qui ne sait pas distinguer (a) mail trivial (« Merci, c'est noté »)
 * (b) mail sans body textuel (image-only, calendar invite) (c) résumé qui a
 * échoué côté backend (Claude timeout, réseau, quota).
 *
 * Après : on distingue 4 cas via `_summaryStatus` + longueur de `_receivedBody`.
 */
function _getEmptyPointsMessage() {
    var bodyLen = (_receivedBody || '').replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim().length;
    if (_summaryStatus === 'error') {
        return 'Résumé indisponible — vérifiez votre connexion ou réessayez.';
    }
    if (bodyLen === 0) {
        return 'Mail sans contenu textuel (PJ uniquement ou invitation).';
    }
    if (bodyLen < 40) {
        return 'Mail trop court pour un résumé.';
    }
    // Mail normal mais Claude n'a rien extrait (mail trivial type "Merci, c'est noté")
    return 'Pas de points clés identifiés.';
}

/**
 * #11 Garde défensive : applique disabled/innerHTML sur btnSend uniquement
 * si l'élément existe encore dans le DOM. Si le dialog a été fermé entre
 * le clic envoi et l'arrivée de la réponse Graph (.then tardif), on
 * écrirait silencieusement sur un élément null → exception JS visible
 * dans console.error qui pollue Sentry et déclenche le toast cross-origin.
 *
 * Usage :
 *   _safeSetSendBtn({ html: '✅ Envoye', disabled: true });   // succès
 *   _safeSetSendBtn({ html: '📤 Relire', disabled: false });  // erreur, réactiver
 *   _safeSetSendBtn({ disabled: false });                      // juste réactiver
 */
function _safeSetSendBtn(opts) {
    var btn = document.getElementById('btnSend');
    if (!btn) return;  // Dialog fermé, on no-op
    if (opts && typeof opts.html === 'string') btn.innerHTML = opts.html;
    if (opts && typeof opts.disabled === 'boolean') btn.disabled = opts.disabled;
}

/**
 * fetch avec timeout explicite (21/04 audit cycle 2 #A).
 * fetch() natif n'a pas de timeout → peut bloquer indéfiniment si le
 * serveur ne ferme jamais la connexion (ex: V2 down, réseau freeze).
 * Wrap via AbortController.
 */
function _fetchTimeout(url, options, timeoutMs) {
    var ctrl = new AbortController();
    var timer = setTimeout(function(){ ctrl.abort(); }, timeoutMs || 5000);
    var opts = Object.assign({}, options || {}, { signal: ctrl.signal });
    return fetch(url, opts).finally(function(){ clearTimeout(timer); });
}

/**
 * Charge le body du mail (mode standalone) — P2 audit 21/04 :
 *   - Si on a _messageId (params URL du dialog), on fetch DIRECT /api/email_body
 *     EN PARALLÈLE de /api/current_mail. Le premier qui a un body gagne.
 *   - Économise jusqu'à 500 ms vs chaîne séquentielle courante → email_body.
 *   - _applyMailMeta s'exécute immédiatement avec les données URL.
 */
function _loadMailBodyStandalone() {
    _applyMailMeta();   // Immédiat : infos déjà en URL params

    // Fix 23/04 (orchestration) : placeholder "Recherche de l'historique…"
    // DIFFÉRÉ de 500 ms. Si le body arrive avant (cache HIT = ~50 ms), le
    // timer est annulé et aucun placeholder ne s'affiche → rendu 100% propre.
    // Si body tarde (Graph fetch 1-3 s), le placeholder s'affiche à 500 ms
    // pour rassurer l'user.
    var _historyPlaceholderTimer = null;
    if (_mode !== 'new') {
        _historyPlaceholderTimer = setTimeout(function() {
            _showProgressPlaceholder('history');
            _historyPlaceholderTimer = null;
        }, 500);
    }

    var done = false;   // Garde course : premier résultat gagne
    var fetches = [];

    // Helper : annule le placeholder en attente si body arrive rapidement.
    // Utilisé par les deux paths (email_body + current_mail) au succès.
    function _cancelHistoryPlaceholder() {
        if (_historyPlaceholderTimer) {
            clearTimeout(_historyPlaceholderTimer);
            _historyPlaceholderTimer = null;
        }
    }

    // Path 1 — /api/email_body (direct si on a le messageId). Timeout 5s.
    if (_messageId) {
        fetches.push(
            _fetchTimeout(_backendUrl + '/api/email_body?messageId=' + encodeURIComponent(_messageId), null, 5000)
                .then(function(r) { return r.json(); })
                .then(function(ebody) {
                    if (done) return;
                    var full = ebody && (ebody.html_body || ebody.body);
                    // Phase 3 : propager le flag cached (true = email_cache DB hit)
                    if (full && _setMailBody(full, !!(ebody && ebody.cached))) {
                        done = true;
                        _cancelHistoryPlaceholder();  // body rapide → pas besoin de placeholder
                        // Fix 23/04 : PJ jamais rendues en standalone. La réponse
                        // /api/email_body contient déjà attachments, on les rend
                        // maintenant. Sinon l'onglet "PJ" reste vide même pour les
                        // mails avec pièces jointes.
                        if (ebody.attachments && ebody.attachments.length > 0) {
                            try { _renderAttachments(ebody.attachments); } catch(e){}
                        }
                    }
                })
                .catch(function(){ /* other path or timeout */ })
        );
    }

    // Path 2 — /api/current_mail (fallback : le backend a parfois le body). Timeout 5s.
    fetches.push(
        _fetchTimeout(_backendUrl + '/api/current_mail', null, 5000)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (done || !data || data.status !== 'ok' || !data.mail) return;
                var mail = data.mail;
                // Backend fait autorité sur les métadonnées : rafraîchit si différent
                if (mail.from_name) _fromName = mail.from_name;
                if (mail.from_email) _fromEmail = mail.from_email;
                if (mail.subject) _subject = mail.subject;
                if (mail.message_id) _messageId = mail.message_id;
                _applyMailMeta();
                if (mail.body && _setMailBody(mail.body)) {
                    done = true;
                    _cancelHistoryPlaceholder();
                }
            })
            .catch(function(){ /* other path or timeout */ })
    );

    // Quand tous les fetches sont terminés, si aucun n'a fourni de body → message d'erreur
    Promise.allSettled(fetches).then(function() {
        _cancelHistoryPlaceholder();  // fin du flow body, plus besoin du placeholder timer
        if (done) return;
        var mb = document.getElementById('mailBody');
        if (mb) mb.innerHTML = _messageId
            ? '<p style="color:#999;">Contenu du mail non disponible.</p>'
            : '<p style="color:#999;">Body en attente (cliquez le bouton BoosterMail dans Outlook).</p>';
        var bs = document.getElementById('bodySpinner');
        if (bs) bs.classList.remove('active');
    });

    // Fix 23/04 (orchestration) : _tryInstantReply differé de 50 ms au lieu
    // de 400 ms. Raison : instant_reply consulte des caches indexés par
    // message_id (draft user, preemptive, template) — indépendants du body.
    // Aucune raison d'attendre le body pour les interroger. Gain perçu ~350 ms
    // sur le moment où la réponse cache apparaît dans l'éditeur.
    // Si cache miss, _triggerAutoGenerate() attend toujours le body (timeout
    // 3 s interne) avant de lancer generateReply() Claude — robuste.
    setTimeout(_tryInstantReply, 50);

    // Résumé du mail (21/04) : fetch /api/mail_summary et peupler les
    // sections "Points principaux" + "Actions attendues" du panneau gauche.
    // Non-bloquant — se déroule en parallèle du chargement du body.
    if (_messageId) {
        _fetchMailSummary();
    }

    // Fix 26/04 (Bug A) — En mode standalone (Outlook New, le mode courant),
    // _loadMailBodyStandalone N'APPELAIT PAS _fetchSinglePreviewPlates →
    // les 3 encadrés (échéance / classement / classement PJ) restaient
    // bloqués sur "—" indéfiniment. Le fetch est dans _loadDialogBundle
    // mais celui-ci n'est jamais appelé en mode standalone.
    // Symptôme observé sur 5/5 mails testés (Ombeline, V.Hubert, V.Lecou,
    // Christelle, Jules) : tous les encadrés affichaient "—" placeholder.
    if (_messageId) {
        _fetchSinglePreviewPlates();
    }
}

/**
 * Charge le résumé IA du mail (points principaux + actions attendues).
 *
 * Pipeline audit 22/04 (Phase 1+2) :
 *   1. Fetch /api/mail_summary?wait=2 (long-poll DB 2s)
 *      → HIT cache → rendu INSTANTANÉ en un bloc
 *   2. MISS cache → fallback SSE /api/mail_summary_stream
 *      → points affichés PROGRESSIVEMENT (un par un, Haiku streaming)
 *
 * Logique utilisateur (user 22/04) :
 *   « si le body/résumé est prêt en cache, il apparait en instantané ;
 *     par contre si le résumé est rédigé en streaming : alors affichage
 *     progressif »
 */
function _fetchMailSummary() {
    var pointsBox = document.getElementById('resumePoints');
    var actionsBox = document.getElementById('resumeActionsList');
    var spinner = document.getElementById('resumeSpinner');
    var _sseSource = null;
    var _pointsUL = null;    // créé lazy à la première ligne
    var _actionsUL = null;

    function _ensurePointsUL() {
        if (_pointsUL || !pointsBox) return _pointsUL;
        var title = pointsBox.querySelector('.resume-section-title');
        pointsBox.innerHTML = '';
        if (title) pointsBox.appendChild(title);
        _pointsUL = document.createElement('ul');
        _pointsUL.style.cssText = 'margin:0;padding-left:16px;font-size:11px;line-height:1.5;';
        pointsBox.appendChild(_pointsUL);
        return _pointsUL;
    }
    function _ensureActionsUL() {
        if (_actionsUL || !actionsBox) return _actionsUL;
        actionsBox.innerHTML = '';
        _actionsUL = document.createElement('ul');
        _actionsUL.style.cssText = 'margin:0;padding-left:16px;font-size:11px;line-height:1.5;';
        actionsBox.appendChild(_actionsUL);
        return _actionsUL;
    }
    function _appendPoint(text) {
        var ul = _ensurePointsUL();
        if (!ul) return;
        var li = document.createElement('li');
        li.textContent = text;
        li.style.opacity = '0';
        li.style.transition = 'opacity 0.2s ease-in';
        ul.appendChild(li);
        requestAnimationFrame(function() { li.style.opacity = '1'; });
    }
    function _appendAction(text) {
        var ul = _ensureActionsUL();
        if (!ul) return;
        var li = document.createElement('li');
        li.textContent = text;
        li.style.opacity = '0';
        li.style.transition = 'opacity 0.2s ease-in';
        ul.appendChild(li);
        requestAnimationFrame(function() { li.style.opacity = '1'; });
    }
    function _finalize(hadPoints, hadActions) {
        if (spinner) spinner.classList.remove('active');
        if (!hadPoints && pointsBox && !pointsBox.querySelector('ul')) {
            var title = pointsBox.querySelector('.resume-section-title');
            pointsBox.innerHTML = '';
            if (title) pointsBox.appendChild(title);
            var empty = document.createElement('div');
            empty.style.cssText = 'color:#999;font-size:10px;';
            empty.textContent = _getEmptyPointsMessage();  // #16 wording contextualisé
            pointsBox.appendChild(empty);
        }
        if (!hadActions && actionsBox && !actionsBox.querySelector('ul')) {
            actionsBox.innerHTML = '';
            var emptyA = document.createElement('span');
            emptyA.style.cssText = 'color:#999;font-size:10px;';
            emptyA.textContent = 'Aucune action explicite.';
            actionsBox.appendChild(emptyA);
        }
    }

    // Rendu INSTANTANÉ (cache hit) : on affiche tous les points/actions d'un coup
    function _renderInstant(points, actions) {
        _perfMonitor.mark('T4_summary_first_point', 'cache');
        if (pointsBox) {
            var title = pointsBox.querySelector('.resume-section-title');
            pointsBox.innerHTML = '';
            if (title) pointsBox.appendChild(title);
            if (points.length === 0) {
                var empty = document.createElement('div');
                empty.style.cssText = 'color:#999;font-size:10px;';
                empty.textContent = _getEmptyPointsMessage();  // #16 wording contextualisé
                pointsBox.appendChild(empty);
            } else {
                var ul = document.createElement('ul');
                ul.style.cssText = 'margin:0;padding-left:16px;font-size:11px;line-height:1.5;';
                points.forEach(function(p) {
                    var li = document.createElement('li');
                    li.textContent = p;
                    ul.appendChild(li);
                });
                pointsBox.appendChild(ul);
            }
        }
        if (actionsBox) {
            actionsBox.innerHTML = '';
            if (actions.length === 0) {
                var emptyA = document.createElement('span');
                emptyA.style.cssText = 'color:#999;font-size:10px;';
                emptyA.textContent = 'Aucune action explicite.';
                actionsBox.appendChild(emptyA);
            } else {
                var ulA = document.createElement('ul');
                ulA.style.cssText = 'margin:0;padding-left:16px;font-size:11px;line-height:1.5;';
                actions.forEach(function(a) {
                    var li = document.createElement('li');
                    li.textContent = a;
                    ulA.appendChild(li);
                });
                actionsBox.appendChild(ulA);
            }
        }
        if (spinner) spinner.classList.remove('active');
        _perfMonitor.mark('T4_summary_done', 'cache');
    }

    // Rendu PROGRESSIF via SSE (cache miss)
    function _startSSE() {
        _perfMonitor.mark('T4_summary_source', 'stream');
        var url = _backendUrl + '/api/mail_summary_stream?message_id='
                  + encodeURIComponent(_messageId);
        try {
            _sseSource = new EventSource(url);
            // Chef sortant : EventSource enregistré → close() au beforeunload
            _registerStream(_sseSource);
        } catch (e) {
            console.warn('[dialog] EventSource indisponible :', e);
            _summaryStatus = 'error';  // #16 EventSource KO → afficher message d'erreur
            _finalize(false, false);
            return;
        }
        var hadPoints = false;
        var hadActions = false;
        _sseSource.addEventListener('point', function(ev) {
            try {
                var d = JSON.parse(ev.data);
                if (d && d.text) {
                    _appendPoint(d.text);
                    if (!hadPoints) _perfMonitor.mark('T4_summary_first_point', 'stream');
                    hadPoints = true;
                }
            } catch (e) {}
        });
        _sseSource.addEventListener('action', function(ev) {
            try {
                var d = JSON.parse(ev.data);
                if (d && d.text) { _appendAction(d.text); hadActions = true; }
            } catch (e) {}
        });
        _sseSource.addEventListener('done', function(ev) {
            try { _sseSource.close(); } catch (e) {}
            _sseSource = null;
            _summaryStatus = 'success';  // #16 stream complet (même si 0 points → mail trivial)
            _finalize(hadPoints, hadActions);
            _perfMonitor.mark('T4_summary_done', 'stream');
        });
        _sseSource.addEventListener('error', function(ev) {
            // EventSource émet 'error' aussi en cas de fin ou coupure réseau —
            // on ne ferme que si readyState = CLOSED (vraie erreur terminale)
            if (_sseSource && _sseSource.readyState === 2) {
                console.info('[dialog] mail_summary_stream : flux fermé');
                _sseSource = null;
                // #16 Si on a déjà reçu des points/actions, on ne dégrade pas le status
                if (!hadPoints && !hadActions) _summaryStatus = 'error';
                _finalize(hadPoints, hadActions);
            }
        });
    }

    // 1re tentative : cache DB long-poll (2s max côté backend)
    fetch(_backendUrl + '/api/mail_summary?message_id=' + encodeURIComponent(_messageId) + '&wait=2')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var status = (data && data.status) || 'none';
            var points = (data && data.points) || [];
            var actions = (data && data.actions) || [];
            if (status === 'done') {
                // HIT cache → instant
                _summaryStatus = 'success';  // #16 résumé reçu (même si 0 points)
                _renderInstant(points, actions);
                return;
            }
            // MISS cache → bascule SSE (résumé progressif via Haiku stream)
            console.info('[dialog] mail_summary MISS → SSE streaming');
            _startSSE();
        })
        .catch(function(e) {
            console.warn('[dialog] mail_summary erreur :', e);
            // Tentative SSE quand même (réseau peut-être revenu)
            _startSSE();
        });
}

// _checkSpeculativeCache supprime 27/04 PM (audit kit #10) — deprecated 21/04,
// remplace par _tryInstantReply() depuis 6 jours. Code mort apres `return` jamais
// execute, fonction jamais appelee dans le flow actuel.

/**
 * (B10) Fonction appelée par PyQt via page.runJavaScript() pour pré-charger les données.
 * Le dialog caché reçoit les données du mail AVANT d'être rendu visible.
 */
function _preloadMailData(data) {
    if (!data) return;

    // Stocker les données
    _fromName = data.from_name || _fromName;
    _fromEmail = data.from_email || _fromEmail;
    _subject = data.subject || _subject;
    _messageId = data.message_id || _messageId;
    _receivedBody = data.body || '';
    _mailBodyForGeneration = data.body || '';

    // Pré-remplir le panneau gauche
    document.getElementById('mailFrom').textContent = _fromName
        ? _fromName + ' <' + _fromEmail + '>'
        : _fromEmail || '—';
    document.getElementById('mailSubject').textContent = _subject || '—';

    if (_receivedBody) {
        // Fix audit 21/04 : utiliser _sanitizeHtml (5 regex) au lieu d'un
        // sanitize partiel (2 regex) qui laissait passer <iframe>, <object>,
        // <embed>, <link rel=import>. Cohérence avec _setMailBody().
        document.getElementById('mailBody').innerHTML = _sanitizeHtml(_receivedBody);
        var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');
    }

    // Pré-remplir les champs
    if (_fromEmail && _mode === 'reply') {
        document.getElementById('fieldTo').value = _fromEmail;
    }
    if (_subject) {
        var prefix = _mode === 'forward' ? 'Fw: ' : 'Re: ';
        var subjectClean = _subject.replace(/^(re\s*:|fw\s*:|fwd\s*:|tr\s*:)\s*/i, '');
        document.getElementById('fieldSubject').value = prefix + subjectClean;
    }

    _updateHeader();
    console.log('[dialog] Preload data received (' + (_receivedBody.length || 0) + ' chars body)');
}

/**
 * Envoi en mode standalone — GRAPH-FIRST routing (21/04 migration OOM).
 *
 *   1. Essai /send_reply (Mode Complet, route existante enrichie) :
 *      - Envoi HTTPS pur via Graph, aucun popup OOM Guardian
 *      - Marche sur New / Classic / Mac / Web identique
 *      - Idempotence via client_request_id (évite double envoi sur retry)
 *   2. Fallback /api/companion/inject_reply (Mode Dégradé / Graph KO) :
 *      - COM Outlook — popup OOM possible mais accepté en transitoire
 */
function _sendViaCompanion(body, to, cc, subject) {
    // UUID idempotence unique au click (crypto.randomUUID dispo Chromium récent)
    var clientReqId = '';
    try {
        clientReqId = (window.crypto && typeof window.crypto.randomUUID === 'function')
            ? window.crypto.randomUUID()
            : ('c_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10));
    } catch(_) {
        clientReqId = 'c_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10);
    }

    function _onSuccessUi(route) {
        // #11 Garde défensive : si dialog fermé entre le clic et l'arrivée Graph,
        // headerStatus et btnSend peuvent être détachés du DOM.
        var _hdr = document.getElementById('headerStatus');
        if (_hdr) _hdr.textContent =
            route === 'graph' ? 'Mail envoyé' : 'Reponse injectee dans Outlook';
        _safeSetSendBtn({ html: '&#x2705; Envoye' });
        _postSend(body, to, cc, subject);
    }

    function _onErrorUi(msg) {
        alert(msg);
        // #11 Garde défensive
        _safeSetSendBtn({ html: '&#x1f4e4; Envoyer', disabled: false });
    }

    // Cleanup 27/04 PM : _sendViaCompanionFallback supprime (companion local
    // PyQt n'existe plus en SaaS, le POST /api/companion/inject_reply
    // retournait 403 systematiquement depuis le pivot et generait une UX
    // confuse). Erreurs Graph 403/reseau remontent maintenant directement
    // a l'user via _onErrorUi avec message clair.

    // 1. Graph first via /send_reply (route existante, enrichie 21/04 avec
    //    idempotence + conversion internet_id → Graph id + attachments).
    // #10 AbortController timeout 30s — protège contre Graph qui ne répond pas.
    _fetchTimeout(_backendUrl + '/send_reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            mode: _mode,
            message_id: _messageId || '',
            body: body,
            to: to || '',
            cc: cc || '',
            subject: subject || '',
            client_request_id: clientReqId,
        })
    }, 30000)
    .then(function(r) {
        if (r.status === 403) {
            // Token Microsoft expiré ou non disponible
            // #15 bandeau in-dialog avec bouton Se reconnecter (vs alert + nav manuelle)
            _showReauthBanner('Session Microsoft expirée. Reconnectez-vous pour envoyer.');
            _safeSetSendBtn({ html: '&#x1f4e4; Envoyer', disabled: false });
            return null;
        }
        if (!r.ok) {
            return r.json().then(function(err) {
                throw new Error(err.error || err.reason || ('HTTP ' + r.status));
            });
        }
        return r.json();
    })
    .then(function(data) {
        if (!data) return;  // erreur deja affichee
        if (data.success) {
            _onSuccessUi('graph');
        } else if (data.auth_required) {
            // #15 bandeau in-dialog avec bouton Se reconnecter (au lieu de alert via _onErrorUi)
            _showReauthBanner('Session Microsoft expirée. Reconnectez-vous pour envoyer.');
            _safeSetSendBtn({ html: '&#x1f4e4; Envoyer', disabled: false });
        } else {
            _onErrorUi('Erreur envoi : ' + (data.error || data.reason || 'inconnue'));
        }
    })
    .catch(function(err) {
        // Erreur reseau ou exception JS : message clair user
        console.warn('[dialog] Envoi Graph échoué : ' + (err && err.message ? err.message : 'inconnue'));
        // #10 Détection AbortError = timeout 30s explicite
        var msg = (err && err.name === 'AbortError')
            ? 'Délai d\'envoi dépassé (30s). Réseau lent ou serveur indisponible. Réessayez.'
            : 'Erreur d\'envoi : ' + (err && err.message ? err.message : 'inconnue') + '. Verifiez votre connexion et reessayez.';
        _onErrorUi(msg);
    });
}
