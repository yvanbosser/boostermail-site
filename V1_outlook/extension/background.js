/**
 * BoosterMail — Service Worker (background)
 *
 * Reçoit les demandes du content script et ouvre la fenêtre dialog
 * via chrome.windows.create (aucune popup blocker possible : c'est une
 * API d'extension, pas window.open).
 */

const DIALOG_WINDOW_WIDTH = 1200;
const DIALOG_WINDOW_HEIGHT = 800;

// Garde : une seule fenêtre dialog ouverte à la fois (évite l'empilement)
let _currentDialogWindowId = null;

function _log(...args) {
    try { console.log('[BoosterMail ext/bg]', ...args); } catch(e){}
}

chrome.runtime.onMessage.addListener(function (message, sender, sendResponse) {
    if (!message || message.type !== 'boostermail-open-window') return false;

    _log('Ouverture fenêtre dialog demandée', message);

    // Utiliser le dialogUrl reçu tel quel (il a déjà tous les params de l'add-in)
    let dialogUrl = message.dialogUrl || '';
    if (!dialogUrl) {
        // Fallback : construire depuis data
        const data = message.data || {};
        const params = new URLSearchParams();
        params.set('standalone', '1');
        for (const k of ['subject', 'from', 'fromName', 'fromEmail', 'messageId', 'hasAttachments', 'to', 'cc', 'mode']) {
            if (data[k]) params.set(k, data[k]);
        }
        dialogUrl = 'https://localhost:3443/plugin/dialog.html?' + params.toString();
    } else {
        // Ajouter standalone=1 si absent (le dialog doit savoir qu'il tourne hors Office.js)
        if (dialogUrl.indexOf('standalone=1') === -1) {
            dialogUrl += (dialogUrl.indexOf('?') === -1 ? '?' : '&') + 'standalone=1';
        }
    }

    // Fermer la fenêtre précédente si elle existe encore
    const openAfterClose = function () {
        chrome.windows.create({
            url: dialogUrl,
            type: 'popup',
            width: DIALOG_WINDOW_WIDTH,
            height: DIALOG_WINDOW_HEIGHT,
            focused: true
        }, function (win) {
            if (chrome.runtime.lastError) {
                _log('Erreur chrome.windows.create:', chrome.runtime.lastError.message);
                sendResponse({ ok: false, error: chrome.runtime.lastError.message });
                return;
            }
            _currentDialogWindowId = win ? win.id : null;
            _log('Fenêtre dialog créée id=' + _currentDialogWindowId);
            sendResponse({ ok: true, windowId: _currentDialogWindowId });
        });
    };

    if (_currentDialogWindowId != null) {
        chrome.windows.remove(_currentDialogWindowId, function () {
            _currentDialogWindowId = null;
            // lastError ignoré (fenêtre peut déjà être fermée)
            openAfterClose();
        });
    } else {
        openAfterClose();
    }

    // Indique qu'on répond de façon async
    return true;
});

// Nettoyage : si la fenêtre dialog est fermée par l'utilisateur, oublier son id
chrome.windows.onRemoved.addListener(function (windowId) {
    if (_currentDialogWindowId === windowId) {
        _currentDialogWindowId = null;
        _log('Fenêtre dialog fermée par l\'utilisateur');
    }
});

_log('Service worker chargé');
