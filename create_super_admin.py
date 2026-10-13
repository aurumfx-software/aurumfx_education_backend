from getpass import getpass

import database_models
from database import Base, SessionLocal, engine
from database_models import User
from utils.password import hash_password

# Match the app's startup behavior: create any missing model tables.
Base.metadata.create_all(bind=engine)

email = "admin@gmail.com"
password = getpass("Enter the initial password: ")
if not password:
    raise ValueError("Password cannot be empty.")

with SessionLocal() as db:
    if db.query(User).filter(User.email == email).first():
        raise SystemExit(f"A user with {email} already exists; no changes made.")

    db.add(User(
        name="Admin",
        email=email,
        password_hash=hash_password(password),
        role="super_admin",
        status="Active",
    ))
    db.commit()

print(f"Created super-admin account for {email}.")