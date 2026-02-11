"""API key storage and validation."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets



def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def load_api_keys(keys_file: str, env_keys: str = "") -> dict:
    keys = {}

    if env_keys:
        for k in env_keys.split(","):
            k = k.strip()
            if k:
                keys[hash_api_key(k)] = "(env)"

    if os.path.exists(keys_file):
        with open(keys_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if ":" in line:
                        name, key_or_hash = line.split(":", 1)
                        key_or_hash = key_or_hash.strip()
                        if len(key_or_hash) == 64 and all(c in "0123456789abcdef" for c in key_or_hash):
                            keys[key_or_hash] = name.strip()
                        else:
                            keys[hash_api_key(key_or_hash)] = name.strip()
                    else:
                        if len(line) == 64 and all(c in "0123456789abcdef" for c in line):
                            keys[line] = "(unnamed)"
                        else:
                            keys[hash_api_key(line)] = "(unnamed)"

    return keys


def validate_api_key(provided_key: str, valid_keys: dict) -> bool:
    if not valid_keys:
        return True
    provided_hash = hash_api_key(provided_key)
    for stored_hash in valid_keys:
        if hmac.compare_digest(provided_hash, stored_hash):
            return True
    return False


def generate_api_key(keys_file: str, name: str = "") -> str:
    key = f"sk-btp-{secrets.token_hex(24)}"
    key_hash = hash_api_key(key)
    os.makedirs(os.path.dirname(keys_file) or ".", exist_ok=True)
    with open(keys_file, "a") as f:
        f.write(f"{name}:{key_hash}\n" if name else f"{key_hash}\n")
    os.chmod(keys_file, 0o600)
    return key


def list_api_keys(keys_file: str) -> list:
    if not os.path.exists(keys_file):
        return []
    result = []
    with open(keys_file) as f:
        idx = 0
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            idx += 1
            if ":" in line:
                name, _ = line.split(":", 1)
                result.append({"id": idx, "name": name.strip() or "(unnamed)"})
            else:
                result.append({"id": idx, "name": "(unnamed)"})
    return result
