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
    super_admin_staff_verification,
    super_admin_courses,
    super_admin_gst,
    branch_admin_gst,
    branch_dashboard,
    super_admin_dashboard,
    branch_profit,
    super_admin_branch_profit,
    branch_expenses,
    super_admin_expenses,
    branch_receipts,
    super_admin_receipts,
    super_admin_attendance,
    staff_attendance,
    branch_admin_attendance,
    messages,
    admissions,
    student_assignments,
    course_announcements,
    sidebar_navigation,
    student_staff_messages,
    staff_super_admin_messages,
    staff_monitoring,
    student_study_materials,
    student_management,
)

app = FastAPI()
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


database_models.Base.metadata.create_all(
    bind=engine
)


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
                "ALTER TABLE admission_payments "
                "ADD COLUMN IF NOT EXISTS reviewed_by_user_id INTEGER "
                "REFERENCES users(id) ON DELETE SET NULL;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE admission_payments "
                "ADD COLUMN IF NOT EXISTS reviewed_at "
                "TIMESTAMP WITH TIME ZONE;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE admission_payments "
                "ADD COLUMN IF NOT EXISTS rejection_reason TEXT;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE admission_payments "
                "ADD COLUMN IF NOT EXISTS payment_reference VARCHAR;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE admission_payments "
                "ADD COLUMN IF NOT EXISTS upi_transaction_id VARCHAR;"
            )
        )
        conn.execute(
            text(
                "ALTER TABLE admission_payments "
                "ADD COLUMN IF NOT EXISTS credited_to_balance BOOLEAN "
                "NOT NULL DEFAULT FALSE;"
            )
        )
        conn.execute(
            text(
                "UPDATE admission_payments "
                "SET credited_to_balance = TRUE "
                "WHERE status = 'received';"
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

        for column_definition in (
            "base_price FLOAT NOT NULL DEFAULT 0",
            "cgst_percent FLOAT NOT NULL DEFAULT 0",
            "sgst_percent FLOAT NOT NULL DEFAULT 0",
            "cgst_amount FLOAT NOT NULL DEFAULT 0",
            "sgst_amount FLOAT NOT NULL DEFAULT 0",
        ):
            conn.execute(
                text(
                    "ALTER TABLE courses "
                    f"ADD COLUMN IF NOT EXISTS {column_definition};"
                )
            )

        conn.execute(
            text(
                "UPDATE courses SET base_price = price "
                "WHERE base_price = 0 AND price > 0;"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE announcements "
                "ADD COLUMN IF NOT EXISTS audience VARCHAR "
                "NOT NULL DEFAULT 'both';"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE staff "
                "ADD COLUMN IF NOT EXISTS staff_code VARCHAR;"
            )
        )

        conn.execute(
            text(
                "ALTER TABLE course_tasks "
                "ADD COLUMN IF NOT EXISTS max_marks FLOAT "
                "NOT NULL DEFAULT 100;"
            )
        )

        for column_definition in (
            "submission_key VARCHAR",
            "submission_filename VARCHAR",
            "submitted_at TIMESTAMP WITH TIME ZONE",
            "marks_obtained FLOAT",
            "feedback TEXT",
            "marked_at TIMESTAMP WITH TIME ZONE",
        ):
            conn.execute(
                text(
                    "ALTER TABLE student_task_assignments "
                    f"ADD COLUMN IF NOT EXISTS {column_definition};"
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
            "verification_approved_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
            "verification_rejection_reason TEXT",
            "verification_rejected_at TIMESTAMP WITH TIME ZONE",
            "verification_rejected_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL",
        ):
            conn.execute(
                text(
                    "ALTER TABLE staff "
                    f"ADD COLUMN IF NOT EXISTS {column_definition};"
                )
            )

        conn.execute(
            text(
                """
                DO $$
                DECLARE
                    staff_record RECORD;
                    candidate_code VARCHAR;
                    attempts INTEGER;
                BEGIN
                    FOR staff_record IN
                        SELECT id FROM staff WHERE staff_code IS NULL
                    LOOP
                        attempts := 0;
                        LOOP
                            candidate_code :=
                                'STF' || (100 + floor(random() * 900)::INTEGER)::TEXT;
                            EXIT WHEN NOT EXISTS (
                                SELECT 1 FROM staff
                                WHERE staff_code = candidate_code
                            );
                            attempts := attempts + 1;
                            IF attempts >= 900 THEN
                                RAISE EXCEPTION
                                    'No unused three-digit staff codes are available';
                            END IF;
                        END LOOP;
                        UPDATE staff
                        SET staff_code = candidate_code
                        WHERE id = staff_record.id;
                    END LOOP;
                END $$;
                """
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



os.makedirs(
    "uploads",
    exist_ok=True
)


app.mount(
    "/uploads",
    StaticFiles(directory="uploads"),
    name="uploads"
)

app.include_router(auth.router)
app.include_router(student_management.router)
app.include_router(courses.router)
app.include_router(super_admin_courses.router)
app.include_router(super_admin_gst.router)
app.include_router(branch_admin_gst.router)
app.include_router(enquiries.router)
app.include_router(super_admin_enquiries.router)
app.include_router(super_admin_records.router)
app.include_router(settings.router)
app.include_router(enrollments.router)
app.include_router(super_admin_enrollments.router)
app.include_router(announcements.router)
app.include_router(super_admin_branch_announcements.router)
app.include_router(profile.router)
app.include_router(branches.router)
app.include_router(branches.public_router)
app.include_router(branch_announcements.router)
app.include_router(payments.router)
app.include_router(staff.router)
app.include_router(staff_portal.router)
app.include_router(student_study_materials.router)
app.include_router(student_assignments.router)
app.include_router(course_announcements.router)
app.include_router(sidebar_navigation.router)
app.include_router(branch_admin_staff_verification.router)
app.include_router(super_admin_staff.router)
app.include_router(super_admin_staff_verification.router)
app.include_router(branch_dashboard.router)
app.include_router(super_admin_dashboard.router)
app.include_router(branch_profit.router)
app.include_router(super_admin_branch_profit.router)
app.include_router(branch_expenses.router)
app.include_router(super_admin_expenses.router)
app.include_router(branch_receipts.router)
app.include_router(super_admin_receipts.router)
app.include_router(super_admin_attendance.router)
app.include_router(staff_attendance.router)
app.include_router(branch_admin_attendance.router)
app.include_router(messages.router)
app.include_router(student_staff_messages.router)
app.include_router(staff_super_admin_messages.router)
app.include_router(staff_monitoring.router)
app.include_router(admissions.router)


@app.get("/")
def greet():
    return {
        "status": "success",
        "message": "AurumFX server is running"
    }