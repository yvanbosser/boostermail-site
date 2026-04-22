"""
Génère un certificat auto-signé pour localhost (développement plugin Outlook).
Usage: python generate_cert.py
Crée localhost.crt et localhost.key dans le même dossier.
"""
import datetime
import ipaddress as ipaddress_module
import os
import sys

try:
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
except ImportError:
    print("Installation de 'cryptography'...")
    os.system(f'"{sys.executable}" -m pip install cryptography')
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

dir_path = os.path.dirname(os.path.abspath(__file__))
key_path = os.path.join(dir_path, "localhost.key")
cert_path = os.path.join(dir_path, "localhost.crt")

# Clé privée RSA 2048 bits
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

# Certificat auto-signé valide 365 jours
subject = issuer = x509.Name([
    x509.NameAttribute(NameOID.COMMON_NAME, "localhost"),
    x509.NameAttribute(NameOID.ORGANIZATION_NAME, "EasyMail Dev"),
])

cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
    .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=365))
    .add_extension(
        # Fix 22/04 : SAN couvrant localhost + IPv4 + IPv6. Sans ::1 dans
        # la SAN, WebView2 qui résout "localhost" en IPv6 d'abord peut
        # rejeter le cert comme "CN mismatch" → addin jamais chargé.
        x509.SubjectAlternativeName([
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress_module.ip_address("127.0.0.1")),
            x509.IPAddress(ipaddress_module.ip_address("::1")),
        ]),
        critical=False,
    )
    .sign(key, hashes.SHA256())
)

# Écriture fichiers
with open(key_path, "wb") as f:
    f.write(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))

with open(cert_path, "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))

print(f"[OK] Certificat créé :")
print(f"  - {cert_path}")
print(f"  - {key_path}")
print(f"  Valide jusqu'au {cert.not_valid_after_utc.strftime('%d/%m/%Y')}")
