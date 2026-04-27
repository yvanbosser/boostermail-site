/*
 * EasyMail — autorunshared.js
 * Runtime partagé (shared runtime) pour les clients modernes (VersionOverrides 1.1).
 * Gère :
 *   - Le bouton ruban / action bar (#3 / #7b) → openEasyMailDialog
 *   - L'Event-Based OnMessageCompose (#19) → onNewMessageComposeHandler (couvre new + reply + reply-all + forward)
 *
 * Ce fichier remplace commands.js pour les clients V1_1.
 * commands.js reste en place pour le fallback V1_0 (Outlook 2019/2021).
 */

/* global Office */

var _backendUrl = 'https://api.boostermail.ai';

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

// Marqueur de version : s'écrit dès le chargement du JS → permet de vérifier
// en lisant addin_debug.log que Outlook a bien rechargé le nouveau fichier.
var _ADDIN_VERSION = 'v10-cache-versioned-27-04';
_debugLog('js_loaded', { version: _ADDIN_VERSION });

// Safety net global (21/04 P3) : toute exception non catchée → log backend
// (non bloquant). Évite qu'une erreur silencieuse casse les handlers suivants.
if (typeof window !== 'undefined') {
    window.addEventListener('error', function(ev) {
        try {
            _debugLog('addin_js_error', {
                msg: (ev.error && ev.error.message) || ev.message || '',
                src: (ev.filename || '').split('/').pop(),
                line: ev.lineno, col: ev.colno,
            });
        } catch(_){}
    });
    window.addEventListener('unhandledrejection', function(ev) {
        try {
            _debugLog('addin_unhandled_rejection', {
                reason: String(ev.reason && ev.reason.message || ev.reason),
            });
        } catch(_){}
    });
}

// ============================================================================
// INITIALISATION
// ============================================================================

Office.onReady(function (info) {
    _debugLog('office_ready', { host: (info && info.host) || '?' });
    if (info.host === Office.HostType.Outlook) {
        // Enregistrer ItemChanged pour alimenter la popup PyQt en continu
        // Le shared runtime persiste — pas besoin de taskpane
        try {
            Office.context.mailbox.addHandlerAsync(
                Office.EventType.ItemChanged,
                _onItemChanged,
                function(result) {
                    _debugLog('item_changed_register', {
                        status: (result && result.status) || '?',
                        error: (result && result.error && result.error.message) || ''
                    });
                }
            );
        } catch (e) {
            _debugLog('item_changed_register_error', { error: String(e) });
        }

        // Rendre le demarrage automatique permanent (jour 2+)
        try {
            if (Office.addin && Office.addin.setStartupBehavior) {
                Office.addin.setStartupBehavior(Office.StartupBehavior.load);
            }
        } catch (e) {}

        // Alimenter immédiatement avec le mail courant
        _onItemChanged();
    }
});

function _onItemChanged() {
    var item = Office.context.mailbox.item;
    if (!item) {
        _debugLog('item_changed_fired_no_item', {});
        return;
    }

    // Lecture seule (pas compose)
    if (item.subject && typeof item.subject.getAsync === 'function') {
        _debugLog('item_changed_skip_compose', {});
        return;
    }

    var from = item.from ? item.from.emailAddress || '' : '';
    var fromName = item.from ? item.from.displayName || '' : '';
    var subject = item.subject || '';

    _debugLog('item_changed_fired', {
        subject: String(subject).substring(0, 60),
        from_email: from
    });
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
 *
 * Pivot SaaS 27/04/2026 — fast path newOutlook (POST companion local) supprimé.
 * Toutes les plateformes (Classic, New Outlook, Web) passent désormais par
 * displayDialogAsync via _buildAndOpenDialog. Plus de companion PyQt local
 * en SaaS → POST /api/companion/open_dialog_native retournait 503 et le
 * dialog ne s'ouvrait pas du tout sur New Outlook desktop.
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
    var _mailBody = '';
    item.body.getAsync(Office.CoercionType.Text, function(bodyResult) {
        if (bodyResult.status === Office.AsyncResultStatus.Succeeded) {
            _mailBody = bodyResult.value || '';
        }
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

        // Fix audit 21/04 : envoi répété (3 essais à 500ms, 1200ms, 2000ms)
        // car le dialog peut ne pas avoir enregistré son listener dans les
        // 500ms initiaux (Office.js dialog boot + fetches parallèles). Le
        // handler côté dialog est idempotent : il ne remplit que les champs
        // vides, donc plusieurs envois sont safe.
        var _delays = [500, 1200, 2000];
        var _payload = JSON.stringify({
            action: 'compose_data',
            subject: _cd.subject,
            to: _cd.to,
            cc: _cd.cc,
            mode: _cd.mode
        });
        _delays.forEach(function(delay) {
            setTimeout(function() {
                try {
                    if (_dialogRef) _dialogRef.messageChild(_payload);
                } catch(e) {
                    // Dialog peut être fermé entre-temps → silencieux
                }
            }, delay);
        });
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
 * Détecte la plateforme Outlook en cours.
 * Retourne : 'classic' | 'newOutlook' | 'web' | 'mac' | 'mobile' | 'unknown'
 *
 * Pivot SaaS 27/04/2026 — toutes les plateformes ouvrent désormais le dialog
 * via displayDialogAsync (plus de companion PyQt local en SaaS). La détection
 * reste utile pour télémétrie et adaptations UX futures (ex: gestion code 12011
 * spécifique Outlook Web — Phase 6).
 */
var _cachedPlatform = null;
function _detectOutlookPlatform() {
    if (_cachedPlatform !== null) return _cachedPlatform;   // Cache session (21/04 nettoyage)
    try {
        var diag = Office.context.mailbox && Office.context.mailbox.diagnostics;
        var host = diag ? (diag.hostName || '') : '';
        if (host === 'newOutlookWindows') _cachedPlatform = 'newOutlook';
        else if (host === 'newOutlookMac') _cachedPlatform = 'newOutlook';
        else if (host === 'OutlookWebApp' || host === 'OutlookWeb') _cachedPlatform = 'web';
        else if (host === 'Outlook') {
            // Classic Windows desktop
            var plat = Office.context.platform;
            _cachedPlatform = (plat === Office.PlatformType.Mac) ? 'mac' : 'classic';
        }
        else if (host === 'OutlookIOS' || host === 'OutlookAndroid') _cachedPlatform = 'mobile';
        else if (Office.context.platform === Office.PlatformType.OfficeOnline) _cachedPlatform = 'web';
        else if (Office.context.platform === Office.PlatformType.PC) _cachedPlatform = 'classic';
        else _cachedPlatform = 'unknown';
    } catch (e) {
        _cachedPlatform = 'unknown';
    }
    return _cachedPlatform;
}

/**
 * Construit l'URL du dialog et l'ouvre via displayDialogAsync.
 * Partagé entre _openDialogFromRead et _openDialogFromCompose.
 *
 * Pivot SaaS 27/04/2026 — _openDialogPlatformRouted (companion local newOutlook)
 * supprimé. Toutes les plateformes passent par _openViaDisplayDialog directement.
 */
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

    _debugLog('dialog_open_attempt', { platform: _detectOutlookPlatform() });
    _openViaDisplayDialog(item, dialogUrl, data, getMailBody, fromName, fromEmail, event, onDialogOpen);
}

function _openViaDisplayDialog(item, dialogUrl, data, getMailBody, fromName, fromEmail, event, onDialogOpen) {
    _debugLog('display_dialog_attempt', { url: dialogUrl });
    Office.context.ui.displayDialogAsync(
        dialogUrl,
        { width: 80, height: 74, promptBeforeOpen: false, displayInIframe: true },
        function (asyncResult) {
            if (asyncResult.status === Office.AsyncResultStatus.Failed) {
                _debugLog('display_dialog_error', {
                    code: asyncResult.error.code,
                    message: asyncResult.error.message
                });
                console.error('EasyMail: erreur ouverture dialog', asyncResult.error.message);
                event.completed();
                return;
            }
            _debugLog('display_dialog_ok', {});

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
