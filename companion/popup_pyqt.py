"""
BoosterMail — Popup PyQt6 (Phase 3)
Conteneur QWebEngineView pour l'overlay (popup.html) et le dialog (dialog.html).

Architecture :
- Demarre directement en overlay (haut droite) avec barre de progression
- Barre de progression → warmup backend → transition vers popup.html
- QWebEngineView cache charge dialog.html?standalone=1 (Etat 2, pre-charge O7)
- Certificat auto-signe localhost accepte (P10)
- Communication popup.html → PyQt via URL scheme easymail://
- Detection fermeture Outlook → arret automatique

Dependances : PyQt6, PyQt6-WebEngine
Installation : pip install PyQt6 PyQt6-WebEngine
"""

import sys
import json
import logging
import ssl
import threading
import time
import urllib.request
from urllib.parse import unquote

from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout,
                              QWidget, QStackedWidget, QLabel, QProgressBar)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

logging.basicConfig(level=logging.INFO, format='%(asctime)s [popup-pyqt] %(levelname)s — %(message)s')
logger = logging.getLogger('popup-pyqt')

BACKEND_URL = 'https://localhost:3443'
POPUP_URL = f'{BACKEND_URL}/plugin/popup.html?container=pyqt'
DIALOG_URL = f'{BACKEND_URL}/plugin/dialog.html?standalone=1'


# =============================================================================
# PAGE PERSONNALISEE — accepte le certificat auto-signe localhost (P10)
# =============================================================================

class LocalhostPage(QWebEnginePage):
    easymail_action = None

    def certificateError(self, error):
        url = error.url()
        if url.host() in ('localhost', '127.0.0.1'):
            error.acceptCertificate()
            return
        error.rejectCertificate()

    def createWindow(self, window_type):
        """Intercepte window.open() — ouvre dans le navigateur systeme (BUG 1)."""
        page = QWebEnginePage(self.profile(), self)
        def _open_and_cleanup(url):
            self._open_in_browser(url)
            page.deleteLater()  # P8 : eviter fuite memoire
        page.urlChanged.connect(_open_and_cleanup)
        return page

    def _open_in_browser(self, url):
        """Ouvre l'URL dans le navigateur par defaut."""
        if url.scheme() in ('http', 'https'):
            logger.info(f"window.open intercepte → navigateur systeme : {url.toString()}")
            QDesktopServices.openUrl(url)

    def acceptNavigationRequest(self, url, nav_type, is_main_frame):
        if url.scheme() == 'easymail':
            if self.easymail_action:
                path = url.host()
                mode = url.path().lstrip('/')
                self.easymail_action(path, mode)
            return False
        return True


# =============================================================================
# FENETRE PRINCIPALE
# =============================================================================

class EasyMailPopup(QMainWindow):

    def __init__(self, direct_dialog_params=None):
        """
        direct_dialog_params : dict optionnel { mode, messageId, subject, fromName, fromEmail, to, cc }
            Si fourni → mode "direct dialog" (New Outlook) : skip overlay+warmup, ouvre directement le dialog
            Si None → mode normal (Classic) : overlay + warmup + dialog sur clic
        """
        super().__init__()
        self.setWindowTitle('BoosterMail')

        self._direct_mode = direct_dialog_params is not None

        # Mode direct : fenêtre centrale sans StaysOnTop (fenêtre normale redimensionnable)
        # Mode overlay : petite fenêtre haut-droite toujours au-dessus
        if self._direct_mode:
            self.setWindowFlags(Qt.WindowType.Window)
        else:
            self.setWindowFlags(
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )

        self._screen = QApplication.primaryScreen().availableGeometry()
        self._overlay_w = min(max(int(self._screen.width() * 0.22), 280), 380)
        self._overlay_h = int(self._screen.height() * 0.31)

        # --- Layout principal ---
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        if self._direct_mode:
            # --- MODE DIRECT (New Outlook) : juste le dialog, plein écran ---
            self._dialog_view = QWebEngineView()
            self._dialog_page = LocalhostPage(QWebEngineProfile.defaultProfile(), self._dialog_view)
            self._dialog_view.setPage(self._dialog_page)
            self._dialog_page.easymail_action = self._on_easymail_action
            self._stack.addWidget(self._dialog_view)

            # Construire l'URL du dialog avec les params
            from urllib.parse import urlencode
            query = {'standalone': '1', **{k: v for k, v in direct_dialog_params.items() if v}}
            dialog_url = f'{BACKEND_URL}/plugin/dialog.html?' + urlencode(query)
            self._dialog_view.load(QUrl(dialog_url))
            self._stack.setCurrentIndex(0)

            # Fenêtre centrée, 80% écran (comme le dialog Office.js)
            w = min(1200, int(self._screen.width() * 0.80))
            h = min(800, int(self._screen.height() * 0.80))
            self.resize(w, h)
            self.move((self._screen.width() - w) // 2, (self._screen.height() - h) // 2)

            # Timer detection fermeture Outlook (même comportement qu'en overlay)
            self._outlook_check_timer = QTimer()
            self._outlook_check_timer.timeout.connect(self._check_outlook_alive)
            self._outlook_fail_count = 0
            self._outlook_check_timer.start(5000)

            logger.info(f"PyQt direct dialog — mode={direct_dialog_params.get('mode', 'reply')}")
            return

        # --- MODE OVERLAY (Classic/fallback) : 3 vues stackées ---

        # --- Vue 0 : Ecran chargement (barre de progression) ---
        self._loading = self._build_loading_screen()
        self._stack.addWidget(self._loading)

        # --- Vue 1 : popup.html (Etat 1 — overlay) ---
        self._popup_view = QWebEngineView()
        self._popup_page = LocalhostPage(QWebEngineProfile.defaultProfile(), self._popup_view)
        self._popup_view.setPage(self._popup_page)
        self._popup_page.easymail_action = self._on_easymail_action
        self._stack.addWidget(self._popup_view)

        # --- Vue 2 : dialog.html (Etat 2, pre-charge O7) ---
        self._dialog_view = QWebEngineView()
        self._dialog_page = LocalhostPage(QWebEngineProfile.defaultProfile(), self._dialog_view)
        self._dialog_view.setPage(self._dialog_page)
        self._dialog_page.easymail_action = self._on_easymail_action
        self._stack.addWidget(self._dialog_view)

        # --- TOUJOURS positionner en haut a droite (pas de restore geometry) ---
        self._stack.setCurrentIndex(0)
        self.resize(self._overlay_w, self._overlay_h)
        self.move(self._screen.width() - self._overlay_w, 48)

        # --- Timer detection fermeture Outlook ---
        self._outlook_check_timer = QTimer()
        self._outlook_check_timer.timeout.connect(self._check_outlook_alive)
        self._outlook_fail_count = 0

        logger.info("Overlay PyQt demarre — phase chargement")

        # Lancer le warmup automatiquement
        self._start_warmup()

    # =========================================================================
    # ECRAN DE CHARGEMENT
    # =========================================================================

    def _build_loading_screen(self):
        """Ecran de chargement : barre de progression + noms des mails."""
        widget = QWidget()
        widget.setStyleSheet('background: #fff;')
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(15, 12, 15, 12)
        layout.setSpacing(8)

        # Logo compact
        logo = QLabel('\u2709 BoosterMail')
        logo.setStyleSheet('font-size: 14px; font-weight: 700; color: #0F6CBD; padding: 0;')
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        # Barre de progression
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(6)
        self._progress_bar.setStyleSheet(
            'QProgressBar { background: #E8E8E8; border: none; border-radius: 3px; }'
            'QProgressBar::chunk { background: #0F6CBD; border-radius: 3px; }'
        )
        layout.addWidget(self._progress_bar)

        self._progress_label = QLabel('Chargement des mails...')
        self._progress_label.setStyleSheet('font-size: 10px; color: #0F6CBD; padding: 0;')
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_label.setWordWrap(True)
        layout.addWidget(self._progress_label)

        self._mail_label = QLabel('')
        self._mail_label.setStyleSheet('font-size: 9px; color: #999; padding: 0; font-style: italic;')
        self._mail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mail_label.setWordWrap(True)
        layout.addWidget(self._mail_label)

        layout.addStretch()
        return widget

    # =========================================================================
    # WARMUP (chargement des mails au demarrage)
    # =========================================================================

    def _start_warmup(self):
        """Demarre le warmup automatiquement."""
        logger.info("Phase chargement — warmup")

        # Etat partage avec le thread reseau (thread-safe via GIL)
        self._wp = {
            'started': False, 'pct': 0, 'label': 'Connexion au serveur...',
            'subject': '', 'done': False
        }

        # Thread reseau (ne bloque JAMAIS le thread Qt)
        threading.Thread(target=self._warmup_worker, daemon=True).start()

        # Timer Qt : met a jour l'UI toutes les 300ms + coupe a 10s max
        self._warmup_elapsed = 0
        self._warmup_timer = QTimer()
        self._warmup_timer.setInterval(300)
        self._warmup_timer.timeout.connect(self._update_warmup_ui)
        self._warmup_timer.start()

        # Timer detection fermeture Outlook
        self._outlook_check_timer.start(5000)

    def _warmup_worker(self):
        """Thread reseau : lance le warmup + poll la progression. Ne touche JAMAIS l'UI."""
        try:
            self._warmup_worker_impl()
        except Exception as e:
            # P4 : catch global — le thread ne doit JAMAIS mourir silencieusement
            logger.error(f"Warmup worker crash: {e}")
            self._wp['pct'] = 100
            self._wp['label'] = 'Pret !'
            self._wp['done'] = True

    def _warmup_worker_impl(self):
        """Implementation du worker warmup (separee pour le try/except global)."""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        # Etape 1 : attendre que le backend soit pret + lancer le warmup
        for _ in range(20):  # 20 x 0.5s = 10s max
            if self._wp['done']:
                return
            try:
                req = urllib.request.Request(
                    f'{BACKEND_URL}/api/warmup_inbox',
                    data=b'{}',
                    headers={'Content-Type': 'application/json'},
                    method='POST'
                )
                urllib.request.urlopen(req, context=ctx, timeout=1)
                self._wp['started'] = True
                self._wp['label'] = 'Chargement des mails...'
                logger.info("Warmup lance")
                break
            except Exception:
                self._wp['label'] = 'Demarrage du serveur...'
                self._wp['pct'] = min(20, self._wp['pct'] + 2)
                time.sleep(0.5)

        # Etape 2 : poll la progression
        for _ in range(40):  # 40 x 0.25s = 10s max
            if self._wp['done']:
                return
            try:
                resp = urllib.request.urlopen(
                    f'{BACKEND_URL}/api/warmup_inbox/progress', context=ctx, timeout=1
                )
                data = json.loads(resp.read().decode('utf-8'))
                status = data.get('status', 'idle')
                loaded = data.get('loaded', 0)
                total = data.get('total', 10) or 10
                subject = data.get('current_subject', '')

                self._wp['pct'] = min(95, int(25 + (loaded / total) * 70))
                self._wp['label'] = f'{loaded}/{total} mails charges'
                if subject:
                    self._wp['subject'] = subject if len(subject) <= 45 else subject[:42] + '...'

                # P15 : detecter done ET error
                if status in ('done', 'error'):
                    self._wp['pct'] = 100
                    self._wp['label'] = 'Pret !' if status == 'done' else 'Chargement partiel'
                    self._wp['done'] = True
                    return
            except Exception:
                pass
            time.sleep(0.25)

    def _update_warmup_ui(self):
        """Timer Qt (300ms) : met a jour l'UI depuis l'etat partage. Coupe a 10s max."""
        self._warmup_elapsed += 300

        # Mettre a jour l'UI
        self._progress_bar.setValue(self._wp['pct'])
        self._progress_label.setText(self._wp['label'])
        if self._wp['subject']:
            self._mail_label.setText(self._wp['subject'])

        # Warmup termine → transition
        if self._wp['done']:
            self._warmup_timer.stop()
            QTimer.singleShot(400, self._transition_to_overlay)
            return

        # 10s max → transition forcee avec animation finale (P12)
        if self._warmup_elapsed >= 10000:
            self._wp['done'] = True
            self._wp['pct'] = 100
            self._wp['label'] = 'Pret !'
            self._progress_bar.setValue(100)
            self._progress_label.setText('Pret !')
            self._warmup_timer.stop()
            QTimer.singleShot(400, self._transition_to_overlay)

    def _transition_to_overlay(self):
        """Bascule vers popup.html (overlay). Pas de repositionnement — deja en haut a droite."""
        logger.info("Transition vers overlay")
        self._popup_view.load(QUrl(POPUP_URL))
        self._stack.setCurrentIndex(1)

        # Pre-charger le dialog (O7)
        self._dialog_view.load(QUrl(DIALOG_URL + '&mode=reply'))
        logger.info("Dialog pre-charge (O7)")

    # =========================================================================
    # DETECTION FERMETURE OUTLOOK (BUG 2)
    # =========================================================================

    def _check_outlook_alive(self):
        """Detecte si Outlook tourne encore. Sinon ferme la popup."""
        if _is_outlook_running():
            self._outlook_fail_count = 0
            return
        self._outlook_fail_count += 1
        if self._outlook_fail_count >= 2:
            logger.info("Outlook ferme depuis 10s — fermeture automatique popup")
            self.close()

    # =========================================================================
    # NAVIGATION easymail:// (A6)
    # =========================================================================

    def _on_easymail_action(self, path, mode):
        mode = unquote(mode) if mode else 'reply'
        logger.info(f"Action easymail://{path}/{mode}")
        if path in ('compose', 'open-dialog'):
            self._open_dialog(mode)
        elif path == 'close-dialog':
            self._close_dialog()

    def _open_dialog(self, mode='reply'):
        logger.info(f"Ouverture dialog mode={mode}")
        dialog_url = f'{DIALOG_URL}&mode={mode}'
        self._dialog_view.load(QUrl(dialog_url))

        # Sauvegarder la geometrie overlay AVANT de redimensionner
        self._overlay_geometry_backup = (self.size().width(), self.size().height(),
                                         self.pos().x(), self.pos().y())

        w = min(1200, self._screen.width() - 40)
        h = min(800, self._screen.height() - 40)
        self.resize(w, h)
        self.move(
            (self._screen.width() - w) // 2,
            (self._screen.height() - h) // 2
        )
        self._stack.setCurrentIndex(2)
        try:
            self._dialog_page.urlChanged.disconnect(self._on_dialog_url_changed)
        except TypeError:
            pass
        self._dialog_page.urlChanged.connect(self._on_dialog_url_changed)

    def _on_dialog_url_changed(self, url):
        if url.toString() == 'about:blank':
            self._close_dialog()

    def _close_dialog(self):
        logger.info("Fermeture dialog, retour overlay")
        # Restaurer la geometrie overlay
        if hasattr(self, '_overlay_geometry_backup') and self._overlay_geometry_backup:
            w, h, x, y = self._overlay_geometry_backup
            self.resize(w, h)
            self.move(x, y)
        else:
            self.resize(self._overlay_w, self._overlay_h)
            self.move(self._screen.width() - self._overlay_w, 48)
        self._stack.setCurrentIndex(1)

    def closeEvent(self, event):
        # P9 : stopper TOUS les timers pour eviter segfault
        if hasattr(self, '_outlook_check_timer'):
            self._outlook_check_timer.stop()
        if hasattr(self, '_warmup_timer'):
            self._warmup_timer.stop()
        # P2 : signaler au thread worker de s'arreter
        if hasattr(self, '_wp'):
            self._wp['done'] = True
        event.accept()
        # Mode direct : quitter l'application quand la fenêtre se ferme
        if getattr(self, '_direct_mode', False):
            QApplication.quit()


# =============================================================================
# DETECTION OUTLOOK
# =============================================================================

def _is_outlook_running():
    """Detecte si Outlook (New ou Classic) tourne — methode rapide via ctypes."""
    import ctypes
    from ctypes import wintypes

    TH32CS_SNAPPROCESS = 0x00000002
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ('dwSize', wintypes.DWORD),
            ('cntUsage', wintypes.DWORD),
            ('th32ProcessID', wintypes.DWORD),
            ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)),
            ('th32ModuleID', wintypes.DWORD),
            ('cntThreads', wintypes.DWORD),
            ('th32ParentProcessID', wintypes.DWORD),
            ('pcPriClassBase', ctypes.c_long),
            ('dwFlags', wintypes.DWORD),
            ('szExeFile', ctypes.c_char * 260),
        ]

    kernel32 = ctypes.windll.kernel32
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return False

    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
    targets = {b'olk.exe', b'outlook.exe'}

    try:
        if kernel32.Process32First(snapshot, ctypes.byref(pe)):
            while True:
                name = pe.szExeFile.lower().strip(b'\x00')
                if name in targets:
                    return True
                if not kernel32.Process32Next(snapshot, ctypes.byref(pe)):
                    break
    finally:
        kernel32.CloseHandle(snapshot)
    return False


# =============================================================================
# POINT D'ENTREE
# =============================================================================

def main():
    """
    Usage :
      python popup_pyqt.py                          → mode overlay (Classic, démarrage)
      python popup_pyqt.py --direct-dialog --mode=reply --messageId=xxx --subject="..." ...
                                                    → mode direct dialog (New Outlook, clic bouton)
    """
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--direct-dialog', action='store_true',
                        help='Ouvre directement le dialog (skip overlay+warmup)')
    parser.add_argument('--mode', default='reply',
                        help='Mode du dialog : reply/reply_all/forward/new')
    parser.add_argument('--messageId', default='')
    parser.add_argument('--subject', default='')
    parser.add_argument('--fromName', default='')
    parser.add_argument('--fromEmail', default='')
    parser.add_argument('--from', dest='from_addr', default='')
    parser.add_argument('--to', default='')
    parser.add_argument('--cc', default='')
    parser.add_argument('--hasAttachments', default='0')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName('BoosterMail')
    app.setOrganizationName('BoosterMail')
    app.setStyle('Fusion')

    # Cache : on ne touche PAS au profil WebEngine (ni clearHttpCache ni NoCache).
    # Toute manipulation du cache casse la session SSL du cert auto-signé localhost
    # (observé : dialog blanc, aucune requête atteint V2).
    # Le Cache-Control: no-cache cote V2 (commit 3461fc5) suffit à forcer le rechargement
    # des assets JS/CSS/HTML à chaque ouverture du dialog.

    if args.direct_dialog:
        # Mode New Outlook : dialog direct, pas d'overlay
        direct_params = {
            'mode': args.mode,
            'messageId': args.messageId,
            'subject': args.subject,
            'fromName': args.fromName,
            'fromEmail': args.fromEmail or args.from_addr,
            'from': args.from_addr or args.fromEmail,
            'to': args.to,
            'cc': args.cc,
            'hasAttachments': args.hasAttachments,
        }
        popup = EasyMailPopup(direct_dialog_params=direct_params)
        popup.show()
        popup.raise_()
        popup.activateWindow()

        # Forcer la fenêtre au PREMIER PLAN (devant Outlook).
        # Sur Windows, popup.raise_() ne suffit pas car un autre process (Outlook)
        # a le focus → trick : activer brièvement WindowStaysOnTopHint puis le retirer.
        def _bring_to_front():
            try:
                popup.setWindowFlags(popup.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
                popup.show()
                popup.raise_()
                popup.activateWindow()
                # Retirer le flag 200ms plus tard pour que la fenêtre soit focusable
                # normalement et passe derrière si l'utilisateur clique ailleurs
                def _clear_topmost():
                    popup.setWindowFlags(popup.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
                    popup.show()
                QTimer.singleShot(200, _clear_topmost)

                # Windows : force SetForegroundWindow via Win32 API (ultime recours)
                if sys.platform == 'win32':
                    try:
                        import ctypes
                        hwnd = int(popup.winId())
                        # ASFW_ANY : autorise tout process à prendre le foreground
                        ctypes.windll.user32.AllowSetForegroundWindow(-1)
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                    except Exception as _e:
                        logger.debug(f"SetForegroundWindow failed: {_e}")
            except Exception as e:
                logger.error(f"_bring_to_front: {e}")

        QTimer.singleShot(50, _bring_to_front)
        logger.info(f"PyQt direct dialog visible — mode={args.mode}")
    else:
        # Mode overlay classique
        popup = EasyMailPopup()
        popup.show()
        logger.info(f"Overlay PyQt visible — backend: {BACKEND_URL}")

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
