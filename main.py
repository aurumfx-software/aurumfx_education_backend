import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from database import engine
import database_models

from fastapi.staticfiles import StaticFiles

from routers import (
    auth,
    courses,
    enquiries,
    settings,
    enrollments,
    announcements,
    profile,
    branches,
    branch_announcements,
    payments,
)


app = FastAPI()


# ==========================================
# CORS
# ==========================================

allowed_origins_env = os.getenv("ALLOWED_ORIGINS")

origins = (
    [origin.strip() for origin in allowed_origins_env.split(",")]
    if allowed_origins_env
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==========================================
# DATABASE TABLE CREATION
# ==========================================

database_models.Base.metadata.create_all(
    bind=engine
)


# ==========================================
# DATABASE MIGRATIONS
# ==========================================

try:
    with engine.connect() as conn:

        # --------------------------------------
        # USERS
        # --------------------------------------

        conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS phone VARCHAR;"
            )
        )

        # --------------------------------------
        # ENQUIRIES
        # --------------------------------------

        conn.execute(
            text(
                "ALTER TABLE enquiries "
                "ADD COLUMN IF NOT EXISTS parents_phone VARCHAR;"
            )
        )

        # --------------------------------------
        # ENROLLMENTS
        # --------------------------------------

        conn.execute(
            text(
                "ALTER TABLE enrollments "
                "ADD COLUMN IF NOT EXISTS razorpay_order_id VARCHAR;"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE enrollments "
                "ADD COLUMN IF NOT EXISTS razorpay_payment_id VARCHAR;"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE enrollments "
                "ADD COLUMN IF NOT EXISTS created_at "
                "TIMESTAMP WITH TIME ZONE DEFAULT NOW();"
            )
        )

        conn.commit()

except Exception as e:
    print(f"Migration note: {e}")


# ==========================================
# UPLOADS DIRECTORY
# ==========================================

os.makedirs(
    "uploads",
    exist_ok=True
)


# ==========================================
# STATIC FILES
# ==========================================

app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)


# ==========================================
# ROUTERS
# ==========================================

app.include_router(auth.router)

app.include_router(courses.router)

app.include_router(enquiries.router)

app.include_router(settings.router)

app.include_router(enrollments.router)

app.include_router(announcements.router)

app.include_router(profile.router)

# Super Admin branch routes
app.include_router(branches.router)

# Public branch routes
app.include_router(branches.public_router)

app.include_router(branch_announcements.router)

app.include_router(payments.router)


# ==========================================
# ROOT
# ==========================================

@app.get("/")
def greet():
    return {
        "status": "success",
        "message": "AurumFX server is running"
    }