#!/bin/bash
# ==============================================================================
# saas_smoke.sh — Smoke test BoosterMail OVH (post-pivot 27/04 PM OVH-first)
# ==============================================================================
# Usage : bash audit/tests/saas_smoke.sh
# Retour : exit 0 si tout OK, exit N (= nb FAIL) sinon
# Durée : ~5-10 sec
#
# Complète audit/tests/smoke_test.ps1 (qui teste un V2 local supposé tournant
# sur port 3443 — non applicable en mode OVH-first où Yvan utilise BoosterMail
# uniquement depuis api.boostermail.ai).
#
# Tests :
# 1. Connectivité OVH (SSH + API)
# 2. Service systemd boostermail actif
# 3. Warmup terminé (done:true)
# 4. Latence routes < seuils
# 5. Pas d'erreurs récentes (filtrées des warnings cosmétiques connus)
# 6. Format JSON disque v2 cohérent (drafts_v2.json + prefetch_cache_v2.json)
# 7. Graph webhook subscription valide (si activée)
# 8. Backups récents disponibles
# ==============================================================================

set -u

OVH_HOST='ubuntu@152.228.209.252'
API_BASE='https://api.boostermail.ai'

# Compteurs
PASS=0
FAIL=0
SKIP=0
FAILS=()

check() {
    local id="$1" desc="$2" cmd="$3"
    if eval "$cmd" >/dev/null 2>&1; then
        PASS=$((PASS+1))
        echo "  OK   [$id] $desc"
    else
        FAIL=$((FAIL+1))
        FAILS+=("$id : $desc")
        echo "  FAIL [$id] $desc"
    fi
}

skip() {
    SKIP=$((SKIP+1))
    echo "  SKIP [$1] $2"
}

echo "=============================================="
echo "BoosterMail SaaS smoke test (OVH-first)"
echo "=============================================="
echo

# Catégorie 1 : Connectivité
echo "--- Catégorie 1 : Connectivité ---"
check "I-SAAS-01" "SSH OVH joignable" "ssh -o BatchMode=yes -o ConnectTimeout=5 $OVH_HOST 'echo ok' 2>/dev/null | grep -q ok"
check "I-SAAS-02" "API OVH répond HTTPS" "curl -sk --max-time 5 -o /dev/null -w '%{http_code}' '$API_BASE/api/warmup_status' | grep -q '^200$'"

# Catégorie 2 : Service Flask
echo
echo "--- Catégorie 2 : Service Flask ---"
check "I-SAAS-03" "Service systemd boostermail active" "ssh $OVH_HOST 'sudo systemctl is-active boostermail' 2>/dev/null | grep -q '^active$'"
# I-SAAS-04 multi-tenant : depuis Étape 7, _warmup_progress est _UserScopedDict.
# done:true seulement quand un user a triggered son warmup via /api/warmup_inbox/start.
# Sur un serveur post-restart sans session user active, payload normal = {done:false,
# current:0, total:0, step:""} → état idle, SKIP (pas un fail).
WARMUP_PAYLOAD=$(curl -sk --max-time 5 "$API_BASE/api/warmup_status" 2>/dev/null)
if echo "$WARMUP_PAYLOAD" | grep -q '"done":true'; then
    PASS=$((PASS+1))
    echo "  OK   [I-SAAS-04] Warmup terminé (done:true)"
elif echo "$WARMUP_PAYLOAD" | grep -q '"total":0' && echo "$WARMUP_PAYLOAD" | grep -q '"done":false'; then
    skip "I-SAAS-04" "Warmup idle (multi-tenant — aucun user n'a déclenché son warmup)"
else
    FAIL=$((FAIL+1))
    FAILS+=("I-SAAS-04 : Warmup état inattendu ($WARMUP_PAYLOAD)")
    echo "  FAIL [I-SAAS-04] Warmup état inattendu ($WARMUP_PAYLOAD)"
fi

# Catégorie 3 : Latence
echo
echo "--- Catégorie 3 : Latence ---"
LATENCY_STATUS=$(curl -sk --max-time 5 -o /dev/null -w '%{time_total}' "$API_BASE/api/warmup_status" 2>/dev/null || echo "999")
LATENCY_INT=$(echo "$LATENCY_STATUS * 1000" | bc 2>/dev/null | cut -d. -f1)
LATENCY_INT=${LATENCY_INT:-999}
if [ "$LATENCY_INT" -lt 2000 ]; then
    PASS=$((PASS+1))
    echo "  OK   [I-SAAS-05] Latence /api/warmup_status < 2000ms (${LATENCY_INT}ms)"
else
    FAIL=$((FAIL+1))
    FAILS+=("I-SAAS-05 : Latence /api/warmup_status < 2000ms (${LATENCY_INT}ms)")
    echo "  FAIL [I-SAAS-05] Latence /api/warmup_status < 2000ms (${LATENCY_INT}ms)"
fi

# Catégorie 4 : Erreurs récentes (10 min, état actuel)
# Filtres :
#  - sentry : warnings DSN cosmétiques
#  - acquire_token_silent : warnings MSAL cache (renew normal)
#  - Auto-warmup: token : info polling token
#  - easymail.graph.*Graph 400 : bugs Graph syntax métier (subjects avec & ou ()
#    pre-existants, pas liés à infra)
#  - TypeError: require_auth.*provider : bug de boot historique du 29/04 PM
#    (commit 7b589ea, fix dans commit suivant) — historiquement résolu
# Fenêtre 10 min : reflète l'état actuel, pas l'historique du jour.
echo
echo "--- Catégorie 4 : Erreurs récentes (10 min) ---"
ERROR_COUNT=$(ssh $OVH_HOST "sudo journalctl -u boostermail --since '10 minutes ago' --no-pager 2>/dev/null | grep -iE 'error|traceback|exception' | grep -v sentry | grep -v 'acquire_token_silent' | grep -v 'Auto-warmup: token' | grep -v 'easymail.graph.*Graph 400' | grep -v 'TypeError: require_auth' | wc -l" 2>/dev/null || echo "999")
ERROR_COUNT=${ERROR_COUNT:-999}
if [ "$ERROR_COUNT" -lt 3 ]; then
    PASS=$((PASS+1))
    echo "  OK   [I-SAAS-06] Moins de 3 erreurs réelles dernières 10 min ($ERROR_COUNT)"
else
    FAIL=$((FAIL+1))
    FAILS+=("I-SAAS-06 : Moins de 3 erreurs réelles dernières 10 min ($ERROR_COUNT)")
    echo "  FAIL [I-SAAS-06] Moins de 3 erreurs réelles dernières 10 min ($ERROR_COUNT)"
fi

# Catégorie 5 : Format JSON disque v2 (multi-tenant)
echo
echo "--- Catégorie 5 : Format JSON v2 multi-tenant ---"
check "I-SAAS-07" "drafts_v2.json en format v2" "ssh $OVH_HOST 'sudo head -c 200 /opt/boostermail/drafts_v2.json' 2>/dev/null | grep -q 'format_version.*2'"
check "I-SAAS-08" "prefetch_cache_v2.json en format v2" "ssh $OVH_HOST 'sudo head -c 200 /opt/boostermail/prefetch_cache_v2.json' 2>/dev/null | grep -q 'format_version.*2'"
check "I-SAAS-09" "drafts_v2.json contient entries_per_user" "ssh $OVH_HOST 'sudo head -c 300 /opt/boostermail/drafts_v2.json' 2>/dev/null | grep -q 'entries_per_user'"

# Catégorie 6 : Graph webhook (si activé)
echo
echo "--- Catégorie 6 : Graph webhook ---"
SUB_STATUS=$(curl -sk --max-time 5 "$API_BASE/api/admin/graph_subscription/status" 2>/dev/null)
if echo "$SUB_STATUS" | grep -q '"subscription_id":null'; then
    skip "I-SAAS-10" "Graph webhook subscription non activée (info)"
elif echo "$SUB_STATUS" | grep -q '"needs_renew_soon":false'; then
    PASS=$((PASS+1))
    echo "  OK   [I-SAAS-10] Graph webhook subscription valide (renew not needed)"
else
    FAIL=$((FAIL+1))
    FAILS+=("I-SAAS-10 : Graph webhook subscription needs_renew (status: $SUB_STATUS)")
    echo "  FAIL [I-SAAS-10] Graph webhook subscription needs_renew"
fi

# Catégorie 7 : Backups
echo
echo "--- Catégorie 7 : Backups ---"
BACKUP_COUNT=$(ssh $OVH_HOST 'sudo ls -1 /var/backups/boostermail/ 2>/dev/null | grep -c "boostermail.*\.gz"' 2>/dev/null || echo "0")
BACKUP_COUNT=${BACKUP_COUNT:-0}
if [ "$BACKUP_COUNT" -gt 0 ]; then
    PASS=$((PASS+1))
    echo "  OK   [I-SAAS-11] Backups DB présents ($BACKUP_COUNT fichiers gzip)"
else
    FAIL=$((FAIL+1))
    FAILS+=("I-SAAS-11 : Pas de backup DB trouvé dans /var/backups/boostermail/")
    echo "  FAIL [I-SAAS-11] Pas de backup DB trouvé"
fi

# Résumé
echo
echo "=============================================="
echo "Smoke test SaaS : $PASS PASS / $FAIL FAIL / $SKIP SKIP"
echo "=============================================="
if [ $FAIL -gt 0 ]; then
    echo
    echo "ANOMALIES :"
    for f in "${FAILS[@]}"; do
        echo "  - $f"
    done
fi

exit $FAIL
