import secrets
import string


SAFE_SUBKEY_CHARS = string.ascii_letters + string.digits + "-_"


def normalize_subkey_prefix(prefix: str) -> str:
    cleaned = "".join(char for char in prefix.strip() if char in SAFE_SUBKEY_CHARS)
    if cleaned and not cleaned.endswith("_"):
        cleaned = f"{cleaned}_"
    return cleaned


def is_valid_subkey(value: str) -> bool:
    return bool(value) and all(char in SAFE_SUBKEY_CHARS for char in value)


def generate_subkey(prefix: str = "", length: int = 32) -> str:
    normalized_prefix = normalize_subkey_prefix(prefix)
    random_part = "".join(secrets.choice(SAFE_SUBKEY_CHARS) for _ in range(max(8, length)))
    return f"{normalized_prefix}{random_part}"
