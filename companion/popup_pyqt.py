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

from PyQt6.QtCore import Qt, QUrl, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal, QObject
from PyQt6.QtGui import QDesktopServices, QFont, QLinearGradient, QPalette, QColor, QBrush
from PyQt6.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QHBoxLayout,
                              QWidget, QStackedWidget, QLabel, QProgressBar,
                              QPushButton, QGraphicsOpacityEffect, QSizePolicy)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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
        # Dimensions élargies pour le CTA marketing (user pas activé)
        self._marketing_w = min(max(int(self._screen.width() * 0.30), 420), 520)
        self._marketing_h = min(max(int(self._screen.height() * 0.55), 420), 560)

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

        # --- Détection du mode d'activation (Plan 3 §9.3) ---
        # 4 modes : flash / warmup / marketing / marketing_warmup
        self._activation_mode = _fetch_activation_mode()
        logger.info(f"Mode popup détecté : {self._activation_mode}")

        # --- Vue 0 : Ecran chargement (adapté au mode) ---
        self._loading = self._build_loading_screen(self._activation_mode)
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

        # --- Positionnement : popup de lancement toujours centrée ---
        # Audit 20/04 : la popup de lancement (tous modes) est centrée et
        # grande pour être visible avec les boutons Annuler/Lancer.
        # Après clic "Lancer" → _transition_to_overlay redimensionne en
        # overlay discret haut-droite.
        self._stack.setCurrentIndex(0)
        self.resize(self._marketing_w, self._marketing_h)
        self.move(
            (self._screen.width() - self._marketing_w) // 2,
            (self._screen.height() - self._marketing_h) // 2,
        )

        # --- Timer detection fermeture Outlook ---
        self._outlook_check_timer = QTimer()
        self._outlook_check_timer.timeout.connect(self._check_outlook_alive)
        self._outlook_fail_count = 0

        logger.info(f"Overlay PyQt demarre — mode={self._activation_mode}")

        # --- Dispatch selon le mode ---
        if self._activation_mode == 'flash':
            # Cache chaud — popup de lancement + barre rapide (~2,5 s).
            # Pas de vrai warmup (pas besoin : prefetch_cache_v2.json < 48h).
            # L'animation rapide donne un feedback visible sans faire attendre.
            self._outlook_check_timer.start(5000)
            self._start_flash_animation()
        elif self._activation_mode == 'marketing':
            # Pas activé + cache chaud : pas de warmup, on attend le clic user
            self._outlook_check_timer.start(5000)
        else:
            # 'warmup' ou 'marketing_warmup' → warmup normal en arrière-plan
            self._start_warmup()

    # =========================================================================
    # ECRAN DE CHARGEMENT (dispatcher 4 modes — Plan 3 §9.3)
    # =========================================================================

    def _build_loading_screen(self, mode='warmup'):
        """
        4 modes :
          - 'flash'           : user activé + cache chaud → popup warmup + barre rapide (~2 s)
          - 'warmup'          : user activé + cache froid → popup warmup + barre ~8 s
          - 'marketing'       : user pas activé + cache chaud → CTA bloquant
          - 'marketing_warmup': user pas activé + cache froid → CTA + barre en bas
        Crée les widgets `_progress_bar`, `_progress_label`, `_mail_label` dans
        tous les modes (le code de warmup suppose leur existence).

        Correction audit 20/04 : flash utilise maintenant le même design que
        warmup (popup de lancement + barre de progression) pour donner un
        feedback visible, juste avec un remplissage plus rapide quand cache
        chaud (~2 s au lieu de ~8 s).
        """
        if mode == 'marketing':
            return self._build_marketing_screen(with_warmup=False)
        if mode == 'marketing_warmup':
            return self._build_marketing_screen(with_warmup=True)
        # mode flash et warmup partagent le même design — différence = durée bar
        return self._build_warmup_screen()

    # -------- Mode WARMUP (user activé) — design moderne --------------------

    def _build_warmup_screen(self):
        """
        Popup de lancement moderne (audit 20/04, suite retour utilisateur
        "l'actuelle est horrible"). Carte blanche, gradient subtil, 2 boutons
        Annuler/Lancer. Le warmup tourne en BG pendant que user décide.
        Clic Lancer → transition dialog. Clic Annuler → close popup.
        """
        widget = QWidget()
        widget.setStyleSheet(
            'QWidget#root { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,'
            ' stop:0 #f8fafc, stop:1 #eef2ff);'
            ' border: 1px solid #cbd5e1; border-radius: 12px; }'
        )
        widget.setObjectName('root')
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(14, 14, 14, 14)

        # Carte blanche avec ombre visuelle (border-radius 14px)
        card = QWidget()
        card.setObjectName('wCard')
        card.setStyleSheet(
            '#wCard { background: white; border-radius: 14px;'
            ' border: 1px solid #e2e8f0; }'
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 16)
        card_layout.setSpacing(10)

        # Pastille logo (gradient bleu → violet)
        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon = QLabel('✉')
        icon.setFixedSize(52, 52)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            'QLabel { color: white; font-size: 22px; font-family: "Segoe UI";'
            ' border-radius: 26px;'
            ' background: qlineargradient(x1:0, y1:0, x2:1, y2:1,'
            ' stop:0 #0F6CBD, stop:1 #5B4FBF); }'
        )
        icon_row.addWidget(icon)
        icon_row.addStretch()
        card_layout.addLayout(icon_row)

        # Titre
        title = QLabel('BoosterMail')
        title.setStyleSheet(
            'font-family: "Segoe UI"; font-size: 20px; font-weight: 700;'
            ' color: #1a1a2e; padding-top: 4px; letter-spacing: 0.2px;'
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        # Sous-titre rassurant
        sub = QLabel('Votre assistant email intelligent')
        sub.setStyleSheet(
            'font-family: "Segoe UI"; font-size: 11px; color: #64748B;'
        )
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(sub)

        card_layout.addSpacing(4)

        # Barre de progression (visible dès l'affichage — travail en BG)
        self._progress_bar = self._make_progress_bar()
        card_layout.addWidget(self._progress_bar)

        self._progress_label = QLabel('Préparation en arrière-plan…')
        self._progress_label.setStyleSheet(
            'font-family: "Segoe UI"; font-size: 10px; color: #0F6CBD;'
            ' padding-top: 2px;'
        )
        self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress_label.setWordWrap(True)
        card_layout.addWidget(self._progress_label)

        self._mail_label = QLabel('')
        self._mail_label.setStyleSheet(
            'font-family: "Segoe UI"; font-size: 9px; color: #94A3B8;'
            ' font-style: italic;'
        )
        self._mail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mail_label.setWordWrap(True)
        card_layout.addWidget(self._mail_label)

        card_layout.addSpacing(6)

        # Boutons Annuler / Lancer
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_cancel = QPushButton('Annuler')
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet(
            'QPushButton { background: transparent; color: #64748B;'
            ' border: 1px solid #cbd5e1; border-radius: 18px;'
            ' font-family: "Segoe UI"; font-size: 12px; padding: 0 18px; }'
            'QPushButton:hover { background: #f1f5f9; color: #334155; }'
        )
        btn_cancel.clicked.connect(self.close)
        btn_row.addWidget(btn_cancel)

        btn_launch = QPushButton('Lancer')
        btn_launch.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_launch.setFixedHeight(36)
        btn_launch.setStyleSheet(
            'QPushButton {'
            '  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,'
            '    stop:0 #0F6CBD, stop:1 #5B4FBF);'
            '  color: white; border: none; border-radius: 18px;'
            '  font-family: "Segoe UI"; font-size: 12px; font-weight: 600;'
            '  padding: 0 22px;'
            '}'
            'QPushButton:hover { background: #0d5ca3; }'
            'QPushButton:pressed { background: #094a86; }'
        )
        btn_launch.clicked.connect(self._on_launch_click)
        btn_row.addWidget(btn_launch)

        card_layout.addLayout(btn_row)

        outer.addWidget(card)
        return widget

    def _on_launch_click(self):
        """Clic 'Lancer' : transition vers l'overlay (popup.html) haut-droite."""
        logger.info('[popup] Lancer cliqué → overlay popup.html')
        if hasattr(self, '_flash_timer') and self._flash_timer.isActive():
            self._flash_timer.stop()
        if hasattr(self, '_warmup_timer') and self._warmup_timer.isActive():
            self._warmup_timer.stop()
        self._transition_to_overlay()

    # -------- Mode FLASH (user activé, cache chaud) --------------------------

    def _build_flash_screen(self):
        """
        Splash de confirmation « BoosterMail prêt » — user activé + cache chaud.
        Affiché ~1500 ms (temps de perception humaine, correction audit 20/04)
        puis transition vers l'overlay popup.html.

        Design : large pastille verte animée (fade-in) + logo + texte centré.
        """
        widget = QWidget()
        widget.setStyleSheet(
            'QWidget { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,'
            ' stop:0 #ffffff, stop:1 #EAF4FC); }'
        )
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.addStretch()

        # Pastille verte avec check
        check_row = QHBoxLayout()
        check_row.addStretch()
        check = QLabel('✓')
        check.setFixedSize(48, 48)
        check.setAlignment(Qt.AlignmentFlag.AlignCenter)
        check.setStyleSheet(
            'background: #16A34A; color: white; border-radius: 24px;'
            ' font-size: 26px; font-weight: 700; font-family: "Segoe UI";'
        )
        check_row.addWidget(check)
        check_row.addStretch()
        layout.addLayout(check_row)

        layout.addSpacing(8)

        logo = QLabel('BoosterMail')
        logo.setStyleSheet(
            'font-family: "Segoe UI"; font-size: 18px; font-weight: 700;'
            ' color: #0F6CBD; letter-spacing: 0.3px;'
        )
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        ready = QLabel('est prêt')
        ready.setStyleSheet(
            'font-family: "Segoe UI"; font-size: 12px; color: #475569;'
            ' padding-top: 2px;'
        )
        ready.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ready)

        layout.addStretch()

        # Animation fade-in sur le widget (donne une sensation de "pop" léger)
        try:
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
            effect.setOpacity(0.0)
            anim = QPropertyAnimation(effect, b"opacity", widget)
            anim.setDuration(220)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()
            # Garder référence pour éviter GC prématuré
            self._flash_fade_anim = anim
        except Exception:
            pass

        # Widgets "factices" pour compatibilité avec le code warmup commun
        self._progress_bar = self._make_progress_bar()
        self._progress_bar.setValue(100)
        self._progress_bar.hide()
        self._progress_label = QLabel('')
        self._progress_label.hide()
        self._mail_label = QLabel('')
        self._mail_label.hide()
        return widget

    # -------- Mode MARKETING (user pas activé) -------------------------------

    def _build_marketing_screen(self, with_warmup=False):
        """
        Popup d'activation — design cohérent avec warmup (audit 20/04).
        Fond gradient doux (pas agressif), carte blanche, icone gradient,
        2 boutons Annuler/Activer en 2 min.
        """
        widget = QWidget()
        widget.setObjectName('root')
        widget.setStyleSheet(
            'QWidget#root { background: qlineargradient(x1:0, y1:0, x2:1, y2:1,'
            ' stop:0 #f8fafc, stop:1 #eef2ff); }'
        )
        outer = QVBoxLayout(widget)
        outer.setContentsMargins(18, 18, 18, 18)

        card = QWidget()
        card.setObjectName('mkCard')
        card.setStyleSheet(
            '#mkCard { background: white; border-radius: 14px;'
            ' border: 1px solid #e2e8f0; }'
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(26, 24, 26, 20)
        card_layout.setSpacing(10)

        # Icône pastille gradient (comme warmup)
        icon_row = QHBoxLayout()
        icon_row.addStretch()
        icon = QLabel('✉')
        icon.setFixedSize(56, 56)
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(
            'QLabel { color: white; font-size: 24px; font-family: "Segoe UI";'
            ' border-radius: 28px;'
            ' background: qlineargradient(x1:0, y1:0, x2:1, y2:1,'
            ' stop:0 #0F6CBD, stop:1 #5B4FBF); }'
        )
        icon_row.addWidget(icon)
        icon_row.addStretch()
        card_layout.addLayout(icon_row)

        title = QLabel('Bienvenue sur BoosterMail')
        title.setStyleSheet(
            'font-family: "Segoe UI"; font-size: 20px; font-weight: 700;'
            ' color: #1a1a2e; padding-top: 4px; letter-spacing: 0.2px;'
        )
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(title)

        baseline = QLabel('Répondez à vos mails 5× plus vite')
        baseline.setStyleSheet(
            'font-family: "Segoe UI"; font-size: 12px; color: #64748B;'
        )
        baseline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        baseline.setWordWrap(True)
        card_layout.addWidget(baseline)

        card_layout.addSpacing(2)

        # Barre de progression discrète si cache froid
        if with_warmup:
            self._progress_bar = self._make_progress_bar()
            card_layout.addWidget(self._progress_bar)

            self._progress_label = QLabel('Préparation en arrière-plan…')
            self._progress_label.setStyleSheet(
                'font-family: "Segoe UI"; font-size: 10px; color: #0F6CBD;'
            )
            self._progress_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(self._progress_label)

            self._mail_label = QLabel('')
            self._mail_label.setStyleSheet(
                'font-family: "Segoe UI"; font-size: 9px; color: #94A3B8;'
                ' font-style: italic;'
            )
            self._mail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._mail_label.setWordWrap(True)
            card_layout.addWidget(self._mail_label)
        else:
            # Factices pour compat avec _update_warmup_ui
            self._progress_bar = self._make_progress_bar()
            self._progress_bar.hide()
            self._progress_label = QLabel('')
            self._progress_label.hide()
            self._mail_label = QLabel('')
            self._mail_label.hide()

        card_layout.addSpacing(4)

        # Boutons Annuler / Activer (mêmes styles que warmup)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_cancel = QPushButton('Plus tard')
        btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_cancel.setFixedHeight(36)
        btn_cancel.setStyleSheet(
            'QPushButton { background: transparent; color: #64748B;'
            ' border: 1px solid #cbd5e1; border-radius: 18px;'
            ' font-family: "Segoe UI"; font-size: 12px; padding: 0 18px; }'
            'QPushButton:hover { background: #f1f5f9; color: #334155; }'
        )
        btn_cancel.clicked.connect(self.close)
        btn_row.addWidget(btn_cancel)

        btn_activate = QPushButton('Activer en 2 minutes')
        btn_activate.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_activate.setFixedHeight(36)
        btn_activate.setStyleSheet(
            'QPushButton {'
            '  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,'
            '    stop:0 #0F6CBD, stop:1 #5B4FBF);'
            '  color: white; border: none; border-radius: 18px;'
            '  font-family: "Segoe UI"; font-size: 12px; font-weight: 600;'
            '  padding: 0 20px;'
            '}'
            'QPushButton:hover { background: #0d5ca3; }'
            'QPushButton:pressed { background: #094a86; }'
        )
        btn_activate.clicked.connect(self._on_activate_click)
        btn_row.addWidget(btn_activate)

        card_layout.addLayout(btn_row)

        outer.addWidget(card)
        return widget

    # -------- Helper : barre de progression stylée --------------------------

    def _make_progress_bar(self):
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(6)
        bar.setStyleSheet(
            'QProgressBar { background: #E8EEF6; border: none; border-radius: 3px; }'
            'QProgressBar::chunk {'
            '  background: qlineargradient(x1:0, y1:0, x2:1, y2:0,'
            '    stop:0 #0F6CBD, stop:1 #5B4FBF);'
            '  border-radius: 3px;'
            '}'
        )
        return bar

    # -------- Handler : clic "Activer en 2 minutes" -------------------------

    def _on_activate_click(self):
        """
        Le user clique sur le CTA : on ouvre le flow d'onboarding dans le dialog.
        Le reste (OAuth, etc.) se fait côté web — la popup laisse la main.
        """
        logger.info('CTA marketing cliqué → bascule onboarding')
        # TODO Phase 5 : déclencher le flow d'onboarding complet.
        # Pour l'instant, on bascule vers popup.html (Etat 1 overlay) qui
        # contient déjà le bouton d'activation Microsoft.
        self._transition_to_overlay()

    # =========================================================================
    # FLASH ANIMATION (cache chaud — simule le warmup rapidement)
    # =========================================================================

    def _start_flash_animation(self):
        """
        Popup de lancement en mode flash : la barre de progression se remplit
        en ~2,5 s pour donner un feedback visible sans faire attendre inutilement.
        Pas d'appel backend (cache déjà chaud via prefetch_cache_v2.json < 48h).
        """
        self._progress_label.setText('BoosterMail — cache chaud, prêt en un instant…')
        self._flash_progress = 0
        self._flash_timer = QTimer()
        self._flash_timer.setInterval(50)  # 50ms × 50 ticks = 2,5 s
        self._flash_timer.timeout.connect(self._tick_flash)
        self._flash_timer.start()

    def _tick_flash(self):
        self._flash_progress += 2  # +2% toutes les 50 ms → 100% en 2,5 s
        self._progress_bar.setValue(min(100, self._flash_progress))
        if self._flash_progress >= 95:
            self._progress_label.setText('Prêt — cliquez sur Lancer')
        if self._flash_progress >= 100:
            self._flash_timer.stop()
            # Audit 20/04 : pas d'auto-transition — attendre clic "Lancer"

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

        # Warmup termine
        if self._wp['done']:
            self._warmup_timer.stop()
            self._on_warmup_finished()
            return

        # 10s max → fin forcee (P12)
        if self._warmup_elapsed >= 10000:
            self._wp['done'] = True
            self._wp['pct'] = 100
            self._wp['label'] = 'Pret !'
            self._progress_bar.setValue(100)
            self._progress_label.setText('Pret !')
            self._warmup_timer.stop()
            self._on_warmup_finished()

    def _on_warmup_finished(self):
        """Appelé quand le warmup est fini. Audit 20/04 : plus d'auto-transition.
        La popup reste affichée jusqu'au clic user sur "Lancer" ou "Annuler".
        """
        # Juste mettre à jour le label pour indiquer que c'est prêt
        if self._progress_label:
            self._progress_label.setText('Prêt — cliquez sur Lancer')
        if self._mail_label and self._mail_label.isVisible():
            self._mail_label.hide()

    def _transition_to_overlay(self):
        """
        Bascule vers popup.html (overlay discret haut-droite).
        Audit 20/04 : la popup de lancement était centrée et grande.
        Ici, on réduit et on la déplace en haut-droite pour ne plus gêner.
        """
        logger.info("Transition vers overlay")
        self._popup_view.load(QUrl(POPUP_URL))
        self._stack.setCurrentIndex(1)
        # Redimensionner en overlay discret haut-droite
        self.resize(self._overlay_w, self._overlay_h)
        self.move(self._screen.width() - self._overlay_w, 48)

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
        if hasattr(self, '_flash_timer'):
            self._flash_timer.stop()
        # P2 : signaler au thread worker de s'arreter
        if hasattr(self, '_wp'):
            self._wp['done'] = True
        event.accept()
        # Mode direct : quitter l'application quand la fenêtre se ferme
        if getattr(self, '_direct_mode', False):
            QApplication.quit()

    # Plan 2 Phase 4 — handler de hot instance (reçoit params via IPC)
    def open_dialog_via_ipc(self, params):
        """
        Appelé par le bridge IPC quand l'add-in Outlook clique sur le bouton.
        Charge dialog.html avec les nouveaux params et bascule l'affichage,
        sans relancer un nouveau process Python/PyQt (instance chaude).
        """
        try:
            from urllib.parse import urlencode
            logger.info(f"[hot] open_dialog_via_ipc mode={params.get('mode', 'reply')} "
                        f"subject={params.get('subject', '')[:50]}")
            # Construire l'URL avec les params (même format que mode direct)
            query = {'standalone': '1', **{k: v for k, v in params.items() if v}}
            dialog_url = f'{BACKEND_URL}/plugin/dialog.html?' + urlencode(query)

            # Si on est en mode direct (fenêtre dédiée dialog), juste recharger
            if getattr(self, '_direct_mode', False):
                self._dialog_view.load(QUrl(dialog_url))
            else:
                # Mode overlay : charger puis basculer sur la vue dialog
                self._dialog_view.load(QUrl(dialog_url))
                # Sauvegarder la géométrie overlay avant redimensionnement
                self._overlay_geometry_backup = (
                    self.size().width(), self.size().height(),
                    self.pos().x(), self.pos().y(),
                )
                w = min(1200, self._screen.width() - 40)
                h = min(800, self._screen.height() - 40)
                self.resize(w, h)
                self.move((self._screen.width() - w) // 2,
                          (self._screen.height() - h) // 2)
                self._stack.setCurrentIndex(2)  # vue dialog

            # Ramener la fenêtre au premier plan
            self.show()
            self.raise_()
            self.activateWindow()
            if sys.platform == 'win32':
                try:
                    import ctypes
                    hwnd = int(self.winId())
                    ctypes.windll.user32.AllowSetForegroundWindow(-1)
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"[hot] open_dialog_via_ipc erreur : {e}")


# =============================================================================
# DETECTION OUTLOOK
# =============================================================================

def _fetch_activation_mode():
    """
    Interroge le backend V2 pour connaître l'état d'activation du user + cache.
    Retourne un des 4 modes : 'flash' / 'warmup' / 'marketing' / 'marketing_warmup'.
    Défaut (backend pas prêt) : 'warmup' — bon compromis (affiche juste la barre).
    """
    data = _fetch_activation_full()
    return data.get('mode', 'warmup')


def _fetch_activation_full():
    """Version complète : retourne le dict JSON complet de /api/activation_status."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        resp = urllib.request.urlopen(
            f'{BACKEND_URL}/api/activation_status', context=ctx, timeout=1.5
        )
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logger.info(f"activation_status indisponible ({e}) → fallback warmup")
        return {'mode': 'warmup', 'should_show_popup': True}


def _mark_popup_shown():
    """Signale au backend que la popup a été affichée aujourd'hui (anti-spam)."""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            f'{BACKEND_URL}/api/mark_popup_shown',
            data=b'{}', headers={'Content-Type': 'application/json'},
            method='POST',
        )
        urllib.request.urlopen(req, context=ctx, timeout=1.5)
    except Exception as e:
        logger.debug(f"mark_popup_shown indispo ({e})")


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
# Plan 2 Phase 4 — IPC hot instance : écoute localhost:5052
# =============================================================================

IPC_PORT = 5052
IPC_HOST = '127.0.0.1'


class _IPCBridge(QObject):
    """Bridge thread-safe HTTP→Qt. Émet un signal qui sera reçu sur le Qt thread."""
    open_dialog_requested = pyqtSignal(dict)


_ipc_bridge = None  # Instance globale (setée au démarrage Qt)


class _IPCHandler(BaseHTTPRequestHandler):
    """Handler HTTP minimal : GET /ping, POST /open_dialog."""

    def log_message(self, format, *args):
        # Silence les logs http.server par défaut (bruyant)
        logger.debug(f"[ipc] {format % args}")

    def _json_response(self, payload, status=200):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/ping':
            self._json_response({"alive": True, "pid": os.getpid()})
        else:
            self._json_response({"error": "not found"}, 404)

    def do_POST(self):
        if self.path != '/open_dialog':
            self._json_response({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length) if length > 0 else b'{}'
            params = json.loads(body.decode('utf-8') or '{}')
        except Exception as e:
            self._json_response({"error": f"bad json: {e}"}, 400)
            return
        if _ipc_bridge:
            # Émettre sur le Qt thread via signal
            _ipc_bridge.open_dialog_requested.emit(params)
            self._json_response({"ok": True, "handled_by": "hot_instance"})
        else:
            self._json_response({"error": "bridge not initialized"}, 503)


def _start_ipc_server():
    """Démarre le serveur HTTP IPC dans un thread daemon."""
    try:
        server = ThreadingHTTPServer((IPC_HOST, IPC_PORT), _IPCHandler)
        logger.info(f"[ipc] Hot instance serveur démarré sur {IPC_HOST}:{IPC_PORT}")
        server.serve_forever()
    except OSError as e:
        # Port déjà occupé → un autre popup tourne déjà
        logger.info(f"[ipc] Port {IPC_PORT} occupé ({e}) → pas de hot instance")
    except Exception as e:
        logger.warning(f"[ipc] Erreur serveur IPC : {e}")


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
        global _ipc_bridge
        # Mode overlay classique — vérifier anti-spam (audit 20/04 Q3)
        status = _fetch_activation_full()
        show_popup = status.get('should_show_popup', True)
        popup = EasyMailPopup()
        if show_popup:
            popup.show()
            _mark_popup_shown()  # marquer pour ne pas réafficher aujourd'hui
            logger.info(f"Overlay PyQt visible — backend: {BACKEND_URL}")
        else:
            logger.info(f"Popup déjà affichée aujourd'hui "
                        f"(popup_shown_date={status.get('popup_shown_date')}) → cachée, "
                        f"service hot instance prêt pour le dialog")

        # Plan 2 Phase 4 — Hot instance : serveur IPC pour éviter de relancer
        # Python + PyQt + QWebEngineView à chaque clic bouton dans Outlook.
        # Actif dans les deux cas (popup visible ou cachée) pour que le bouton
        # BM dans Outlook reste instantané.
        _ipc_bridge = _IPCBridge()
        _ipc_bridge.open_dialog_requested.connect(popup.open_dialog_via_ipc)
        threading.Thread(target=_start_ipc_server, daemon=True, name='ipc-server').start()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
