from getpass import getpass

from database import SessionLocal
from database_models import User
from utils.password import hash_password

 

def create_admin():

    db = SessionLocal()

    try:

        email = input("Admin email: ")
        password = getpass("Admin password: ")

        # Check whether email already exists
        existing_user = db.query(User).filter(
            User.email == email
        ).first()

        if existing_user:
            print("A user with this email already exists.")
            return

        # Create admin
        admin = User(
            name="Admin",
            email=email,
            password_hash=hash_password(password),
            role="admin",
            is_active=True
        )

        db.add(admin)
        db.commit()

        print("Admin created successfully!")

    finally:
        db.close()


create_admin()


