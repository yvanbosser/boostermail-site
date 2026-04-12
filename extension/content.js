/**
 * EasyMail Extension — Content Script
 *
 * Injecte dans les pages Outlook Web (outlook.office365.com).
 *
 * Etat 1 : cree un overlay draggable (Shadow DOM) avec le contenu de popup.html (P35, B11).
 * Etat 2 : ouvre le dialog via window.open (P42).
 *
 * Communication :
 * - popup.html → content script : via postMessage (compose detecte)
 * - content script → background.js : via chrome.runtime.sendMessage (fetch proxy B11)
 * - content script → DOM Outlook Web : parsing sujet + expediteur (O10)
 */

var BACKEND_URL = 'https://localhost:3443';
var _overlayHost = null;
var _overlayVisible = false;
var _lastComposeTimestamp = 0;
var _initRetryCount = 0;
var _MAX_INIT_RETRIES = 12;  // 12 × 5s = 1 minute max

// =============================================================================
// INITIALISATION — attendre que la page Outlook Web soit chargee
// =============================================================================

(function init() {
    // Verifier que le backend est disponible avant d'injecter l'overlay
    _proxyFetch(BACKEND_URL + '/api/status', function (response) {
        if (response && response.ok) {
            // Overlay affiche TOUJOURS pour travailler le design
            // La logique API/non-API sera ajoutee plus tard
            var mode = (response.json && response.json.mode) || 'unknown';
            console.log('[easymail-ext] Backend detecte (mode=' + mode + '), injection overlay');
            _injectOverlay();
            _startDOMWatcher();
        } else {
            _initRetryCount++;
            if (_initRetryCount >= _MAX_INIT_RETRIES) {
                console.log('[easymail-ext] Backend non disponible apres ' + _MAX_INIT_RETRIES + ' tentatives. Arret. Lancez le backend EasyMail puis rechargez la page.');
                return;
            }
            console.log('[easymail-ext] Backend non disponible, retry ' + _initRetryCount + '/' + _MAX_INIT_RETRIES + ' dans 5s');
            setTimeout(init, 5000);
        }
    });
})();

// =============================================================================
// OVERLAY — Shadow DOM draggable (P35)
// =============================================================================

function _injectOverlay() {
    // Creer le conteneur host
    _overlayHost = document.createElement('div');
    _overlayHost.id = 'easymail-overlay-host';

    // Taille responsive en fonction de l'ecran
    var screenW = window.innerWidth;
    var screenH = window.innerHeight;
    var overlayW = Math.min(Math.max(Math.round(screenW * 0.22), 280), 380);
    var overlayH = Math.round(screenH * 0.31);

    _overlayHost.style.cssText = [
        'position: fixed',
        'top: 48px',          // Juste sous le ruban Outlook
        'right: 0px',         // Colle au bord droit (comme un panneau natif)
        'width: ' + overlayW + 'px',
        'height: ' + overlayH + 'px',
        'z-index: 999999',
        'border: none',
        'border-radius: 0 0 0 8px',
        'box-shadow: -2px 2px 12px rgba(0,0,0,0.15)',
        'overflow: hidden',
        'background: #fff',
        'display: flex',
        'flex-direction: column',
    ].join('; ');

    // --- Header draggable (comme un panneau Outlook natif) ---
    var header = document.createElement('div');
    header.id = 'easymail-drag-header';
    header.style.cssText = [
        'height: 6px',
        'background: #0F6CBD',
        'cursor: grab',
        'flex-shrink: 0',
        'display: flex',
        'align-items: center',
        'justify-content: flex-end',
        'padding: 0 4px',
    ].join('; ');

    // Bouton reduire (pas fermer) — reduit l'overlay a un petit onglet
    var minimizeBtn = document.createElement('div');
    minimizeBtn.innerHTML = '&#x2015;';  // tiret horizontal
    minimizeBtn.title = 'Reduire';
    minimizeBtn.style.cssText = 'color: #fff; font-size: 16px; font-weight: bold; cursor: pointer; line-height: 1; padding: 0 6px;';
    minimizeBtn.addEventListener('click', function (e) {
        e.stopPropagation();
        _overlayHost.style.display = 'none';
        _toggleBtn.style.display = 'flex';
        _overlayVisible = false;
    });
    header.appendChild(minimizeBtn);
    _overlayHost.appendChild(header);

    // --- Iframe popup.html ---
    var iframe = document.createElement('iframe');
    iframe.src = BACKEND_URL + '/plugin/popup.html?container=extension';
    iframe.style.cssText = 'width: 100%; flex: 1; border: none;';
    iframe.setAttribute('allow', 'clipboard-read; clipboard-write');
    _overlayHost.appendChild(iframe);

    // --- Bouton toggle (visible quand l'overlay est ferme) ---
    _toggleBtn = document.createElement('div');
    _toggleBtn.id = 'easymail-toggle';
    _toggleBtn.innerHTML = '&#x2709;';
    _toggleBtn.title = 'Ouvrir EasyMail';
    _toggleBtn.style.cssText = [
        'position: fixed',
        'top: 48px',
        'right: 0px',
        'width: 36px',
        'height: 36px',
        'border-radius: 0 0 0 8px',
        'background: #0F6CBD',
        'color: white',
        'font-size: 16px',
        'display: none',
        'align-items: center',
        'justify-content: center',
        'cursor: pointer',
        'z-index: 999998',
        'box-shadow: -2px 2px 8px rgba(0,0,0,0.15)',
    ].join('; ');
    _toggleBtn.addEventListener('click', function () {
        _overlayHost.style.display = 'flex';
        _toggleBtn.style.display = 'none';
        _overlayVisible = true;
    });
    document.body.appendChild(_toggleBtn);

    // Ajouter l'overlay a la page
    document.body.appendChild(_overlayHost);
    _overlayVisible = true;

    // Ecouter les messages de popup.html (compose detecte, etc.)
    window.addEventListener('message', function (e) {
        if (!e.data || e.data.type !== 'easymail_compose') return;
        _onComposeFromPopup(e.data.mode || 'reply');
    });

    // Drag fluide depuis le header uniquement
    _makeDraggable(_overlayHost, header);

    // Adapter la taille quand la fenetre est redimensionnee
    window.addEventListener('resize', function () {
        if (!_overlayVisible) return;
        var w = Math.min(Math.max(Math.round(window.innerWidth * 0.22), 280), 380);
        var h = Math.round(window.innerHeight * 0.30);
        _overlayHost.style.width = w + 'px';
        _overlayHost.style.height = h + 'px';
    });
}

var _toggleBtn = null;

// =============================================================================
// DRAGGABLE — fluide depuis le header
// =============================================================================

function _makeDraggable(el, handle) {
    var isDragging = false;
    var startX, startY, origLeft, origTop;

    handle.addEventListener('mousedown', function (e) {
        isDragging = true;
        handle.style.cursor = 'grabbing';
        startX = e.clientX;
        startY = e.clientY;
        var rect = el.getBoundingClientRect();
        origLeft = rect.left;
        origTop = rect.top;
        e.preventDefault();
    });

    document.addEventListener('mousemove', function (e) {
        if (!isDragging) return;
        var dx = e.clientX - startX;
        var dy = e.clientY - startY;
        el.style.left = (origLeft + dx) + 'px';
        el.style.top = (origTop + dy) + 'px';
        el.style.right = 'auto';
        el.style.bottom = 'auto';
    });

    document.addEventListener('mouseup', function () {
        if (isDragging) {
            isDragging = false;
            handle.style.cursor = 'grab';
        }
    });
}

// =============================================================================
// COMPOSE DETECTE — ouvrir le dialog (P42)
// =============================================================================

function _onComposeFromPopup(mode) {
    console.log('[easymail-ext] Compose detecte, mode=' + mode);
    // (P42) Ouvrir le dialog dans une fenetre separee (window.open)
    // window.open n'est PAS soumis a la CSP de la page hote
    window.open(
        BACKEND_URL + '/plugin/dialog.html?standalone=1&mode=' + encodeURIComponent(mode),
        'easymail_dialog',
        'width=1200,height=800,left=100,top=50'
    );
}

// =============================================================================
// DOM WATCHER — detecter le mail selectionne (O10)
// =============================================================================

var _lastDetectedSubject = '';

var _composeDetected = false;

function _startDOMWatcher() {
    // Observer les changements dans le DOM Outlook Web
    setInterval(function () {
        _detectCurrentMail();
        _detectCompose();
    }, 2000);  // Poll DOM toutes les 2s
}

/**
 * Detecte si un compose (Repondre/Transferer/Nouveau) est ouvert dans Outlook Web.
 * Cherche une zone contenteditable + bouton Envoyer dans le DOM.
 * Fonctionne sur Outlook Web ET New Outlook Windows (meme DOM, WebView2).
 * PAS besoin d'admin deploy ni de LaunchEvent.
 */
function _detectCompose() {
    try {
        // Outlook Web/New Outlook : le compose a un div contenteditable="true"
        // avec un bouton Envoyer visible
        var editables = document.querySelectorAll('[contenteditable="true"]');
        var hasCompose = false;

        for (var i = 0; i < editables.length; i++) {
            var el = editables[i];
            // Le contenteditable du compose est dans un conteneur specifique
            // (pas les petits contenteditable de la barre de recherche)
            if (el.offsetHeight > 100 || el.getAttribute('aria-label') === 'Corps du message' ||
                el.getAttribute('aria-label') === 'Message body') {
                hasCompose = true;
                break;
            }
        }

        // Verification supplementaire : chercher le bouton Envoyer
        if (!hasCompose) {
            var buttons = document.querySelectorAll('button[aria-label*="nvoyer"], button[aria-label*="Send"]');
            if (buttons.length > 0) {
                hasCompose = true;
            }
        }

        if (hasCompose && !_composeDetected) {
            // Compose detecte via DOM.
            // NOTE : on NE lance PAS le dialog automatiquement ici car le DOM parsing
            // ne permet pas de recuperer les donnees fiables du mail recu (sujet, expediteur, body).
            // Le dialog standalone serait vide ou avec des faux positifs.
            // A la place, l'utilisateur utilise le bouton "Repondre avec EasyMail" dans l'overlay
            // ou le bouton #7b dans la barre d'actions (qui a acces au mail complet via Office.js).
            _composeDetected = true;
            console.log('[easymail-ext] Compose detecte via DOM (pas d\'auto-ouverture — utiliser le bouton overlay)');

        } else if (!hasCompose && _composeDetected) {
            // Le compose a ete ferme
            _composeDetected = false;
            console.log('[easymail-ext] Compose ferme');
        }

    } catch (e) {
        // Silencieux
    }
}

function _detectCurrentMail() {
    // Outlook Web affiche le sujet dans un element avec role="heading"
    // et l'expediteur dans un element avec des classes specifiques
    // Note : cette detection est FRAGILE — Microsoft peut changer le DOM a tout moment
    // C'est pourquoi on l'utilise comme SOURCE SECONDAIRE (le bouton #7b est le turbo)

    try {
        // Chercher le sujet du mail ouvert
        // Strategie 1 : chercher le sujet dans le titre de la page (le plus fiable)
        // Outlook Web met le sujet du mail ouvert dans document.title : "sujet - email - Outlook"
        var subject = '';
        var pageTitle = document.title || '';
        if (pageTitle && pageTitle.indexOf(' - ') > 0) {
            // Extraire la premiere partie avant " - "
            var titleParts = pageTitle.split(' - ');
            if (titleParts[0].length > 3 && titleParts[0].length < 200) {
                subject = titleParts[0].trim();
            }
        }

        // Strategie 2 (fallback) : chercher dans les headings du volet de lecture
        if (!subject) {
            var _ignoreSubjects = ['volet de navigation', 'navigation pane', 'prioritaire', 'focused',
                'autres', 'other', 'boîte de réception', 'inbox', 'dossiers', 'folders',
                'groupes', 'groups', 'favoris', 'favorites', 'viva insights', 'microsoft viva',
                'copilot', 'tips', 'conseils', 'bienvenue', 'welcome', 'nouveautés', 'what\'s new',
                'calendrier', 'calendar', 'contacts', 'personnes', 'people', 'tâches', 'tasks',
                'paramètres', 'settings', 'aide', 'help', 'rechercher', 'search',
                'courrier', 'mail', 'outlook'];
            var headings = document.querySelectorAll('[role="heading"]');
            for (var i = 0; i < headings.length; i++) {
                var text = headings[i].textContent.trim();
                if (text && text.length > 5 && text.length < 200) {
                    if (_ignoreSubjects.indexOf(text.toLowerCase()) >= 0) continue;
                    subject = text;
                    break;
                }
            }
        }

        if (!subject || subject === _lastDetectedSubject) return;
        _lastDetectedSubject = subject;

        // Chercher l'expediteur (souvent dans un element avec aria-label contenant "de" ou "from")
        var fromEmail = '';
        var fromName = '';
        var senderElements = document.querySelectorAll('[aria-label*="@"], [title*="@"]');
        for (var j = 0; j < senderElements.length; j++) {
            var label = senderElements[j].getAttribute('aria-label') || senderElements[j].getAttribute('title') || '';
            var emailMatch = label.match(/[\w.-]+@[\w.-]+\.\w+/);
            if (emailMatch) {
                fromEmail = emailMatch[0];
                fromName = label.replace(fromEmail, '').replace(/[<>]/g, '').trim();
                break;
            }
        }

        if (!fromEmail) return;

        // (O10) POST au backend pour prefetch partiel B+C (pas de conversationId ni body)
        console.log('[easymail-ext] Mail detecte: ' + subject + ' de ' + fromEmail);
        _proxyPost(BACKEND_URL + '/api/event/message_read', {
            subject: subject,
            from_email: fromEmail,
            from_name: fromName,
            message_id: '',
            conversation_id: '',
            has_attachments: false,
            to: '',
            cc: '',
            body: '',
        });

    } catch (e) {
        // Silencieux — le DOM parsing est best-effort
    }
}

// =============================================================================
// PROXY FETCH via Background Script (B11)
// =============================================================================

function _proxyFetch(url, callback) {
    chrome.runtime.sendMessage({ action: 'fetch', url: url }, function (response) {
        callback(response || { ok: false, error: 'no_response' });
    });
}

function _proxyPost(url, data) {
    chrome.runtime.sendMessage({ action: 'fetch_post', url: url, data: data }, function () {
        // Fire and forget
    });
}
