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
var _contactsCache = [];       // Cache contacts pour autocomplete

// (Phase 3) Mode standalone : ouvert dans QWebEngineView (PyQt) ou window.open (extension)
var _isStandaloneMode = _params.has('standalone');
var _isOfficeContext = false;
try {
    _isOfficeContext = (typeof Office !== 'undefined' && Office.context &&
                        Office.context.ui && typeof Office.context.ui.messageParent === 'function');
} catch(e) { _isOfficeContext = false; }


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

    // Charger les contacts pour autocomplete
    _loadContacts();
    _initAutocomplete('fieldTo', 'acTo');
    _initAutocomplete('fieldCc', 'acCc');

    // Écouter les messages du parent (taskpane/commands)
    // En Mode Perf. Réduite, le body du mail arrive via messageChild()
    if (!_isStandaloneMode) {
        _listenParentMessages();
    }

    // (O13) Vérifier le speculative cache — seulement en mode non-standalone
    // (en mode standalone, _checkSpeculativeCache est appelé dans _loadMailBodyStandalone
    //  après la récupération du message_id correct depuis /api/current_mail)
    if (!_isStandaloneMode) {
        _checkSpeculativeCache();
    }

    // Bouton fermer
    document.getElementById('btnClose').addEventListener('click', function() {
        _closeDialog();
    });

    // Garde forward : bouton Générer grisé si champ À vide en mode forward
    if (_mode === 'forward') {
        var fieldTo = document.getElementById('fieldTo');
        var btnGen = document.getElementById('btnGenerate');
        btnGen.disabled = true;
        fieldTo.addEventListener('input', function() {
            btnGen.disabled = !fieldTo.value.trim();
        });
    }
})();


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
}

function _loadContactTags() {
    // Charger le profil contact depuis le backend pour les tags header
    if (!_fromEmail) return;
    fetch(_backendUrl + '/api/contact_profile/' + encodeURIComponent(_fromEmail))
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data && data.profile) {
                var p = data.profile;
                // Tag registre (vouvoiement/tutoiement)
                var tagReg = document.getElementById('tagRegister');
                if (tagReg && p.register) {
                    tagReg.textContent = p.register;
                    tagReg.style.display = '';
                }
                // Tag confiance
                var tagConf = document.getElementById('tagConfidence');
                if (tagConf && p.confidence !== undefined) {
                    tagConf.textContent = 'confiance ' + p.confidence + '%';
                    tagConf.style.display = '';
                }
            }
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
    var btnGen = document.getElementById('btnGenerate');
    var fieldTo = document.getElementById('fieldTo');
    if (mode === 'forward') {
        btnGen.disabled = !fieldTo.value.trim();
        // Écouter le champ À
        fieldTo.addEventListener('input', function _fwdGuard() {
            btnGen.disabled = !fieldTo.value.trim();
        });
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

    // Sauvegarder les PJ sélectionnées côté serveur pour l'envoi forward
    if (_fwdSelectedIndexes.length > 0 && _messageId) {
        fetch(_backendUrl + '/api/save_original_attachments/' + encodeURIComponent(_messageId), {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ indices: _fwdSelectedIndexes }),
        }).catch(function(err) {
            console.log('[dialog] Erreur sauvegarde PJ forward:', err.message);
        });
    }
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

    // Tenter de charger le body via Graph API (Mode Standard)
    fetch(_backendUrl + '/api/email_body?messageId=' + encodeURIComponent(_messageId))
        .then(function(r) {
            if (r.status === 403) {
                // Mode Perf. Réduite : le body sera transmis par le taskpane
                document.getElementById('mailBody').innerHTML =
                    '<p style="color:#999; font-size:11px;">Body disponible apres generation (Mode Perf. Reduite).</p>';
                var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');
                return null;
            }
            return r.json();
        })
        .then(function(data) {
            if (!data) return;
            var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');

            if (data.html_body) {
                // Sanitize : supprimer les scripts du HTML reçu (protection XSS basique)
                var sanitized = data.html_body
                    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
                    .replace(/<iframe\b[^>]*>/gi, '<!-- blocked -->')
                    .replace(/<object\b[^>]*>/gi, '<!-- blocked -->')
                    .replace(/<embed\b[^>]*>/gi, '<!-- blocked -->')
                    .replace(/on\w+\s*=/gi, 'data-blocked=');
                document.getElementById('mailBody').innerHTML = sanitized;
                // Stocker pour le post-envoi (save_to_thread direction=received)
                _receivedBody = data.body || data.html_body || '';
                _mailBodyForGeneration = data.body || data.html_body || '';
            } else if (data.body) {
                // Convertir texte brut en paragraphes
                var bodyHtml = data.body.split(/\n\n+/).map(function(p) {
                    return '<p>' + _escapeHtml(p).replace(/\n/g, '<br>') + '</p>';
                }).join('');
                document.getElementById('mailBody').innerHTML = bodyHtml;
                _mailBodyForGeneration = data.body || '';
            } else {
                document.getElementById('mailBody').innerHTML =
                    '<p style="color:#999;">Contenu non disponible.</p>';
            }

            // Mettre à jour les métadonnées (À + Cc + date comme mockup v14)
            if (data.date || data.to) {
                var metaParts2 = [];
                if (data.to) metaParts2.push('A : ' + data.to);
                else if (_toEmail) metaParts2.push('A : ' + _toEmail);
                if (data.cc || _ccEmail) metaParts2.push('Cc : ' + (data.cc || _ccEmail));
                if (data.date) metaParts2.push(new Date(data.date).toLocaleString('fr-FR'));
                document.getElementById('mailMeta').textContent = metaParts2.join(' | ') || '—';
            }

            // PJ
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
    editor.innerHTML = '';
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
        _fetchGenerateReply(body);
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

function _fetchGenerateReply(body) {
    var editor = document.getElementById('editor');
    var spinner = document.getElementById('genSpinner');
    var btnGen = document.getElementById('btnGenerate');
    // SSE streaming
    fetch(_backendUrl + '/generate_reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: body,
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
        var reader = response.body.getReader();
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
                                editor.insertAdjacentText('beforeend', last.chunk);
                                streamedText += last.chunk;
                            }
                        } catch(e) {}
                    }
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
                                spinner.classList.remove('active');
                                document.getElementById('headerStatus').textContent = 'Generation en cours...';
                                editor.insertAdjacentText('beforeend', data.chunk);
                                streamedText += data.chunk;
                            }
                            // data.done (événement applicatif) : on n'agit PAS ici.
                            // Le reformatage final se fait UNE fois dans result.done
                            // (vrai end-of-stream, après tous les chunks résiduels).
                            if (data.error) {
                                spinner.classList.remove('active');
                                editor.innerHTML = '<p style="color:#c00;">' + _escapeHtml(data.error) + '</p>';
                                if (data.auth_required) {
                                    document.getElementById('headerStatus').textContent = 'Session expiree — reconnectez-vous';
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
    var editor = document.getElementById('editor');
    if (streamedText && !editor.querySelector('p')) {
        var paragraphs = streamedText.split(/\n\n+/).map(function(p) {
            return '<p>' + p.replace(/\n/g, '<br>') + '</p>';
        }).join('');
        editor.innerHTML = paragraphs;
    }

    document.getElementById('btnUndo').style.display = _undoStack.length > 0 ? '' : 'none';
    document.getElementById('btnSend').disabled = false;
    var btnRestore = document.getElementById('btnRestore');
    if (btnRestore) btnRestore.style.display = _versionStack.length > 0 ? '' : 'none';
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
    editor.innerHTML = '';

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
        var reader = response.body.getReader();
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
                                editor.insertAdjacentText('beforeend', last.chunk);
                                streamedText += last.chunk;
                            }
                        } catch(e) {}
                    }
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
                                document.getElementById('genSpinner').classList.remove('active');
                                editor.insertAdjacentText('beforeend', data.chunk);
                                streamedText += data.chunk;
                            }
                            // Idem generate : on n'agit pas sur data.done — tout
                            // se passe au vrai end-of-stream (result.done ci-dessus).
                            if (data.error) {
                                document.getElementById('genSpinner').classList.remove('active');
                                editor.innerHTML = '<p style="color:#c00;">' + _escapeHtml(data.error) + '</p>';
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
    generateReply();
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
    fetch(_backendUrl + '/api/status')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            _isStandardMode = data.authenticated && data.mode === 'standard';
            var btnSend = document.getElementById('btnSend');
            if (_isStandardMode) {
                btnSend.innerHTML = '&#x1f4e4; Relire et envoyer';
            } else {
                btnSend.innerHTML = '&#x2709; Valider et envoyer';
            }
            _sendStartTime = Date.now();
        })
        .catch(function() {
            _isStandardMode = false;
            _sendStartTime = Date.now();
            document.getElementById('headerStatus').textContent = 'Backend indisponible';
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

    fetch(_backendUrl + '/send_reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            mode: _mode,
            message_id: _messageId,
            body: body,
            to: to,
            cc: cc,
            subject: subject,
        }),
    }).then(function(r) {
        if (!r.ok && r.status !== 403) {
            throw new Error('Erreur serveur (' + r.status + ')');
        }
        return r.json();
    })
    .then(function(data) {
        if (data.success) {
            // Succès → post-envoi
            document.getElementById('headerStatus').textContent = 'Mail envoye !';
            btnSend.innerHTML = '&#x2705; Envoye';
            _postSend(body, to, cc, subject);
        } else if (data.auth_required) {
            // Token expiré
            alert('Session expir\u00e9e. Reconnectez-vous via Profil > Mode Standard.');
            btnSend.disabled = false;
            btnSend.innerHTML = '&#x1f4e4; Relire et envoyer';
        } else {
            alert('Erreur envoi : ' + (data.error || 'inconnue'));
            btnSend.disabled = false;
            btnSend.innerHTML = '&#x1f4e4; Relire et envoyer';
        }
    })
    .catch(function(err) {
        alert('Erreur r\u00e9seau : ' + err.message);
        btnSend.disabled = false;
        btnSend.innerHTML = '&#x1f4e4; Relire et envoyer';
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
    fetch(_backendUrl + '/api/post_send', {
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
    }).then(function(r) {
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

    fetch(_backendUrl + '/api/classify_email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message_id: _messageId,
            folder_id: _selectedFolderId,
        }),
    }).then(function(r) { return r.json(); })
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

    fetch(_backendUrl + '/api/pj_classification/post_send/' + encodeURIComponent(_messageId))
        .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function(data) {
            if (data.status === 'scanning') {
                setTimeout(function() {
                    fetch(_backendUrl + '/api/pj_classification/post_send/' + encodeURIComponent(_messageId))
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

var _contactsCacheLoaded = false;

function _loadContacts() {
    if (_contactsCacheLoaded) return;
    _contactsCacheLoaded = true;
    fetch(_backendUrl + '/api/contact_profiles')
        .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function(data) {
            _contactsCache = (data.profiles || []).map(function(p) {
                return {
                    name: p.display_name || '',
                    email: p.email || '',
                    org: p.organization || '',
                };
            });
        })
        .catch(function() { _contactsCache = []; });
}

function _initAutocomplete(inputId, dropdownId) {
    var input = document.getElementById(inputId);
    var dropdown = document.getElementById(dropdownId);
    if (!input || !dropdown) return;

    var selectedIndex = -1;

    input.addEventListener('input', function() {
        var val = input.value.trim().toLowerCase();
        if (val.length < 2) {
            dropdown.classList.remove('active');
            return;
        }
        var matches = _contactsCache.filter(function(c) {
            return (c.name && c.name.toLowerCase().indexOf(val) >= 0) ||
                   (c.email && c.email.toLowerCase().indexOf(val) >= 0) ||
                   (c.org && c.org.toLowerCase().indexOf(val) >= 0);
        }).slice(0, 8);

        if (matches.length === 0) {
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

    // Fermer si clic ailleurs
    document.addEventListener('click', function(e) {
        if (e.target !== input && !dropdown.contains(e.target)) {
            dropdown.classList.remove('active');
        }
    });
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

/**
 * Charge le body du mail reçu depuis le backend (mode standalone).
 * Les données ont été alimentées par la popup PyQt via POST /api/event/message_read.
 */
function _loadMailBodyStandalone() {
    fetch(_backendUrl + '/api/current_mail')
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.status !== 'ok' || !data.mail) {
                document.getElementById('mailBody').innerHTML =
                    '<p style="color:#999; font-size:11px;">Donnees du mail non disponibles.</p>';
                var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');
                return;
            }

            var mail = data.mail;

            // Mettre à jour les infos du mail reçu (panneau gauche)
            _fromName = mail.from_name || _fromName;
            _fromEmail = mail.from_email || _fromEmail;
            _subject = mail.subject || _subject;
            _messageId = mail.message_id || _messageId;

            document.getElementById('mailFrom').textContent = _fromName
                ? _fromName + ' <' + _fromEmail + '>'
                : _fromEmail || '—';
            document.getElementById('mailSubject').textContent = _subject || '—';
            _updateHeader();

            // Body
            var body = mail.body || '';
            if (body) {
                // Sanitize HTML
                var sanitized = body
                    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
                    .replace(/<iframe\b[^>]*>/gi, '<!-- blocked -->')
                    .replace(/<object\b[^>]*>/gi, '<!-- blocked -->')
                    .replace(/<embed\b[^>]*>/gi, '<!-- blocked -->')
                    .replace(/on\w+\s*=/gi, 'data-blocked=');
                document.getElementById('mailBody').innerHTML = sanitized;
                _receivedBody = body;
                _mailBodyForGeneration = body;
                var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');
            } else if (_messageId) {
                // Pas de body dans /api/current_mail → fetch séparé via /api/email_body
                // (flow New Outlook : autorunshared.js POST /open_dialog_native qui lance PyQt
                //  sans passer par /api/event/message_read → body absent de _current_mail_data)
                fetch(_backendUrl + '/api/email_body?messageId=' + encodeURIComponent(_messageId))
                    .then(function(r) { return r.json(); })
                    .then(function(ebody) {
                        var _bs2 = document.getElementById('bodySpinner'); if (_bs2) _bs2.classList.remove('active');
                        if (ebody && (ebody.body || ebody.html_body)) {
                            var fullBody = ebody.html_body || ebody.body;
                            var sanitized = fullBody
                                .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
                                .replace(/<iframe\b[^>]*>/gi, '<!-- blocked -->')
                                .replace(/<object\b[^>]*>/gi, '<!-- blocked -->')
                                .replace(/<embed\b[^>]*>/gi, '<!-- blocked -->')
                                .replace(/on\w+\s*=/gi, 'data-blocked=');
                            document.getElementById('mailBody').innerHTML = sanitized;
                            // Pour la génération IA : utiliser le body texte (strippe par _normalize_email),
                            // pas le HTML brut (trop bruyant pour Claude)
                            _receivedBody = ebody.body || ebody.html_body || '';
                            _mailBodyForGeneration = ebody.body || ebody.html_body || '';
                        } else {
                            document.getElementById('mailBody').innerHTML =
                                '<p style="color:#999;">Contenu du mail non disponible.</p>';
                        }
                    })
                    .catch(function(err) {
                        var _bs2 = document.getElementById('bodySpinner'); if (_bs2) _bs2.classList.remove('active');
                        document.getElementById('mailBody').innerHTML =
                            '<p style="color:#c00;">Erreur chargement body : ' + _escapeHtml(err.message || '') + '</p>';
                    });
            } else {
                document.getElementById('mailBody').innerHTML =
                    '<p style="color:#999;">Body en attente (cliquez le bouton EasyMail dans Outlook).</p>';
                var _bs = document.getElementById('bodySpinner'); if (_bs) _bs.classList.remove('active');
            }

            // (O6) Pré-remplir les champs
            if (!document.getElementById('fieldTo').value && _fromEmail && (_mode === 'reply' || _mode === 'reply_all')) {
                document.getElementById('fieldTo').value = _fromEmail;
            }
            if (!document.getElementById('fieldSubject').value && _subject) {
                var prefix = _mode === 'forward' ? 'Fw: ' : 'Re: ';
                var subjectClean = _subject.replace(/^(re\s*:|fw\s*:|fwd\s*:|tr\s*:)\s*/i, '');
                document.getElementById('fieldSubject').value = prefix + subjectClean;
            }
        })
        .catch(function(err) {
            var mb = document.getElementById('mailBody');
            if (mb) mb.innerHTML = '<p style="color:#c00;">Erreur chargement : ' + err.message + '</p>';
            var sp = document.getElementById('bodySpinner');
            if (sp) sp.classList.remove('active');
        });

    // (O13) Vérifier le speculative cache (fonctionne dans les 2 modes)
    _checkSpeculativeCache();
}

/**
 * (O13) Vérifie si une réponse spéculative est prête.
 * Appelé au chargement du dialog (standalone ET Office.js).
 */
function _checkSpeculativeCache() {
    var url = _backendUrl + '/api/prefetch_status';  // fix #6 : utiliser _backendUrl comme tous les autres fetch
    if (_messageId) url += '?message_id=' + encodeURIComponent(_messageId);

    fetch(url)
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.speculative_ready) {
                // La réponse est prête — attendre que le body soit chargé avant de déclencher
                // (le fetch /api/email_body est asynchrone : _mailBodyForGeneration peut être vide)
                console.log('[dialog] Speculative cache ready — attente body...');
                var _waitBody = function(attempts) {
                    if (_mailBodyForGeneration || _mode === 'new' || attempts <= 0) {
                        console.log('[dialog] Declenchement automatique (body=' + _mailBodyForGeneration.length + ' chars)');
                        generateReply();
                    } else {
                        setTimeout(function() { _waitBody(attempts - 1); }, 150);
                    }
                };
                // 20 × 150ms = 3s max d'attente du body avant de déclencher quand même
                _waitBody(20);
            } else if (data.status === 'done') {
                // Prefetch done mais pas de spéculative — contexte prêt
                console.log('[dialog] Prefetch done (A=' + data.a_count + ' B=' + data.b_count + ' C=' + data.c_count + ')');
            }
        })
        .catch(function() {});
}

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
        var sanitized = _receivedBody
            .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
            .replace(/on\w+\s*=/gi, 'data-blocked=');
        document.getElementById('mailBody').innerHTML = sanitized;
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
 * (P18) Envoi en Mode Perf. Réduite standalone : via Companion /inject_reply.
 * Remplace _sendViaOutlook quand messageParent n'est pas disponible.
 */
function _sendViaCompanion(body, to, cc, subject) {
    fetch(_backendUrl + '/api/companion/inject_reply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            html_body: body,
            mode: _mode,
            to: to,
            cc: cc,
            subject: subject,
            compose_already_open: true,  // En standalone, le compose est ouvert par Outlook via OnNewMessageCompose
        })
    })
    .then(function(r) { return r.json(); })
    .then(function(data) {
        if (data.status === 'ok') {
            document.getElementById('headerStatus').textContent = 'Reponse injectee dans Outlook';
            document.getElementById('btnSend').innerHTML = '&#x2705; Envoye';
            _postSend(body, to, cc, subject);
        } else {
            alert('Erreur injection : ' + (data.reason || 'inconnue'));
            document.getElementById('btnSend').disabled = false;
            document.getElementById('btnSend').innerHTML = '&#x1f4e4; Envoyer';
        }
    })
    .catch(function(err) {
        alert('Companion non disponible : ' + err.message);
        document.getElementById('btnSend').disabled = false;
        document.getElementById('btnSend').innerHTML = '&#x1f4e4; Envoyer';
    });
}
