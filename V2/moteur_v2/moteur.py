# moteur_v2/moteur.py — Moteur V2 BoosterMail
# Post-envoi (3 fils), recalibrage adaptatif, re-analyse contacts
# Utilise claude_ai.py et database.py en lecture seule (partagés avec le proto)
# NE PAS MODIFIER les fichiers partagés

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
