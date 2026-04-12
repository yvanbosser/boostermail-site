/**
 * EasyMail Extension — Background Service Worker
 *
 * (B11) Proxy fetch vers localhost:3443.
 * Les content scripts ne peuvent pas fetch vers localhost en cross-origin (CORS).
 * Le service worker n'est PAS soumis aux CORS → il fait le relais.
 *
 * (B16) host_permissions dans manifest.json autorise le service worker
 * a acceder a https://localhost:3443/*.
 */

// Ecouter les messages du content script
chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
    if (msg.action === 'fetch') {
        // Proxy GET
        fetch(msg.url, {
            method: msg.method || 'GET',
            headers: msg.headers || {},
            body: msg.body || undefined,
        })
        .then(function (r) {
            // Lire le content-type pour savoir si c'est du JSON ou du HTML
            var contentType = r.headers.get('Content-Type') || '';
            if (contentType.includes('application/json')) {
                return r.json().then(function (data) {
                    sendResponse({ ok: r.ok, status: r.status, json: data });
                });
            } else {
                return r.text().then(function (text) {
                    sendResponse({ ok: r.ok, status: r.status, html: text });
                });
            }
        })
        .catch(function (err) {
            sendResponse({ ok: false, error: err.message });
        });

        return true; // Indique une reponse async
    }

    if (msg.action === 'fetch_post') {
        // Proxy POST (pour /api/event/message_read, etc.)
        fetch(msg.url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(msg.data || {}),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            sendResponse({ ok: true, json: data });
        })
        .catch(function (err) {
            sendResponse({ ok: false, error: err.message });
        });

        return true;
    }
});
