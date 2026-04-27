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
OUTLOOK_POLL_INTERVAL = 1  # secondes entre chaque check Outlook (audit 20/04 : 2s → 1s, gain détection)

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

# Fix 24/04 soir (Pattern #15, iteration 2) : identification d'un process
# proprietaire de fenetre Windows.
#
# Premiere tentative : GetModuleBaseNameW (psapi.dll).
# ECHEC : cette API necessite la permission PROCESS_VM_READ (0x0010) en
# plus de PROCESS_QUERY_LIMITED_INFORMATION (0x1000). Sur Windows 11,
# les policies refusent PROCESS_VM_READ pour les process protected
# (comme Outlook). Resultat observe : GetLastError = 5 (ACCESS_DENIED),
# la fonction retournait "" pour toutes les fenetres => is_outlook_running
# toujours None => popup jamais declenchee.
#
# Solution retenue : QueryFullProcessImageNameW (kernel32, Win Vista+).
# Cette API ne demande que PROCESS_QUERY_LIMITED_INFORMATION qui est
# accorde meme pour les process protected. Elle retourne le chemin
# complet de l'exe ; on extrait le basename via os.path.basename.
#
# Bonus : declaration explicite argtypes/restypes (HANDLE = 64 bits sur
# Win64, sinon le handle est tronque a 32 bits => invalide).
from ctypes import wintypes as _wt

def _declare_win32_types():
    """Declare les argtypes/restypes corrects pour les APIs Win32
    utilisees dans _get_window_process_name. Idempotente."""
    _u32 = ctypes.windll.user32
    _k32 = ctypes.windll.kernel32

    _u32.GetWindowThreadProcessId.argtypes = [_wt.HWND, ctypes.POINTER(_wt.DWORD)]
    _u32.GetWindowThreadProcessId.restype = _wt.DWORD

    _k32.OpenProcess.argtypes = [_wt.DWORD, _wt.BOOL, _wt.DWORD]
    _k32.OpenProcess.restype = _wt.HANDLE  # CRITIQUE : 64 bits sur Win64

    _k32.CloseHandle.argtypes = [_wt.HANDLE]
    _k32.CloseHandle.restype = _wt.BOOL

    _k32.QueryFullProcessImageNameW.argtypes = [
        _wt.HANDLE, _wt.DWORD, _wt.LPWSTR, ctypes.POINTER(_wt.DWORD)
    ]
    _k32.QueryFullProcessImageNameW.restype = _wt.BOOL

_declare_win32_types()  # Applique des le chargement du module


def _get_window_process_name(hwnd, user32, kernel32, psapi=None):
    """Retourne le nom de l'exe proprietaire d'une fenetre HWND (lowercase).
    Chaine vide si erreur ou process introuvable.

    Utilise GetWindowThreadProcessId + OpenProcess +
    QueryFullProcessImageNameW. Le parametre `psapi` est conserve pour
    compatibilite avec les anciens appels mais n'est plus utilise
    (GetModuleBaseNameW necessitait PROCESS_VM_READ refuse sur Win11).
    """
    try:
        pid = _wt.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return ''
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return ''
        try:
            buf = ctypes.create_unicode_buffer(512)
            size = _wt.DWORD(512)
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size))
            if not ok or not buf.value:
                return ''
            import os as _os
            return _os.path.basename(buf.value).lower()
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ''


def is_outlook_running():
    """Detecte Outlook via la FENETRE visible + PROCESS proprietaire.

    Historique 24/04/2026 (Pattern #15) : la version precedente detectait
    Outlook en cherchant "outlook" / "boite de reception" / "inbox" dans
    le titre de n'importe quelle fenetre visible. Consequence : un onglet
    Outlook Web dans Microsoft Edge, ou une fenetre Teams avec "Outlook"
    dans le titre, etait compte comme "Outlook ouvert". Superviseur
    aveugle aux vraies ouvertures/fermetures du client desktop => popup
    jamais redeclenchee, 37+ min de silence observees le 24/04.

    Fix : pour chaque fenetre candidate, on verifie que le process
    proprietaire est bien olk.exe (New Outlook / Monarch) ou
    outlook.exe (Classic Outlook). Titre seul ne suffit plus.

    Cas particuliers :
    - Classic Outlook : on verifie egalement la classe de fenetre
      'rctrl_renwnd32' (plus fiable que le titre) ; process attendu
      = outlook.exe.
    - Outlook Web (PWA / onglet Edge) : process = msedge.exe,
      explicitement ignore (pas un client BoosterMail valide).
    """
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi

    OUTLOOK_EXES = {'olk.exe', 'outlook.exe'}

    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.POINTER(ctypes.c_int))
    found = [None]

    def callback(hwnd, lParam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.lower()
        # Heuristique rapide d'elimination avant GetWindowThreadProcessId :
        # seulement les fenetres dont le titre evoque Outlook passent le check
        # process (pour ne pas iterer toutes les fenetres du desktop).
        if not ('outlook' in title or 'boite de reception' in title or 'inbox' in title):
            return True
        # Verification du process proprietaire
        exe_name = _get_window_process_name(hwnd, user32, kernel32, psapi)
        if exe_name in OUTLOOK_EXES:
            if exe_name == 'olk.exe':
                found[0] = 'new_outlook'
            else:
                found[0] = 'classic_outlook'
            return False  # Stop enumeration
        # Sinon : titre contenait "outlook" mais process non Outlook
        # (Edge avec Outlook Web, Teams, etc.) -> on ignore cette fenetre
        # et on continue l'enumeration.
        return True

    _cb = EnumWindowsProc(callback)  # Garder la reference (evite GC pendant l'enumeration)
    user32.EnumWindows(_cb, 0)

    if found[0]:
        return found[0]

    # Fallback Classic Outlook : la classe de fenetre 'rctrl_renwnd32'
    # est unique a Outlook Classic. Mais on verifie quand meme le process
    # proprietaire pour coherence avec le fix Pattern #15.
    hwnd = user32.FindWindowW('rctrl_renwnd32', None)
    if hwnd and user32.IsWindowVisible(hwnd):
        exe_name = _get_window_process_name(hwnd, user32, kernel32, psapi)
        if exe_name in OUTLOOK_EXES:
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


def _auto_sideload_outlook_addin():
    """Enregistre l'add-in BoosterMail dans Outlook (New + Classic).

    Délègue à `install_outlook_addin.py` qui fait :
      1. certutil -user -addstore Root (cert localhost trusté, pas d'UAC)
      2. winreg SetValueEx HKCU\\Software\\Microsoft\\Office\\16.0\\Wef\\Developer
         [<manifest_id>] = <manifest path>  (mécanisme officiel Microsoft)

    Fix 21/04 : remplace l'ancien code qui copiait le fichier dans
    Wef\\Developer\\BoosterMail.manifest.xml — ce dossier est uniquement
    pour le Classic, pas New Outlook. Le mécanisme correct c'est le
    registre, identifié via les sources officielles (office-addin-scripts).

    Idempotent : si déjà fait, ne refait rien (vérifié dans le sous-script).
    """
    installer = os.path.join(EASYMAIL_DIR, 'install_outlook_addin.py')
    if not os.path.exists(installer):
        logger.warning(f"Auto-sideload : {installer} introuvable")
        return

    python_exe = find_pythonw()
    try:
        result = subprocess.run(
            [python_exe, installer],
            capture_output=True, text=True, timeout=30,
            creationflags=_NW,  # CREATE_NO_WINDOW
        )
        # Fix audit 23/04 : remonter les lignes [WARN] du script sideload dans
        # le log superviseur, même si rc=0. Sinon un doublon cert détecté par
        # _warn_obsolete_certs() passait silencieusement → bouton BM cassé au
        # démarrage suivant sans aucune trace.
        stdout = (result.stdout or '').strip()
        stderr = (result.stderr or '').strip()
        warn_lines = []
        for line in stdout.splitlines():
            # Format de install_outlook_addin.log() : "[install-addin] [WARN] ..."
            if '[WARN]' in line:
                warn_lines.append(line)
        if warn_lines:
            logger.warning("Auto-sideload addin : alertes detectees (voir dessous) :")
            for wl in warn_lines:
                logger.warning(f"  {wl}")

        if result.returncode == 0:
            if warn_lines:
                logger.info("Auto-sideload addin : OK mais alertes presentes (cf. ci-dessus)")
            else:
                logger.info("Auto-sideload addin : OK (bouton BM enregistré dans Outlook)")
        else:
            logger.warning(f"Auto-sideload addin : échec (rc={result.returncode}) "
                           f"stderr={stderr[:200]}")
    except Exception as e:
        logger.warning(f"Auto-sideload addin : erreur exec : {e}")


def _popup_hide_all():
    """Décision user 24/04 : à la fermeture d'Outlook, demander à popup_pyqt
    de cacher overlay + dialog + child windows.

    Le process popup_pyqt reste vivant (setQuitOnLastWindowClosed=False) pour
    servir un /show_popup instantané au prochain démarrage d'Outlook. Les BG
    loops côté V2 + Companion continuent de tourner (apprentissage, caches).

    No-op si popup_pyqt pas alive (ex: V2 stoppé depuis > 30 min d'idle).
    """
    import urllib.request
    try:
        req = urllib.request.Request(
            'http://127.0.0.1:5052/hide_all',
            data=b'{}',
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        urllib.request.urlopen(req, timeout=1.5)
        logger.info("Popup IPC /hide_all envoyé (Outlook fermé, overlay caché)")
    except Exception as e:
        logger.debug(f"Popup /hide_all ignoré (popup probablement pas alive) : {e}")


def _popup_is_alive():
    """True si popup_pyqt répond à un ping HTTP sur 5052.

    Fix 20/04 : avant on lisait un PID file + OpenProcess Windows. Problème :
    si le PID file était périmé (process tué sans nettoyage du fichier), ou
    si deux appels à show_pyqt_popup arrivaient en parallèle avant l'écriture
    du PID file, on spawnait des doublons.
    Le ping HTTP teste la RÉPONSE RÉELLE de popup_pyqt → plus fiable, plus
    rapide, aucun PID file requis.

    Timeout 1.0 s (21/04 audit C10) : assez pour absorber une petite latence
    locale sous charge sans faux négatif (qui provoquerait un spawn en double).
    """
    import urllib.request
    try:
        with urllib.request.urlopen('http://127.0.0.1:5052/ping', timeout=1.0) as resp:
            return resp.status == 200
    except Exception:
        return False


def _wait_for_popup_alive(timeout=15.0, interval=0.5):
    """Attend que popup_pyqt réponde sur 5052 pendant au plus `timeout` s,
    en pollant toutes les `interval` s. Retourne True si alive, False sinon.

    Fix 24/04 soir (Bug 3, race condition pre-warm vs trigger immédiat) :
    quand le superviseur lance popup_pyqt en pre-warm au boot Windows,
    Qt + QtWebEngine mettent **15-20 secondes** à initialiser le hot
    serveur IPC sur 5052. Si l'utilisateur ouvre Outlook dans cet
    intervalle (cas nominal : user ouvre Outlook immédiatement au logon),
    `show_pyqt_popup()` voit `_popup_is_alive() = False` → tombe en
    fallback subprocess → nouveau process popup_pyqt spawné → entre en
    collision avec le pre-warm qui finit son init (conflit port 5052)
    → le nouveau se suicide → le pre-warm reste vivant mais personne ne
    lui envoie jamais `/show_popup` → popup de lancement jamais affichée.

    Ce helper élimine la race en attendant activement que le pre-warm
    finisse son init (ping success). Dans le cas nominal (popup déjà
    prête), le premier ping retourne True en <50ms donc coût négligeable.
    Pire cas (popup morte ou jamais lancée) : 15 s avant de fallback
    subprocess — acceptable au boot (user attend déjà que BM se charge).
    """
    import urllib.request
    deadline = time.time() + timeout
    while True:
        try:
            with urllib.request.urlopen('http://127.0.0.1:5052/ping', timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        if time.time() >= deadline:
            return False
        time.sleep(interval)


# Fix 20/04 — mutex anti-concurrence sur show_pyqt_popup.
# Sans ce lock, 2 appels parallèles (ex: superviseur détecte Outlook + autre
# trigger) pouvaient tous deux passer _popup_is_alive() avant que le premier
# spawn ne réponde → 2 popup_pyqt lancés en parallèle.
import threading as _bm_threading
_show_popup_lock = _bm_threading.Lock()


def _should_show_popup_now():
    """Anti-spam popup (ajout 20/04, point C du nettoyage).

    Interroge le backend V2 /api/activation_status pour savoir si la popup
    marketing/warmup doit être affichée :
      - Si déjà affichée aujourd'hui → False (pas de réapparition au
        redémarrage Outlook dans la même journée)
      - Si user activé et cache chaud → False (mode flash inutile au reopen)
      - Sinon → True
    En cas d'erreur réseau → True (fallback safe : on affiche).
    """
    try:
        import urllib.request, ssl as _ssl
        ctx = _ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = _ssl.CERT_NONE
        req = urllib.request.Request(
            'https://localhost:3443/api/activation_status',
            headers={'Accept': 'application/json'},
        )
        with urllib.request.urlopen(req, timeout=1.5, context=ctx) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        return bool(body.get('should_show_popup', True))
    except Exception as e:
        logger.debug(f"activation_status check échoué ({e}) — on affiche par défaut")
        return True


def show_pyqt_popup():
    """Affiche la popup PyQt.
    Audit 20/04 — 2 voies :
    1) Si popup process déjà vivant → POST http://127.0.0.1:5052/show_popup
       → réaffichage instantané (~100 ms), pas de respawn Python+Qt.
    2) Sinon → subprocess.Popen popup_pyqt.py (premier lancement, ~5 s).
    Gain attendu : ouverture Outlook → popup visible en ~2 s au lieu de 7 s.

    Ajout 20/04 (point C) : vérification anti-spam via _should_show_popup_now
    avant d'appeler l'IPC pour éviter que la popup marketing ne ressurgisse
    à chaque redémarrage d'Outlook dans la même journée."""
    if not _should_show_popup_now():
        logger.info("Popup déjà affichée aujourd'hui — pas de réaffichage (anti-spam)")
        return

    # Mutex anti-concurrence (fix 20/04) : garantit qu'UN SEUL appel à
    # show_pyqt_popup peut décider de spawner à la fois → plus de doublons
    # quand le superviseur détecte plusieurs triggers rapprochés.
    with _show_popup_lock:
        # Fix 24/04 soir (Bug 3) : au lieu d'un unique ping rapide qui échoue
        # si popup_pyqt est en cours de pre-warm (Qt init 15-20s), on retry
        # activement pendant 15 s. Résout la race condition popup pré-warmée
        # pas encore prête ↔ trigger show_popup au boot.
        if _wait_for_popup_alive(timeout=15.0, interval=0.5):
            # Voie 1 : IPC show_popup (rapide)
            try:
                import urllib.request
                req = urllib.request.Request(
                    'http://127.0.0.1:5052/show_popup',
                    data=b'{}', headers={'Content-Type': 'application/json'},
                    method='POST',
                )
                # Timeout 2.5 s (21/04 audit cycle 1 #5) : avant 1.0 s
                # trop court sous charge (Chromium parse lourd au cold
                # start). Éviter les faux timeouts qui déclenchaient
                # fallback subprocess inutilement.
                urllib.request.urlopen(req, timeout=2.5)
                logger.info("Popup réaffichée via IPC (hot)")
                return
            except Exception as e:
                logger.info(f"IPC show_popup échoué ({e}) → fallback subprocess")
                # fallthrough → subprocess (DANS le mutex)

        # Voie 2 : subprocess fresh spawn (TOUJOURS dans le mutex pour éviter
        # que 2 appels parallèles ne spawnent tous les deux).
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
            # Audit 25/04 (race condition 2 handles 'w' sur même log) :
            # log séparé par backend pour éviter truncate mutuel + NUL padding.
            # Quand un backend respawnait, son open('w') tronquait V2_stderr.log
            # à 0 bytes, mais l'autre backend continuait d'écrire à son offset
            # mémorisé → Windows comblait l'intervalle avec des bytes \x00 →
            # fichier devenait binaire (12 570 NULs comptés en prod le 25/04).
            # Effet collatéral : les logs du backend "victime" étaient perdus.
            # Convention : V2 garde V2_stderr.log (référencé doc) ;
            # les autres backends prennent <slug>_stderr.log.
            if self.name == 'Backend V2':
                _log_filename = 'V2_stderr.log'
            else:
                _log_filename = f"{self.name.lower().replace(' ', '_')}_stderr.log"
            _log_path = os.path.join(EASYMAIL_DIR, _log_filename)
            _log_f = open(_log_path, 'w', encoding='utf-8', errors='replace')
            self.process = subprocess.Popen(
                [self.pythonw, self.script], cwd=EASYMAIL_DIR,
                stdout=subprocess.DEVNULL, stderr=_log_f,
                creationflags=_NW,
            )
            logger.info(f"{self.name}: lance (PID {self.process.pid}, port {self.port})")
            return True
        except Exception as e:
            logger.error(f"{self.name}: erreur lancement: {e}")
            return False

    def is_alive(self):
        # Fix audit 22/04 (Option C) : verifier la VRAIE sante du service via
        # HTTP avant de le declarer mort. Avant : on checkait uniquement que
        # self.process etait vivant ET que le port ecoutait. Probleme : si V2
        # etait lance manuellement (autre PID), self.process est mort mais V2
        # tourne bien. Resultat : "mort detecte" en boucle, "5 tentatives
        # abandon", spam de log.
        #
        # Nouveau : si le service repond a un HTTP check, il est ALIVE peu
        # importe quel PID. Et on reset le restart_count car il tient debout.
        if self._http_health_check():
            if self.restart_count > 0:
                logger.info(f"{self.name}: service repond via HTTP, reset "
                            f"compteur restart ({self.restart_count} -> 0)")
                self.restart_count = 0
            return True
        # Fallback : check classique (process + port)
        if self.process is None or self.process.poll() is not None:
            return False
        return is_port_listening(self.port)

    def _http_health_check(self):
        """Verifie via HTTP que le service repond vraiment (pas juste port
        listening). Plus fiable pour detecter des services zombies ou
        lances manuellement. Retourne True si status 2xx en <3s.
        """
        import urllib.request, ssl, socket
        # V2 (3443) = HTTPS, Companion (5051) = HTTP
        if self.port == 3443:
            url = f'https://127.0.0.1:{self.port}/api/status'
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        else:
            url = f'http://127.0.0.1:{self.port}/status'
            ctx = None
        try:
            if ctx:
                with urllib.request.urlopen(url, timeout=3, context=ctx) as r:
                    return 200 <= r.status < 300
            else:
                with urllib.request.urlopen(url, timeout=3) as r:
                    return 200 <= r.status < 300
        except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
            return False
        except Exception:
            return False

    def restart(self):
        if self.restart_count >= MAX_RESTART:
            # Fix audit 22/04 : ne logger que la PREMIERE fois l'abandon,
            # sinon spam toutes les 30s quand V2 est zombie-lance-manuel.
            if not getattr(self, '_abandon_logged', False):
                logger.error(f"{self.name}: {MAX_RESTART} tentatives, abandon "
                             f"(redemarrer le superviseur pour reset)")
                self._abandon_logged = True
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

    # Ecrire le PID du superviseur (sans enfants pour l'instant)
    write_pid_file(os.getpid(), [])

    # =========================================================
    # PHASE 0 : Auto-sideload du manifest New Outlook (21/04 audit)
    # Copie manifest.xml dans %LOCALAPPDATA%\Microsoft\Office\16.0\Wef\Developer
    # pour que le bouton BoosterMail apparaisse automatiquement dans le ruban
    # Outlook sans intervention user. Persiste entre redémarrages.
    # =========================================================
    try:
        _auto_sideload_outlook_addin()
    except Exception as e:
        logger.warning(f"Auto-sideload manifest échoué : {e}")

    # =========================================================
    # PHASE 1 : Lancer backends IMMEDIATEMENT au logon (audit 20/04)
    # Nouvelle architecture : V2 + Companion tournent en permanence dès le
    # logon Windows. La popup s'affiche quand Outlook s'ouvre. Les backends
    # s'arrêtent 30 min après la fermeture d'Outlook (économie RAM).
    # =========================================================
    managers = []
    logger.info("Lancement backends au logon (pas d'attente Outlook)...")
    for proc in PROCESSES:
        if proc['delay'] > 0:
            time.sleep(proc['delay'])
        mgr = ProcessManager(proc['name'], proc['script'], proc['port'], pythonw)
        mgr.start()
        managers.append(mgr)
    write_pid_file(os.getpid(), [m.pid for m in managers if m.pid])

    # Attendre que V2 soit prêt (port 3443)
    logger.info("Attente de V2 (port 3443)...")
    for _ in range(30):
        if is_port_listening(3443):
            break
        if os.path.exists(STOP_FILE):
            cleanup()
            return False
        time.sleep(1)
    logger.info("Backends prêts — en veille jusqu'à ouverture Outlook")

    # Pre-warm 24/04 : lance popup_pyqt --pre-warm dès que V2 est ready
    # (même si Outlook pas encore ouvert). Charge Qt + QtWebEngine en
    # hot-instance avec popup cachée. Quand Outlook s'ouvre ensuite,
    # show_pyqt_popup() déclenche l'IPC /show_popup sur l'instance déjà
    # chaude → popup visible en ~200ms au lieu de ~70s (cold start Qt au
    # boot Windows sur disque froid).
    if not is_outlook_running() and not _popup_is_alive():
        try:
            subprocess.Popen(
                [pythonw, POPUP_SCRIPT, '--pre-warm'], cwd=EASYMAIL_DIR,
                creationflags=_NW,
            )
            logger.info("Popup PyQt pre-warm lancé (Qt chargé, popup cachée, IPC 5052 prêt)")
        except Exception as e:
            logger.warning(f"Pre-warm popup_pyqt échoué : {e}")

    # Si Outlook est déjà ouvert (ex: logon pendant Outlook actif),
    # afficher la popup immédiatement
    if is_outlook_running():
        show_pyqt_popup()

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
    # PHASE 3 : Surveillance (audit 20/04)
    # Backends tournent en permanence. On surveille Outlook :
    #   - Outlook ouvre (après être fermé) → show_pyqt_popup (si pas montrée aujourd'hui)
    #   - Outlook fermé 30 min → stop backends (économie RAM)
    #   - Outlook réouvre alors que backends stopped → respawn
    # =========================================================
    _health_counter = 0
    _was_running = is_outlook_running()
    _closed_since = None   # epoch du moment où Outlook a fermé (None = pas fermé)
    BACKENDS_IDLE_TIMEOUT = 30 * 60  # 30 min après fermeture Outlook → stop backends
    while True:
        time.sleep(1)  # Audit 20/04 : 5s → 1s, détection re-ouverture Outlook rapide

        if os.path.exists(STOP_FILE):
            logger.info("Stop demandé (STOP_FILE)")
            break

        running = is_outlook_running()

        # Transition : ouvert → fermé
        if _was_running and not running:
            logger.info("Outlook fermé — décompte 30 min avant arrêt backends")
            _closed_since = time.time()
            # Décision user 24/04 : cacher immédiatement overlay + dialog
            # + child windows. Le process popup_pyqt reste vivant pour
            # ré-affichage instantané au prochain démarrage d'Outlook.
            # Les BG loops V2 + Companion continuent de tourner.
            _popup_hide_all()

        # Transition : fermé → ouvert (y compris si backends stopped)
        if running and not _was_running:
            logger.info("Outlook ré-ouvert — popup si applicable")
            _closed_since = None
            # Si backends stoppés pendant idle → respawn
            if not managers or not managers[0].is_alive():
                logger.info("Respawn backends après idle...")
                managers = []
                for proc in PROCESSES:
                    mgr = ProcessManager(proc['name'], proc['script'], proc['port'], pythonw)
                    mgr.start()
                    managers.append(mgr)
                for _ in range(30):
                    if is_port_listening(3443):
                        break
                    time.sleep(1)
            show_pyqt_popup()

        # Outlook fermé depuis trop longtemps → stop backends
        if _closed_since and (time.time() - _closed_since > BACKENDS_IDLE_TIMEOUT):
            if managers and any(m.is_alive() for m in managers):
                logger.info(f"Outlook fermé > {BACKENDS_IDLE_TIMEOUT//60} min → arrêt backends (économie RAM)")
                for mgr in managers:
                    mgr.stop()
                managers = []
                write_pid_file(os.getpid(), [])
            # On ne break pas : le superviseur continue de surveiller

        _was_running = running

        # Health check backends (toutes les 30 s = 30 × 1 s) — seulement si actifs
        _health_counter += 1
        if _health_counter >= 30:
            _health_counter = 0
            for mgr in managers:
                if not mgr.is_alive():
                    logger.warning(f"{mgr.name}: mort détecté")
                    mgr.restart()
            if managers:
                write_pid_file(os.getpid(), [m.pid for m in managers if m.pid])

    # Arret propre des backends + proto + tray (sur STOP_FILE)
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
        # Audit 20/04 : le superviseur tourne en continu depuis le logon Windows.
        # Les backends sont spawn au démarrage (pas à l'ouverture d'Outlook) et
        # restent actifs tant qu'Outlook est ouvert OU pendant 30 min après sa
        # fermeture. Pas de boucle de relance supplémentaire ici.
        run_supervisor(first_launch=True)
        logger.info("Superviseur arrêté.")
