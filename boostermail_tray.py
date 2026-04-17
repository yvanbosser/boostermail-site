"""
BoosterMail — Icone System Tray
Apparait quand BM est lance. Clic gauche → inbox proto. Clic droit → menu.
Uniquement si Classic Outlook est detecte sur le PC.
"""
import os
import sys
import subprocess
import webbrowser
import logging

EASYMAIL_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(EASYMAIL_DIR, 'boostermail.log')
INBOX_URL = 'http://localhost:5050'
ICON_PATH = os.path.join(EASYMAIL_DIR, 'extension', 'icons', 'icon-32.png')

logging.basicConfig(filename=LOG_FILE, level=logging.INFO,
                    format='%(asctime)s [tray] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger('tray')


def has_classic_outlook():
    """Detecte si Classic Outlook est installe sur le PC."""
    paths = [
        r'C:\Program Files\Microsoft Office\root\Office16\OUTLOOK.EXE',
        r'C:\Program Files (x86)\Microsoft Office\root\Office16\OUTLOOK.EXE',
        r'C:\Program Files\Microsoft Office\Office16\OUTLOOK.EXE',
        r'C:\Program Files (x86)\Microsoft Office\Office16\OUTLOOK.EXE',
        r'C:\Program Files\Microsoft Office\root\Office15\OUTLOOK.EXE',
        r'C:\Program Files (x86)\Microsoft Office\root\Office15\OUTLOOK.EXE',
    ]
    for p in paths:
        if os.path.exists(p):
            return True
    # Fallback : chercher dans le registre
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


def create_icon_image():
    """Charge l'icone BM ou cree une icone par defaut."""
    from PIL import Image
    if os.path.exists(ICON_PATH):
        return Image.open(ICON_PATH)
    # Fallback : icone bleue simple
    img = Image.new('RGB', (32, 32), '#0F6CBD')
    return img


def open_inbox():
    """Ouvre l'inbox du proto dans le navigateur."""
    logger.info("Ouverture inbox proto")
    webbrowser.open(INBOX_URL)


def quit_app(icon):
    """Quitte BoosterMail (arrete le tray + signal au superviseur)."""
    logger.info("Quit depuis le tray")
    # Creer le fichier stop pour le superviseur
    stop_file = os.path.join(EASYMAIL_DIR, '.boostermail.stop')
    try:
        with open(stop_file, 'w') as f:
            f.write('stop')
    except Exception:
        pass
    icon.stop()


def run_tray():
    """Lance l'icone system tray."""
    import pystray
    from pystray import MenuItem, Menu

    image = create_icon_image()

    menu = Menu(
        MenuItem('Ouvrir BoosterMail', lambda icon, item: open_inbox(), default=True),
        MenuItem('Quitter', lambda icon, item: quit_app(icon)),
    )

    icon = pystray.Icon('BoosterMail', image, 'BoosterMail', menu)
    logger.info("Icone tray demarree")
    icon.run()


def main():
    try:
        if not has_classic_outlook():
            logger.info("Classic Outlook non detecte — icone tray desactivee")
            return

        logger.info("Classic Outlook detecte — lancement icone tray")
        run_tray()
    except Exception as e:
        logger.error(f"Erreur tray: {e}")
        raise


if __name__ == '__main__':
    main()
