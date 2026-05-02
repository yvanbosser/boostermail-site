/*
 * EasyMail — popup.js
 * Logique de l'Etat 1 (lecture) — page DRY chargee dans 3 conteneurs.
 *
 * Conteneur TASKPANE : Office.js disponible → ItemChanged alimente le backend (source PRIMAIRE)
 * Conteneur PYQT/EXTENSION : pas d'Office.js → consomme le backend via SSE (CONSOMMATEUR)
 *
 * Ce fichier remplace taskpane.js pour l'Etat 1.
 * taskpane.js reste en place (le V1_0 l'utilise via taskpane.html iframe wrapper).
 */

/* global Office */

// Fix 30/04 PM — _backendUrl détecté dynamiquement depuis l'origin de
// la page courante. Avant : hardcodé `https://localhost:3443` qui plantait
// en SaaS (popup.html servi par api.boostermail.ai → boutons Echeances/
// Contacts/Profil naviguaient vers https://localhost:3443/plugin/echeances
// → host inexistant côté Yvan → toast Outlook "Not Found").
// Compatible local (https://localhost:3443) ET SaaS (https://api.boostermail.ai).
var _backendUrl = (window.location && window.location.origin)
    ? window.location.origin
    : 'https://localhost:3443';
var _container = 'taskpane';  // 'taskpane' | 'pyqt' | 'extension'
var _currentItem = null;
var _currentMailData = null;  // Dernières données du mail courant (pour les 3 modes)
var _sseSource = null;
var _companionAvailable = false;

// ============================================================================
// INITIALISATION
// ============================================================================

(function _init() {
    // Detecter le conteneur via query param
    var params = new URLSearchParams(window.location.search);
    _container = params.get('container') || 'taskpane';

    if (_container === 'taskpane') {
        // Mode TASKPANE : Office.js est charge → attendre Office.onReady
        // Le taskpane fonctionne TOUJOURS (avec ou sans API) car il a Office.js
        _waitForOffice();
    } else {
        // Mode PYQT ou EXTENSION : verifier si l'API est disponible AVANT d'afficher
        // Decision 09/04/2026 : si pas d'API → pas d'overlay/popup (pas un overlay qui ne fonctionne pas)
        _checkModeBeforeDisplay();
    }

    // Boutons (communs aux 3 modes) — #13 : guard null
    var _btn = function(id, fn) { var el = document.getElementById(id); if (el) el.addEventListener('click', fn); };
    _btn('btnRepondre', function () { _handleAction('reply'); });
    _btn('btnRepTous', function () { _handleAction('reply_all'); });
    _btn('btnTransferer', function () { _handleAction('forward'); });
    _btn('btnClasser', function () { alert('Classement — a implementer'); });

    // Navigation — Tableau de bord (refonte 30/04 PM tardif, signal Yvan) :
    // ouvre les 3 vues Profil/Contacts/Échéances dans une nouvelle FENÊTRE
    // browser centrée plein-écran (style proto port 5050). Avant : un
    // window.location.href in-place qui bloquait le taskpane sur la page
    // dashboard. Maintenant : window.open() avec fallback in-place si bloqué.
    function _openDashboardWindow(view) {
        var url = _backendUrl + '/plugin/' + view;
        var w = Math.min(1200, (screen.availWidth || 1200) - 80);
        var h = Math.min(800, (screen.availHeight || 800) - 80);
        var x = ((screen.availWidth || 1200) - w) / 2;
        var y = ((screen.availHeight || 800) - h) / 2;
        var feats = 'width=' + w + ',height=' + h + ',left=' + x + ',top=' + y +
                    ',resizable=yes,scrollbars=yes,toolbar=no,menubar=no,location=no';
        try {
            var nw = window.open(url, 'boostermail_dashboard_' + view, feats);
            if (nw) { nw.focus(); return; }
        } catch (e) {}
        // Fallback navigation in-place si window.open bloqué.
        window.location.href = url;
    }

    _btn('navEcheances', function () { _openDashboardWindow('echeances'); });
    _btn('navContacts', function () { _openDashboardWindow('contacts'); });
    _btn('navProfil', function () { _openDashboardWindow('profile'); });

    // Navigation FIXE en haut (Audit 20/04) — même handlers
    _btn('navEcheancesFixed', function () { _openDashboardWindow('echeances'); });
    _btn('navContactsFixed', function () { _openDashboardWindow('contacts'); });
    _btn('navProfilFixed', function () { _openDashboardWindow('profile'); });

    // Phase 02/05/2026 — placeholders pour 2 boutons à activer plus tard :
    // - navComposeFixed : raccourci composition d'un nouveau mail
    // - navHelpFixed    : assistance BoosterMail (chatbot hybride FAQ + Claude)
    _btn('navComposeFixed', function () {
        alert('✏️ Composition rapide d\'un nouveau message — bientôt disponible.');
    });
    _btn('navHelpFixed', function () {
        alert('❓ Assistance BoosterMail — bientôt disponible.\n\n' +
              'En attendant, contactez-nous : support@boostermail.ai');
    });

    // Logique ?view=X — démarrer directement sur la vue demandée si param URL.
    // Permet à dialog.html d'ouvrir popup.html?view=profil et de tomber
    // direct sur la page Profil sans passer par le menu intermédiaire.
    try {
        var _viewParam = new URLSearchParams(window.location.search).get('view');
        if (_viewParam === 'profil' || _viewParam === 'profile') {
            window.location.href = _backendUrl + '/plugin/profile';
        } else if (_viewParam === 'contacts') {
            window.location.href = _backendUrl + '/plugin/contacts';
        } else if (_viewParam === 'echeances') {
            window.location.href = _backendUrl + '/plugin/echeances';
        }
    } catch (e) { /* URLSearchParams indispo : fallback silencieux */ }

    // Afficher la nav fixe + section scrollable dès que overlay
    if (_container === 'pyqt' || _container === 'extension') {
        // Décision Yvan 01/05/2026 — overlay STRICT : header bleu + 3 boutons
        // (Échéances/Contacts/Profil) UNIQUEMENT. Tout le reste (mainContent,
        // scrollSection, emptyState, setupWizard, firstUseState, profilSection)
        // est forcé à `display:none !important` via la classe CSS
        // `mode-strict-overlay` (cf bloc CSS dans popup.html).
        // Le `!important` override les éventuels `style.display = 'block'`
        // que popup.js fait ailleurs (ex: ligne ~474 lors de la sélection
        // d'un mail). Ces accès continuent de fonctionner sans crash car les
        // éléments existent dans le DOM, juste cachés visuellement.
        document.body.classList.add('mode-strict-overlay');

        var fn = document.getElementById('fixedNav');
        if (fn) fn.style.display = 'flex';
    }

    // Test connexion backend
    _checkBackendStatus();
})();

// ============================================================================
// DETECTION MODE — Avec API / Sans API (decision 09/04/2026)
// ============================================================================

function _checkModeBeforeDisplay(attempt) {
    attempt = attempt || 1;
    var maxAttempts = 8;   // 8 × 800ms ≈ 6s de patience au démarrage Flask
    var retryDelay = 800;

    fetch(_backendUrl + '/api/status')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (!data.authenticated) {
                _checkSetup();
            } else {
                _initConsumerMode();
                _checkSetup();
            }
        })
        .catch(function() {
            if (attempt < maxAttempts) {
                console.log('[popup] Backend non disponible, retry ' + attempt + '/' + maxAttempts);
                setTimeout(function() { _checkModeBeforeDisplay(attempt + 1); }, retryDelay);
            } else {
                document.body.innerHTML =
                    '<div style="padding:20px;color:#c00;font-family:sans-serif;font-size:13px;">'
                    + 'BoosterMail : le serveur ne repond pas.<br>'
                    + 'Verifiez que start_v1.bat est lance, puis rouvrez ce panneau.'
                    + '</div>';
                console.log('[popup] Backend indisponible apres ' + maxAttempts + ' tentatives.');
            }
        });
}

// Cleanup 27/04 PM : _checkCompanionForPyQt() supprime.
// Cette fonction etait appelee dans le mode "consommateur" de la popup
// quand on n'etait pas dans une taskpane Office.js (popup PyQt locale).
// En SaaS le PyQt n'existe plus, et la fonction n'etait plus referencee
// par aucun code path actif (verifie par grep complet 27/04 PM).

// ============================================================================
// MODE TASKPANE — Office.js source PRIMAIRE (P36)
// ============================================================================

var _officeWaitCount = 0;
function _waitForOffice() {
    // Office.js peut ne pas etre encore charge (chargement async dans popup.html)
    if (typeof Office === 'undefined') {
        _officeWaitCount++;
        if (_officeWaitCount > 50) {  // 5 secondes max (50 × 100ms)
            console.log('[popup] Office.js non charge apres 5s, fallback mode consommateur');
            _initConsumerMode();
            return;
        }
        setTimeout(_waitForOffice, 100);
        return;
    }
    Office.onReady(function (info) {
        if (info.host === Office.HostType.Outlook) {
            _initTaskpaneMode();
        }
    });
}

function _initTaskpaneMode() {
    // Démarrer le poll warmup (barre de progression au lancement)
    _startWarmupProgressPoll();

    // Charger le mail courant
    _updateFromOfficeJs();

    // ItemChanged : detecte chaque changement de mail (~0ms, source PRIMAIRE)
    Office.context.mailbox.addHandlerAsync(
        Office.EventType.ItemChanged,
        function () { _updateFromOfficeJs(); }
    );

    // Verifier si le setup est termine
    _checkSetup();
}

function _updateFromOfficeJs() {
    var item = Office.context.mailbox.item;
    if (!item) {
        _showEmptyState();
        return;
    }

    _currentItem = item;

    // Lire les proprietes synchrones (mode lecture = ~0ms)
    // Construire la liste des PJ (détail nom + taille, comme taskpane.js Phase 2)
    var attachmentsList = [];
    if (item.attachments) {
        for (var i = 0; i < item.attachments.length; i++) {
            if (!item.attachments[i].isInline) {
                attachmentsList.push({
                    name: item.attachments[i].name || '',
                    size: item.attachments[i].size || 0
                });
            }
        }
    }

    var mailData = {
        subject: item.subject || '',
        from_email: (item.from ? item.from.emailAddress : '') || '',
        from_name: (item.from ? item.from.displayName : '') || '',
        message_id: item.internetMessageId || '',
        conversation_id: item.conversationId || '',  // (O2)
        has_attachments: attachmentsList.length > 0,
        attachments: attachmentsList,
        to: (item.to && item.to.length > 0) ? item.to.map(function(r) { return r.emailAddress; }).join(',') : '',
        cc: (item.cc && item.cc.length > 0) ? item.cc.map(function(r) { return r.emailAddress; }).join(',') : '',
    };

    // Lire le body (async, ~50ms) puis POST au backend
    item.body.getAsync(Office.CoercionType.Text, function(bodyResult) {
        if (bodyResult.status === Office.AsyncResultStatus.Succeeded) {
            mailData.body = bodyResult.value || '';
        }

        // POST au backend (turbo : alimentation + auto-prefetch O8)
        _notifyBackend('/api/event/message_read', mailData);

        // Mettre a jour l'affichage local
        _currentMailData = mailData;
        _showMailContent(mailData);
    });

    // InsightMessage (bandeau natif Outlook, Classic uniquement)
    _addInsightMessage(item);
}

// ============================================================================
// MODE CONSOMMATEUR — SSE temps reel (O3)
// ============================================================================

function _initConsumerMode() {
    // Démarrer le poll warmup (barre de progression au lancement)
    _startWarmupProgressPoll();

    // Ouvrir SSE pour recevoir les events en temps reel
    _connectSSE();

    // Charger les donnees initiales depuis le backend
    _fetchCurrentMail();
}

function _connectSSE() {
    // Fix audit ULTRA 29/04 PM tardif (A2) : fermer l'ancien EventSource
    // avant d'en ouvrir un nouveau. Sans ça, plusieurs callbacks s'accumulaient
    // en cas d'appel multiple (polling fallback ou reconnect manuel) → updates
    // UI dupliquées + double consommation TCP socket OVH.
    if (_sseSource) {
        try { _sseSource.close(); } catch (e) {}
        _sseSource = null;
    }
    try {
        _sseSource = new EventSource(_backendUrl + '/api/events/stream');

        _sseSource.addEventListener('mail_changed', function (e) {
            try {
                var data = JSON.parse(e.data);
                _currentMailData = data;
                _showMailContent(data);
            } catch (err) { console.log('[popup] SSE mail_changed parse error:', err); }
        });

        _sseSource.addEventListener('compose_detected', function (e) {
            try {
                var data = JSON.parse(e.data);
                _onComposeDetected(data);
            } catch (err) { console.log('[popup] SSE compose_detected parse error:', err); }
        });

        _sseSource.addEventListener('prefetch_progress', function (e) {
            try {
                var data = JSON.parse(e.data);
                _updatePrefetchBar(data);
            } catch (err) { console.log('[popup] SSE prefetch_progress parse error:', err); }
        });

        var _sseErrorCount = 0;
        _sseSource.onerror = function () {
            _sseErrorCount++;
            // Laisser EventSource retenter 3 fois avant de basculer en polling
            if (_sseErrorCount >= 3) {
                console.log('[popup] SSE 3 erreurs consecutives, fallback polling');
                if (_sseSource) {
                    _sseSource.close();
                    _sseSource = null;
                }
                _startPolling();
            } else {
                console.log('[popup] SSE erreur ' + _sseErrorCount + '/3, EventSource retente auto');
            }
        };
        // Reset le compteur d'erreurs quand un message arrive
        _sseSource.onmessage = function () { _sseErrorCount = 0; };

    } catch (e) {
        // SSE non supporte — fallback polling
        _startPolling();
    }
}

function _fetchCurrentMail() {
    fetch(_backendUrl + '/api/current_mail')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data.status === 'ok' && data.mail) {
                _currentMailData = data.mail;
                _showMailContent(data.mail);
            }
        })
        .catch(function () {});
}

// Fallback polling si SSE indisponible
var _pollingInterval = null;

function _startPolling() {
    if (_pollingInterval) return;
    _pollingInterval = setInterval(function () {
        _fetchCurrentMail();
        // Verifier aussi le compose
        fetch(_backendUrl + '/api/current_compose')
            .then(function (r) { return r.json(); })
            .then(function (data) {
                if (data.status === 'ok' && data.compose) {
                    _onComposeDetected(data.compose);
                }
            })
            .catch(function () {});
    }, 1000);
}

// ============================================================================
// COMPOSE DETECTE — signaler au conteneur d'ouvrir le dialog
// ============================================================================

var _lastComposeTimestamp = 0;

function _onComposeDetected(composeData) {
    // Eviter les doublons (meme compose detecte plusieurs fois)
    var ts = composeData.timestamp || 0;
    if (ts <= _lastComposeTimestamp) return;
    _lastComposeTimestamp = ts;

    if (_container === 'pyqt') {
        // Signaler au conteneur PyQt via postMessage ou URL scheme
        // Le PyQt ecoute via QWebChannel ou intercepte les navigations
        try {
            window.location.href = 'easymail://compose/' + encodeURIComponent(composeData.mode || 'reply');
        } catch (e) {}
    } else if (_container === 'extension') {
        // Signaler a l'extension via postMessage vers le parent (content script)
        try {
            window.parent.postMessage({
                type: 'easymail_compose',
                mode: composeData.mode || 'reply'
            }, '*');
        } catch (e) {}
    }
    // En taskpane, le compose est gere par le bouton ruban compose (P4)
}

// ============================================================================
// ACTIONS — ouvrir le dialog (adapte au conteneur)
// ============================================================================

function _handleAction(mode) {
    if (_container === 'taskpane') {
        if (!_currentItem) {
            // (B42) Feedback si aucun mail selectionne
            alert('Selectionnez un mail avant de repondre.');
            return;
        }
        // Mode taskpane : ouvrir via Office.js displayDialogAsync
        _openDialogOfficeJs(mode);
    } else if (_container === 'pyqt') {
        // Mode PyQt : signaler au conteneur d'ouvrir le QWebEngineView dialog
        try {
            window.location.href = 'easymail://open-dialog/' + encodeURIComponent(mode);
        } catch (e) {}
    } else if (_container === 'extension') {
        // Mode extension : window.open le dialog standalone
        window.open(
            _backendUrl + '/plugin/dialog.html?standalone=1&mode=' + encodeURIComponent(mode),
            'easymail_dialog',
            'width=1200,height=800'
        );
    }
}

function _openDialogOfficeJs(mode) {
    var item = _currentItem;
    if (!item) return;

    var subject = item.subject || '';
    var fromEmail = item.from ? item.from.emailAddress : '';
    var fromName = item.from ? item.from.displayName : '';
    var messageId = item.internetMessageId || '';
    var hasAttachments = (item.attachments && item.attachments.length > 0) ? '1' : '0';
    var to = (item.to && item.to.length > 0) ? item.to.map(function (r) { return r.emailAddress; }).join(',') : '';
    var cc = (item.cc && item.cc.length > 0) ? item.cc.map(function (r) { return r.emailAddress; }).join(',') : '';

    var dialogUrl = _backendUrl + '/plugin/dialog.html'
        + '?mode=' + encodeURIComponent(mode)
        + '&subject=' + encodeURIComponent(subject)
        + '&from=' + encodeURIComponent(fromEmail)
        + '&fromName=' + encodeURIComponent(fromName)
        + '&messageId=' + encodeURIComponent(messageId)
        + '&hasAttachments=' + hasAttachments
        + '&to=' + encodeURIComponent(to)
        + '&cc=' + encodeURIComponent(cc);

    Office.context.ui.displayDialogAsync(dialogUrl, { width: 80, height: 74, promptBeforeOpen: false }, function (asyncResult) {
        if (asyncResult.status === Office.AsyncResultStatus.Failed) return;

        var dialog = asyncResult.value;

        // Envoyer le body au dialog (Mode Perf. Reduite)
        item.body.getAsync(Office.CoercionType.Text, function(bodyResult) {
            if (bodyResult.status === Office.AsyncResultStatus.Succeeded && bodyResult.value) {
                setTimeout(function() {
                    try {
                        dialog.messageChild(JSON.stringify({
                            action: 'mail_body', body: bodyResult.value,
                            from_name: fromName, from_email: fromEmail,
                        }));
                    } catch(e) {}
                }, 1000);
            }
        });

        dialog.addEventHandler(Office.EventType.DialogMessageReceived, function (arg) {
            try {
                var msg = JSON.parse(arg.message);
                if (msg.action === 'send_via_outlook') _sendViaOutlook(msg);
            } catch (e) {}
        });
    });
}

// ============================================================================
// AFFICHAGE — mail courant (commun aux 3 modes)
// ============================================================================

function _showEmptyState() {
    document.getElementById('emptyState').style.display = 'flex';
    document.getElementById('mailContent').style.display = 'none';
    document.getElementById('profilSection').style.display = 'none';
    document.getElementById('setupWizard').style.display = 'none';
}

function _showMailContent(data) {
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('profilSection').style.display = 'none';
    document.getElementById('setupWizard').style.display = 'none';
    document.getElementById('mailContent').style.display = 'flex';

    var fromName = data.from_name || '';
    var fromEmail = data.from_email || '';

    // Contact
    document.getElementById('contactAvatar').textContent = _getInitials(fromName);
    document.getElementById('contactName').textContent = fromName || fromEmail || '—';
    document.getElementById('contactOrg').textContent = '';
    document.getElementById('contactTags').innerHTML = '';

    // PJ — détail si disponible (mode taskpane), résumé sinon (mode consommateur)
    var pjSection = document.getElementById('pjSection');
    var attachments = data.attachments || [];
    if (attachments.length > 0) {
        pjSection.style.display = 'block';
        var html = '';
        for (var i = 0; i < attachments.length; i++) {
            var att = attachments[i];
            var size = att.size ? _formatSize(att.size) : '';
            html += '<div class="tp-pj-item">'
                + '<span class="tp-pj-icon">&#x1f4c4;</span>'
                + _escapeHtml(att.name)
                + (size ? '<span class="tp-pj-size">' + size + '</span>' : '')
                + '</div>';
        }
        html += '<div style="font-size:8px;color:#e65100;margin-top:2px;">&#x1f50d; ' + attachments.length + ' PJ analysable' + (attachments.length > 1 ? 's' : '') + '</div>';
        document.getElementById('pjList').innerHTML = html;
    } else if (data.has_attachments) {
        pjSection.style.display = 'block';
        document.getElementById('pjList').innerHTML = '<div class="tp-pj-item"><span class="tp-pj-icon">&#x1f4c4;</span> PJ disponibles</div>';
    } else {
        pjSection.style.display = 'none';
    }

    // Echeance + classement : seront charges plus tard
    document.getElementById('echSection').style.display = 'none';
    document.getElementById('clsSection').style.display = 'none';

    // Profil contact depuis le backend
    if (fromEmail) {
        _loadContactProfile(fromEmail);
    }
}

function _updatePrefetchBar(data) {
    var bar = document.getElementById('prefetchBar');
    if (data.status === 'done') {
        bar.textContent = 'Contexte charge : A=' + data.a + ' B=' + data.b + ' C=' + data.c;
        bar.className = 'tp-prefetch active';
        setTimeout(function () { bar.className = 'tp-prefetch'; }, 3000);
    } else {
        bar.textContent = 'Chargement contexte... A=' + (data.a || 0) + ' B=' + (data.b || 0) + ' C=' + (data.c || 0);
        bar.className = 'tp-prefetch active';
    }
}

// ============================================================================
// WARMUP PROGRESS — poll /api/warmup_inbox/progress au démarrage
// ============================================================================

var _warmupPollTimer = null;

function _startWarmupProgressPoll() {
    var bar = document.getElementById('prefetchBar');
    if (!bar) return;

    bar.textContent = 'Demarrage BoosterMail...';
    bar.className = 'tp-prefetch active';

    var maxPolls = 120;   // 120 × 1s = 2min max
    var pollCount = 0;

    function _poll() {
        pollCount++;
        if (pollCount > maxPolls) {
            bar.className = 'tp-prefetch';
            return;
        }
        fetch(_backendUrl + '/api/warmup_inbox/progress')
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.status === 'done') {
                    bar.textContent = 'BoosterMail pret';
                    bar.className = 'tp-prefetch active';
                    setTimeout(function() { bar.className = 'tp-prefetch'; }, 2000);
                    _warmupPollTimer = null;
                } else if (data.status === 'error') {
                    bar.textContent = 'Warmup echoue — reconnexion dans 60s';
                    bar.className = 'tp-prefetch active';
                    setTimeout(function() { bar.className = 'tp-prefetch'; }, 5000);
                    _warmupPollTimer = null;
                } else if (data.status === 'running') {
                    var total = data.total || '?';
                    var loaded = data.loaded || 0;
                    var subj = data.current_subject ? (' — ' + data.current_subject.substring(0, 30)) : '';
                    bar.textContent = 'Chargement ' + loaded + '/' + total + subj;
                    bar.className = 'tp-prefetch active';
                    _warmupPollTimer = setTimeout(_poll, 800);
                } else {
                    // status idle ou inconnu — réessayer plus lentement
                    _warmupPollTimer = setTimeout(_poll, 1500);
                }
            })
            .catch(function() {
                // Backend pas encore prêt — réessayer
                _warmupPollTimer = setTimeout(_poll, 1500);
            });
    }

    _poll();
}

// ============================================================================
// INSIGHT MESSAGE (taskpane uniquement)
// ============================================================================

function _addInsightMessage(item) {
    if (_container !== 'taskpane') return;
    try {
        var attachmentCount = 0;
        if (item.attachments) {
            for (var i = 0; i < item.attachments.length; i++) {
                if (!item.attachments[i].isInline) attachmentCount++;
            }
        }
        var message = 'BoosterMail : mail de ' + (item.from ? item.from.displayName : 'inconnu');
        if (attachmentCount > 0) {
            message += ', ' + attachmentCount + ' PJ';
        }
        item.notificationMessages.replaceAsync('easymail_insight', {
            type: Office.MailboxEnums.ItemNotificationMessageType.InsightMessage,
            message: message,
            icon: 'icon16',
            actions: [{
                actionType: Office.MailboxEnums.ActionType.ShowTaskPane,
                actionText: 'Ouvrir BoosterMail',
                commandId: 'easymailTaskpaneItem'
            }]
        }, function () {});
    } catch (e) {}
}

// ============================================================================
// MODE PERF. REDUITE : envoyer via Outlook natif (taskpane uniquement)
// ============================================================================

function _sendViaOutlook(msg) {
    if (_container !== 'taskpane' || !_currentItem) return;
    var item = _currentItem;
    var htmlBody = msg.htmlBody || '';
    var mode = msg.mode || 'reply';

    try {
        if (mode === 'reply') {
            item.displayReplyForm({ htmlBody: htmlBody });
        } else if (mode === 'reply_all') {
            item.displayReplyAllForm({ htmlBody: htmlBody });
        } else if (mode === 'forward' || mode === 'new') {
            var formData = { htmlBody: htmlBody };
            if (msg.to) {
                formData.toRecipients = msg.to.replace(/;/g, ',').split(',')
                    .map(function (e) { return e.trim(); })
                    .filter(function (e) { return e.length > 0; })
                    .map(function (e) { return { emailAddress: e }; });
            }
            if (msg.subject) formData.subject = msg.subject;
            if (msg.cc) {
                formData.ccRecipients = msg.cc.replace(/;/g, ',').split(',')
                    .map(function (e) { return e.trim(); })
                    .filter(function (e) { return e.length > 0; })
                    .map(function (e) { return { emailAddress: e }; });
            }
            Office.context.mailbox.displayNewMessageForm(formData);
        }
    } catch (e) {
        console.error('EasyMail: erreur displayReplyForm:', e.message);
    }
}

// ============================================================================
// BACKEND — statut + profil contact
// ============================================================================

function _checkBackendStatus() {
    fetch(_backendUrl + '/api/status')
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var badge = document.getElementById('statusBadge');
            if (data && data.status === 'ok') {
                badge.className = 'tp-status ok';
                badge.textContent = 'connecte';
            }
        })
        .catch(function () {
            var badge = document.getElementById('statusBadge');
            badge.className = 'tp-status error';
            badge.textContent = 'hors ligne';
        });
}

function _loadContactProfile(email) {
    fetch(_backendUrl + '/api/contact_profile/' + encodeURIComponent(email))
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data && data.profile) {
                var p = data.profile;
                document.getElementById('contactOrg').textContent = p.organization || '';
                var tagsHtml = '';
                if (p.register) tagsHtml += '<span class="tp-tag green">&#x2713; ' + _escapeHtml(p.register) + '</span>';
                if (p.category) tagsHtml += '<span class="tp-tag orange">' + _escapeHtml(p.category) + '</span>';
                document.getElementById('contactTags').innerHTML = tagsHtml;
            }
        })
        .catch(function () {});
}

function _notifyBackend(route, data) {
    try {
        fetch(_backendUrl + route, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).catch(function () {});
    } catch (e) {}
}

// ============================================================================
// UTILITAIRES
// ============================================================================

function _getInitials(name) {
    if (!name) return '?';
    var parts = name.trim().split(/\s+/);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return name[0].toUpperCase();
}

function _formatSize(bytes) {
    if (bytes < 1024) return bytes + ' o';
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' Ko';
    return (bytes / (1024 * 1024)).toFixed(1) + ' Mo';
}

function _escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

// ============================================================================
// PROFIL (meme logique que taskpane.js)
// ============================================================================

function _showProfilSection() {
    document.getElementById('mailContent').style.display = 'none';
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('profilSection').style.display = 'block';
    _loadProfilData();
}

function _loadProfilData() {
    fetch(_backendUrl + '/api/status')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            var modeDiv = document.getElementById('profilMode');
            var btnActivate = document.getElementById('btnActiverStandard');
            if (data.mode === 'standard' && data.authenticated) {
                modeDiv.innerHTML = '&#x2705; Mode Standard (actif)';
                btnActivate.style.display = 'none';
            } else {
                modeDiv.innerHTML = '&#x26a0; Mode Performance Reduite';
                btnActivate.style.display = 'block';
                btnActivate.onclick = function() {
                    window.open(_backendUrl + '/auth/login', '_blank');
                };
            }
        })
        .catch(function() {
            document.getElementById('profilMode').innerHTML = 'Erreur de connexion';
        });

    fetch(_backendUrl + '/api/ai_model')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.model) {
                var radios = document.querySelectorAll('input[name="aiModel"]');
                radios.forEach(function(radio) { radio.checked = (radio.value === data.model); });
            }
        })
        .catch(function() {});

    fetch(_backendUrl + '/api/settings/user_name')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.value) document.getElementById('profilUserName').value = data.value;
        })
        .catch(function() {});

    // Listeners pour sauvegarder les changements
    document.querySelectorAll('input[name="aiModel"]').forEach(function(radio) {
        radio.onchange = function() {
            fetch(_backendUrl + '/api/ai_model', {
                method: 'POST', headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({model: radio.value}),
            }).catch(function() {});
        };
    });

    document.getElementById('profilUserName').onblur = function() {
        fetch(_backendUrl + '/api/save_setting', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({key: 'user_name', value: this.value.trim()}),
        }).catch(function() {});
    };
}

// ============================================================================
// SETUP WIZARD (meme logique que taskpane.js, taskpane uniquement)
// ============================================================================

// ============================================================================
// DETECTION PLATEFORME
// ============================================================================

var _detectedPlatform = 'unknown'; // 'new_outlook' | 'classic_outlook' | 'web' | 'unknown'

function _detectPlatform() {
    if (_container === 'extension') {
        _detectedPlatform = 'web';
    } else if (_container === 'pyqt') {
        // Demander au backend quelle plateforme (il detecte via le processus)
        try {
            var xhr = new XMLHttpRequest();
            xhr.open('GET', _backendUrl + '/api/detected_platform', false); // synchrone
            xhr.send();
            if (xhr.status === 200) {
                var data = JSON.parse(xhr.responseText);
                _detectedPlatform = data.platform || 'unknown';
            }
        } catch (e) {
            _detectedPlatform = 'unknown';
        }
    } else {
        // Fallback
        _detectedPlatform = 'new_outlook';
    }
    // Afficher dans le setup
    var info = document.getElementById('setupPlatformInfo');
    if (info) {
        var labels = {
            'new_outlook': 'New Outlook detecte',
            'classic_outlook': 'Outlook Classic detecte',
            'web': 'Outlook Web detecte',
            'unknown': ''
        };
        info.textContent = labels[_detectedPlatform] || '';
    }
}

function _getButtonInstruction() {
    switch (_detectedPlatform) {
        case 'new_outlook':
            return 'Dans New Outlook, ouvrez un mail puis cliquez sur le bouton <strong>BoosterMail</strong> (icone &#x2709;) dans la barre d\'outils en haut du mail, a cote des boutons Repondre/Transferer.';
        case 'classic_outlook':
            return 'Dans Outlook, cliquez sur le bouton <strong>BoosterMail</strong> (icone &#x2709;) dans le <strong>ruban</strong>, onglet <strong>Accueil</strong>, groupe <strong>BoosterMail</strong> a droite.';
        case 'web':
            return 'L\'extension Chrome est deja active. Aucune action supplementaire necessaire.';
        default:
            return 'Cliquez sur le bouton <strong>BoosterMail</strong> dans la barre d\'outils d\'Outlook.';
    }
}


// ============================================================================
// ONBOARDING (3 etapes : Auth → Style → Bouton)
// ============================================================================

function _checkSetup() {
    _detectPlatform();

    fetch(_backendUrl + '/api/setup/status')
        .then(function(r) { if (!r.ok) throw new Error(); return r.json(); })
        .then(function(data) {
            if (data.step === 'done') {
                // Setup termine — verifier si etape 3 (bouton) a ete faite
                if (!data.button_activated && _container !== 'extension') {
                    _showFirstUseState();
                }
                return;
            }
            _showSetupWizard(data.step || 'auth');
        })
        .catch(function() {
            // Pas de route setup → verifier juste l'auth
            fetch(_backendUrl + '/api/status')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data.authenticated) {
                        _showSetupWizard('auth');
                    }
                })
                .catch(function() {});
        });
}

function _showSetupWizard(step) {
    document.getElementById('emptyState').style.display = 'none';
    var fu = document.getElementById('firstUseState');
    if (fu) fu.style.display = 'none';
    document.getElementById('mailContent').style.display = 'none';
    document.getElementById('setupWizard').style.display = 'block';

    ['setupStepAuth', 'setupStepStyle', 'setupStepButton', 'setupDone'].forEach(function(id) {
        var el = document.getElementById(id);
        if (el) el.style.display = 'none';
    });

    if (step === 'auth') {
        document.getElementById('setupStepAuth').style.display = 'block';
        document.getElementById('setupBtnAuth').onclick = function() {
            document.getElementById('setupAuthWaiting').style.display = 'block';
            document.getElementById('setupBtnAuth').style.display = 'none';
            window.open(_backendUrl + '/auth/login', '_blank');
            // Polling pour detecter quand l'auth est faite
            _pollAuth();
        };
    } else if (step === 'style') {
        document.getElementById('setupStepStyle').style.display = 'block';
        document.getElementById('setupStartOnboarding').onclick = function() {
            document.getElementById('setupStartOnboarding').style.display = 'none';
            document.getElementById('onboardingProgress').style.display = 'block';
            fetch(_backendUrl + '/api/setup/onboarding', {method: 'POST', headers: {'Content-Type': 'application/json'}})
                .then(function() { _pollOnboarding(); });
        };
    } else if (step === 'button') {
        document.getElementById('setupStepButton').style.display = 'block';
        document.getElementById('setupButtonInstruction').innerHTML = _getButtonInstruction();
        if (_detectedPlatform === 'web') {
            // Pas de bouton a activer sur Web → skip automatique
            setTimeout(function() { _showSetupWizard('done'); }, 1500);
            return;
        }
        document.getElementById('setupSkipButton').onclick = function() {
            _setupPost('button', {skipped: true}, 'done');
        };
        // Polling pour detecter si le bouton a ete clique (le backend recoit un event)
        _pollButtonActivation();
    } else if (step === 'done') {
        document.getElementById('setupDone').style.display = 'block';
        _setupPost('done', {}, null);
        setTimeout(function() {
            document.getElementById('setupWizard').style.display = 'none';
            document.getElementById('emptyState').style.display = 'block';
            _initConsumerMode();
        }, 2500);
    }
}

function _pollAuth() {
    fetch(_backendUrl + '/api/status')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.authenticated) {
                document.getElementById('setupAuthWaiting').style.display = 'none';
                document.getElementById('setupAuthDone').style.display = 'block';
                _setupPost('auth', {}, null);
                setTimeout(function() { _showSetupWizard('style'); }, 1500);
            } else {
                setTimeout(_pollAuth, 2000);
            }
        })
        .catch(function() { setTimeout(_pollAuth, 3000); });
}

function _pollButtonActivation() {
    // Le backend sait si un event message_read a ete recu (= bouton clique)
    fetch(_backendUrl + '/api/current_mail')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.status === 'ok' && data.mail && data.mail.from_email) {
                // Le bouton a ete clique → event recu
                _setupPost('button', {activated: true}, null);
                _showSetupWizard('done');
            } else {
                setTimeout(_pollButtonActivation, 2000);
            }
        })
        .catch(function() { setTimeout(_pollButtonActivation, 3000); });
}

function _showFirstUseState() {
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('setupWizard').style.display = 'none';
    var fu = document.getElementById('firstUseState');
    if (fu) {
        document.getElementById('firstUseInstruction').innerHTML = _getButtonInstruction();
        fu.style.display = 'block';
        // Polling pour detecter l'activation
        _pollButtonActivation();
    }
}

function _setupPost(step, data, nextStep) {
    fetch(_backendUrl + '/api/setup/complete', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({step: step, data: data || {}}),
    })
    .then(function(r) { if (!r.ok) throw new Error(); })
    .then(function() { _showSetupWizard(nextStep); })
    .catch(function() { _showSetupWizard(nextStep); });
}

var _onboardingPollStart = 0;

function _pollOnboarding() {
    if (!_onboardingPollStart) _onboardingPollStart = Date.now();
    if (Date.now() - _onboardingPollStart > 10 * 60 * 1000) {
        document.getElementById('onboardingText').textContent = 'Timeout.';
        setTimeout(function() { _showSetupWizard('done'); }, 2000);
        return;
    }
    fetch(_backendUrl + '/api/setup/onboarding/status')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.status === 'running') {
                var pct = data.total > 0 ? Math.round((data.indexed / data.total) * 100) : 0;
                document.getElementById('onboardingBar').style.width = pct + '%';
                document.getElementById('onboardingText').textContent = data.indexed + '/' + data.total + ' mails indexes';
                setTimeout(_pollOnboarding, 1000);
            } else if (data.status === 'done') {
                document.getElementById('onboardingBar').style.width = '100%';
                document.getElementById('onboardingText').textContent = 'Analyse terminee !';
                setTimeout(function() { _showSetupWizard('done'); }, 1500);
            } else {
                document.getElementById('onboardingText').textContent = 'Erreur : ' + (data.status || 'inconnue');
                setTimeout(function() { _showSetupWizard('done'); }, 2000);
            }
        })
        .catch(function() { setTimeout(_pollOnboarding, 2000); });
}


// =============================================================================
// DRAG overlay — fix audit 22/04
// =============================================================================
// Le Qt handler (_on_easymail_action) gere deja drag-start / drag-move / drag-end
// mais aucun code JS ne les emettait. Cablage mousedown sur header + mousemove
// global. Throttle 16ms (~60fps) pour ne pas spam QWebEngine.
(function _setupOverlayDrag() {
    var header = document.querySelector('.tp-header');
    if (!header) return;

    // CSS : curseur move + pas de selection texte pendant drag
    header.style.userSelect = 'none';
    header.style.cursor = 'move';

    var dragging = false;
    var lastMove = 0;

    // Exclure les boutons du header (reduire, fermer) du drag
    function isDragTarget(el) {
        while (el && el !== header) {
            if (el.classList && el.classList.contains('tp-header-nav-btn')) {
                return false;
            }
            el = el.parentElement;
        }
        return true;
    }

    // Navigation vers easymail:// via un IFRAME hidden pour ne pas perturber
    // la page principale (window.location.href changerait de page dans certains
    // moteurs, meme si Qt intercepte en theorie).
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

    header.addEventListener('mousedown', function(e) {
        if (e.button !== 0) return;          // uniquement click gauche
        if (!isDragTarget(e.target)) return; // boutons exclus
        e.preventDefault();
        dragging = true;
        _nav('drag-start', e.screenX, e.screenY);
    });

    document.addEventListener('mousemove', function(e) {
        if (!dragging) return;
        var now = Date.now();
        if (now - lastMove < 16) return;  // throttle ~60 fps max
        lastMove = now;
        _nav('drag-move', e.screenX, e.screenY);
    });

    document.addEventListener('mouseup', function() {
        if (!dragging) return;
        dragging = false;
        _nav('drag-end');
    });

    // Safety : si la souris quitte la fenetre pendant drag
    document.addEventListener('mouseleave', function() {
        if (dragging) {
            dragging = false;
            _nav('drag-end');
        }
    });

    // Audit Pass 8 — cleanup au unmount popup : clearInterval polling +
    // close SSE pour éviter requêtes fantômes après fermeture (especially
    // multi-open/close avec WebView2 qui garde la page en cache).
    window.addEventListener('beforeunload', function() {
        try {
            if (_pollingInterval) {
                clearInterval(_pollingInterval);
                _pollingInterval = null;
            }
        } catch(e) {}
        try {
            if (_sseSource && _sseSource.readyState !== 2) {
                _sseSource.close();
            }
        } catch(e) {}
    });
})();
