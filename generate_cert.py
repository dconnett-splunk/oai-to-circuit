#!/usr/bin/env python3
"""
Generate self-signed certificates for HTTPS support.
"""

import os
import datetime
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization


def generate_self_signed_cert(hostname="localhost", cert_file="cert.pem", key_file="key.pem"):
    """Generate a self-signed certificate for development."""
    
    # Generate private key
    print("Generating private key...")
    key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    
    # Various subject data
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "California"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "San Francisco"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Circuit Bridge Dev"),
        x509.NameAttribute(NameOID.COMMON_NAME, hostname),
    ])
    
    # Generate certificate
    print("Generating certificate...")
    cert = x509.CertificateBuilder().subject_name(
        subject
    ).issuer_name(
        issuer
    ).public_key(
        key.public_key()
    ).serial_number(
        x509.random_serial_number()
    ).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        # Certificate valid for 1 year
        datetime.datetime.utcnow() + datetime.timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName([
            x509.DNSName(hostname),
            x509.DNSName("localhost"),
            x509.DNSName("127.0.0.1"),
            x509.DNSName("::1"),
        ]),
        critical=False,
    ).sign(key, hashes.SHA256())
    
    # Write private key
    print(f"Writing private key to {key_file}...")
    with open(key_file, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))
    
    # Write certificate
    print(f"Writing certificate to {cert_file}...")
    with open(cert_file, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    
    print("\n✅ Certificate generated successfully!")
    print(f"   Certificate: {cert_file}")
    print(f"   Private key: {key_file}")
    print("\n⚠️  This is a self-signed certificate for development only.")
    print("   Browsers will show a security warning - this is normal.")
    print("\nTo use with the server:")
    print("   python rewriter.py --ssl")
    print("\nTo trust the certificate (optional):")
    print("   - macOS: sudo security add-trusted-cert -d -r trustRoot -k /Library/Keychains/System.keychain cert.pem")
    print("   - Linux: Copy cert.pem to /usr/local/share/ca-certificates/ and run sudo update-ca-certificates")
    print("   - Windows: Import cert.pem using certmgr.msc")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Generate self-signed certificate")
    parser.add_argument("--hostname", default="localhost", help="Hostname for certificate")
    parser.add_argument("--cert", default="cert.pem", help="Certificate output file")
    parser.add_argument("--key", default="key.pem", help="Private key output file")
    
    args = parser.parse_args()
    
    # Check if certificate already exists
    if os.path.exists(args.cert) or os.path.exists(args.key):
        response = input(f"Certificate files already exist. Overwrite? (y/N): ")
        if response.lower() != 'y':
            print("Aborted.")
            exit(0)
    
    generate_self_signed_cert(args.hostname, args.cert, args.key)
