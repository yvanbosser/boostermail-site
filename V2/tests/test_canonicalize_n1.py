"""Tests unitaires Niveau 1 — Canonicalisation des message_id.

Tests standalone (sans Flask). Vérifie :
- _is_canonical_imid_strict accepte/rejette correctement
- _synthesize_imid est stable (idempotent)
- _canonicalize_message_id traite tous les formats
- _extract_imid_from_mail_data extrait correctement depuis un dict
- Outlook ID base64 std et URL-safe produisent le MÊME IMID synthétique
"""
import sys
import os
import hashlib
import threading

# Inject minimal mocks pour permettre l'import sans Flask
_canonicalize_cache = {}
_canonicalize_lock = threading.Lock()
_CANONICALIZE_CACHE_MAX = 1000


class _MockLogger:
    def debug(self, *a, **k):
        pass


logger = _MockLogger()


# === Copie des fonctions à tester ===

def _is_canonical_imid_strict(mid):
    if not isinstance(mid, str) or len(mid) < 5:
        return False
    if not (mid.startswith('<') and mid.endswith('>')):
        return False
    inner = mid[1:-1]
    if '@' not in inner:
        return False
    local, _, domain = inner.partition('@')
    if not local or not domain or '.' not in domain:
        return False
    return True


def _synthesize_imid(outlook_id_urlsafe):
    h = hashlib.sha256(outlook_id_urlsafe.encode('utf-8', errors='replace')).hexdigest()[:24]
    return f"<synthetic:{h}@boostermail.local>"


def _cache_canonicalization(raw, imid):
    if not raw or not imid:
        return
    with _canonicalize_lock:
        if len(_canonicalize_cache) >= _CANONICALIZE_CACHE_MAX:
            for k in list(_canonicalize_cache.keys())[:100]:
                _canonicalize_cache.pop(k, None)
        _canonicalize_cache[raw] = imid


def _canonicalize_message_id(raw, db=None, allow_synthetic=True):
    if not isinstance(raw, str):
        return ''
    raw = raw.strip()
    if not raw:
        return ''
    if _is_canonical_imid_strict(raw):
        return raw
    with _canonicalize_lock:
        cached = _canonicalize_cache.get(raw)
        if cached is not None:
            return cached
    outlook_urlsafe = raw.replace('/', '-').replace('+', '_')
    if db is not None:
        try:
            for lookup_key in (raw, outlook_urlsafe):
                cached_email = db.get_cached_email(lookup_key)
                if cached_email:
                    imid = cached_email.get('internet_message_id', '')
                    if _is_canonical_imid_strict(imid):
                        _cache_canonicalization(raw, imid)
                        return imid
        except Exception as e:
            logger.debug(f"err: {e}")
    if allow_synthetic:
        synthetic = _synthesize_imid(outlook_urlsafe)
        _cache_canonicalization(raw, synthetic)
        return synthetic
    return ''


def _extract_imid_from_mail_data(mail_data):
    if not isinstance(mail_data, dict):
        return ''
    imid = (mail_data.get('internet_message_id') or '').strip()
    if _is_canonical_imid_strict(imid):
        return imid
    mid = (mail_data.get('message_id') or '').strip()
    if _is_canonical_imid_strict(mid):
        return mid
    oid = (mail_data.get('id') or '').strip()
    if oid:
        return _canonicalize_message_id(oid, allow_synthetic=True)
    if mid:
        return _canonicalize_message_id(mid, allow_synthetic=True)
    if imid:
        return _canonicalize_message_id(imid, allow_synthetic=True)
    return ''


# === Mock DB pour tester le lookup email_cache ===

class _MockDB:
    def __init__(self, data=None):
        # data: dict {entry_id: email_json_dict}
        self.data = data or {}

    def get_cached_email(self, entry_id):
        return self.data.get(entry_id)


# === Tests ===

def assert_eq(actual, expected, msg=""):
    if actual != expected:
        print(f"  [FAIL] {msg}: attendu '{expected}', obtenu '{actual}'")
        return False
    print(f"  [OK]   {msg}")
    return True


def run_tests():
    print("=== _is_canonical_imid_strict ===")
    cases_canon = [
        ("<a@b.c>", True, "IMID minimal OK"),
        ("<CALK3gjAu5KkupL5Pig@mail.gmail.com>", True, "IMID gmail réel"),
        ("<2113957095.545385.1@opme11.intraorange>", True, "IMID intraorange"),
        ("<@>", False, "vide rejeté"),
        ("<@a.b>", False, "local vide rejeté"),
        ("<a@>", False, "domain vide rejeté"),
        ("<a@b>", False, "domain sans tld rejeté"),
        ("<sans-arobase>", False, "pas de @ rejeté"),
        ("pas-de-chevrons@mail.com", False, "pas de < > rejeté"),
        ("", False, "vide rejeté"),
        (None, False, "None rejeté"),
        ("<a@b.c", False, "manque > rejeté"),
        ("a@b.c>", False, "manque < rejeté"),
        (42, False, "int rejeté"),
    ]
    ok_count = 0
    total = 0
    for inp, exp, msg in cases_canon:
        total += 1
        if assert_eq(_is_canonical_imid_strict(inp), exp, msg):
            ok_count += 1

    print()
    print("=== _synthesize_imid stable ===")
    h1 = _synthesize_imid("AAMkADNkMDI5-something-CtiP-1Ye4EQJ5rA")
    h2 = _synthesize_imid("AAMkADNkMDI5-something-CtiP-1Ye4EQJ5rA")
    total += 1
    if assert_eq(h1, h2, "même input → même IMID synthétique"):
        ok_count += 1
    total += 1
    if assert_eq(_is_canonical_imid_strict(h1), True, "IMID synthétique passe le strict check"):
        ok_count += 1

    print()
    print("=== _canonicalize_message_id ===")
    # IMID natif passe inchangé
    total += 1
    if assert_eq(_canonicalize_message_id("<CALK3gj@mail.gmail.com>"),
                 "<CALK3gj@mail.gmail.com>", "IMID natif inchangé"):
        ok_count += 1
    # Vide → ''
    total += 1
    if assert_eq(_canonicalize_message_id(""), "", "vide → ''"):
        ok_count += 1
    # None → ''
    total += 1
    if assert_eq(_canonicalize_message_id(None), "", "None → ''"):
        ok_count += 1
    # Outlook ID standard + URL-safe → MÊME synthétique
    _canonicalize_cache.clear()
    oid_std = "AAMkADNk/CtiP/1Ye4EQJ5rA/gblsaW"
    oid_safe = "AAMkADNk-CtiP-1Ye4EQJ5rA-gblsaW"
    canon_std = _canonicalize_message_id(oid_std)
    canon_safe = _canonicalize_message_id(oid_safe)
    total += 1
    if assert_eq(canon_std, canon_safe, "std et URL-safe → MÊME IMID synthétique"):
        ok_count += 1
    # allow_synthetic=False sans DB → ''
    _canonicalize_cache.clear()
    total += 1
    if assert_eq(_canonicalize_message_id("AAMkAD-xxx", allow_synthetic=False),
                 "", "allow_synthetic=False sans DB → ''"):
        ok_count += 1
    # Avec DB qui retourne l'IMID natif
    _canonicalize_cache.clear()
    db = _MockDB({"AAMkAD-xxx": {"internet_message_id": "<real@mail.com>"}})
    total += 1
    if assert_eq(_canonicalize_message_id("AAMkAD-xxx", db=db),
                 "<real@mail.com>", "DB lookup résout vers IMID natif"):
        ok_count += 1
    # DB lookup sur version URL-safe alors qu'on passe le std
    _canonicalize_cache.clear()
    db = _MockDB({"AAMkAD-xxx-yyy": {"internet_message_id": "<real2@mail.com>"}})
    total += 1
    if assert_eq(_canonicalize_message_id("AAMkAD/xxx/yyy", db=db),
                 "<real2@mail.com>", "Lookup std-raw échoue, lookup URL-safe réussit"):
        ok_count += 1

    print()
    print("=== _extract_imid_from_mail_data ===")
    # mail_data avec internet_message_id canonique
    total += 1
    if assert_eq(_extract_imid_from_mail_data({"internet_message_id": "<a@b.c>"}),
                 "<a@b.c>", "internet_message_id canonique"):
        ok_count += 1
    # mail_data dict vide
    total += 1
    if assert_eq(_extract_imid_from_mail_data({}), "", "dict vide → ''"):
        ok_count += 1
    # mail_data avec internet_message_id vide MAIS id Outlook → synthétique
    _canonicalize_cache.clear()
    res = _extract_imid_from_mail_data({"internet_message_id": "", "id": "AAMkAD-xxx"})
    total += 1
    if assert_eq(res.startswith("<synthetic:") and res.endswith("@boostermail.local>"), True,
                 "id Outlook sans IMID → synthétique"):
        ok_count += 1
    # mail_data non-dict
    total += 1
    if assert_eq(_extract_imid_from_mail_data(None), "", "non-dict → ''"):
        ok_count += 1
    if assert_eq(_extract_imid_from_mail_data("string"), "", "str → ''"):
        ok_count += 1
        total += 1

    print()
    print(f"=== RÉSULTAT : {ok_count}/{total} tests OK ===")
    return ok_count == total


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
