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

function skipPjAnalysis() {
    _pjChoiceMade = true;
    _extractedPjContext = '';
    document.getElementById('popupPjAnalysis').classList.remove('active');
    // Continuer la génération
    generateReply();
}

function acceptPjAnalysis() {
    _pjChoiceMade = true;
    _pjSelectedIndices = [];
    document.querySelectorAll('.pj-analysis-cb:checked').forEach(function(cb) {
        _pjSelectedIndices.push(parseInt(cb.getAttribute('data-index'), 10));
    });
    document.getElementById('popupPjAnalysis').classList.remove('active');

    if (_pjSelectedIndices.length === 0) {
        // Aucune PJ sélectionnée → générer sans
        generateReply();
        return;
    }

    // Extraire le texte des PJ sélectionnées via le backend
    document.getElementById('headerStatus').textContent = 'Analyse des pieces jointes...';
    fetch(_backendUrl + '/api/extract_attachments/' + encodeURIComponent(_messageId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ indices: _pjSelectedIndices }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.text) {
            _extractedPjContext = data.text;
        }
        // Lancer la génération avec le contexte PJ
        generateReply();
    })
    .catch(function(err) {
        console.log('[dialog] Erreur extraction PJ:', err.message);
        generateReply();
    });
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

/** Rendu body (extrait de _loadMailBody pour réutilisation dans bundle) */
function _renderMailBody(data) {
    var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');
    var _bodyCached = !!(data && data.cached);
    var _mailBodyEl = document.getElementById('mailBody');
    if (data.html_body) {
        var sanitized = data.html_body
            .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
            .replace(/<iframe\b[^>]*>/gi, '<!-- blocked -->')
            .replace(/<object\b[^>]*>/gi, '<!-- blocked -->')
            .replace(/<embed\b[^>]*>/gi, '<!-- blocked -->')
            .replace(/on\w+\s*=/gi, 'data-blocked=');
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
    if (data.date || data.to) {
        var metaParts2 = [];
        if (data.to) metaParts2.push('A : ' + data.to);
        else if (_toEmail) metaParts2.push('A : ' + _toEmail);
        if (data.cc || _ccEmail) metaParts2.push('Cc : ' + (data.cc || _ccEmail));
        if (data.date) metaParts2.push(new Date(data.date).toLocaleString('fr-FR'));
        document.getElementById('mailMeta').textContent = metaParts2.join(' | ') || '—';
    }
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
        } else {
            var clsStatus = preview.classement.status;
            var clsData = preview.classement.data;
            if (clsStatus === 'running' || clsStatus === 'miss') {
                clsEl.textContent = 'Analyse en cours…';
            } else if (clsData && clsData.suggestion) {
                var sugg = clsData.suggestion;
                var folderPath = sugg.folder_path || sugg.folder_name || sugg.folder_id || 'Dossier suggéré';
                clsEl.textContent = folderPath;
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
            }
        }
    }

    // Classement PJ (Phase 2 - 24/04)
    var pjEl = document.getElementById('infoClassementPJContent');
    if (pjEl) {
        if (!preview || !preview.pj_classement) {
            pjEl.textContent = 'Néant';
        } else {
            var pjStatus = preview.pj_classement.status;
            var pjData = preview.pj_classement.data;
            if (pjStatus === 'running' || pjStatus === 'miss') {
                pjEl.textContent = 'Analyse en cours…';
            } else if (pjData && pjData.source === 'no_pj') {
                pjEl.textContent = 'Néant';  // Fix Néant (25/04) — "Pas de PJ" → "Néant" (demande user)
            } else if (pjData && pjData.suggestion) {
                var pjSugg = pjData.suggestion;
                var pjPath = pjSugg.folder_path || pjSugg.dest_folder || pjSugg.folder_name || 'Dossier suggéré';
                pjEl.textContent = pjPath;
            } else {
                pjEl.textContent = 'Néant';
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
        } else if (res.data && res.data.suggestion) {
            var sugg = res.data.suggestion;
            var folderPath = sugg.folder_path || sugg.folder_name || sugg.folder_id || 'Dossier suggéré';
            clsEl.textContent = folderPath;
        } else {
            clsEl.textContent = 'Néant';
        }
    } else if (plateName === 'pj_classement') {
        var pjEl = document.getElementById('infoClassementPJContent');
        if (!pjEl) return;
        if (res.status === 'running' || res.status === 'miss') {
            pjEl.textContent = 'Analyse en cours…';
        } else if (res.data && res.data.source === 'no_pj') {
            pjEl.textContent = 'Néant';
        } else if (res.data && res.data.suggestion) {
            var pjSugg = res.data.suggestion;
            var pjPath = pjSugg.folder_path || pjSugg.dest_folder || pjSugg.folder_name || 'Dossier suggéré';
            pjEl.textContent = pjPath;
        } else {
            pjEl.textContent = 'Néant';
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
        tagConf.textContent = 'confiance ' + p.confidence + '%';
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
            alert('Session expir\u00e9e. Reconnectez-vous via Profil > Mode Standard.');
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

function _showClassMailPopup(suggestion, folders) {
    var sugHtml = '';
    if (suggestion.suggestion && suggestion.source === 'rule') {
        var s = suggestion.suggestion;
        sugHtml = '<div class="em-folder-suggestion" onclick="_selectFolder(\'' + _escapeAttr(s.folder_id || '') + '\', this)">'
            + '&#x1f4c1; ' + _escapeHtml(s.folder_path || s.folder_id || 'Dossier suggere')
            + '</div>';
        _selectedFolderId = s.folder_id || '';
        document.getElementById('btnClassMail').disabled = false;
    } else if (suggestion.suggestion && suggestion.source === 'ai') {
        var fid = suggestion.suggestion.folder_id || '';
        sugHtml = '<div class="em-folder-suggestion" onclick="_selectFolder(\'' + _escapeAttr(fid) + '\', this)">'
            + '&#x1f4c1; Suggestion IA : ' + _escapeHtml(fid)
            + '</div>';
        _selectedFolderId = fid;
        document.getElementById('btnClassMail').disabled = false;
    }
    document.getElementById('classMailSuggestion').innerHTML = sugHtml;

    // Arborescence dossiers
    if (folders && folders.length > 0) {
        var treeHtml = '';
        folders.forEach(function(f) {
            var indent = '&nbsp;'.repeat((f.depth || 0) * 4);
            treeHtml += '<div class="em-folder-item" onclick="_selectFolder(\'' + _escapeAttr(f.id) + '\', this)">'
                + indent + _escapeHtml(f.name) + '</div>';
        });
        document.getElementById('classMailTree').innerHTML = treeHtml;
    }

    document.getElementById('popupClassMail').classList.add('active');
}

function _selectFolder(folderId, element) {
    _selectedFolderId = folderId;
    document.getElementById('btnClassMail').disabled = false;
    // Highlight
    document.querySelectorAll('.em-folder-item, .em-folder-suggestion').forEach(function(el) {
        el.classList.remove('selected');
    });
    if (element && element.classList) {
        element.classList.add('selected');
    }
}

function doClassMail() {
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

function skipClassMail() {
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

function _showClassPJPopup(pjData) {
    var listHtml = '<p style="margin-bottom:8px;">Pieces jointes a classer :</p>';
    pjData.attachments.forEach(function(att) {
        listHtml += '<div class="pj-chip" style="margin-bottom:4px;">&#x1f4c4; '
            + _escapeHtml(att.name) + '</div>';
    });
    document.getElementById('classPJList').innerHTML = listHtml;

    if (pjData.suggestion) {
        document.getElementById('classPJSuggestion').innerHTML =
            '<div class="em-folder-suggestion">&#x1f4c1; ' + _escapeHtml(pjData.suggestion.folder_path || 'Dossier suggere') + '</div>';
        document.getElementById('btnClassPJ').disabled = false;
    }

    document.getElementById('popupClassPJ').classList.add('active');
}

function doClassPJ() {
    if (!_postSendPJData) return;
    document.getElementById('btnClassPJ').disabled = true;
    document.getElementById('btnClassPJ').textContent = 'Classement...';

    var pjDestFolder = _postSendPJData.suggestion ? (_postSendPJData.suggestion.folder_path || '') : '';
    if (!pjDestFolder) {
        // Pas de dossier sélectionné → skip
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

    // Fermer si clic ailleurs — fix audit 21/04 : flag sur l'élément pour
    // éviter d'accumuler des handlers click au document (un par appel de
    // _initAutocomplete : appelé pour fieldTo + fieldCc → 2 handlers sinon).
    if (!input.__autocompleteGlobalClickBound) {
        document.addEventListener('click', function(e) {
            if (e.target !== input && !dropdown.contains(e.target)) {
                dropdown.classList.remove('active');
            }
        });
        input.__autocompleteGlobalClickBound = true;
    }
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
            // Token Microsoft expire ou non disponible
            _onErrorUi('Session Microsoft expiree. Reconnectez-vous via Profil > Mode Standard, puis reessayez.');
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
            _onErrorUi('Session expirée. Reconnectez-vous via Profil > Mode Standard.');
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
