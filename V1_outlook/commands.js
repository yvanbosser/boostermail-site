/*
 * EasyMail — commands.js
 * Handler du bouton ruban Outlook.
 * Lit le mail ouvert via Office.js, puis ouvre le dialog.
 */

/* global Office */

Office.onReady(function (info) {
    if (info.host === Office.HostType.Outlook) {
        // Prêt — le bouton ruban peut appeler openEasyMailDialog
    }
});

/**
 * Appelé par le bouton EasyMail dans le ruban (ExecuteFunction).
 * Lit les métadonnées du mail ouvert, puis ouvre le dialog avec ces données en URL params.
 */
function openEasyMailDialog(event) {
    var item = Office.context.mailbox.item;

    if (!item) {
        event.completed();
        return;
    }

    // Récupérer les données du mail ouvert
    var subject = item.subject || '';
    var from = '';
    if (item.from) {
        from = item.from.emailAddress || '';
    }
    var internetMessageId = item.internetMessageId || '';
    var hasAttachments = item.attachments ? item.attachments.length > 0 : false;
    var to = '';
    if (item.to && item.to.length > 0) {
        to = item.to.map(function(r) { return r.emailAddress; }).join(',');
    }
    var cc = '';
    if (item.cc && item.cc.length > 0) {
        cc = item.cc.map(function(r) { return r.emailAddress; }).join(',');
    }

    // Construire l'URL du dialog avec les données en query params
    var baseUrl = 'https://localhost:3443/plugin/dialog.html';
    var fromName = item.from ? (item.from.displayName || '') : '';
    var params = [
        'subject=' + encodeURIComponent(subject),
        'from=' + encodeURIComponent(from),
        'fromName=' + encodeURIComponent(fromName),
        'fromEmail=' + encodeURIComponent(from),
        'messageId=' + encodeURIComponent(internetMessageId),
        'hasAttachments=' + (hasAttachments ? '1' : '0'),
        'to=' + encodeURIComponent(to),
        'cc=' + encodeURIComponent(cc),
        'mode=reply'
    ];
    var dialogUrl = baseUrl + '?' + params.join('&');

    // Récupérer le body du mail (pour le transmettre au dialog en Mode Perf. Réduite)
    var mailBody = '';
    item.body.getAsync(Office.CoercionType.Text, function(bodyResult) {
        if (bodyResult.status === Office.AsyncResultStatus.Succeeded) {
            mailBody = bodyResult.value || '';
        }
    });

    // Ouvrir le dialog (80% largeur, 80% hauteur)
    Office.context.ui.displayDialogAsync(
        dialogUrl,
        { width: 80, height: 74 },
        function (asyncResult) {
            if (asyncResult.status === Office.AsyncResultStatus.Failed) {
                console.error('EasyMail: erreur ouverture dialog', asyncResult.error.message);
                event.completed();
                return;
            }

            var dialog = asyncResult.value;

            // Envoyer le body du mail au dialog (Mode Perf. Réduite)
            // Le dialog ne peut pas lire le mail via Graph, on lui envoie via messageChild
            setTimeout(function() {
                try {
                    if (mailBody) {
                        dialog.messageChild(JSON.stringify({
                            action: 'mail_body',
                            body: mailBody,
                            from_name: fromName,
                            from_email: from,
                        }));
                    }
                } catch(e) {
                    console.log('EasyMail: messageChild non supporté ou dialog pas prêt');
                }
            }, 1000);  // Attendre 1s que le dialog soit chargé

            // Écouter les messages du dialog
            dialog.addEventHandler(Office.EventType.DialogMessageReceived, function (arg) {
                try {
                    var message = JSON.parse(arg.message);

                    if (message.action === 'send_via_outlook') {
                        // Mode Performance Réduite : injecter la réponse dans Outlook natif
                        _sendViaOutlook(item, message);
                    }
                    // Mode Standard : le dialog envoie via Graph API, rien à faire ici

                } catch (e) {
                    console.error('EasyMail: erreur traitement message dialog', e);
                }
            });

            // Écouter la fermeture du dialog — libérer le runtime SEULEMENT ici
            dialog.addEventHandler(Office.EventType.DialogEventReceived, function (arg) {
                // Dialog fermé → maintenant on peut libérer le runtime
                event.completed();
            });

            // NE PAS appeler event.completed() ici — le runtime doit rester actif
            // tant que le dialog est ouvert, sinon New Outlook ferme le dialog.
        }
    );
}

/**
 * Mode Performance Réduite : ouvre la fenêtre de réponse Outlook native
 * avec le texte généré par EasyMail déjà rempli.
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
            // displayNewMessageForm pour forward et new mail
            var formData = { htmlBody: htmlBody };
            if (message.to) {
                // Split sur , et ; (les CC peuvent utiliser les deux séparateurs)
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

// Enregistrer la fonction pour le bouton ruban
if (typeof Office !== 'undefined') {
    Office.actions = Office.actions || {};
    Office.actions.associate("openEasyMailDialog", openEasyMailDialog);
}
