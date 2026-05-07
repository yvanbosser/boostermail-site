#!/usr/bin/env bash
# cloture_check.sh — Vérification mécanique des invariants I-SESS-* en fin de session
#
# Usage : bash audit/tests/cloture_check.sh
# Exit  : 0 si tous les invariants OK, 1+ si anomalies détectées
#
# Invariants testés (cf audit/INVARIANTS.md catégorie 13) :
#   I-SESS-01 : git status --short retourne vide
#   I-SESS-02 : aucune ref obsolète dans docs vivants (PLUS_TARD.md sans VF, etc.)
#   I-SESS-03 : top commit hash dans PROMPT_REPRISE coherent avec git log
#   I-SESS-04 : chiffres "N commits" dans docs vivants dédupliqués → ≤ 1 valeur
#
# Lié au Workflow 7 ("Kit fin de session") du audit/PLAYBOOK.md.

set -uo pipefail

# Aller à la racine du repo (depuis audit/tests/)
cd "$(dirname "$0")/../.." || exit 1

ANOMALIES=0
RAPPORT=""

print_section() {
    echo ""
    echo "==============================================="
    echo "  $1"
    echo "==============================================="
}

ko() {
    ANOMALIES=$((ANOMALIES + 1))
    RAPPORT="${RAPPORT}\n❌ $1"
    echo "❌ $1"
}

ok() {
    echo "✅ $1"
}

# --------------------------------------------------------------------------
# I-SESS-01 : git status --short retourne vide
# --------------------------------------------------------------------------
print_section "I-SESS-01 — git status --short doit être vide"

GIT_STATUS=$(git status --short 2>/dev/null)
if [ -z "$GIT_STATUS" ]; then
    ok "I-SESS-01 : aucune modif locale non commitée"
else
    ko "I-SESS-01 : modifs locales non commitées détectées"
    echo "$GIT_STATUS" | sed 's/^/    /'
fi

# --------------------------------------------------------------------------
# I-SESS-02 : aucune ref obsolète dans docs vivants
# --------------------------------------------------------------------------
print_section "I-SESS-02 — aucune référence obsolète dans docs vivants"

# Pattern 1 : refs vers `docs/PLUS_TARD.md` (sans _VF) hors archives bandeau
# On exclut :
#   - docs/PLUS_TARD.md lui-même (archive avec bandeau)
#   - docs/PLUS_TARD_VF.md (mention historique des sources consolidées, OK)
#   - docs/sessions/BILAN_SESSION_*.md (anciens bilans figés, OK)
#   - docs/sessions/OUTLOOK_BILAN_SESSION_*.md (bilan référence le doc archivé, OK)
#   - docs/saas/AUDIT_OUTLOOK_TO_SAAS_20260427.md (audit du matin figé, OK)
PLUS_TARD_OBSOLETE=$(grep -rn "docs/PLUS_TARD\.md" docs/ --include='*.md' 2>/dev/null \
    | grep -v "PLUS_TARD_VF" \
    | grep -v "docs/PLUS_TARD\.md:" \
    | grep -v "docs/PLUS_TARD_VF\.md:" \
    | grep -v "BILAN_SESSION_" \
    | grep -v "AUDIT_OUTLOOK_TO_SAAS_" \
    | grep -v "PLAN_1_APPLICATION_DOCUMENTATION" \
    || true)
if [ -z "$PLUS_TARD_OBSOLETE" ]; then
    ok "Pas de ref obsolète vers docs/PLUS_TARD.md (sans _VF) dans docs vivants"
else
    ko "Refs obsolètes vers docs/PLUS_TARD.md détectées :"
    echo "$PLUS_TARD_OBSOLETE" | sed 's/^/    /'
fi

# Pattern 2 : refs TODO_SESSION_SUIVANTE qualifiées "état courant"
TODO_ETAT_COURANT=$(grep -rn "TODO_SESSION_SUIVANTE.md.*état courant\|TODO_SESSION_SUIVANTE.md.*etat courant" docs/ --include='*.md' 2>/dev/null \
    | grep -v "BILAN_SESSION_" \
    || true)
if [ -z "$TODO_ETAT_COURANT" ]; then
    ok "Pas de ref TODO_SESSION_SUIVANTE qualifiée 'état courant'"
else
    ko "Refs TODO_SESSION_SUIVANTE qualifiées 'état courant' (devrait être archivée) :"
    echo "$TODO_ETAT_COURANT" | sed 's/^/    /'
fi

# --------------------------------------------------------------------------
# I-SESS-03 : top commit hash dans PROMPT_REPRISE cohérent
# --------------------------------------------------------------------------
print_section "I-SESS-03 — top commit hash dans PROMPT_REPRISE cohérent"

PROMPT_FILE="docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md"
if [ ! -f "$PROMPT_FILE" ]; then
    ko "I-SESS-03 : fichier $PROMPT_FILE introuvable"
else
    # Extraire les hashes courts (7-10 chars hex) mentionnés dans le prompt
    PROMPT_HASHES=$(grep -oE '\b[0-9a-f]{7,10}\b' "$PROMPT_FILE" 2>/dev/null | sort -u || true)
    if [ -z "$PROMPT_HASHES" ]; then
        # Pas de hash mentionné dans le prompt → OK (référence générique)
        ok "I-SESS-03 : aucun hash figé dans PROMPT_REPRISE (référence dynamique = OK)"
    else
        # Pour chaque hash mentionné, vérifier qu'il existe dans les 20 derniers commits
        LAST_HASHES=$(git log --oneline -n 20 2>/dev/null | awk '{print $1}')
        ALL_FOUND=1
        for H in $PROMPT_HASHES; do
            if ! echo "$LAST_HASHES" | grep -q "^$H"; then
                ko "I-SESS-03 : hash '$H' mentionné dans PROMPT_REPRISE absent des 20 derniers commits"
                ALL_FOUND=0
            fi
        done
        if [ $ALL_FOUND -eq 1 ]; then
            ok "I-SESS-03 : tous les hashes du PROMPT_REPRISE sont dans les 20 derniers commits"
        fi
    fi
fi

# --------------------------------------------------------------------------
# I-SESS-04 : chiffres "N commits" dans docs vivants dédupliqués
# --------------------------------------------------------------------------
print_section "I-SESS-04 — chiffres 'N commits' cohérents entre docs vivants"

# Cibler uniquement les docs vivants qui ont vocation à mentionner le chiffre du jour
DOCS_VIVANTS=(
    "docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md"
    "docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md"
    "docs/PLUS_TARD_VF.md"
    "docs/SOMMAIRE_DETAILLE.md"
    "docs/specs_proto/HISTORIQUE_DECISIONS.md"
)

# Extraire tous les "N commits master" / "N commits cumulés" mentionnés
CHIFFRES=""
for f in "${DOCS_VIVANTS[@]}"; do
    if [ -f "$f" ]; then
        # Match patterns courants : "30 commits master", "30 commits cumulés", "30 commits sur la"
        N=$(grep -oE '[0-9]+ commits (master|cumulés|cumulees|sur la|sur l)' "$f" 2>/dev/null | grep -oE '^[0-9]+' | sort -u || true)
        if [ -n "$N" ]; then
            CHIFFRES="${CHIFFRES}${N}\n"
        fi
    fi
done

CHIFFRES_UNIQUES=$(echo -e "$CHIFFRES" | grep -v '^$' | sort -u | wc -l)

if [ "$CHIFFRES_UNIQUES" -eq 0 ]; then
    ok "I-SESS-04 : aucun chiffre 'N commits' figé dans docs vivants (formulation relative privilégiée = OK)"
elif [ "$CHIFFRES_UNIQUES" -eq 1 ]; then
    UNIQUE=$(echo -e "$CHIFFRES" | grep -v '^$' | sort -u)
    ok "I-SESS-04 : tous les docs vivants mentionnent le même chiffre ($UNIQUE commits)"
else
    ko "I-SESS-04 : chiffres 'N commits' incohérents entre docs vivants :"
    echo -e "$CHIFFRES" | grep -v '^$' | sort -u | sed 's/^/    valeur trouvée : /'
    echo "    → harmoniser tous les docs à la même valeur OU passer en formulation relative ('~30 commits' ou hash 'XXXXXXX+')"
fi

# --------------------------------------------------------------------------
# I-SESS-05 : aucun chemin OneDrive\Desktop\EasyMail dans docs vivants
# --------------------------------------------------------------------------
print_section "I-SESS-05 — aucun chemin OneDrive obsolète dans docs vivants"

DOCS_VIVANTS_RACINE=(
    "docs/outlook/PROMPT_REPRISE_NEW_OUTLOOK.md"
    "docs/outlook/ONBOARDING_NEW_OUTLOOK_VIA_OVH.md"
    "docs/saas/ONBOARDING_SESSION_SAAS.md"
    "docs/PLUS_TARD_VF.md"
    "docs/SOMMAIRE_DETAILLE.md"
)

ONEDRIVE_REFS=""
for f in "${DOCS_VIVANTS_RACINE[@]}"; do
    if [ -f "$f" ]; then
        # Match OneDrive[\/]Desktop[\/]EasyMail (toute slash, casse insensible)
        # Exclut les bandeaux d'avertissement qui mentionnent le chemin POUR
        # avertir (mots-clés "vestige", "JAMAIS l'utiliser", "I-SESS-05" =
        # le doc explique le piège, pas un chemin de travail actif)
        REFS=$(grep -inE 'OneDrive[\\/]+Desktop[\\/]+EasyMail' "$f" 2>/dev/null \
            | grep -viE 'vestige|JAMAIS l.utiliser|I-SESS-05|pré-migration|piège' \
            || true)
        if [ -n "$REFS" ]; then
            ONEDRIVE_REFS="${ONEDRIVE_REFS}${f}:\n${REFS}\n"
        fi
    fi
done

if [ -z "$ONEDRIVE_REFS" ]; then
    ok "I-SESS-05 : aucune ref OneDrive\\Desktop\\EasyMail dans les docs vivants"
else
    ko "I-SESS-05 : refs OneDrive obsolètes détectées dans docs vivants (racine projet = C:\\EasyMail\\ depuis 12/04) :"
    echo -e "$ONEDRIVE_REFS" | sed 's/^/    /'
fi

# --------------------------------------------------------------------------
# I-SESS-06 : pas de session sur la branche `dev` ou `master` (07/05/2026)
#
# Convention git absolue : Yvan travaille sur `feat/yvan/frontend`,
# Michael sur `feat/michael/multi-user`. Aucun commit/push direct sur
# `dev` ou `master`. Si la branche active est dev/master en fin de
# session, c'est un signal qu'on a oublié la convention.
# --------------------------------------------------------------------------
print_section "I-SESS-06 — branche active != dev/master (convention contributeur)"

CURRENT_BRANCH=$(git branch --show-current 2>/dev/null)
if [ -z "$CURRENT_BRANCH" ]; then
    ok "I-SESS-06 : detached HEAD (worktree temporaire OK)"
elif [ "$CURRENT_BRANCH" = "dev" ] || [ "$CURRENT_BRANCH" = "master" ] || [ "$CURRENT_BRANCH" = "main" ]; then
    ko "I-SESS-06 : branche active = '$CURRENT_BRANCH' — INTERDIT"
    echo "    → Yvan doit travailler sur 'feat/yvan/frontend'"
    echo "    → Michael doit travailler sur 'feat/michael/multi-user'"
    echo "    → Voir docs/CONVENTIONS_GIT_BRANCHES.md"
else
    ok "I-SESS-06 : branche active = '$CURRENT_BRANCH' (pas dev/master)"
fi


# --------------------------------------------------------------------------
# Synthèse finale
# --------------------------------------------------------------------------
print_section "SYNTHÈSE"

if [ $ANOMALIES -eq 0 ]; then
    echo ""
    echo "🎉 TOUS LES INVARIANTS I-SESS-* SONT OK"
    echo ""
    echo "Session prête à être déclarée close."
    echo "Workflow 7 du audit/PLAYBOOK.md peut continuer."
    exit 0
else
    echo ""
    echo "⚠️  $ANOMALIES anomalie(s) détectée(s)"
    echo ""
    echo "Récap des anomalies :"
    echo -e "$RAPPORT"
    echo ""
    echo "→ Fix les anomalies puis relancer le script jusqu'à exit 0."
    echo "→ Ne PAS déclarer la session close avant exit 0."
    exit 1
fi
