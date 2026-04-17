# moteur_v2/speculation.py — Génération spéculative V2
# Prépare la réponse en arrière-plan avant que l'utilisateur clique
# 5 filtres : vieux (>7j), traité, noreply, court (<10 chars), CC
# Indépendant du proto (pas de COM)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
