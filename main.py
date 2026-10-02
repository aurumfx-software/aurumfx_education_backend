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
    super_admin_enquiries,
    super_admin_records,
    settings,
    enrollments,
    super_admin_enrollments,
    announcements,
    super_admin_branch_announcements,
    profile,
    branches,
    branch_announcements,
    payments,
    staff,
    staff_portal,
    branch_admin_staff_verification,
    super_admin_staff,
    super_admin_courses,
    branch_dashboard,
    super_admin_dashboard,
    branch_profit,
    super_admin_branch_profit,
    super_admin_attendance,
    staff_attendance,
    branch_admin_attendance,
    messages,
    admissions
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

        conn.execute(
            text(
                "ALTER TABLE admission_payments "
                "ADD COLUMN IF NOT EXISTS payment_method VARCHAR "
                "NOT NULL DEFAULT 'unknown';"
            )
        )

        conn.execute(
            text(
                "UPDATE admission_payments "
                "SET payment_method = CASE "
                "WHEN cash_amount > 0 AND upi_amount > 0 THEN 'cash_upi' "
                "WHEN cash_amount > 0 THEN 'cash' "
                "ELSE 'unknown' END "
                "WHERE payment_method = 'unknown';"
            )
        )

        # --------------------------------------
        # USERS
        # --------------------------------------

        conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS phone VARCHAR;"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE users "
                "ADD COLUMN IF NOT EXISTS allowed_ip_address VARCHAR;"
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

        conn.execute(
            text(
                "ALTER TABLE enquiries "
                "ADD COLUMN IF NOT EXISTS branch_id INTEGER "
                "REFERENCES branches(id);"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE enquiries "
                "ADD COLUMN IF NOT EXISTS branch_admin_status "
                "VARCHAR NOT NULL DEFAULT 'pending';"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE enquiries "
                "ADD COLUMN IF NOT EXISTS branch_admin_read_at "
                "TIMESTAMP WITH TIME ZONE;"
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

        conn.execute(
            text(
                "ALTER TABLE enrollments "
                "ADD COLUMN IF NOT EXISTS branch_approval_status "
                "VARCHAR NOT NULL DEFAULT 'pending';"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE enrollments "
                "ADD COLUMN IF NOT EXISTS super_admin_approval_status "
                "VARCHAR NOT NULL DEFAULT 'pending';"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE enrollments "
                "ADD COLUMN IF NOT EXISTS super_admin_rejection_reason TEXT;"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE enrollments "
                "ADD COLUMN IF NOT EXISTS super_admin_rejected_at "
                "TIMESTAMP WITH TIME ZONE;"
            )
        )

        conn.execute(
            text(
                "UPDATE enrollments "
                "SET branch_approval_status = 'approved', "
                "super_admin_approval_status = 'approved' "
                "WHERE course_status = 'approved';"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE courses "
                "ADD COLUMN IF NOT EXISTS installment_terms JSONB;"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE staff "
                "ADD COLUMN IF NOT EXISTS staff_code VARCHAR;"
            )
        )

        for column_definition in (
            "verification_status VARCHAR NOT NULL DEFAULT 'pending'",
            "aadhaar_number VARCHAR",
            "pan_number VARCHAR",
            "bank_account_number VARCHAR",
            "bank_ifsc VARCHAR",
            "aadhaar_front_key VARCHAR",
            "aadhaar_back_key VARCHAR",
            "pan_card_key VARCHAR",
            "bank_passbook_key VARCHAR",
            "other_document_key VARCHAR",
            "other_document_name VARCHAR",
            "verification_submitted_at TIMESTAMP WITH TIME ZONE",
            "verification_approved_at TIMESTAMP WITH TIME ZONE",
            "verification_rejection_reason TEXT",
            "verification_rejected_at TIMESTAMP WITH TIME ZONE",
        ):
            conn.execute(
                text(
                    "ALTER TABLE staff "
                    f"ADD COLUMN IF NOT EXISTS {column_definition};"
                )
            )

        conn.execute(
            text(
                "UPDATE staff "
                "SET staff_code = 'STF-' || branch_id || '-' || "
                "upper(substr(md5(random()::text || id::text), 1, 10)) "
                "WHERE staff_code IS NULL;"
            )
        )

        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_staff_staff_code "
                "ON staff (staff_code);"
            )
        )

        conn.execute(
            text(
                "INSERT INTO staff_courses (staff_id, course_id) "
                "SELECT id, course_id FROM staff "
                "ON CONFLICT (staff_id, course_id) DO NOTHING;"
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

app.include_router(super_admin_courses.router)

app.include_router(enquiries.router)

app.include_router(super_admin_enquiries.router)

app.include_router(super_admin_records.router)

app.include_router(settings.router)

app.include_router(enrollments.router)

app.include_router(super_admin_enrollments.router)

app.include_router(announcements.router)

app.include_router(super_admin_branch_announcements.router)

app.include_router(profile.router)

# Super Admin branch routes
app.include_router(branches.router)

# Public branch routes
app.include_router(branches.public_router)

app.include_router(branch_announcements.router)

app.include_router(payments.router)

# Branch admin staff routes
app.include_router(staff.router)

app.include_router(staff_portal.router)
app.include_router(branch_admin_staff_verification.router)

# Super admin staff routes
app.include_router(super_admin_staff.router)

# Branch admin dashboard routes
app.include_router(branch_dashboard.router)

app.include_router(super_admin_dashboard.router)

# Branch profit routes
app.include_router(branch_profit.router)

app.include_router(super_admin_branch_profit.router)

app.include_router(super_admin_attendance.router)

# Branch admin staff attendance routes
app.include_router(staff_attendance.router)

# ==========================================
# BRANCH ADMIN ATTENDANCE ROUTES
# ==========================================
app.include_router(branch_admin_attendance.router)

# ==========================================
# MESSAGES ROUTES
# ==========================================
app.include_router(messages.router)


# ==========================================
# ADMISSIONS ROUTES
# ==========================================
app.include_router(admissions.router)


# ==========================================
# ROOT
# ==========================================

@app.get("/")
def greet():
    return {
        "status": "success",
        "message": "AurumFX server is running"
    }