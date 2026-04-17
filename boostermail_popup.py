"""
BoosterMail — Popup de lancement (tkinter)
Design moderne. Boutons Annuler + Lancer. Barre de progression.
Ecrit .boostermail.launch au clic Lancer.
"""
import os
import sys
import time
import socket
import tkinter as tk
import tkinter.ttk as ttk

EASYMAIL_DIR = os.path.dirname(os.path.abspath(__file__))
SIGNAL_FILE = os.path.join(EASYMAIL_DIR, '.boostermail.launch')
PORTS = [5051, 3443]


def is_port_listening(port):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(('127.0.0.1', port)) == 0
    except Exception:
        return False


def main():
    root = tk.Tk()
    root.title("BoosterMail")
    root.overrideredirect(True)  # Pas de barre titre
    root.configure(bg='#5B4FBF')
    root.attributes('-topmost', True)

    # Dimensions
    W, H = 440, 320
    root.geometry(f"{W}x{H}")
    root.update_idletasks()
    x = (root.winfo_screenwidth() - W) // 2
    y = (root.winfo_screenheight() - H) // 2
    root.geometry(f"{W}x{H}+{x}+{y}")

    # Arrondi simule : fond degrade
    bg = '#5B4FBF'

    # Carte blanche centree
    card = tk.Frame(root, bg='white', highlightbackground='#e0e0e0', highlightthickness=1)
    card.place(relx=0.5, rely=0.5, anchor='center', width=400, height=280)

    # Icone
    icon_frame = tk.Frame(card, bg='#0F6CBD', width=56, height=56)
    icon_frame.place(relx=0.5, y=30, anchor='center')
    icon_label = tk.Label(icon_frame, text='\u2709', font=('Segoe UI', 24), fg='white', bg='#0F6CBD')
    icon_label.place(relx=0.5, rely=0.5, anchor='center')

    # Titre
    tk.Label(card, text='BoosterMail', font=('Segoe UI', 20, 'bold'),
             fg='#1a1a2e', bg='white').place(relx=0.5, y=75, anchor='center')

    # Sous-titre
    sub = tk.Label(card, text='Repondez a vos mails 5X plus vite\ngrace a l\'intelligence artificielle',
                   font=('Segoe UI', 11), fg='#666', bg='white', justify='center')
    sub.place(relx=0.5, y=115, anchor='center')

    # Zone boutons
    btn_frame = tk.Frame(card, bg='white')
    btn_frame.place(relx=0.5, y=175, anchor='center')

    def on_cancel():
        root.destroy()

    def on_launch():
        btn_frame.place_forget()
        progress_frame.place(relx=0.5, y=185, anchor='center', width=320)
        try:
            with open(SIGNAL_FILE, 'w') as f:
                f.write('launch')
        except Exception:
            pass
        start_progress()

    btn_cancel = tk.Button(btn_frame, text='Annuler', font=('Segoe UI', 11),
                           fg='#666', bg='#f0f0f0', activebackground='#e0e0e0',
                           relief='flat', padx=20, pady=8, cursor='hand2',
                           command=on_cancel)
    btn_cancel.pack(side='left', padx=(0, 10))

    btn_launch = tk.Button(btn_frame, text='Lancer BoosterMail', font=('Segoe UI', 11, 'bold'),
                           fg='white', bg='#0F6CBD', activebackground='#0a5a9e',
                           relief='flat', padx=20, pady=8, cursor='hand2',
                           command=on_launch)
    btn_launch.pack(side='left')

    # Zone progression (cachee)
    progress_frame = tk.Frame(card, bg='white')

    style = ttk.Style()
    style.theme_use('default')
    style.configure('BM.Horizontal.TProgressbar',
                    troughcolor='#e8e8e8', background='#0F6CBD', thickness=6)
    pbar = ttk.Progressbar(progress_frame, length=320, mode='determinate',
                           style='BM.Horizontal.TProgressbar')
    pbar.pack(pady=(0, 8))
    plabel = tk.Label(progress_frame, text='Preparation en cours...',
                      font=('Segoe UI', 9), fg='#999', bg='white')
    plabel.pack()

    def start_progress():
        start_time = time.time()
        max_duration = 8.0

        def tick():
            elapsed = time.time() - start_time
            ports_ready = sum(1 for p in PORTS if is_port_listening(p))
            real_pct = (ports_ready / len(PORTS)) * 100
            time_pct = min(95, (elapsed / max_duration) * 100)
            pct = max(real_pct, time_pct)
            pbar['value'] = pct

            if ports_ready == len(PORTS) or elapsed >= max_duration:
                pbar['value'] = 100
                plabel.config(text='Pret !')
                root.after(500, root.destroy)
                return
            root.after(300, tick)

        tick()

    # Fermeture par X ou clic hors popup → ecrire le signal aussi
    def on_close():
        try:
            with open(SIGNAL_FILE, 'w') as f:
                f.write('launch')
        except Exception:
            pass
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', on_close)

    # Focus
    root.lift()
    root.focus_force()
    root.after(500, lambda: (root.lift(), root.focus_force()))
    root.after(2000, lambda: (root.lift(), root.focus_force()))

    root.mainloop()


if __name__ == '__main__':
    main()
