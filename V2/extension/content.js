/**
 * BoosterMail — Content Script
 *
 * Injecté dans Outlook Web (outlook.office.com, outlook.live.com, etc.)
 * ET dans tous ses iframes (all_frames: true) pour capter les postMessage
 * émis depuis l'iframe add-in.
 *
 * Rôle :
 *  1. Écouter les messages type='boostermail-open-dialog' émis par l'add-in
 *     (autorunshared.js dans V2/)
 *  2. Renvoyer un ACK pour que l'add-in sache que l'extension est présente
 *  3. Relayer la demande au background service worker qui ouvrira la fenêtre
 */

(function () {
    'use strict';

    // Garde : ne charger qu'une fois par frame
    if (window.__boostermail_content_loaded) return;
    window.__boostermail_content_loaded = true;

    var VERSION = '1.0.0';

    function _log() {
        try { console.log.apply(console, ['[BoosterMail ext]'].concat([].slice.call(arguments))); } catch(e){}
    }

    function _ackSender(source, origin) {
        try {
            source.postMessage({
                type: 'boostermail-ack',
                version: VERSION,
                extension: true
            }, origin || '*');
        } catch (e) {}
    }

    window.addEventListener('message', function (event) {
        var msg = event.data;
        if (!msg || typeof msg !== 'object') return;
        if (msg.type !== 'boostermail-open-dialog') return;

        _log('Dialog request reçue', msg);

        // 1) ACK immédiat pour que l'add-in sache qu'on est là
        _ackSender(event.source, event.origin);

        // 2) Relai au background service worker (qui a chrome.windows.create)
        try {
            chrome.runtime.sendMessage({
                type: 'boostermail-open-window',
                dialogUrl: msg.dialogUrl,
                data: msg.data || {}
            }, function (response) {
                // Ignorer la réponse (lastError normal si popup fermée)
                if (chrome.runtime.lastError) {
                    _log('sendMessage error (ignoré):', chrome.runtime.lastError.message);
                }
            });
        } catch (e) {
            _log('chrome.runtime.sendMessage non disponible', e);
        }
    }, false);

    _log('Content script chargé — v' + VERSION + ' @ ' + window.location.href);
})();
