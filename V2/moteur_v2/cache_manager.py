# moteur_v2/cache_manager.py — Gestion des caches V2
# Prefetch, cache mémoire, cache DB, synchronisation avec Graph API
# Indépendant du proto (pas de COM)

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
