
import sys

from api.db.database import SessionLocal, init_db
from api.db.models import ServiceKey
from api.services.api_keys import api_key_prefix, generate_api_key, hash_api_key


def main():
    if len(sys.argv) != 3:
        print("Usage: python -m scripts.create_service_key <organization_id> <name>")
        raise SystemExit(1)

    organization_id = int(sys.argv[1])
    name = sys.argv[2]

    init_db()

    raw_key = generate_api_key()

    with SessionLocal() as db:
        service_key = ServiceKey(
            organization_id=organization_id,
            name=name,
            key_hash=hash_api_key(raw_key),
            key_prefix=api_key_prefix(raw_key),
        )
        db.add(service_key)
        db.commit()

    print("Service key created. Copy it now; it will not be shown again.")
    print(raw_key)


if __name__ == "__main__":
    main()

