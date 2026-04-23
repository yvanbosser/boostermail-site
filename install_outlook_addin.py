"""
BoosterMail - Installation silencieuse de l'add-in Outlook (New + Classic)
==========================================================================

Enregistre le manifest Office.js pour que le bouton "EasyMail" apparaisse
dans Outlook **sans AUCUNE action utilisateur** :

  1. Installe le certificat localhost.crt dans le store "Trusted Root"
     du user courant (via certutil, aucun UAC requis).
  2. Écrit la clé registre de sideload dans
     HKCU\\Software\\Microsoft\\Office\\16.0\\Wef\\Developer :
       Valeur = <GUID du manifest>
       Type   = REG_SZ
       Data   = chemin absolu vers manifest.xml
     C'est EXACTEMENT ce que fait `office-addin-dev-settings` (le moteur
     derrière `npx @microsoft/teamsapp-cli install`) pour un manifest XML.

Usage :
  py install_outlook_addin.py           # installation silencieuse
  py install_outlook_addin.py --verbose # log détaillé
  py install_outlook_addin.py --uninstall

Appelé automatiquement par :
  - install.ps1                          (installation initiale BM)
  - boostermail_service.py au logon      (auto-réparation idempotente)

Exit codes :
  0 = tout bon (déjà installé OU install réussie)
  1 = erreur (logs avec --verbose)
"""

import os
import sys
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

# --- Configuration -----------------------------------------------------------
EASYMAIL_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = EASYMAIL_DIR / 'V2' / 'manifest.xml'
CERT_PATH = EASYMAIL_DIR / 'V2' / 'localhost.crt'

# Clé registre sideload (Office 16.0 = Office 2016+, 2019, 2021, 365)
# Référence : Office-Addin-Scripts/dev-settings-windows.ts (Microsoft officiel)
REG_KEY_PATH = r'Software\Microsoft\Office\16.0\Wef\Developer'

# Nom de cert pour le store (permet désinstallation propre)
CERT_FRIENDLY_NAME = 'BoosterMail localhost dev'

VERBOSE = '--verbose' in sys.argv or '-v' in sys.argv
UNINSTALL = '--uninstall' in sys.argv


def log(msg, level='INFO'):
    """Log simple : always print errors/warnings, INFO only in verbose.
    Fix audit 22/04 (it.2) : WARN ajoute au toujours-afficher pour que les
    alertes user (ex: cert a nettoyer manuellement dans --uninstall) soient
    visibles meme sans -v."""
    if level in ('ERROR', 'WARN') or VERBOSE:
        print(f"[install-addin] [{level}] {msg}")


def read_manifest_id(manifest_path: Path) -> str | None:
    """Parse manifest.xml pour extraire le <Id>GUID</Id>."""
    try:
        tree = ET.parse(manifest_path)
        root = tree.getroot()
        # Le tag <Id> peut avoir un namespace (OfficeApp ns)
        for elem in root.iter():
            tag = elem.tag.split('}')[-1]  # strip namespace
            if tag == 'Id' and elem.text:
                return elem.text.strip()
        return None
    except Exception as e:
        log(f"Erreur parsing manifest {manifest_path}: {e}", 'ERROR')
        return None


def write_sideload_registry(manifest_id: str, manifest_path: Path) -> bool:
    """Écrit la clé registre de sideload New/Classic Outlook.

    Crée/ouvre HKCU\\Software\\Microsoft\\Office\\16.0\\Wef\\Developer
    puis y pose une valeur REG_SZ nommée <manifest_id> contenant le
    chemin absolu du manifest.xml.

    Idempotent : si la valeur existe déjà avec le bon chemin, ne fait rien.
    """
    try:
        import winreg
    except ImportError:
        log("winreg non disponible (pas Windows ?)", 'ERROR')
        return False

    target_path = str(manifest_path.resolve())

    try:
        # KEY_SET_VALUE suffit, pas besoin d'admin pour HKCU
        key = winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0,
                                 winreg.KEY_READ | winreg.KEY_WRITE)
        try:
            # Vérifier idempotence
            try:
                existing, existing_type = winreg.QueryValueEx(key, manifest_id)
                if existing_type == winreg.REG_SZ and existing == target_path:
                    log(f"Registry déjà à jour : {manifest_id} -> {target_path}")
                    return True
                log(f"Registry existe avec valeur différente ({existing}) -> mise à jour")
            except FileNotFoundError:
                log(f"Registry absent -> création")

            winreg.SetValueEx(key, manifest_id, 0, winreg.REG_SZ, target_path)
            log(f"Registry écrit : HKCU\\{REG_KEY_PATH}  [{manifest_id}] = {target_path}")
            return True
        finally:
            winreg.CloseKey(key)
    except PermissionError as e:
        log(f"Permission refusée pour écrire le registry : {e}", 'ERROR')
        return False
    except Exception as e:
        log(f"Erreur écriture registry : {e}", 'ERROR')
        return False


def remove_sideload_registry(manifest_id: str) -> bool:
    """Retire la valeur de sideload (pour --uninstall)."""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0,
                             winreg.KEY_READ | winreg.KEY_WRITE)
        try:
            winreg.DeleteValue(key, manifest_id)
            log(f"Registry supprimé : {manifest_id}")
        finally:
            winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        log("Registry absent (rien à supprimer)")
        return True
    except Exception as e:
        log(f"Erreur suppression registry : {e}", 'ERROR')
        return False


def install_cert_trusted_root(cert_path: Path) -> bool:
    """Installe le certificat dans le store 'Trusted Root' de l'user courant.

    Utilise certutil (outil Windows natif) : aucun UAC requis avec -user.
    Idempotent : certutil -addstore ne duplique pas si le cert est déjà présent.

    Pourquoi : WebView2 de New Outlook refuse les self-signed sinon
    (NET::ERR_CERT_AUTHORITY_INVALID, dialog blanc).
    """
    if not cert_path.exists():
        log(f"Certificat introuvable : {cert_path}", 'ERROR')
        return False

    # Audit 22/04 (D1) : on DÉTECTE les certs BoosterMail obsolètes pour
    # alerter l'user (pollution du store), mais on ne les SUPPRIME PAS
    # automatiquement. Raison : Windows protège les certs Trusted Root avec
    # un popup de confirmation modal impossible à bypasser en CLI silencieux.
    # Un ancien cert "voisin" est inoffensif en pratique : V2 sert le cert
    # depuis le FICHIER localhost.crt, Windows valide via le thumbprint du
    # cert servi -> seul le cert matching est utilisé.
    _warn_obsolete_certs(cert_path)

    try:
        # certutil -user -addstore : store user, pas de UAC
        # Root = "Trusted Root Certification Authorities"
        result = subprocess.run(
            ['certutil', '-user', '-addstore', '-f', 'Root', str(cert_path)],
            capture_output=True, text=True, timeout=15,
            creationflags=0x08000000,  # CREATE_NO_WINDOW : pas de flash console
        )
        if result.returncode == 0:
            log(f"Certificat installé dans Cert:\\CurrentUser\\Root")
            return True
        log(f"certutil a échoué (code {result.returncode}) : {result.stderr.strip()}",
            'ERROR')
        return False
    except subprocess.TimeoutExpired:
        log("certutil timeout 15s", 'ERROR')
        return False
    except FileNotFoundError:
        log("certutil.exe introuvable (ce n'est pas Windows ?)", 'ERROR')
        return False
    except Exception as e:
        log(f"Erreur certutil : {e}", 'ERROR')
        return False


def _warn_obsolete_certs(current_cert_path: Path) -> None:
    """
    Détecte la présence de certs BoosterMail obsolètes (CN=localhost,
    O=EasyMail Dev) dans le Trusted Root user/machine qui n'ont pas le
    thumbprint du fichier cert courant. Logge un warning TRÈS VISIBLE
    avec la commande EXACTE à copier-coller - ne supprime PAS (Windows
    protège les certs Trusted Root avec popup de confirmation modal
    impossible à bypasser en CLI silencieux).

    Fix audit 23/04 : auparavant l'alerte était noyée, le superviseur ne
    remontait rien, et le doublon cassait silencieusement le bouton BM au
    démarrage. Maintenant : bloc encadré, commande exacte, visibilité max.
    """
    try:
        # Thumbprint du fichier cert courant (celui qu'on veut GARDER)
        current_thumb = ''
        try:
            ps_get_thumb = (
                f"$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2('{current_cert_path}'); "
                "$cert.Thumbprint"
            )
            r = subprocess.run(
                ['powershell', '-NoProfile', '-Command', ps_get_thumb],
                capture_output=True, text=True, timeout=5,
                creationflags=0x08000000,
            )
            current_thumb = (r.stdout or '').strip().upper()
        except Exception:
            pass

        # Lister les certs BoosterMail dans CurrentUser\Root ET LocalMachine\Root
        # (les 2 stores peuvent contenir des doublons).
        ps_script = (
            "Get-ChildItem Cert:\\CurrentUser\\Root, Cert:\\LocalMachine\\Root "
            "-ErrorAction SilentlyContinue | "
            "Where-Object { $_.Subject -like '*CN=localhost*' -and "
            "$_.Subject -like '*EasyMail Dev*' } | "
            "ForEach-Object { $_.PSParentPath.Split(':')[-1] + '|' + "
            "$_.Thumbprint + '|' + $_.NotAfter.ToString('yyyy-MM-dd') }"
        )
        result = subprocess.run(
            ['powershell', '-NoProfile', '-Command', ps_script],
            capture_output=True, text=True, timeout=10,
            creationflags=0x08000000,
        )
        raw_lines = [l.strip() for l in (result.stdout or '').splitlines() if l.strip()]

        # Séparer current vs obsolètes
        obsolete = []
        for line in raw_lines:
            parts = line.split('|')
            if len(parts) >= 2 and parts[1].upper() != current_thumb:
                obsolete.append(line)

        if not obsolete:
            return  # propre

        # Bloc alerte très visible (repéré par boostermail_service superviseur)
        log('', 'WARN')
        log('================================================================', 'WARN')
        log('!! CERT DOUBLON DETECTE - LE BOUTON BM RISQUE DE NE PAS APPARAITRE', 'WARN')
        log('================================================================', 'WARN')
        log(f'{len(obsolete)} cert(s) BoosterMail obsolete(s) dans Trusted Root :', 'WARN')
        for line in obsolete:
            log(f'   {line}', 'WARN')
        log('Cert ACTUEL a conserver :', 'WARN')
        log(f'   {current_thumb}' if current_thumb else '   (thumbprint non lu)', 'WARN')
        log('', 'WARN')
        log('ACTION REQUISE - commandes a executer dans PowerShell :', 'WARN')
        # Regrouper par store pour commandes lisibles
        user_thumbs = set()
        machine_thumbs = set()
        for line in obsolete:
            parts = line.split('|')
            if len(parts) >= 2:
                thumb = parts[1]
                if 'CurrentUser' in parts[0]:
                    user_thumbs.add(thumb)
                elif 'LocalMachine' in parts[0]:
                    machine_thumbs.add(thumb)
        if user_thumbs:
            log('  --- Pour store UTILISATEUR (PowerShell normal) ---', 'WARN')
            for t in sorted(user_thumbs):
                log(f'     certutil -user -delstore Root {t}', 'WARN')
            log('     --> cliquer "Oui" sur le popup Windows', 'WARN')
        if machine_thumbs:
            log('  --- Pour store MACHINE (PowerShell en ADMIN) ---', 'WARN')
            log('     clic droit sur PowerShell -> "Executer en tant qu\'administrateur"', 'WARN')
            for t in sorted(machine_thumbs):
                log(f'     certutil -delstore Root {t}', 'WARN')
        log('', 'WARN')
        log('Apres nettoyage : redemarrer Outlook pour voir le bouton BM reapparaitre.', 'WARN')
        log('================================================================', 'WARN')
        log('', 'WARN')
    except Exception as e:
        log(f"Detection certs obsoletes : {e}")


def remove_cert_trusted_root() -> bool:
    """Retire le cert du store Root (pour --uninstall). Best effort.

    Fix audit 22/04 (Pattern #7) : certutil -delstore sur CurrentUser\\Root
    declenche un popup Windows modal "Voulez-vous SUPPRIMER le certificat"
    qui bloque le subprocess en CLI silencieux (timeout 15s). On ne tente
    plus la suppression automatique - on alerte l'user pour nettoyage manuel
    via MMC ou PowerShell interactif.
    """
    # Fix audit 22/04 (it.2) : level WARN pour que le message soit VISIBLE
    # meme sans -v. Sans ca, `--uninstall` silencieux disait "succes" alors
    # que le cert restait dans Trusted Root (alerte jamais delivree).
    log("Cert removal : nettoyage manuel requis (popup Windows modal "
        "bloquant empeche la suppression silencieuse).", 'WARN')
    log("  Win+R > mmc > Ajouter composant > Certificats > Mon compte user",
        'WARN')
    log("  > Autorites racines de confiance > Certificats > supprimer "
        "'O=EasyMail Dev, CN=localhost'", 'WARN')
    log("  OU PowerShell interactif :", 'WARN')
    log('    Get-ChildItem Cert:\\CurrentUser\\Root | Where-Object { '
        '$_.Subject -like "*EasyMail Dev*" } | Remove-Item', 'WARN')
    # Retourne True car ce n'est pas un echec - juste deporte sur l'user
    return True


def copy_manifest_to_wef_developer(manifest_path: Path) -> bool:
    """Copie le manifest.xml dans %LOCALAPPDATA%\\Microsoft\\Office\\16.0\\Wef\\Developer\\
    - mécanisme utilisé par **Classic Outlook** (outlook.exe) pour détecter
    les add-ins sideloadés.

    Fix 21/04 audit (correction d'une erreur précédente) : contrairement à ce
    que je pensais, Classic Outlook N'UTILISE PAS la clé registre - il scanne
    ce dossier au démarrage. Il faut donc les DEUX mécanismes en parallèle :
      - Fichier ici (pour Classic)
      - Clé registre HKCU\\...\\Wef\\Developer\\<id> = path (pour New Outlook)

    Idempotent : compare les hash SHA256 avant d'écraser.
    """
    import shutil
    import hashlib

    local_appdata = os.environ.get('LOCALAPPDATA', '')
    if not local_appdata:
        return False
    wef_dir = Path(local_appdata) / 'Microsoft' / 'Office' / '16.0' / 'Wef' / 'Developer'
    dst = wef_dir / 'BoosterMail.manifest.xml'

    try:
        wef_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        log(f"Impossible de créer {wef_dir} : {e}", 'ERROR')
        return False

    def _sha256(p: Path) -> str | None:
        try:
            h = hashlib.sha256()
            with open(p, 'rb') as f:
                h.update(f.read())
            return h.hexdigest()
        except Exception:
            return None

    src_hash = _sha256(manifest_path)
    dst_hash = _sha256(dst) if dst.exists() else None
    if src_hash and src_hash == dst_hash:
        log(f"Wef\\Developer\\BoosterMail.manifest.xml déjà à jour")
        return True

    try:
        shutil.copy2(str(manifest_path), str(dst))
        log(f"Manifest copié (Classic Outlook) : {dst}")
        return True
    except Exception as e:
        log(f"Échec copie manifest : {e}", 'ERROR')
        return False


def remove_manifest_from_wef_developer() -> bool:
    """Retire le manifest du dossier Wef\\Developer (désinstallation)."""
    local_appdata = os.environ.get('LOCALAPPDATA', '')
    if not local_appdata:
        return False
    legacy = Path(local_appdata) / 'Microsoft' / 'Office' / '16.0' / 'Wef' \
             / 'Developer' / 'BoosterMail.manifest.xml'
    if legacy.exists():
        try:
            legacy.unlink()
            log(f"Manifest retiré : {legacy}")
            return True
        except Exception as e:
            log(f"Impossible de supprimer {legacy} : {e}")
            return False
    return True


def main() -> int:
    log(f"EASYMAIL_DIR = {EASYMAIL_DIR}")
    log(f"manifest     = {MANIFEST_PATH}")
    log(f"cert         = {CERT_PATH}")

    if not MANIFEST_PATH.exists():
        log(f"Manifest introuvable : {MANIFEST_PATH}", 'ERROR')
        return 1

    manifest_id = read_manifest_id(MANIFEST_PATH)
    if not manifest_id:
        log("Impossible de lire le <Id> du manifest", 'ERROR')
        return 1
    log(f"Manifest Id = {manifest_id}")

    if UNINSTALL:
        log("=== DÉSINSTALLATION ===")
        r1 = remove_sideload_registry(manifest_id)
        r2 = remove_cert_trusted_root()
        r3 = remove_manifest_from_wef_developer()
        return 0 if (r1 and r2 and r3) else 1

    # === INSTALLATION ===
    log("=== INSTALLATION ===")

    # 1. Cert en Trusted Root (user, pas UAC)
    ok_cert = install_cert_trusted_root(CERT_PATH)
    if not ok_cert:
        log("Échec install cert - WebView2 pourrait refuser https://localhost:3443",
            'ERROR')
        # On continue quand même : parfois le cert existe déjà sans que certutil
        # le détecte. Le registry vaut le coup d'être écrit dans tous les cas.

    # 2a. Fichier Wef\Developer (mécanisme Classic Outlook)
    ok_file = copy_manifest_to_wef_developer(MANIFEST_PATH)
    if not ok_file:
        log("Échec copie manifest dans Wef\\Developer - bouton Classic Outlook pourrait ne pas apparaître", 'ERROR')

    # 2b. Registry HKCU\...\Wef\Developer\<id> = path (mécanisme New Outlook)
    ok_reg = write_sideload_registry(manifest_id, MANIFEST_PATH)
    if not ok_reg:
        log("Échec écriture registry", 'ERROR')
        return 1

    log("OK - Outlook doit être redémarré pour que le bouton EasyMail apparaisse.")
    print("[install-addin] OK - redémarrez Outlook pour voir le bouton EasyMail dans le ruban.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
