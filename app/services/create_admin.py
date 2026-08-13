from app.db.database import SessionLocal
from app.models.user import User
from app.services.auth_service import hash_password


def create_admin():
    db = SessionLocal()

    try:
        existing_user = (
            db.query(User)
            .filter(User.username == "admin")
            .first()
        )

        if existing_user:
            print("Admin user already exists.")
            return

        admin = User(
            username="admin",
            password_hash=hash_password("Admin@123"),
            role="admin",
            is_active=True,
        )

        db.add(admin)
        db.commit()

        print("Admin user created successfully.")

    finally:
        db.close()


if __name__ == "__main__":
    create_admin()