"""
BoosterMail — Overlay (PyQt6, fenetre NORMALE)
Fenetre standard Windows = drag, resize, close, minimize NATIFS.
Charge popup.html dans un QWebEngineView.
Se repositionne sur la fenetre Outlook toutes les 250ms.
"""
import os
import sys
import ctypes
import ctypes.wintypes as wintypes
import logging

from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile

EASYMAIL_DIR = os.path.dirname(os.path.abspath(__file__))
POPUP_URL = 'https://localhost:3443/plugin/popup.html?container=pyqt'
LOG_FILE = os.path.join(EASYMAIL_DIR, 'boostermail.log')

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s [overlay] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger('overlay')
try:
    sys.stdout.write('')
    logger.addHandler(logging.StreamHandler(sys.stdout))
except Exception:
    pass

user32 = ctypes.windll.user32

# Position et taille en % de la fenetre Outlook
X_PCT = 0.72    # 72% depuis la gauche = colle a droite
Y_PCT = 0.10    # 10% depuis le haut = sous le ruban
W_PCT = 0.28    # 28% de la largeur
H_PCT = 0.30    # 30% de la hauteur
W_MIN, W_MAX = 280, 420
H_MIN, H_MAX = 180, 400


# =============================================================================
# ACCEPTER LE CERTIFICAT AUTO-SIGNE
# =============================================================================
class LocalhostPage(QWebEnginePage):
    """Accepte le certificat auto-signe de localhost:3443."""
    def certificateError(self, error):
        error.acceptCertificate()
        return True


# =============================================================================
# DETECTION FENETRE OUTLOOK
# =============================================================================
def find_outlook_hwnd():
    """Trouve le HWND de la fenetre Outlook principale visible."""
    # Classic Outlook
    hwnd = user32.FindWindowW('rctrl_renwnd32', None)
    if hwnd and user32.IsWindowVisible(hwnd):
        return hwnd
    # New Outlook (par titre)
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int))
    result = [None]
    def callback(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.lower()
                if 'outlook' in title or 'boite de reception' in title or 'inbox' in title:
                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))
                    w = rect.right - rect.left
                    h = rect.bottom - rect.top
                    if w > 400 and h > 300:
                        result[0] = hwnd
                        return False
        return True
    _cb = EnumWindowsProc(callback)
    user32.EnumWindows(_cb, 0)
    return result[0]


def get_window_rect(hwnd):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def calc_overlay_geo(outlook_rect):
    ox, oy, ow, oh = outlook_rect
    x = ox + int(ow * X_PCT)
    y = oy + int(oh * Y_PCT)
    w = max(W_MIN, min(W_MAX, int(ow * W_PCT)))
    h = max(H_MIN, min(H_MAX, int(oh * H_PCT)))
    return (x, y, w, h)


# =============================================================================
# OVERLAY WINDOW
# =============================================================================
class OverlayWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle('BoosterMail')
        # Fenetre NORMALE : drag, resize, close, minimize = tout natif Windows
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool  # Pas dans la barre des taches
        )

        # WebView pour charger popup.html
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        self._web = QWebEngineView()
        self._page = LocalhostPage(QWebEngineProfile.defaultProfile(), self._web)
        self._web.setPage(self._page)
        layout.addWidget(self._web)

        # Etat
        self._outlook_hwnd = None
        self._last_geo = None
        self._user_moved = False

        # Position initiale
        self._outlook_hwnd = find_outlook_hwnd()
        if self._outlook_hwnd:
            geo = calc_overlay_geo(get_window_rect(self._outlook_hwnd))
            self.setGeometry(*geo)
            self._last_geo = geo
            logger.info(f"Outlook detecte (hwnd={self._outlook_hwnd}), overlay {geo}")
        else:
            self.setGeometry(500, 100, 380, 250)
            logger.info("Outlook pas visible, position par defaut")

        # Charger popup.html
        self._web.load(QUrl(POPUP_URL))

        # Timer 250ms : suivre Outlook
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(250)

        logger.info("Overlay demarre")

    def moveEvent(self, event):
        """Detecte si l'utilisateur deplace manuellement l'overlay."""
        super().moveEvent(event)
        # Si le move ne vient pas de notre timer, c'est l'utilisateur
        if self._last_geo:
            expected_x, expected_y = self._last_geo[0], self._last_geo[1]
            actual = self.pos()
            if abs(actual.x() - expected_x) > 5 or abs(actual.y() - expected_y) > 5:
                self._user_moved = True

    def _tick(self):
        """Appelé toutes les 250ms : suit Outlook."""
        # Chercher Outlook si pas encore trouve
        if not self._outlook_hwnd:
            hwnd = find_outlook_hwnd()
            if hwnd:
                self._outlook_hwnd = hwnd
                self._user_moved = False
                logger.info(f"Outlook detecte (hwnd={hwnd})")
            else:
                return

        # Outlook ferme ?
        if not user32.IsWindow(self._outlook_hwnd):
            self._outlook_hwnd = None
            self.hide()
            logger.info("Outlook ferme, overlay cache")
            return

        # Outlook minimise ?
        if user32.IsIconic(self._outlook_hwnd):
            if self.isVisible():
                self.hide()
            return

        # Outlook visible → montrer l'overlay
        if not self.isVisible():
            self.show()

        # Si l'utilisateur a deplace manuellement, ne pas repositionner
        if self._user_moved:
            return

        # Recalculer et repositionner si Outlook a bouge/resize
        rect = get_window_rect(self._outlook_hwnd)
        geo = calc_overlay_geo(rect)
        if geo != self._last_geo:
            x, y, w, h = geo
            self.setGeometry(x, y, w, h)
            self._last_geo = geo


def main():
    app = QApplication(sys.argv)
    overlay = OverlayWindow()
    overlay.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
