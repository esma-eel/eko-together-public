"""Script to generate development RS256 private and public key pairs."""

from __future__ import annotations

from pathlib import Path

from shared.jwt.tokens import generate_rsa_key_pair


def main() -> None:
    keys_dir = Path("keys")
    private_key_path = keys_dir / "private_key.pem"
    public_key_path = keys_dir / "public_key.pem"

    print(f"Generating RSA 2048-bit key pair in {keys_dir.resolve()}...")
    generate_rsa_key_pair(private_key_path, public_key_path)
    print(f"✅ Generated private key: {private_key_path}")
    print(f"✅ Generated public key:  {public_key_path}")


if __name__ == "__main__":
    main()
