#!/usr/bin/env python3
"""EasyMail - Installeur V2 : flux guide en 4 etapes avec popups Windows."""

import subprocess
import sys
import os
import json
import ctypes
import shutil

# ============================================================
#  Constantes
# ============================================================
EASYMAIL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(EASYMAIL_DIR, "config.json")
DEPS_FLAG = os.path.join(EASYMAIL_DIR, ".deps_installed")
STYLE_FILE = os.path.join(EASYMAIL_DIR, "style_profile.txt")
DB_FILE = os.path.join(EASYMAIL_DIR, "emails.db")

# Cle API Anthropic (injectee par build_zip.bat)
API_KEY = "__API_KEY_PLACEHOLDER__"

# Token Git read-only (injecte par build_zip.bat)
GIT_TOKEN = "__GIT_TOKEN_PLACEHOLDER__"
GIT_REPO = "github.com/Easymailpower/easymail.git"

REQUIRED_PACKAGES = ["flask==3.0.0", "anthropic==0.40.0", "pywin32"]
OPTIONAL_PACKAGES = ["PyPDF2", "python-docx", "openpyxl"]

# ============================================================
#  Fonctions utilitaires
# ============================================================

# MessageBox constants
MB_OK = 0x00
MB_OKCANCEL = 0x01
MB_YESNO = 0x04
MB_ICONINFO = 0x40
MB_ICONWARNING = 0x30
MB_ICONERROR = 0x10
IDOK = 1
IDYES = 6
IDNO = 7


def popup(title, message, flags=MB_OK | MB_ICONINFO):
    """Affiche une popup Windows native. Retourne le bouton clique."""
    return ctypes.windll.user32.MessageBoxW(0, message, title, flags)


def popup_yesno(title, message):
    """Popup avec boutons Oui/Non. Retourne True si Oui."""
    result = ctypes.windll.user32.MessageBoxW(0, message, title, MB_YESNO | MB_ICONINFO)
    return result == IDYES


def print_step(num, total, text, status=""):
    """Affiche une etape formatee dans la console."""
    prefix = f"  [{num}/{total}]"
    if status:
        print(f"{prefix} {text:<40s} {status}")
    else:
        print(f"{prefix} {text}")


def run_pip(package, quiet=True):
    """Installe un package pip. Retourne True si succes."""
    args = [sys.executable, "-m", "pip", "install", package]
    if quiet:
        args.append("--quiet")
    result = subprocess.run(args, capture_output=True, text=True)
    return result.returncode == 0


def check_git():
    """Verifie si Git est installe. Retourne le chemin ou None."""
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            return result.stdout.strip()
    except FileNotFoundError:
        pass
    # Chercher dans les chemins courants
    for path in [r"C:\Program Files\Git\bin\git.exe", r"C:\Program Files\Git\cmd\git.exe"]:
        if os.path.exists(path):
            return path
    return None


def check_outlook():
    """Verifie si Outlook est installe. Retourne le chemin ou None."""
    # Registre
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\OUTLOOK.EXE")
        path, _ = winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)
        if os.path.exists(path):
            return path
    except Exception:
        pass
    # Chemins courants
    for path in [
        r"C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE",
        r"C:\Program Files (x86)\Microsoft Office\root\Office16\OUTLOOK.EXE",
    ]:
        if os.path.exists(path):
            return path
    return None


# ============================================================
#  DEBUT DE L'INSTALLATION
# ============================================================
print()
print("========================================")
print("  EasyMail - Installation")
print("========================================")
print()

popup("EasyMail - Installation",
      "Bienvenue dans l'installation d'EasyMail !\n\n"
      "L'installation va se derouler en 4 etapes :\n\n"
      "  1. Verification des composants\n"
      "  2. Installation des composants manquants\n"
      "  3. Configuration d'EasyMail\n"
      "  4. Finalisation\n\n"
      "Cliquez OK pour commencer.")


# ============================================================
#  ETAPE 1/4 : Verification des composants
# ============================================================
print("  Etape 1/4 : Verification des composants...")
print()

# --- Python (deja la puisqu'on execute ce script) ---
py_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
print_step(1, 4, f"Python {py_version}", "OK")

# --- Git ---
git_info = check_git()
git_ok = git_info is not None
if git_ok:
    print_step(1, 4, f"Git : {git_info}", "OK")
else:
    print_step(1, 4, "Git : non detecte", "A INSTALLER")

# --- Outlook ---
outlook_path = check_outlook()
outlook_ok = outlook_path is not None
if outlook_ok:
    print_step(1, 4, "Outlook : detecte", "OK")
else:
    print_step(1, 4, "Outlook : non detecte", "REQUIS")

# --- Outlook obligatoire ---
if not outlook_ok:
    popup("EasyMail - Outlook requis",
          "Microsoft Outlook n'a pas ete detecte sur votre ordinateur.\n\n"
          "EasyMail necessite Outlook (version bureau) pour fonctionner.\n\n"
          "Installez Microsoft 365 puis relancez l'installation.",
          MB_OK | MB_ICONERROR)
    print("\n  ERREUR : Outlook non detecte. Installation annulee.")
    sys.exit(1)

print()


# ============================================================
#  ETAPE 2/4 : Installation des composants manquants
# ============================================================
print("  Etape 2/4 : Installation des composants manquants...")
print()

# --- Git ---
if not git_ok:
    install_git = popup_yesno(
        "EasyMail - Etape 2/4 : Mises a jour automatiques",
        "EasyMail a besoin d'un composant appele Git pour\n"
        "recevoir les mises a jour automatiquement.\n\n"
        "Git est un logiciel gratuit et sur, utilise par\n"
        "des millions d'entreprises dans le monde.\n\n"
        "Voulez-vous l'installer maintenant ? (2 minutes)")

    if install_git:
        # Essayer winget d'abord (silencieux)
        print_step(2, 4, "Installation de Git (winget)...", "")
        winget_ok = False
        try:
            result = subprocess.run(
                ["winget", "install", "--id", "Git.Git", "--accept-source-agreements",
                 "--accept-package-agreements", "--silent"],
                capture_output=True, text=True, timeout=120)
            if result.returncode == 0:
                winget_ok = True
                print_step(2, 4, "Git installe via winget", "OK")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        if not winget_ok:
            # Fallback : ouvrir le navigateur
            print_step(2, 4, "Winget non disponible, ouverture du navigateur...", "")
            import webbrowser
            webbrowser.open("https://git-scm.com/download/win")
            popup("EasyMail - Installation de Git",
                  "Votre navigateur va s'ouvrir sur la page de telechargement de Git.\n\n"
                  "Laissez toutes les options par defaut et cliquez 'Next' jusqu'a la fin.\n\n"
                  "Cliquez OK une fois l'installation de Git terminee.",
                  MB_OK | MB_ICONINFO)

        # Re-verifier
        # Rafraichir PATH (Git vient d'etre installe)
        git_paths = [r"C:\Program Files\Git\cmd", r"C:\Program Files\Git\bin"]
        for gp in git_paths:
            if gp not in os.environ.get("PATH", ""):
                os.environ["PATH"] = gp + ";" + os.environ.get("PATH", "")

        git_info = check_git()
        git_ok = git_info is not None
        if git_ok:
            print_step(2, 4, "Git verifie", "OK")
        else:
            print_step(2, 4, "Git non detecte apres installation", "ATTENTION")
            print("    Les mises a jour automatiques ne seront pas disponibles.")
            print("    Vous pourrez installer Git plus tard si besoin.")
    else:
        print_step(2, 4, "Git : installation reportee", "SKIP")
        print("    Les mises a jour automatiques ne seront pas disponibles.")
else:
    print_step(2, 4, "Tous les composants sont presents", "OK")

print()


# ============================================================
#  ETAPE 3/4 : Configuration d'EasyMail
# ============================================================
print("  Etape 3/4 : Configuration d'EasyMail...")
print()

# --- pip ---
print_step(3, 4, "Verification de pip...", "")
result = subprocess.run([sys.executable, "-m", "pip", "--version"],
                        capture_output=True, text=True)
if result.returncode != 0:
    subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"],
                   capture_output=True, text=True)
    result = subprocess.run([sys.executable, "-m", "pip", "--version"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        popup("EasyMail - Erreur pip",
              "pip (gestionnaire de paquets Python) n'a pas pu etre installe.\n\n"
              "Essayez : python -m ensurepip --upgrade\n"
              "Puis relancez l'installation.",
              MB_OK | MB_ICONERROR)
        sys.exit(1)
print_step(3, 4, "pip", "OK")

# --- Dependances ---
print_step(3, 4, "Installation des dependances...", "")
for pkg in REQUIRED_PACKAGES:
    name = pkg.split("==")[0]
    print(f"        {name:<30s}", end=" ", flush=True)
    if run_pip(pkg):
        print("OK")
    else:
        print("ECHEC")
        popup("EasyMail - Erreur dependance",
              f"Le composant '{name}' n'a pas pu etre installe.\n\n"
              "Verifiez votre connexion internet et relancez l'installation.",
              MB_OK | MB_ICONERROR)
        sys.exit(1)

for pkg in OPTIONAL_PACKAGES:
    print(f"        {pkg:<30s}", end=" ", flush=True)
    if run_pip(pkg):
        print("OK")
    else:
        print("optionnel")

# --- Post-install pywin32 ---
print_step(3, 4, "Verification COM (Outlook)...", "")
try:
    import win32com.client
    print_step(3, 4, "win32com.client", "OK")
except ImportError:
    scripts_dir = os.path.join(os.path.dirname(sys.executable), "Scripts")
    postinstall = os.path.join(scripts_dir, "pywin32_postinstall.py")
    if os.path.exists(postinstall):
        subprocess.run([sys.executable, postinstall, "-install"],
                       capture_output=True, text=True)
    try:
        subprocess.run([sys.executable, "-c",
                        "import pywin32_postinstall; pywin32_postinstall.install()"],
                       capture_output=True, text=True)
    except Exception:
        pass
    try:
        import win32com.client
        print_step(3, 4, "win32com.client", "OK (apres post-install)")
    except ImportError:
        popup("EasyMail - Erreur COM",
              "Le composant COM (win32com) n'a pas pu etre charge.\n\n"
              "Essayez : pip install --force-reinstall pywin32\n"
              "Puis relancez l'installation.",
              MB_OK | MB_ICONERROR)
        sys.exit(1)

try:
    import pythoncom
    print_step(3, 4, "pythoncom", "OK")
except ImportError:
    popup("EasyMail - Erreur COM",
          "Le composant pythoncom n'est pas disponible.\n\n"
          "Reinstallez pywin32 et relancez l'installation.",
          MB_OK | MB_ICONERROR)
    sys.exit(1)

# --- Test Outlook ---
print_step(3, 4, "Test connexion Outlook...", "")
try:
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()

    # Verifier si Outlook est en cours d'execution
    outlook_running = False
    try:
        result = subprocess.run(["tasklist", "/FI", "IMAGENAME eq OUTLOOK.EXE"],
                                capture_output=True, text=True)
        outlook_running = "OUTLOOK.EXE" in result.stdout
    except Exception:
        pass

    if not outlook_running:
        popup("EasyMail - Outlook",
              "Outlook n'est pas demarre.\n\n"
              "EasyMail va tenter de lancer Outlook.\n"
              "Patientez quelques secondes...",
              MB_OK | MB_ICONINFO)
        try:
            os.startfile(outlook_path)
            import time
            time.sleep(10)
        except Exception:
            pass

    try:
        app = win32com.client.GetActiveObject("Outlook.Application")
    except Exception:
        app = win32com.client.Dispatch("Outlook.Application")

    ns = app.GetNamespace("MAPI")
    try:
        user = ns.CurrentUser.Name
        print_step(3, 4, f"Utilisateur Outlook : {user}", "OK")
    except Exception:
        print_step(3, 4, "Utilisateur Outlook : inconnu", "")

    try:
        inbox = ns.GetDefaultFolder(6)
        count = inbox.Items.Count
        print_step(3, 4, f"Boite de reception : {count} messages", "OK")
    except Exception as e:
        if "GetDefaultFolder" in str(e) or "MAPI" in str(e):
            popup("EasyMail - Configuration Outlook",
                  "Outlook est ouvert mais aucun compte n'est configure.\n\n"
                  "Ajoutez votre compte email dans Outlook puis relancez l'installation.",
                  MB_OK | MB_ICONWARNING)
            pythoncom.CoUninitialize()
            sys.exit(1)
    pythoncom.CoUninitialize()

except Exception as e:
    print(f"    Avertissement connexion Outlook : {e}")
    print("    Lancez Outlook avant de demarrer EasyMail.")

# --- Git clone/init ---
if git_ok:
    print_step(3, 4, "Configuration mises a jour automatiques...", "")
    os.chdir(EASYMAIL_DIR)
    is_git_repo = subprocess.run(["git", "rev-parse", "--git-dir"],
                                 capture_output=True, text=True).returncode == 0
    if is_git_repo:
        result = subprocess.run(["git", "pull", "--quiet"],
                                capture_output=True, text=True, timeout=30)
        print_step(3, 4, "Mises a jour", "OK (depot existant)")
    else:
        if GIT_TOKEN != "__GIT_TOKEN_PLACEHOLDER__":
            remote_url = f"https://{GIT_TOKEN}@{GIT_REPO}"
            subprocess.run(["git", "init", "--quiet"], capture_output=True, text=True)
            subprocess.run(["git", "remote", "add", "origin", remote_url],
                           capture_output=True, text=True)
            result = subprocess.run(["git", "fetch", "--quiet", "origin"],
                                    capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                subprocess.run(["git", "checkout", "-B", "main", "origin/main", "--quiet"],
                               capture_output=True, text=True)
                print_step(3, 4, "Mises a jour automatiques", "OK")
            else:
                print_step(3, 4, "Connexion depot distant", "ECHEC")
                print("    Les mises a jour ne seront pas disponibles.")
                git_dir = os.path.join(EASYMAIL_DIR, ".git")
                if os.path.isdir(git_dir):
                    shutil.rmtree(git_dir, ignore_errors=True)
else:
    print_step(3, 4, "Mises a jour automatiques", "SKIP (Git non installe)")

# --- config.json ---
print_step(3, 4, "Configuration cle API...", "")
print(f"    Chemin config : {CONFIG_PATH}", flush=True)
print(f"    Cle API source : {'injectee' if API_KEY != '__API_KEY_PLACEHOLDER__' else 'placeholder'}", flush=True)
_config_ok = False
try:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
        key = config.get("ANTHROPIC_API_KEY", "")
        if key and "COLLER_ICI" not in key and key.startswith("sk-"):
            print_step(3, 4, "config.json existant preserve", "OK")
            _config_ok = True
        else:
            if API_KEY != "__API_KEY_PLACEHOLDER__":
                config["ANTHROPIC_API_KEY"] = API_KEY
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
                print_step(3, 4, "Cle API mise a jour", "OK")
                _config_ok = True
    else:
        if API_KEY != "__API_KEY_PLACEHOLDER__":
            config = {"ANTHROPIC_API_KEY": API_KEY}
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            print_step(3, 4, "config.json cree", "OK")
            _config_ok = True
        else:
            config = {"ANTHROPIC_API_KEY": "COLLER_ICI_VOTRE_CLE_ANTHROPIC"}
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            print("    config.json cree avec un placeholder.")
except Exception as e:
    print(f"    ERREUR creation config.json : {e}", flush=True)

# Verification finale : config.json existe et contient une cle valide
if not _config_ok:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _check = json.load(f)
        if _check.get("ANTHROPIC_API_KEY", "").startswith("sk-"):
            _config_ok = True
    except Exception:
        pass

if not _config_ok:
    print("    ATTENTION : config.json n'a pas pu etre configure correctement.", flush=True)
    print(f"    Creez manuellement le fichier : {CONFIG_PATH}", flush=True)
    print(f"    Contenu : {{\"ANTHROPIC_API_KEY\": \"votre_cle_ici\"}}", flush=True)

# --- Preservation donnees ---
preserved = []
if os.path.exists(DB_FILE):
    preserved.append("emails.db")
if os.path.exists(STYLE_FILE):
    preserved.append("style_profile.txt")
if preserved:
    print(f"    Donnees existantes preservees : {', '.join(preserved)}")

# --- Warning OneDrive ---
if "\\OneDrive\\" in EASYMAIL_DIR or "\\OneDrive " in EASYMAIL_DIR:
    print()
    print("    NOTE : EasyMail est dans un dossier OneDrive.")
    print("    Si vous rencontrez des lenteurs, deplacez-le dans C:\\EasyMail")

print()


# ============================================================
#  ETAPE 4/4 : Finalisation
# ============================================================
print("  Etape 4/4 : Finalisation...")
print()

# --- Raccourci bureau ---
print_step(4, 4, "Creation du raccourci bureau...", "")
try:
    import pythoncom
    pythoncom.CoInitialize()
    import win32com.client
    shell = win32com.client.Dispatch("WScript.Shell")
    desktop = shell.SpecialFolders("Desktop")
    shortcut_path = os.path.join(desktop, "EasyMail.lnk")
    start_bat = os.path.join(EASYMAIL_DIR, "start.bat")

    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.TargetPath = start_bat
    shortcut.WorkingDirectory = EASYMAIL_DIR
    shortcut.Description = "EasyMail - Assistant email intelligent"
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    shortcut.IconLocation = os.path.join(system_root, "System32", "shell32.dll") + ",19"
    shortcut.save()
    print_step(4, 4, "Raccourci bureau", "OK")
except Exception as e:
    print(f"    Echec creation raccourci : {e}")
    print(f"    Creez un raccourci vers : {os.path.join(EASYMAIL_DIR, 'start.bat')}")

# --- Flag deps ---
with open(DEPS_FLAG, "w") as f:
    f.write("ok")

# --- Message final console ---
print()
print("========================================")
print("  Installation terminee !")
print("========================================")
print()

# --- Popup finale ---
popup("EasyMail - Installation terminee !",
      "EasyMail est installe avec succes !\n\n"
      "Un raccourci 'EasyMail' a ete cree sur votre bureau.\n\n"
      "Avant le premier lancement :\n"
      "  - Outlook doit etre ouvert\n"
      "  - Internet doit etre connecte\n\n"
      "Au premier demarrage, EasyMail analysera vos emails\n"
      "pendant 2-3 minutes pour apprendre votre style.\n\n"
      "Les mises a jour sont automatiques a chaque\n"
      "demarrage d'EasyMail. Rien a faire !",
      MB_OK | MB_ICONINFO)
