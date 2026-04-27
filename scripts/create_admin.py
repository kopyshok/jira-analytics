"""Create first admin user. Run once after fresh deployment.

Usage:
    py -3.10 scripts/create_admin.py
    py -3.10 scripts/create_admin.py --email admin@company.com --password secret
"""
import argparse
import sys
import uuid

sys.path.insert(0, ".")

from app.config import get_settings
from app.core.security import hash_password
from app.database import SessionLocal
from app.models.user import User, UserRole


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default=settings.admin_email or "admin@example.com")
    parser.add_argument("--password", default=settings.admin_password or "changeme")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        if db.query(User).filter(User.email == args.email).first():
            print(f"User {args.email} already exists. Skipping.")
            return
        user = User(
            id=str(uuid.uuid4()),
            email=args.email,
            password_hash=hash_password(args.password),
            display_name="Admin",
            role=UserRole.admin,
            is_active=True,
        )
        db.add(user)
        db.commit()
        print(f"Admin created: {args.email}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
