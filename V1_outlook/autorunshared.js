/*
 * EasyMail — autorunshared.js
 * Runtime partagé (shared runtime) pour les clients modernes (VersionOverrides 1.1).
 * Gère :
 *   - Le bouton ruban / action bar (#3 / #7b) → openEasyMailDialog
 *   - L'Event-Based OnNewMessageCompose (#19) → onNewMessageComposeHandler
 *
 * Ce fichier remplace commands.js pour les clients V1_1.
 * commands.js reste en place pour le fallback V1_0 (Outlook 2019/2021).
 */

/* global Office */

var _backendUrl = 'https://localhost:3443';

/**
 * Debug log : envoie un événement au backend qui l'écrit dans boostermail.log
 * Permet de diagnostiquer le comportement de l'add-in côté serveur.
 * Silencieux en cas d'échec (ne doit jamais casser le flux).
 */
function _debugLog(eventName, details) {
    try {
        fetch(_backendUrl + '/api/debug_addin_log', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                event: eventName,
                details: details || {},
                ts: Date.now()
            }),
            keepalive: true
        }).catch(function(){});
    } catch(e) {}
}

// ============================================================================
// INITIALISATION
// ============================================================================

Office.onReady(function (info) {
    if (info.host === Office.HostType.Outlook) {
        // Enregistrer ItemChanged pour alimenter la popup PyQt en continu
        // Le shared runtime persiste — pas besoin de taskpane
        try {
            Office.context.mailbox.addHandlerAsync(
                Office.EventType.ItemChanged,
                _onItemChanged
            );
            console.log('[autorun] ItemChanged handler enregistré');
        } catch (e) {
            console.log('[autorun] ItemChanged non supporté:', e);
        }

        // Rendre le demarrage automatique permanent (jour 2+)
        try {
            if (Office.addin && Office.addin.setStartupBehavior) {
                Office.addin.setStartupBehavior(Office.StartupBehavior.load);
                console.log('[autorun] setStartupBehavior(load) — demarrage auto active');
            }
        } catch (e) {
            console.log('[autorun] setStartupBehavior non supporte:', e);
        }

        // Alimenter immédiatement avec le mail courant
        _onItemChanged();
    }
});

function _onItemChanged() {
    var item = Office.context.mailbox.item;
    if (!item) return;

    // Lecture seule (pas compose)
    if (item.subject && typeof item.subject.getAsync === 'function') return;

    var from = item.from ? item.from.emailAddress || '' : '';
    var fromName = item.from ? item.from.displayName || '' : '';
    var subject = item.subject || '';
    var hasAttachments = item.attachments ? item.attachments.length > 0 : false;
    var to = (item.to && item.to.length > 0) ? item.to.map(function(r) { return r.emailAddress; }).join(',') : '';
    var cc = (item.cc && item.cc.length > 0) ? item.cc.map(function(r) { return r.emailAddress; }).join(',') : '';

    // Construire la liste PJ
    var attachments = [];
    if (item.attachments) {
        for (var i = 0; i < item.attachments.length; i++) {
            if (!item.attachments[i].isInline) {
                attachments.push({
                    name: item.attachments[i].name || '',
                    size: item.attachments[i].size || 0
                });
            }
        }
    }

    // POST au backend → SSE → popup PyQt
    _notifyBackend('/api/event/message_read', {
        subject: subject,
        from_email: from,
        from_name: fromName,
        message_id: item.internetMessageId || '',
        conversation_id: item.conversationId || '',
        has_attachments: hasAttachments,
        attachments: attachments,
        to: to,
        cc: cc
    });
}

// ============================================================================
// HANDLER — BOUTON RUBAN / ACTION BAR (ExecuteFunction)
// ============================================================================

/**
 * Appelé par le bouton EasyMail (ruban lecture, action bar, ou ruban compose).
 * Détecte le contexte (lecture = propriétés synchrones, compose = propriétés async).
 * Lit les métadonnées du mail, notifie le backend (turbo + prefetch), puis ouvre le dialog.
 */
function openEasyMailDialog(event) {
    // Trace début : confirme que le clic arrive dans le nouveau code
    var _diag = (Office && Office.context && Office.context.mailbox && Office.context.mailbox.diagnostics) || {};
    _debugLog('button_clicked', {
        hostName: _diag.hostName || '?',
        hostVersion: _diag.hostVersion || '?',
        OWAView: _diag.OWAView || '?'
    });

    var item = Office.context.mailbox.item;

    if (!item) {
        _debugLog('button_clicked_but_no_item', {});
        event.completed();
        return;
    }

    // (P16) Détecter lecture vs compose
    var isCompose = (item.subject && typeof item.subject.getAsync === 'function');
    _debugLog('mode_detected', { isCompose: isCompose });

    if (isCompose) {
        _openDialogFromCompose(item, event);
    } else {
        _openDialogFromRead(item, event);
    }
}

/**
 * Ouvre le dialog depuis le mode LECTURE (propriétés synchrones).
 * C'est le cas le plus courant : l'utilisateur lit un mail et clique le bouton EasyMail.
 */
function _openDialogFromRead(item, event) {
    var subject = item.subject || '';
    var from = '';
    var fromName = '';
    if (item.from) {
        from = item.from.emailAddress || '';
        fromName = item.from.displayName || '';
    }
    var internetMessageId = item.internetMessageId || '';
    var conversationId = item.conversationId || '';  // (O2)
    var hasAttachments = item.attachments ? item.attachments.length > 0 : false;
    var to = '';
    if (item.to && item.to.length > 0) {
        to = item.to.map(function(r) { return r.emailAddress; }).join(',');
    }
    var cc = '';
    if (item.cc && item.cc.length > 0) {
        cc = item.cc.map(function(r) { return r.emailAddress; }).join(',');
    }

    // Notifier le backend (turbo : alimentation + auto-prefetch O8)
    _notifyBackend('/api/event/message_read', {
        subject: subject,
        from_email: from,
        from_name: fromName,
        message_id: internetMessageId,
        conversation_id: conversationId,
        has_attachments: hasAttachments,
        to: to,
        cc: cc
    });

    // IMPORTANT : displayDialogAsync DOIT être appelé dans le contexte user-gesture (le clic).
    // Tout appel async AVANT (body.getAsync, fetch...) fait perdre ce contexte → popup blocker.
    // Solution : lancer getAsync en parallèle, stocker le résultat dans _mailBody,
    // puis le lire depuis le closure APRÈS que le dialog est ouvert (setTimeout 1000ms dans
    // _buildAndOpenDialog laisse largement le temps à getAsync de finir, ~50-200ms en pratique).
    var _mailBody = '';
    item.body.getAsync(Office.CoercionType.Text, function(bodyResult) {
        if (bodyResult.status === Office.AsyncResultStatus.Succeeded) {
            _mailBody = bodyResult.value || '';
        }
        // (Mode Perf. Réduite uniquement — en Mode Standard, le body vient de Graph /api/email_body)
    });

    // Ouvrir le dialog IMMÉDIATEMENT pendant qu'on est encore dans le contexte du clic
    _buildAndOpenDialog(item, event, {
        subject: subject, from: from, fromName: fromName,
        messageId: internetMessageId, hasAttachments: hasAttachments,
        to: to, cc: cc, mode: 'reply'
    }, function() { return _mailBody; }, fromName, from);
}

/**
 * Ouvre le dialog depuis le mode COMPOSE (propriétés async via getAsync).
 * L'utilisateur a cliqué le bouton EasyMail dans le ruban du compose.
 * (P2) NE PAS utiliser body.getAsync ici — il retourne le body du compose, pas le mail reçu.
 */
function _openDialogFromCompose(item, event) {
    // IMPORTANT : même principe que _openDialogFromRead — ouvrir le dialog AVANT
    // les getAsync pour rester dans le contexte user-gesture (éviter popup blocker).
    // On ouvre avec mode=new et champs vides, puis on envoie les vraies valeurs
    // via messageChild quand TOUT est prêt (données + dialog ouvert).

    var _cd = { subject: '', to: '', cc: '', mode: 'new' };
    var _dialogRef = null;
    var _dataReady = false;

    function _trySendComposeData() {
        // N'envoie que si les deux conditions sont réunies
        if (!_dataReady || !_dialogRef) return;
        setTimeout(function() {
            try {
                _dialogRef.messageChild(JSON.stringify({
                    action: 'compose_data',
                    subject: _cd.subject,
                    to: _cd.to,
                    cc: _cd.cc,
                    mode: _cd.mode
                }));
            } catch(e) {
                console.log('EasyMail: messageChild compose_data failed', e);
            }
        }, 500);  // Laisser le temps au dialog de charger
    }

    var _pending = 3;
    function _onAsync() {
        _pending--;
        if (_pending > 0) return;

        // Déterminer le mode depuis le sujet
        var sl = _cd.subject.toLowerCase();
        if (sl.indexOf('re:') === 0 || sl.indexOf('re :') === 0) {
            _cd.mode = 'reply';
        } else if (sl.indexOf('fw:') === 0 || sl.indexOf('fwd:') === 0 ||
                   sl.indexOf('tr:') === 0 || sl.indexOf('tr :') === 0) {
            _cd.mode = 'forward';
        }

        _dataReady = true;
        _trySendComposeData();
    }

    item.subject.getAsync(function(r) {
        if (r.status === Office.AsyncResultStatus.Succeeded) _cd.subject = r.value || '';
        _onAsync();
    });
    item.to.getAsync(function(r) {
        if (r.status === Office.AsyncResultStatus.Succeeded && r.value) {
            _cd.to = r.value.map(function(rec) { return rec.emailAddress; }).join(',');
        }
        _onAsync();
    });
    item.cc.getAsync(function(r) {
        if (r.status === Office.AsyncResultStatus.Succeeded && r.value) {
            _cd.cc = r.value.map(function(rec) { return rec.emailAddress; }).join(',');
        }
        _onAsync();
    });

    // Ouvrir le dialog IMMÉDIATEMENT (contexte user-gesture) avec mode=new par défaut
    _buildAndOpenDialog(item, event, {
        subject: '', from: '', fromName: '',
        messageId: '', hasAttachments: false,
        to: '', cc: '', mode: 'new'
    }, function() { return ''; }, '', '', function(handle) {
        _dialogRef = handle;
        _trySendComposeData();
    });
}

/**
 * Construit l'URL du dialog et l'ouvre via displayDialogAsync.
 * Partagé entre _openDialogFromRead et _openDialogFromCompose.
 */
/**
 * Détecte la plateforme Outlook en cours.
 * Retourne : 'classic' | 'newOutlook' | 'web' | 'mac' | 'mobile' | 'unknown'
 *
 * Stratégie d'ouverture du dialog par plateforme :
 *  - classic    → displayDialogAsync + promptBeforeOpen:false (overlay natif, aucune popup)
 *  - newOutlook → POST localhost:5051/open_dialog_native → PyQt native (zéro popup)
 *  - web        → postMessage vers extension BoosterMail (zéro popup)
 *  - mac/mobile → fallback displayDialogAsync (meilleur effort)
 */
function _detectOutlookPlatform() {
    try {
        var diag = Office.context.mailbox && Office.context.mailbox.diagnostics;
        var host = diag ? (diag.hostName || '') : '';
        if (host === 'newOutlookWindows') return 'newOutlook';
        if (host === 'newOutlookMac') return 'newOutlook';
        if (host === 'OutlookWebApp' || host === 'OutlookWeb') return 'web';
        if (host === 'Outlook') {
            // Classic Windows desktop
            var plat = Office.context.platform;
            if (plat === Office.PlatformType.Mac) return 'mac';
            return 'classic';
        }
        if (host === 'OutlookIOS' || host === 'OutlookAndroid') return 'mobile';
        // Fallback via Office.context.platform
        if (Office.context.platform === Office.PlatformType.OfficeOnline) return 'web';
        if (Office.context.platform === Office.PlatformType.PC) return 'classic';
        return 'unknown';
    } catch (e) {
        return 'unknown';
    }
}

/**
 * Ouvre le dialog en routant vers la stratégie adaptée à la plateforme.
 * Retourne true si la stratégie plateforme-spécifique a été utilisée (New/Web),
 * false si on doit tomber sur displayDialogAsync (Classic/fallback).
 */
function _openDialogPlatformRouted(dialogUrl, data, getMailBody, fromName, fromEmail, event) {
    var platform = _detectOutlookPlatform();

    // --- New Outlook : Companion local + PyQt native ---
    // IMPORTANT : on passe par le proxy HTTPS /api/companion/open_dialog_native
    // Pas de fetch direct vers http://localhost:5051 (bloqué mixed-content HTTPS→HTTP)
    if (platform === 'newOutlook') {
        var payload = {
            mode: data.mode,
            messageId: data.messageId,
            subject: data.subject,
            fromName: data.fromName,
            fromEmail: data.from,
            from: data.from,
            to: data.to,
            cc: data.cc,
            hasAttachments: data.hasAttachments ? '1' : '0'
        };
        _debugLog('newOutlook_click', { platform: platform, payload: payload });
        // IMPORTANT : keepalive: true garantit que le fetch continue même si
        // event.completed() est appelé immédiatement après (sinon le runtime
        // ExecuteFunction se libère et annule le fetch en cours → "Failed to fetch").
        try {
            fetch(_backendUrl + '/api/companion/open_dialog_native', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
                keepalive: true
            }).then(function(r) {
                _debugLog('newOutlook_fetch_result', { status: r.status, ok: r.ok });
            }).catch(function(err) {
                _debugLog('newOutlook_fetch_error', { error: String(err) });
            });
        } catch(e) {
            _debugLog('newOutlook_fetch_exception', { error: String(e) });
        }
        // Libérer le runtime immédiatement (le Companion gère la fenêtre)
        event.completed();
        return true;
    }

    // --- Outlook Web : postMessage vers extension BoosterMail ---
    if (platform === 'web') {
        try {
            // L'extension écoute sur window.parent (ou window.top) via content-script
            var extensionPayload = {
                type: 'boostermail-open-dialog',
                version: 1,
                dialogUrl: dialogUrl,
                data: data
            };
            // postMessage sur parent ET top pour maximiser les chances (iframe imbriqué)
            try { window.parent.postMessage(extensionPayload, '*'); } catch(e){}
            try { if (window.top !== window.parent) window.top.postMessage(extensionPayload, '*'); } catch(e){}

            // Handshake : attendre un ACK de l'extension (max 500ms)
            var _ackReceived = false;
            var _ackHandler = function(ev) {
                if (ev.data && ev.data.type === 'boostermail-ack') {
                    _ackReceived = true;
                    window.removeEventListener('message', _ackHandler);
                }
            };
            window.addEventListener('message', _ackHandler);
            setTimeout(function() {
                window.removeEventListener('message', _ackHandler);
                if (!_ackReceived) {
                    console.warn('BoosterMail: extension non détectée — fallback displayDialogAsync');
                    _openViaDisplayDialog(null, dialogUrl, data, getMailBody, fromName, fromEmail, event);
                } else {
                    event.completed();
                }
            }, 500);
        } catch (e) {
            console.error('BoosterMail: postMessage extension échoué', e);
            _openViaDisplayDialog(dialogUrl, data, getMailBody, fromName, fromEmail, event);
        }
        return true;
    }

    // --- Classic ou fallback : displayDialogAsync ---
    return false;
}

function _buildAndOpenDialog(item, event, data, getMailBody, fromName, fromEmail, onDialogOpen) {
    var params = [
        'subject=' + encodeURIComponent(data.subject),
        'from=' + encodeURIComponent(data.from),
        'fromName=' + encodeURIComponent(data.fromName),
        'fromEmail=' + encodeURIComponent(data.from),
        'messageId=' + encodeURIComponent(data.messageId),
        'hasAttachments=' + (data.hasAttachments ? '1' : '0'),
        'to=' + encodeURIComponent(data.to),
        'cc=' + encodeURIComponent(data.cc),
        'mode=' + encodeURIComponent(data.mode)
    ];
    var dialogUrl = _backendUrl + '/plugin/dialog.html?' + params.join('&');

    // Routing plateforme : New Outlook → Companion PyQt, Web → extension, Classic → dialog
    if (_openDialogPlatformRouted(dialogUrl, data, getMailBody, fromName, fromEmail, event)) {
        return;
    }

    // Classic / fallback : dialog Office.js natif
    _openViaDisplayDialog(item, dialogUrl, data, getMailBody, fromName, fromEmail, event, onDialogOpen);
}

function _openViaDisplayDialog(item, dialogUrl, data, getMailBody, fromName, fromEmail, event, onDialogOpen) {
    Office.context.ui.displayDialogAsync(
        dialogUrl,
        { width: 80, height: 74, promptBeforeOpen: false },
        function (asyncResult) {
            if (asyncResult.status === Office.AsyncResultStatus.Failed) {
                console.error('EasyMail: erreur ouverture dialog', asyncResult.error.message);
                event.completed();
                return;
            }

            var dialog = asyncResult.value;

            // Callback optionnel (ex: _openDialogFromCompose pour envoyer compose_data)
            if (typeof onDialogOpen === 'function') {
                onDialogOpen(dialog);
            }

            // Envoyer le body du mail au dialog (Mode Perf. Réduite, lecture uniquement)
            // Délai 1000ms : laisse le temps au dialog de charger + à getAsync de finir
            setTimeout(function() {
                var mailBody = getMailBody();
                if (mailBody) {
                    try {
                        dialog.messageChild(JSON.stringify({
                            action: 'mail_body',
                            body: mailBody,
                            from_name: fromName,
                            from_email: fromEmail,
                        }));
                    } catch(e) {
                        console.log('EasyMail: messageChild non supporté ou dialog pas prêt');
                    }
                }
            }, 1000);

            // Écouter les messages du dialog
            dialog.addEventHandler(Office.EventType.DialogMessageReceived, function (arg) {
                try {
                    var message = JSON.parse(arg.message);
                    if (message.action === 'send_via_outlook') {
                        _sendViaOutlook(item, message);
                    }
                } catch (e) {
                    console.error('EasyMail: erreur traitement message dialog', e);
                }
            });

            // Écouter la fermeture du dialog — libérer le runtime SEULEMENT ici
            dialog.addEventHandler(Office.EventType.DialogEventReceived, function () {
                // Dialog fermé → maintenant on peut libérer le runtime
                event.completed();
            });

            // NE PAS appeler event.completed() ici — le runtime doit rester actif
            // tant que le dialog est ouvert, sinon New Outlook ferme le dialog.
        }
    );
}

// ============================================================================
// HANDLER — EVENT-BASED OnNewMessageCompose (#19)
// ============================================================================

/**
 * Déclenché automatiquement quand l'utilisateur clique Répondre / Rép. tous / Transférer.
 * Ne peut PAS appeler displayDialogAsync ni showAsTaskpane (APIs bloquées dans les event handlers Outlook).
 * Se contente de notifier le backend via POST /api/event/new_compose.
 * C'est la popup PyQt (desktop) ou l'extension #12 (Web) qui détecte le compose via SSE
 * et ouvre le dialog en QWebEngineView ou window.open.
 */
function onNewMessageComposeHandler(event) {
    var item = Office.context.mailbox.item;

    if (!item) {
        event.completed();
        return;
    }

    // Lire le sujet (compose = propriétés async via getAsync)
    item.subject.getAsync(function(subjectResult) {
        var subject = '';
        if (subjectResult.status === Office.AsyncResultStatus.Succeeded) {
            subject = subjectResult.value || '';
        }

        // Déterminer le mode depuis le sujet
        var mode = 'new';
        var subjectLower = subject.toLowerCase();
        if (subjectLower.indexOf('re:') === 0 || subjectLower.indexOf('re :') === 0) {
            mode = 'reply';
        } else if (subjectLower.indexOf('fw:') === 0 || subjectLower.indexOf('fwd:') === 0 ||
                   subjectLower.indexOf('tr:') === 0 || subjectLower.indexOf('tr :') === 0) {
            mode = 'forward';
        }

        // Notifier le backend — la popup PyQt/extension détectera le compose via SSE
        _notifyBackend('/api/event/new_compose', {
            subject: subject,
            mode: mode
        });

        event.completed();
    });
}

// ============================================================================
// MODE PERF. RÉDUITE — Envoi via Outlook natif
// ============================================================================

/**
 * Ouvre la fenêtre de réponse Outlook native avec le texte généré par EasyMail.
 */
function _sendViaOutlook(item, message) {
    var htmlBody = message.htmlBody || '';
    var mode = message.mode || 'reply';

    try {
        if (mode === 'reply') {
            item.displayReplyForm({
                htmlBody: htmlBody
            });
        } else if (mode === 'reply_all') {
            item.displayReplyAllForm({
                htmlBody: htmlBody
            });
        } else if (mode === 'forward' || mode === 'new') {
            var formData = { htmlBody: htmlBody };
            if (message.to) {
                formData.toRecipients = message.to.replace(/;/g, ',').split(',')
                    .map(function(email) { return email.trim(); })
                    .filter(function(email) { return email.length > 0; })
                    .map(function(email) { return { emailAddress: email }; });
            }
            if (message.subject) {
                formData.subject = message.subject;
            }
            if (message.cc) {
                formData.ccRecipients = message.cc.replace(/;/g, ',').split(',')
                    .map(function(email) { return email.trim(); })
                    .filter(function(email) { return email.length > 0; })
                    .map(function(email) { return { emailAddress: email }; });
            }
            Office.context.mailbox.displayNewMessageForm(formData);
        }
    } catch (e) {
        console.error('EasyMail: erreur displayReplyForm:', e.message);
    }
}

// ============================================================================
// UTILITAIRE — Notification backend (fire-and-forget)
// ============================================================================

/**
 * POST vers le backend pour alimenter la popup PyQt / extension.
 * Silencieux en cas d'erreur (le backend peut être hors ligne).
 */
function _notifyBackend(route, data) {
    try {
        fetch(_backendUrl + route, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        }).catch(function() {
            // Silencieux — le backend peut ne pas être disponible
        });
    } catch(e) {
        // fetch non disponible dans certains runtimes legacy
    }
}

// ============================================================================
// ENREGISTREMENT DES HANDLERS
// ============================================================================

if (typeof Office !== 'undefined') {
    Office.actions = Office.actions || {};
    Office.actions.associate("openEasyMailDialog", openEasyMailDialog);
    Office.actions.associate("onNewMessageComposeHandler", onNewMessageComposeHandler);
}
