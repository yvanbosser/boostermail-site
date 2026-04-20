"""
BoosterMail — Superviseur (watcher Outlook + lancement auto)
1. Se lance au logon Windows (tache planifiee) — tres leger, ne fait RIEN tant qu'Outlook n'est pas ouvert
2. Detecte Outlook (olk.exe ou OUTLOOK.EXE) via Windows API (instantane)
3. Lance les 3 backends + affiche la popup marketing
4. Surveille la sante des backends, relance si crash
5. Quand Outlook se ferme, arrete les backends (optionnel)

Usage :
  pythonw.exe boostermail_service.py          (mode normal, invisible)
  python boostermail_service.py               (mode debug, avec console)
  python boostermail_service.py --stop        (arrete tout)
"""

import os
import sys
import time
import json
import socket
import logging
import subprocess
import ctypes
from ctypes import wintypes

# --- Configuration ---
EASYMAIL_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(EASYMAIL_DIR, 'config.json')
PID_FILE = os.path.join(EASYMAIL_DIR, '.boostermail.pid')
STOP_FILE = os.path.join(EASYMAIL_DIR, '.boostermail.stop')
LOG_FILE = os.path.join(EASYMAIL_DIR, 'boostermail.log')
POPUP_PID_FILE = os.path.join(EASYMAIL_DIR, 'companion', '.popup_pid')
POPUP_SCRIPT = os.path.join(EASYMAIL_DIR, 'companion', 'popup_pyqt.py')
_NW = 0x08000000  # CREATE_NO_WINDOW
_MUTEX_HANDLE = None  # Handle mutex Windows (eviter GC)

PROCESSES = [
    # Audit 20/04 : delay=0 sur les deux — pas de dépendance entre Companion
    # et V2 (ports/DB différents). Démarrage réellement parallèle, gain ~1 s.
    {'name': 'Companion',  'script': os.path.join(EASYMAIL_DIR, 'companion', 'companion.py'),  'port': 5051, 'delay': 0},
    {'name': 'Backend V2', 'script': os.path.join(EASYMAIL_DIR, 'V2', 'app_plugin.py'),        'port': 3443, 'delay': 0},
]

# Proto + Tray : DESACTIVES (decision 18/04/2026)
# Depuis que V2 est autonome, le proto n'a plus besoin de tourner en parallele.
# Eviter les interferences : deux serveurs Flask + deux DB + risque de conflit.
# Pour reactiver le lancement auto du proto, mettre ENABLE_PROTO_AUTO_LAUNCH = True.
ENABLE_PROTO_AUTO_LAUNCH = False
PROTO_SCRIPT = os.path.join(EASYMAIL_DIR, 'app.py')
TRAY_SCRIPT = os.path.join(EASYMAIL_DIR, 'boostermail_tray.py')

def _has_classic_outlook():
    """Detecte si Classic Outlook est installe."""
    paths = [
        r'C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE',
        r'C:\Program Files (x86)\Microsoft Office\root\Office16\OUTLOOK.EXE',
        r'C:\Program Files\Microsoft Office\Office16\OUTLOOK.EXE',
        r'C:\Program Files (x86)\Microsoft Office\Office16\OUTLOOK.EXE',
    ]
    for p in paths:
        if os.path.exists(p):
            return True
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r'SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\OUTLOOK.EXE')
        val, _ = winreg.QueryValueEx(key, '')
        winreg.CloseKey(key)
        if val and os.path.exists(val):
            return True
    except Exception:
        pass
    return False

MAX_RESTART = 5
HEALTH_CHECK_INTERVAL = 30
OUTLOOK_POLL_INTERVAL = 2  # secondes entre chaque check Outlook (audit 20/04 : 3s → 2s, détection plus rapide)

# --- Logging ---
logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format='%(asctime)s [superviseur] %(message)s', datefmt='%Y-%m-%d %H:%M:%S',
)
logger = logging.getLogger('boostermail')
try:
    sys.stdout.write('')
    _console = logging.StreamHandler(sys.stdout)
    _console.setFormatter(logging.Formatter('%(asctime)s [superviseur] %(message)s'))
    logger.addHandler(_console)
except Exception:
    pass


# =============================================================================
# DETECTION OUTLOOK (Windows API, instantane, zero console)
# =============================================================================

def is_outlook_running():
    """Detecte Outlook via la FENETRE visible (pas le processus en arriere-plan).
    Outlook laisse un processus resident meme quand il est ferme — on ne peut pas
    se fier au processus. La fenetre visible = l'utilisateur a vraiment ouvert Outlook."""
    user32 = ctypes.windll.user32
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int))
    found = [None]

    def callback(hwnd, lParam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.lower()
                # New Outlook : titre contient "outlook" ou "boite de reception" / "inbox"
                if 'outlook' in title:
                    found[0] = 'new_outlook'
                    return False  # Stop enumeration
                if 'boite de reception' in title or 'inbox' in title:
                    found[0] = 'new_outlook'
                    return False
        return True

    _cb = EnumWindowsProc(callback)  # Garder la reference (evite GC pendant l'enumeration)
    user32.EnumWindows(_cb, 0)

    if found[0]:
        return found[0]

    # Fallback : verifier aussi la classe de fenetre Classic Outlook
    hwnd = user32.FindWindowW('rctrl_renwnd32', None)
    if hwnd and user32.IsWindowVisible(hwnd):
        return 'classic_outlook'

    return None


# =============================================================================
# UTILITAIRES
# =============================================================================

def find_pythonw():
    python_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(python_dir, 'pythonw.exe')
    if os.path.exists(pythonw):
        return pythonw
    for path_dir in os.environ.get('PATH', '').split(';'):
        candidate = os.path.join(path_dir, 'pythonw.exe')
        if os.path.exists(candidate) and 'WindowsApps' not in candidate:
            return candidate
    return sys.executable


def is_port_listening(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        return False


def kill_port(port):
    try:
        result = subprocess.run(['netstat', '-aon'], capture_output=True, text=True,
                                errors='replace', creationflags=_NW)
        for line in result.stdout.splitlines():
            if f':{port} ' in line and 'LISTENING' in line:
                pid = line.strip().split()[-1]
                if pid.isdigit() and int(pid) != os.getpid():
                    subprocess.run(['taskkill', '/PID', pid, '/F'],
                                   capture_output=True, creationflags=_NW)
                    logger.info(f"Port {port}: PID {pid} tue")
                    return True
    except Exception as e:
        logger.warning(f"kill_port({port}): {e}")
    return False


def write_pid_file(sup_pid, child_pids):
    try:
        with open(PID_FILE, 'w') as f:
            json.dump({'supervisor': sup_pid, 'children': child_pids,
                        'started': time.strftime('%Y-%m-%dT%H:%M:%S')}, f)
    except Exception:
        pass


def cleanup():
    for f in [PID_FILE, STOP_FILE, POPUP_PID_FILE]:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass


def validate_prerequisites():
    errors = []
    if not os.path.exists(CONFIG_PATH):
        errors.append("config.json introuvable")
    else:
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            key = cfg.get('ANTHROPIC_API_KEY', '') or cfg.get('anthropic_api_key', '')
            if not key or 'COLLER' in key.upper():
                errors.append("Cle Anthropic manquante dans config.json")
        except Exception as e:
            errors.append(f"config.json invalide: {e}")
    cert = os.path.join(EASYMAIL_DIR, 'V2', 'localhost.crt')
    if not os.path.exists(cert):
        errors.append("Certificat HTTPS introuvable")
    for p in PROCESSES:
        if not os.path.exists(p['script']):
            errors.append(f"Script introuvable: {p['script']}")
    if errors:
        for e in errors:
            logger.error(f"PREREQUIS: {e}")
    return len(errors) == 0


def _popup_is_alive():
    """True si le PID stocké correspond à un process vivant (anti-doublon)."""
    try:
        with open(POPUP_PID_FILE, 'r') as f:
            pid = int(f.read().strip())
    except Exception:
        return False
    try:
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED = 0x1000
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
        if not h:
            return False
        exit_code = wintypes.DWORD()
        kernel32.GetExitCodeProcess(h, ctypes.byref(exit_code))
        kernel32.CloseHandle(h)
        return exit_code.value == 259  # STILL_ACTIVE
    except Exception:
        return False


def show_pyqt_popup():
    """Lance la popup PyQt (popup_pyqt.py) en processus séparé.
    La popup interroge /api/activation_status pour choisir son mode (Plan 3 §9.3)."""
    if _popup_is_alive():
        logger.info("Popup déjà vivante — skip (anti-doublon)")
        return
    try:
        pythonw = find_pythonw()
        proc = subprocess.Popen(
            [pythonw, POPUP_SCRIPT], cwd=EASYMAIL_DIR,
            creationflags=_NW,
        )
        try:
            with open(POPUP_PID_FILE, 'w') as f:
                f.write(str(proc.pid))
        except Exception:
            pass
        logger.info(f"Popup PyQt lancee (PID {proc.pid})")
    except Exception as e:
        logger.warning(f"Popup PyQt erreur: {e}")


# =============================================================================
# GESTION DES PROCESSUS
# =============================================================================

class ProcessManager:
    def __init__(self, name, script, port, pythonw_path):
        self.name = name
        self.script = script
        self.port = port
        self.pythonw = pythonw_path
        self.process = None
        self.restart_count = 0
        self.last_restart = 0

    def start(self):
        if is_port_listening(self.port):
            kill_port(self.port)
            time.sleep(0.5)
        try:
            self.process = subprocess.Popen(
                [self.pythonw, self.script], cwd=EASYMAIL_DIR,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=_NW,
            )
            logger.info(f"{self.name}: lance (PID {self.process.pid}, port {self.port})")
            return True
        except Exception as e:
            logger.error(f"{self.name}: erreur lancement: {e}")
            return False

    def is_alive(self):
        if self.process is None or self.process.poll() is not None:
            return False
        return is_port_listening(self.port)

    def restart(self):
        if self.restart_count >= MAX_RESTART:
            logger.error(f"{self.name}: {MAX_RESTART} tentatives, abandon")
            return False
        wait = 5 * (2 ** self.restart_count)
        if time.time() - self.last_restart < wait:
            return False
        self.restart_count += 1
        self.last_restart = time.time()
        logger.warning(f"{self.name}: relance ({self.restart_count}/{MAX_RESTART})")
        self.stop()
        return self.start()

    def stop(self):
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            logger.info(f"{self.name}: arrete")

    @property
    def pid(self):
        return self.process.pid if self.process else None


# =============================================================================
# STOP
# =============================================================================

def stop_existing():
    """Arrete le superviseur et ses enfants."""
    try:
        with open(PID_FILE, 'r') as f:
            data = json.load(f)
    except Exception:
        logger.info("Pas de superviseur en cours")
        return

    # Fichier stop pour arret propre
    try:
        with open(STOP_FILE, 'w') as f:
            f.write('stop')
    except Exception:
        pass

    time.sleep(3)

    # Tuer les enfants
    for pid in data.get('children', []):
        try:
            subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                           capture_output=True, creationflags=_NW)
        except Exception:
            pass

    # Tuer le superviseur
    sup = data.get('supervisor')
    if sup and sup != os.getpid():
        try:
            subprocess.run(['taskkill', '/PID', str(sup), '/F'],
                           capture_output=True, creationflags=_NW)
        except Exception:
            pass

    cleanup()
    time.sleep(1)


# =============================================================================
# BOUCLE PRINCIPALE
# =============================================================================

def run_supervisor(first_launch=True):
    # Mutex Windows : empecher 2 superviseurs simultanes
    if first_launch:
        global _MUTEX_HANDLE
        _MUTEX_HANDLE = ctypes.windll.kernel32.CreateMutexW(None, True, "BoosterMailSupervisor")
        if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            logger.info("Un superviseur tourne deja — abandon")
            return False

    logger.info("=" * 50)
    logger.info("BoosterMail Superviseur demarre (mode watcher)")
    logger.info(f"Repertoire: {EASYMAIL_DIR}")

    stop_existing()
    if os.path.exists(STOP_FILE):
        os.remove(STOP_FILE)

    # Nettoyage garanti meme en cas de crash
    import atexit
    atexit.register(cleanup)

    if not validate_prerequisites():
        logger.error("Prerequis non remplis — abandon")
        try:
            ctypes.windll.user32.MessageBoxW(
                0, "BoosterMail ne peut pas demarrer.\nVerifiez boostermail.log",
                "BoosterMail", 0x10)
        except Exception:
            pass
        return

    pythonw = find_pythonw()
    logger.info(f"pythonw: {pythonw}")
    logger.info("En attente d'Outlook...")

    # Ecrire le PID du superviseur (sans enfants pour l'instant)
    write_pid_file(os.getpid(), [])

    # =========================================================
    # PHASE 1 : Attendre qu'Outlook soit lance PAR L'UTILISATEUR
    # =========================================================
    # Au premier lancement, si Outlook est deja ouvert (processus residuel),
    # attendre qu'il se ferme pour eviter les faux positifs.
    # Aux cycles suivants (Outlook vient de fermer), on attend juste 10s
    # que les fenetres residuelles disparaissent.
    if not first_launch:
        logger.info("Attente 10s que les fenetres Outlook disparaissent...")
        time.sleep(10)
    elif is_outlook_running():
        logger.info("Outlook deja ouvert — attente qu'il se ferme d'abord (max 5 min)...")
        _wait_start = time.time()
        while is_outlook_running():
            if os.path.exists(STOP_FILE):
                cleanup()
                return False
            if time.time() - _wait_start > 300:  # 5 min timeout
                logger.info("Outlook ouvert depuis 5 min — lancement direct")
                break
            time.sleep(OUTLOOK_POLL_INTERVAL)
        else:
            logger.info("Outlook ferme. En attente d'une NOUVELLE ouverture...")
            time.sleep(3)

    while True:
        if os.path.exists(STOP_FILE):
            logger.info("Stop demande pendant l'attente")
            cleanup()
            return

        platform = is_outlook_running()
        if platform:
            logger.info(f"Outlook detecte ({platform}) !")
            # Audit 20/04 : sleep(2) supprimé. V2 + Companion ne dépendent pas
            # du fait qu'Outlook soit "complètement lancé". Le Companion gère
            # gracieusement les échecs COM temporaires (retry). Gain : 2 s.
            break
        time.sleep(OUTLOOK_POLL_INTERVAL)

    # =========================================================
    # PHASE 2 : Outlook detecte — backends puis popup PyQt
    # Nouveau flow (Phase 0 Plan 2) : les backends se lancent en premier
    # pour que la popup PyQt puisse interroger /api/activation_status.
    # =========================================================
    managers = []

    # Lancer les backends
    logger.info("Lancement des backends...")
    for proc in PROCESSES:
        if proc['delay'] > 0:
            time.sleep(proc['delay'])
        mgr = ProcessManager(proc['name'], proc['script'], proc['port'], pythonw)
        mgr.start()
        managers.append(mgr)
    write_pid_file(os.getpid(), [m.pid for m in managers if m.pid])

    # Attendre que V2 (port 3443) réponde, indispensable pour /api/activation_status
    logger.info("Attente de V2 (port 3443) pour popup...")
    for _ in range(30):  # 30 × 1s = 30s max
        if is_port_listening(3443):
            break
        if os.path.exists(STOP_FILE):
            cleanup()
            return False
        time.sleep(1)

    # Lancer la popup PyQt (interroge /api/activation_status elle-même)
    show_pyqt_popup()

    # Attendre que tous les ports répondent (max 60s au total)
    logger.info("Attente des autres ports...")
    for _ in range(60):
        if all(is_port_listening(p['port']) for p in PROCESSES):
            break
        time.sleep(1)

    ready = [p['port'] for p in PROCESSES if is_port_listening(p['port'])]
    logger.info(f"Ports prets: {ready}")

    # =========================================================
    # PHASE 2b : Proto + Tray — DESACTIVES par defaut (decision 18/04/2026)
    # =========================================================
    # V2 etant autonome, le proto n'a plus besoin de tourner en parallele.
    # Pour reactiver (si besoin beta-testeurs), mettre ENABLE_PROTO_AUTO_LAUNCH = True en haut.
    proto_proc = None
    tray_proc = None

    if not ENABLE_PROTO_AUTO_LAUNCH:
        logger.info("Proto + tray DESACTIVES (ENABLE_PROTO_AUTO_LAUNCH=False) - V2 seul actif")
    else:
        _classic = _has_classic_outlook()
        if _classic:
            logger.info("Classic Outlook detecte → lancement Proto + icone tray")

            # Lancer le proto (port 5050) — le proto ouvre Chrome (= inbox BM)
            if os.path.exists(PROTO_SCRIPT):
                try:
                    # Nettoyer le port 5050 si occupe
                    if is_port_listening(5050):
                        kill_port(5050)
                        time.sleep(0.5)
                    proto_proc = subprocess.Popen(
                        [pythonw, PROTO_SCRIPT], cwd=EASYMAIL_DIR,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=_NW,
                    )
                    logger.info(f"Proto lance (PID {proto_proc.pid}, port 5050)")
                except Exception as e:
                    logger.warning(f"Proto erreur: {e}")

            # Lancer l'icone tray
            if os.path.exists(TRAY_SCRIPT):
                try:
                    tray_proc = subprocess.Popen(
                        [pythonw, TRAY_SCRIPT], cwd=EASYMAIL_DIR,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=_NW,
                    )
                    logger.info(f"Icone tray lancee (PID {tray_proc.pid})")
                except Exception as e:
                    logger.warning(f"Tray erreur: {e}")
        else:
            logger.info("Classic Outlook NON detecte → Proto et tray desactives")

    # =========================================================
    # PHASE 3 : Surveillance
    # =========================================================
    _health_counter = 0
    while True:
        time.sleep(5)  # Check Outlook toutes les 5s (pas 30s)

        if os.path.exists(STOP_FILE):
            logger.info("Stop demande")
            break

        # Verifier si Outlook est encore ouvert (toutes les 5s)
        if not is_outlook_running():
            logger.info("Outlook ferme — arret des backends")
            break

        # Health check backends (toutes les 30s = 6 × 5s)
        _health_counter += 1
        if _health_counter >= 6:
            _health_counter = 0
            for mgr in managers:
                if not mgr.is_alive():
                    logger.warning(f"{mgr.name}: mort detecte")
                    mgr.restart()
            write_pid_file(os.getpid(), [m.pid for m in managers if m.pid])

    # Arret propre des backends + proto + tray
    logger.info("Arret des backends...")
    for mgr in managers:
        mgr.stop()

    # Arreter le proto
    if proto_proc and proto_proc.poll() is None:
        try:
            proto_proc.terminate()
            proto_proc.wait(timeout=3)
            logger.info("Proto arrete")
        except Exception:
            try:
                proto_proc.kill()
            except Exception:
                pass

    # Arreter l'icone tray
    if tray_proc and tray_proc.poll() is None:
        try:
            tray_proc.terminate()
            tray_proc.wait(timeout=3)
            logger.info("Tray arrete")
        except Exception:
            try:
                tray_proc.kill()
            except Exception:
                pass

    # Retourner True si Outlook ferme (cycle), False si --stop
    return not os.path.exists(STOP_FILE)


# --- Point d'entree ---
if __name__ == '__main__':
    if '--stop' in sys.argv:
        stop_existing()
        print("BoosterMail arrete.")
    else:
        # Boucle : surveille Outlook → lance BM → Outlook ferme → attend → recommence
        first = True
        while True:
            should_continue = run_supervisor(first_launch=first)
            first = False
            if not should_continue:
                break  # --stop demande
            cleanup()
            logger.info("Retour en mode attente Outlook...")
