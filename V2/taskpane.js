/*
 * EasyMail — taskpane.js
 * Logique du taskpane pinable.
 * Lit le mail courant via Office.js, met a jour l'UI, gere l'InsightMessage.
 * Ouvre le dialog au clic sur "Repondre avec EasyMail".
 */

/* global Office */

var _currentItem = null;
var _backendUrl = 'https://localhost:3443';

// ============================================================================
// INITIALISATION
// ============================================================================

Office.onReady(function (info) {
    if (info.host === Office.HostType.Outlook) {
        // Charger le mail courant
        _updateForCurrentItem();

        // Ecouter les changements de mail (taskpane pinable)
        Office.context.mailbox.addHandlerAsync(
            Office.EventType.ItemChanged,
            _onItemChanged
        );

        // Boutons
        document.getElementById('btnRepondre').addEventListener('click', function () {
            _openDialog('reply');
        });
        document.getElementById('btnRepTous').addEventListener('click', function () {
            _openDialog('reply_all');
        });
        document.getElementById('btnTransferer').addEventListener('click', function () {
            _openDialog('forward');
        });
        document.getElementById('btnClasser').addEventListener('click', function () {
            // TODO etape 12i : ouvrir popup classement
            alert('Classement — a implementer (etape 12i)');
        });

        // Navigation
        document.getElementById('navEcheances').addEventListener('click', function () {
            // TODO : afficher la page echeances dans le taskpane
            alert('Page Echeances — a implementer');
        });
        document.getElementById('navContacts').addEventListener('click', function () {
            alert('Page Contacts — a implementer');
        });
        document.getElementById('navProfil').addEventListener('click', function () {
            _showProfilSection();
        });

        // Test connexion backend
        _checkBackendStatus();

        // Vérifier si le setup est terminé (premier lancement)
        _checkSetup();
    }
});

// ============================================================================
// ITEM CHANGED (taskpane pinable)
// ============================================================================

function _onItemChanged() {
    _updateForCurrentItem();
}

function _updateForCurrentItem() {
    // Masquer les sections overlay (Profil, Setup) si elles étaient visibles
    document.getElementById('profilSection').style.display = 'none';
    document.getElementById('setupWizard').style.display = 'none';

    var item = Office.context.mailbox.item;

    if (!item) {
        _showEmptyState();
        return;
    }

    _currentItem = item;
    _showMailContent(item);
    _addInsightMessage(item);
}

// ============================================================================
// AFFICHAGE DU MAIL
// ============================================================================

function _showEmptyState() {
    document.getElementById('emptyState').style.display = 'flex';
    document.getElementById('mailContent').style.display = 'none';
}

function _showMailContent(item) {
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('mailContent').style.display = 'block';

    // Contact
    var fromName = '';
    var fromEmail = '';
    if (item.from) {
        fromName = item.from.displayName || '';
        fromEmail = item.from.emailAddress || '';
    }

    var initials = _getInitials(fromName);
    document.getElementById('contactAvatar').textContent = initials;
    document.getElementById('contactName').textContent = fromName || fromEmail || '—';
    document.getElementById('contactOrg').textContent = '';

    // Tags : on les chargera depuis le backend plus tard (profil contact)
    document.getElementById('contactTags').innerHTML = '';

    // PJ
    var attachments = item.attachments || [];
    var pjSection = document.getElementById('pjSection');
    var pjList = document.getElementById('pjList');
    var realAttachments = [];
    for (var i = 0; i < attachments.length; i++) {
        if (!attachments[i].isInline) {
            realAttachments.push(attachments[i]);
        }
    }

    if (realAttachments.length > 0) {
        pjSection.style.display = 'block';
        var html = '';
        for (var j = 0; j < realAttachments.length; j++) {
            var att = realAttachments[j];
            var size = att.size ? _formatSize(att.size) : '';
            html += '<div class="tp-pj-item">'
                + '<span class="tp-pj-icon">&#x1f4c4;</span>'
                + _escapeHtml(att.name)
                + '<span class="tp-pj-size">' + size + '</span>'
                + '</div>';
        }
        html += '<div class="tp-pj-note">&#x1f50d; ' + realAttachments.length + ' PJ analysable' + (realAttachments.length > 1 ? 's' : '') + '</div>';
        pjList.innerHTML = html;
    } else {
        pjSection.style.display = 'none';
    }

    // Echeance et classement : seront charges via le backend (etapes suivantes)
    document.getElementById('echSection').style.display = 'none';
    document.getElementById('clsSection').style.display = 'none';

    // Charger le profil contact depuis le backend
    if (fromEmail) {
        _loadContactProfile(fromEmail);
    }
}

// ============================================================================
// INSIGHT MESSAGE (bandeau natif Outlook)
// ============================================================================

function _addInsightMessage(item) {
    // InsightMessage en lecture : fonctionne uniquement sur Classic Outlook Windows
    // Sur New Outlook et Web : silencieusement ignore
    try {
        var attachmentCount = 0;
        if (item.attachments) {
            for (var i = 0; i < item.attachments.length; i++) {
                if (!item.attachments[i].isInline) attachmentCount++;
            }
        }

        var message = 'EasyMail : mail de ' + (item.from ? item.from.displayName : 'inconnu');
        if (attachmentCount > 0) {
            message += ', ' + attachmentCount + ' PJ analysable' + (attachmentCount > 1 ? 's' : '');
        }

        item.notificationMessages.replaceAsync('easymail_insight', {
            type: Office.MailboxEnums.ItemNotificationMessageType.InsightMessage,
            message: message,
            icon: 'icon16',
            actions: [{
                actionType: Office.MailboxEnums.ActionType.ShowTaskPane,
                actionText: 'Ouvrir EasyMail',
                commandId: 'easymailTaskpaneButton'
            }]
        }, function (result) {
            if (result.status === Office.AsyncResultStatus.Failed) {
                // InsightMessage non supporte sur cette plateforme — pas grave
                console.log('InsightMessage non supporte :', result.error.message);
            }
        });
    } catch (e) {
        // Silencieux : InsightMessage est un bonus, pas critique
        console.log('InsightMessage erreur :', e.message);
    }
}

// ============================================================================
// OUVRIR LE DIALOG
// ============================================================================

function _openDialog(mode) {
    var item = _currentItem;
    if (!item) return;

    var subject = item.subject || '';
    var fromEmail = item.from ? item.from.emailAddress : '';
    var fromName = item.from ? item.from.displayName : '';
    var internetMessageId = item.internetMessageId || '';
    var hasAttachments = (item.attachments && item.attachments.length > 0) ? '1' : '0';

    var to = '';
    if (item.to && item.to.length > 0) {
        to = item.to.map(function (r) { return r.emailAddress; }).join(',');
    }
    var cc = '';
    if (item.cc && item.cc.length > 0) {
        cc = item.cc.map(function (r) { return r.emailAddress; }).join(',');
    }

    var dialogUrl = _backendUrl + '/plugin/dialog.html'
        + '?mode=' + encodeURIComponent(mode)
        + '&subject=' + encodeURIComponent(subject)
        + '&from=' + encodeURIComponent(fromEmail)
        + '&fromName=' + encodeURIComponent(fromName)
        + '&messageId=' + encodeURIComponent(internetMessageId)
        + '&hasAttachments=' + hasAttachments
        + '&to=' + encodeURIComponent(to)
        + '&cc=' + encodeURIComponent(cc);

    Office.context.ui.displayDialogAsync(
        dialogUrl,
        { width: 80, height: 74, promptBeforeOpen: false },
        function (asyncResult) {
            if (asyncResult.status === Office.AsyncResultStatus.Failed) {
                console.error('EasyMail dialog erreur :', asyncResult.error.message);
                return;
            }

            var dialog = asyncResult.value;

            // Envoyer le body du mail au dialog (Mode Perf. Réduite)
            item.body.getAsync(Office.CoercionType.Text, function(bodyResult) {
                if (bodyResult.status === Office.AsyncResultStatus.Succeeded && bodyResult.value) {
                    setTimeout(function() {
                        try {
                            dialog.messageChild(JSON.stringify({
                                action: 'mail_body',
                                body: bodyResult.value,
                                from_name: fromName,
                                from_email: fromEmail,
                            }));
                        } catch(e) {
                            console.log('EasyMail: messageChild non supporté');
                        }
                    }, 1000);
                }
            });

            dialog.addEventHandler(Office.EventType.DialogMessageReceived, function (arg) {
                try {
                    var msg = JSON.parse(arg.message);
                    if (msg.action === 'send_via_outlook') {
                        _sendViaOutlook(msg);
                    }
                } catch (e) {
                    console.error('Dialog message erreur :', e);
                }
            });

            dialog.addEventHandler(Office.EventType.DialogEventReceived, function () {
                // Dialog ferme
            });
        }
    );
}

// ============================================================================
// MODE PERFORMANCE REDUITE : envoyer via Outlook natif
// ============================================================================

function _sendViaOutlook(msg) {
    var item = _currentItem;
    if (!item) return;

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
                    .map(function (email) { return email.trim(); })
                    .filter(function (email) { return email.length > 0; })
                    .map(function (email) { return { emailAddress: email }; });
            }
            if (msg.subject) {
                formData.subject = msg.subject;
            }
            if (msg.cc) {
                formData.ccRecipients = msg.cc.replace(/;/g, ',').split(',')
                    .map(function (email) { return email.trim(); })
                    .filter(function (email) { return email.length > 0; })
                    .map(function (email) { return { emailAddress: email }; });
            }
            Office.context.mailbox.displayNewMessageForm(formData);
        }
    } catch (e) {
        console.error('EasyMail: erreur displayReplyForm:', e.message);
    }
}

// ============================================================================
// BACKEND : statut + profil contact
// ============================================================================

var _companionAvailable = false;

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

    // Détecter le Companion Windows (localhost:5051)
    _detectCompanion();
}

function _detectCompanion() {
    try {
        fetch('http://localhost:5051/status', {
            mode: 'cors',
            signal: AbortSignal.timeout(2000),
        })
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data && data.status === 'ok') {
                _companionAvailable = true;
                console.log('[taskpane] Companion detecte v' + (data.version || '?'));
            }
        })
        .catch(function () {
            _companionAvailable = false;
        });
    } catch (e) {
        _companionAvailable = false;
    }
}

function _loadContactProfile(email) {
    // Appel backend pour charger le profil contact (etape suivante)
    // Pour l'instant : placeholder
    fetch(_backendUrl + '/api/contact_profile/' + encodeURIComponent(email))
        .then(function (r) { return r.json(); })
        .then(function (data) {
            if (data && data.profile) {
                var p = data.profile;
                var org = p.organization || '';
                document.getElementById('contactOrg').textContent = org;

                var tagsHtml = '';
                if (p.register) {
                    tagsHtml += '<span class="tp-tag green">&#x2713; ' + _escapeHtml(p.register) + '</span>';
                }
                if (p.category) {
                    tagsHtml += '<span class="tp-tag orange">' + _escapeHtml(p.category) + '</span>';
                }
                document.getElementById('contactTags').innerHTML = tagsHtml;
            }
        })
        .catch(function () {
            // Pas de profil : pas grave, on affiche juste le nom
        });
}

// ============================================================================
// UTILITAIRES
// ============================================================================

function _getInitials(name) {
    if (!name) return '?';
    var parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
        return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    }
    return name[0].toUpperCase();
}

function _formatSize(bytes) {
    if (bytes < 1024) return bytes + ' o';
    if (bytes < 1024 * 1024) return Math.round(bytes / 1024) + ' Ko';
    return (bytes / (1024 * 1024)).toFixed(1) + ' Mo';
}

// ============================================================================
// SETUP WIZARD (12n)
// ============================================================================

function _checkSetup() {
    /** Vérifie si le setup est terminé. Si non, affiche le wizard. */
    fetch(_backendUrl + '/api/setup/status')
        .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function(data) {
            if (data.step === 'done') {
                // Setup terminé — ne rien afficher
                return;
            }
            _showSetupWizard(data.step || '2');
        })
        .catch(function() {
            // Backend down — ne pas bloquer
        });
}

function _setupPost(step, data, nextStep) {
    /** Helper : POST /api/setup/complete avec protection r.ok + catch */
    fetch(_backendUrl + '/api/setup/complete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({step: step, data: data || {}}),
    })
    .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); })
    .then(function() { _showSetupWizard(nextStep); })
    .catch(function(err) {
        console.error('[setup] Erreur etape ' + step + ':', err.message);
        // Continuer malgré l'erreur (le setup est non-bloquant)
        _showSetupWizard(nextStep);
    });
}

function _showSetupWizard(step) {
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('mailContent').style.display = 'none';
    document.getElementById('setupWizard').style.display = 'block';

    // Masquer toutes les étapes
    ['setupStep2', 'setupStep3', 'setupStep4', 'setupStep5', 'setupDone'].forEach(function(id) {
        document.getElementById(id).style.display = 'none';
    });

    // Afficher l'étape courante
    if (step === '1' || step === '2') {
        document.getElementById('setupStep2').style.display = 'block';
        document.getElementById('setupNext2').onclick = function() {
            var name = document.getElementById('setupName').value.trim();
            if (!name) { alert('Veuillez saisir votre nom.'); return; }
            _setupPost('2', {user_name: name}, '3');
        };
    } else if (step === '3') {
        // Détecter si Windows (Companion proposé)
        var isWindows = navigator.platform && navigator.platform.indexOf('Win') >= 0;
        if (!isWindows) {
            _setupPost('3', {companion_installed: false}, '4');
            return;
        }
        document.getElementById('setupStep3').style.display = 'block';
        document.getElementById('setupInstallCompanion').onclick = function() {
            alert('Telechargez le Companion depuis le site EasyMail, puis relancez le plugin.');
            _setupPost('3', {companion_installed: true}, '4');
        };
        document.getElementById('setupSkipCompanion').onclick = function() {
            _setupPost('3', {companion_installed: false}, '4');
        };
    } else if (step === '4') {
        document.getElementById('setupStep4').style.display = 'block';
        document.getElementById('setupActivateStandard').onclick = function() {
            window.open(_backendUrl + '/auth/login', '_blank');
            _setupPost('4', {}, '5');
        };
        document.getElementById('setupSkipStandard').onclick = function() {
            _setupPost('4', {}, '5');
        };
    } else if (step === '5') {
        document.getElementById('setupStep5').style.display = 'block';
        document.getElementById('setupStartOnboarding').onclick = function() {
            document.getElementById('setupStartOnboarding').style.display = 'none';
            document.getElementById('onboardingProgress').style.display = 'block';
            // Lancer l'onboarding
            fetch(_backendUrl + '/api/setup/onboarding', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
            }).then(function() {
                _pollOnboarding();
            });
        };
    } else if (step === 'done') {
        document.getElementById('setupDone').style.display = 'block';
        setTimeout(function() {
            document.getElementById('setupWizard').style.display = 'none';
            document.getElementById('emptyState').style.display = 'block';
        }, 3000);
    }
}

var _onboardingPollStart = 0;
var _onboardingPollFailures = 0;

function _pollOnboarding() {
    // Timeout global 10 min
    if (!_onboardingPollStart) _onboardingPollStart = Date.now();
    if (Date.now() - _onboardingPollStart > 10 * 60 * 1000) {
        document.getElementById('onboardingText').textContent = 'Timeout : analyse interrompue.';
        setTimeout(function() { _showSetupWizard('done'); }, 2000);
        return;
    }

    fetch(_backendUrl + '/api/setup/onboarding/status')
        .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function(data) {
            _onboardingPollFailures = 0;  // Reset compteur erreurs
            if (data.status === 'running') {
                var pct = data.total > 0 ? Math.round((data.indexed / data.total) * 100) : 0;
                document.getElementById('onboardingBar').style.width = pct + '%';
                document.getElementById('onboardingText').textContent = data.indexed + '/' + data.total + ' mails indexes';
                setTimeout(_pollOnboarding, 1000);
            } else if (data.status === 'done') {
                document.getElementById('onboardingBar').style.width = '100%';
                document.getElementById('onboardingText').textContent = 'Analyse terminee !';
                setTimeout(function() { _showSetupWizard('done'); }, 1500);
            } else if (data.status === 'no_mails') {
                document.getElementById('onboardingText').textContent = 'Aucun mail trouve. L\'analyse sera faite plus tard.';
                setTimeout(function() { _showSetupWizard('done'); }, 2000);
            } else {
                document.getElementById('onboardingText').textContent = 'Erreur : ' + (data.status || 'inconnue');
                setTimeout(function() { _showSetupWizard('done'); }, 2000);
            }
        })
        .catch(function() {
            _onboardingPollFailures++;
            if (_onboardingPollFailures > 5) {
                document.getElementById('onboardingText').textContent = 'Serveur indisponible. Relancez le plugin.';
                return;
            }
            setTimeout(_pollOnboarding, 2000);
        });
}


function _escapeHtml(str) {
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}


// ============================================================================
// PAGE PROFIL (12m)
// ============================================================================

function _showProfilSection() {
    // Masquer le contenu mail, afficher le profil
    document.getElementById('mailContent').style.display = 'none';
    document.getElementById('emptyState').style.display = 'none';
    document.getElementById('profilSection').style.display = 'block';

    // Charger les données
    _loadProfilData();
}

function _hideProfilSection() {
    document.getElementById('profilSection').style.display = 'none';
    // Restaurer le contenu mail
    if (_currentItem) {
        document.getElementById('mailContent').style.display = 'block';
    } else {
        document.getElementById('emptyState').style.display = 'block';
    }
}

function _loadProfilData() {
    // Mode EasyMail
    fetch(_backendUrl + '/api/status')
        .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function(data) {
            var modeDiv = document.getElementById('profilMode');
            var btnActivate = document.getElementById('btnActiverStandard');
            if (data.mode === 'standard' && data.authenticated) {
                modeDiv.innerHTML = '&#x2705; Mode Standard (actif)';
                modeDiv.style.borderLeftColor = '#4caf50';
                btnActivate.style.display = 'none';
            } else {
                modeDiv.innerHTML = '&#x26a0; Mode Performance Reduite';
                modeDiv.style.borderLeftColor = '#ff9800';
                btnActivate.style.display = 'block';
                btnActivate.onclick = function() {
                    window.open(_backendUrl + '/auth/login?return_url=' + encodeURIComponent(_backendUrl + '/plugin/taskpane.html'), '_blank');
                };
            }
        })
        .catch(function() {
            document.getElementById('profilMode').innerHTML = 'Erreur de connexion';
        });

    // Modèle IA actif
    fetch(_backendUrl + '/api/ai_model')
        .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function(data) {
            if (data.model) {
                var radios = document.querySelectorAll('input[name="aiModel"]');
                radios.forEach(function(radio) {
                    radio.checked = (radio.value === data.model);
                });
            }
        })
        .catch(function() {});

    // Nom utilisateur
    fetch(_backendUrl + '/api/settings/user_name')
        .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function(data) {
            if (data.value) {
                document.getElementById('profilUserName').value = data.value;
            }
        })
        .catch(function() {});
}

function _changeAIModel(model) {
    var statusDiv = document.getElementById('aiModelStatus');
    fetch(_backendUrl + '/api/ai_model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: model }),
    })
    .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function(data) {
        if (data.status === 'ok') {
            statusDiv.textContent = 'Sauvegarde !';
            statusDiv.style.display = 'block';
            setTimeout(function() { statusDiv.style.display = 'none'; }, 2000);
        }
    })
    .catch(function() {
        statusDiv.textContent = 'Erreur de sauvegarde';
        statusDiv.style.color = '#c00';
        statusDiv.style.display = 'block';
    });
}

function _saveUserName(name) {
    fetch(_backendUrl + '/api/save_setting', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'user_name', value: name.trim() }),
    })
    .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
    .then(function(data) {
        if (data.status === 'ok') {
            console.log('[taskpane] Nom sauvegarde : ' + name);
        }
    })
    .catch(function() {});
}
