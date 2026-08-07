import base64
import json
from getpass import getpass


def decode_jwt(token: str):
    parts = token.strip().split(".")
    if len(parts) != 3:
        return None

    def decode_part(part: str):
        padded = part + "=" * (-len(part) % 4)
        return json.loads(base64.urlsafe_b64decode(padded))

    return {
        "header": decode_part(parts[0]),
        "claims": decode_part(parts[1]),
    }


for token_name in ("id_token", "access_token"):
    token = getpass(f"{token_name}: ")
    decoded = decode_jwt(token)

    if decoded is None:
        print(f"{token_name}: kein lesbares JWT, möglicherweise opaque oder verschlüsselt")
        continue

    print(f"\n{token_name} Header:")
    print(json.dumps(decoded["header"], indent=2))

    print(f"{token_name} Claim-Namen:")
    print(sorted(decoded["claims"].keys()))

    print(f"{token_name} Claims lokal:")
    print(json.dumps(decoded["claims"], indent=2, ensure_ascii=False))