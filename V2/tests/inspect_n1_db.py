"""Inspection lecture seule de la DB pour préparer la migration Niveau 1.

Vérifie la faisabilité de la canonicalisation des entry_id non-canoniques
dans email_cache (peut-on retrouver l'IMID natif via email_json ?).
"""
import sqlite3
import json
import sys

DB = sys.argv[1] if len(sys.argv) > 1 else "/opt/boostermail/V2/boostermail.db"

c = sqlite3.connect(DB)
c.row_factory = sqlite3.Row

print("=== EMAIL_CACHE non-canoniques ===")
rows = list(c.execute(
    "SELECT entry_id, internet_message_id, email_json FROM email_cache "
    "WHERE entry_id IS NOT NULL AND entry_id != '' "
    "AND NOT (entry_id LIKE '<%@%>')"
))
print("Total non-canon:", len(rows))

resolvable_move = 0
resolvable_dup = 0
not_resolvable = 0
samples = []
non_resolv_samples = []

for r in rows:
    imid_col = (r["internet_message_id"] or "").strip()
    imid_json = ""
    try:
        d = json.loads(r["email_json"])
        imid_json = (d.get("internet_message_id", "") or "").strip()
    except Exception:
        d = {}

    good_imid = ""
    for cand in (imid_col, imid_json):
        if cand and cand.startswith("<") and "@" in cand and cand.endswith(">"):
            good_imid = cand
            break

    if good_imid:
        existing = c.execute(
            "SELECT 1 FROM email_cache WHERE entry_id = ?", (good_imid,)
        ).fetchone()
        if existing:
            resolvable_dup += 1
            if len(samples) < 3:
                samples.append((r["entry_id"][:60], good_imid[:60], "DUP"))
        else:
            resolvable_move += 1
            if len(samples) < 3:
                samples.append((r["entry_id"][:60], good_imid[:60], "MOVE"))
    else:
        not_resolvable += 1
        if len(non_resolv_samples) < 3:
            non_resolv_samples.append((r["entry_id"][:80], r["email_json"][:200]))

print()
print(f"Résolvables MOVE (IMID absent → migration simple)        : {resolvable_move}")
print(f"Résolvables DUP  (IMID déjà présent → delete non-canon)  : {resolvable_dup}")
print(f"Non résolvables (pas d'IMID dans la ligne)              : {not_resolvable}")
print()
if samples:
    print("Samples résolvables:")
    for s in samples:
        print(f"  {s[0]} ... -> {s[1]} [{s[2]}]")
print()
if non_resolv_samples:
    print("Samples non résolvables (email_json preview):")
    for s in non_resolv_samples:
        print(f"  entry_id={s[0]}")
        print(f"  json={s[1]}")

# Vérification metrics.email_id non-canoniques : ressemblent-ils à quoi ?
print()
print("=== METRICS.email_id non-canoniques (sample) ===")
rows = list(c.execute(
    "SELECT email_id, action FROM metrics WHERE email_id IS NOT NULL AND email_id != '' "
    "AND NOT (email_id LIKE '<%@%>') LIMIT 5"
))
for r in rows:
    print(f"  email_id={r['email_id'][:60]} action={r['action']}")

# folder_classifications.entry_id : confirme format MAPI hex
print()
print("=== FOLDER_CLASSIFICATIONS.entry_id (sample) ===")
rows = list(c.execute("SELECT entry_id FROM folder_classifications LIMIT 3"))
for r in rows:
    print(f"  entry_id={r['entry_id'][:70]}")

# contact_profiles.entry_ids stats
print()
print("=== CONTACT_PROFILES.entry_ids ===")
rows = list(c.execute(
    "SELECT email, entry_ids FROM contact_profiles "
    "WHERE entry_ids IS NOT NULL AND entry_ids != '[]' AND entry_ids != ''"
))
total_ids = 0
canon_ids = 0
for r in rows:
    try:
        ids = json.loads(r["entry_ids"])
        if isinstance(ids, list):
            total_ids += len(ids)
            for i in ids:
                if isinstance(i, str) and i.startswith("<") and "@" in i and i.endswith(">"):
                    canon_ids += 1
    except Exception:
        pass
print(f"Total entry_ids dans contact_profiles : {total_ids}")
print(f"Dont canoniques (IMID)               : {canon_ids}")
print(f"Dont non-canoniques (hex MAPI legacy) : {total_ids - canon_ids}")

c.close()
print()
print("=== FIN INSPECTION ===")
