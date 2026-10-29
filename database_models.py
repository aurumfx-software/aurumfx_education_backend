from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Boolean,
    DateTime,
    Date,
    Text,
    ForeignKey,
    UniqueConstraint
)

from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

from database import Base


# ============================================================
# USER
# ============================================================

class User(Base):
    __tablename__ = "users"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String,
        nullable=False
    )

    email = Column(
        String,
        unique=True,
        index=True,
        nullable=False
    )

    password_hash = Column(
        String,
        nullable=False
    )

    phone = Column(
        String,
        nullable=True
    )

    # ========================================================
    # BRANCH ADMIN ID
    # ========================================================

    branch_admin_id = Column(
        String,
        unique=True,
        nullable=True
    )

    allowed_ip_address = Column(
        String,
        nullable=True
    )

    # ========================================================
    # BRANCH
    # ========================================================

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=True
    )

    # ========================================================
    # USER PROFILE
    # ========================================================

    parent_name = Column(
        String,
        nullable=True
    )

    parent_phone = Column(
        String,
        nullable=True
    )

    highest_qualification = Column(
        String,
        nullable=True
    )

    address = Column(
        String,
        nullable=True
    )

    profile_image = Column(
        String,
        nullable=True
    )

    # ========================================================
    # ROLE
    # ========================================================

    role = Column(
        String,
        default="user",
        nullable=False
    )

    status = Column(
        String,
        default="Active",
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# ============================================================
# PASSWORD RESET OTP
# ============================================================

class PasswordResetOTP(Base):
    __tablename__ = "password_reset_otps"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, index=True)
    otp_hash = Column(String, nullable=False)
    reset_token_hash = Column(String, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    used_at = Column(DateTime(timezone=True), nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )


# ============================================================
# BRANCH
# ============================================================

class Branch(Base):
    __tablename__ = "branches"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    name = Column(
        String,
        nullable=False
    )

    location = Column(
        String,
        nullable=False
    )

    phone = Column(
        String,
        nullable=True
    )

    email = Column(
        String,
        nullable=True
    )

    status = Column(
        String,
        default="Active",
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class BranchExpense(Base):
    __tablename__ = "branch_expenses"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(
        Integer,
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    item = Column(String(255), nullable=False)
    cost = Column(Float, nullable=False)
    expense_date = Column(Date, nullable=False, index=True)
    created_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# ============================================================
# COURSE
# ============================================================

class Course(Base):
    __tablename__ = "courses"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=False
    )

    title = Column(
        String,
        nullable=False
    )

    description = Column(
        String,
        nullable=False
    )

    price = Column(
        Float,
        nullable=False
    )

    base_price = Column(
        Float,
        nullable=False,
        default=0,
    )

    cgst_percent = Column(
        Float,
        nullable=False,
        default=0,
    )

    sgst_percent = Column(
        Float,
        nullable=False,
        default=0,
    )

    cgst_amount = Column(
        Float,
        nullable=False,
        default=0,
    )

    sgst_amount = Column(
        Float,
        nullable=False,
        default=0,
    )

    duration = Column(
        String,
        nullable=False
    )

    # ========================================================
    # COURSE PERIOD
    # ========================================================

    start_date = Column(
        Date,
        nullable=True
    )

    end_date = Column(
        Date,
        nullable=True
    )

    image = Column(
        String,
        nullable=True
    )

    category = Column(
        String,
        nullable=True
    )

    level = Column(
        String,
        nullable=True
    )

    curriculum = Column(
        JSONB,
        nullable=True
    )

    # ========================================================
    # INSTALLMENT DETAILS
    # ========================================================

    installment_schedule = Column(
        String,
        nullable=True
    )

    installment_count = Column(
        Integer,
        nullable=True
    )

    installment_terms = Column(
        JSONB,
        nullable=True
    )

    # ========================================================
    # STATUS
    # ========================================================

    is_active = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    @property
    def total_gst_percent(self):
        return round(self.cgst_percent + self.sgst_percent, 2)

    @property
    def total_gst_amount(self):
        return round(self.cgst_amount + self.sgst_amount, 2)

    @property
    def total_amount(self):
        return self.price


# ============================================================
# COURSE REVIEW
# ============================================================

class CourseReview(Base):
    __tablename__ = "course_reviews"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "course_id",
            name="uq_course_review_user_course",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    branch_id = Column(
        Integer,
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    review = Column(Text, nullable=False)
    rating = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


# ============================================================
# ENQUIRY
# ============================================================

class Enquiry(Base):
    __tablename__ = "enquiries"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=True,
        index=True
    )

    name = Column(
        String,
        nullable=False
    )

    email = Column(
        String,
        nullable=False
    )

    phone = Column(
        String,
        nullable=True
    )

    course = Column(
        String,
        nullable=True
    )

    qualification = Column(
        String,
        nullable=True
    )

    message = Column(
        String,
        nullable=True
    )

    status = Column(
        String,
        default="New",
        nullable=False
    )

    branch_admin_status = Column(
        String,
        default="pending",
        nullable=False
    )

    contact_status = Column(
        String,
        default="not_contacted",
        nullable=False
    )

    branch_admin_read_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# ============================================================
# SYSTEM SETTINGS
# ============================================================

class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    address = Column(
        String,
        nullable=True
    )

    phone = Column(
        String,
        nullable=True
    )

    alt_phone = Column(
        String,
        nullable=True
    )

    email = Column(
        String,
        nullable=True
    )

    admissions_email = Column(
        String,
        nullable=True
    )

    working_hours = Column(
        String,
        nullable=True
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


class GSTSettings(Base):
    __tablename__ = "gst_settings"

    id = Column(Integer, primary_key=True)
    cgst_percent = Column(Float, nullable=False, default=0)
    sgst_percent = Column(Float, nullable=False, default=0)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# ============================================================
# BRANCH ADMIN SIDEBAR NAVIGATION
# ============================================================

class BranchSidebarNavigation(Base):
    __tablename__ = "branch_sidebar_navigation"

    id = Column(Integer, primary_key=True, index=True)
    branch_id = Column(
        Integer,
        ForeignKey("branches.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    nav_links = Column(JSONB, nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


# ============================================================
# ANNOUNCEMENT
# ============================================================

class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=True
    )

    title = Column(
        String,
        nullable=False
    )

    message = Column(
        String,
        nullable=False
    )

    audience = Column(
        String,
        nullable=False,
        default="both",
        server_default="both",
    )

    image = Column(
        String,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

# ============================================================
# ENROLLMENT
# ============================================================

class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    # ========================================================
    # USER
    # ========================================================

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    # ========================================================
    # COURSE
    # ========================================================

    course_id = Column(
        Integer,
        ForeignKey("courses.id"),
        nullable=False
    )

    course_title = Column(
        String,
        nullable=True
    )

    # ========================================================
    # BRANCH
    # ========================================================

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=False
    )

    # ========================================================
    # CREATED BY BRANCH ADMIN
    # ========================================================

    created_by_branch_admin_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    # ========================================================
    # STUDENT DETAILS
    # ========================================================

    name = Column(
        String,
        nullable=True
    )

    email = Column(
        String,
        nullable=True
    )

    phone = Column(
        String,
        nullable=True
    )

    parent_name = Column(
        String,
        nullable=True
    )

    parent_phone = Column(
        String,
        nullable=True
    )

    highest_qualification = Column(
        String,
        nullable=True
    )

    address = Column(
        String,
        nullable=True
    )

    # ========================================================
    # COURSE FEE
    # ========================================================

    total_fee = Column(
        Float,
        nullable=False
    )

    # ========================================================
    # ADMISSION
    # ========================================================

    admission_date = Column(
        Date,
        nullable=True
    )

    # ========================================================
    # INSTALLMENT DETAILS
    # ========================================================

    installment_schedule = Column(
        String,
        nullable=True
    )

    installment_count = Column(
        Integer,
        nullable=True
    )

    installment_amount = Column(
        Float,
        nullable=True
    )

    # ========================================================
    # PAYMENT SUMMARY
    # ========================================================

    total_paid = Column(
        Float,
        default=0,
        nullable=False
    )

    balance_amount = Column(
        Float,
        default=0,
        nullable=False
    )

    # ========================================================
    # PAYMENT STATUS
    # pending / paid
    # ========================================================

    status = Column(
        String,
        default="pending",
        nullable=False
    )

    # ========================================================
    # COURSE STATUS
    # pending / approved
    # ========================================================

    course_status = Column(
        String,
        default="pending",
        nullable=False
    )

    branch_approval_status = Column(
        String,
        default="pending",
        nullable=False
    )

    super_admin_approval_status = Column(
        String,
        default="pending",
        nullable=False
    )

    super_admin_rejection_reason = Column(
        String,
        nullable=True
    )

    super_admin_rejected_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # ========================================================
    # RAZORPAY
    # ========================================================

    razorpay_order_id = Column(
        String,
        nullable=True
    )

    razorpay_payment_id = Column(
        String,
        nullable=True
    )

    # ========================================================
    # PAYMENT DATE
    # ========================================================

    paid_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # ========================================================
    # CREATED DATE
    # ========================================================

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

# ============================================================
# ENROLLMENT INSTALLMENT
# ============================================================

class EnrollmentInstallment(Base):
    __tablename__ = "enrollment_installments"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    # ========================================================
    # ENROLLMENT
    # ========================================================

    enrollment_id = Column(
        Integer,
        ForeignKey(
            "enrollments.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    # ========================================================
    # INSTALLMENT NUMBER
    # ========================================================

    installment_number = Column(
        Integer,
        nullable=False
    )

    # ========================================================
    # INSTALLMENT AMOUNT
    # ========================================================

    amount = Column(
        Float,
        nullable=False
    )

    # ========================================================
    # PAID AMOUNT
    # ========================================================

    paid_amount = Column(
        Float,
        default=0,
        nullable=False
    )

    # ========================================================
    # DUE DATE
    # ========================================================

    due_date = Column(
        Date,
        nullable=False
    )

    # ========================================================
    # STATUS
    # pending / partial / paid
    # ========================================================

    status = Column(
        String,
        default="pending",
        nullable=False
    )

    # ========================================================
    # PAID DATE
    # ========================================================

    paid_date = Column(
        Date,
        nullable=True
    )

    # ========================================================
    # PAYMENT SPLIT
    # ========================================================

    cash_amount = Column(
        Float,
        default=0,
        nullable=False
    )

    upi_amount = Column(
        Float,
        default=0,
        nullable=False
    )

    # ========================================================
    # CREATED
    # ========================================================

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# ============================================================
# ADMISSION PAYMENT
# ============================================================

class AdmissionPayment(Base):
    __tablename__ = "admission_payments"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    # ========================================================
    # ENROLLMENT
    # ========================================================

    enrollment_id = Column(
        Integer,
        ForeignKey(
            "enrollments.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    # ========================================================
    # INSTALLMENT
    # ========================================================

    installment_id = Column(
        Integer,
        ForeignKey(
            "enrollment_installments.id",
            ondelete="SET NULL"
        ),
        nullable=True
    )

    installment_number = Column(
        Integer,
        nullable=False
    )

    # ========================================================
    # STUDENT
    # ========================================================

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    # ========================================================
    # BRANCH
    # ========================================================

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=False
    )

    # ========================================================
    # PAYMENT
    # ========================================================

    amount = Column(
        Float,
        nullable=False
    )

    cash_amount = Column(
        Float,
        default=0,
        nullable=False
    )

    upi_amount = Column(
        Float,
        default=0,
        nullable=False
    )

    payment_method = Column(
        String,
        default="unknown",
        nullable=False
    )

    # ========================================================
    # PAYMENT DATE
    # ========================================================

    payment_date = Column(
        Date,
        nullable=False
    )

    # ========================================================
    # STATUS
    # ========================================================

    status = Column(
        String,
        default="received",
        nullable=False
    )

    credited_to_balance = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    reviewed_by_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    reviewed_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    rejection_reason = Column(
        Text,
        nullable=True
    )

    payment_reference = Column(
        String,
        nullable=True
    )

    upi_transaction_id = Column(
        String,
        nullable=True,
    )

    # ========================================================
    # CREATED
    # ========================================================

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# ============================================================
# RAZORPAY PAYMENT ORDER
# ============================================================

class RazorpayPaymentOrder(Base):
    __tablename__ = "razorpay_payment_orders"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    enrollment_id = Column(
        Integer,
        ForeignKey("enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    installment_id = Column(
        Integer,
        ForeignKey("enrollment_installments.id", ondelete="SET NULL"),
        nullable=True
    )

    razorpay_order_id = Column(
        String,
        nullable=False,
        unique=True,
        index=True
    )

    amount = Column(
        Float,
        nullable=False
    )

    status = Column(
        String,
        default="created",
        nullable=False
    )

    razorpay_payment_id = Column(
        String,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# ============================================================
# STAFF
# ============================================================

class Staff(Base):
    __tablename__ = "staff"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        unique=True
    )

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=False
    )

    staff_code = Column(
        String,
        nullable=True,
        unique=True,
        index=True
    )

    course_id = Column(
        Integer,
        ForeignKey("courses.id"),
        nullable=False
    )

    name = Column(
        String,
        nullable=False
    )

    email = Column(
        String,
        nullable=False
    )

    phone = Column(
        String,
        nullable=True
    )

    address = Column(
        String,
        nullable=True
    )

    salary = Column(
        Float,
        nullable=False
    )

    verification_status = Column(
        String,
        default="pending",
        nullable=False
    )

    aadhaar_number = Column(
        String,
        nullable=True
    )

    pan_number = Column(
        String,
        nullable=True
    )

    bank_account_number = Column(
        String,
        nullable=True
    )

    bank_ifsc = Column(
        String,
        nullable=True
    )

    aadhaar_front_key = Column(
        String,
        nullable=True
    )

    aadhaar_back_key = Column(
        String,
        nullable=True
    )

    pan_card_key = Column(
        String,
        nullable=True
    )

    bank_passbook_key = Column(
        String,
        nullable=True
    )

    other_document_key = Column(
        String,
        nullable=True
    )

    other_document_name = Column(
        String,
        nullable=True
    )

    verification_submitted_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    verification_approved_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    verification_approved_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    verification_rejection_reason = Column(
        String,
        nullable=True
    )

    verification_rejected_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    verification_rejected_by_user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=True
    )

    status = Column(
        String,
        default="Active",
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# ============================================================
# STAFF COURSE ASSIGNMENTS
# ============================================================

class StaffCourse(Base):
    __tablename__ = "staff_courses"
    __table_args__ = (
        UniqueConstraint(
            "staff_id",
            "course_id",
            name="uq_staff_course_assignment",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    staff_id = Column(
        Integer,
        ForeignKey("staff.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )


# ============================================================
# COURSE ANNOUNCEMENTS
# ============================================================

class CourseAnnouncement(Base):
    __tablename__ = "course_announcements"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    staff_id = Column(
        Integer,
        ForeignKey("staff.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    event_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CourseStudyMaterial(Base):
    __tablename__ = "course_study_materials"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    staff_id = Column(
        Integer,
        ForeignKey("staff.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    file_key = Column(String, nullable=False, unique=True)
    filename = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================
# COURSE TASKS AND STUDENT ASSIGNMENTS
# ============================================================

class CourseTask(Base):
    __tablename__ = "course_tasks"

    id = Column(Integer, primary_key=True, index=True)
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    staff_id = Column(
        Integer,
        ForeignKey("staff.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    due_date = Column(Date, nullable=True)
    max_marks = Column(Float, nullable=False, default=100)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class StudentTaskAssignment(Base):
    __tablename__ = "student_task_assignments"
    __table_args__ = (
        UniqueConstraint(
            "task_id",
            "student_id",
            name="uq_student_task_assignment",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(
        Integer,
        ForeignKey("course_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    student_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    submission_key = Column(String, nullable=True)
    submission_filename = Column(String, nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    marks_obtained = Column(Float, nullable=True)
    feedback = Column(Text, nullable=True)
    marked_at = Column(DateTime(timezone=True), nullable=True)


# ============================================================
# STAFF ATTENDANCE
# ============================================================

class StaffAttendance(Base):
    __tablename__ = "staff_attendance"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    staff_id = Column(
        Integer,
        ForeignKey("staff.id"),
        nullable=False
    )

    staff_name = Column(
        String,
        nullable=False
    )

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=False
    )

    date = Column(
        Date,
        nullable=False
    )

    status = Column(
        String,
        nullable=False
    )

    marked_by = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    marked_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "staff_id",
            "date",
            name="unique_staff_attendance_per_day"
        ),
    )


# ============================================================
# BRANCH ADMIN ATTENDANCE
# ============================================================

class BranchAdminAttendance(Base):
    __tablename__ = "branch_admin_attendance"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    branch_admin_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=False
    )

    date = Column(
        Date,
        nullable=False
    )

    status = Column(
        String,
        nullable=False
    )

    marked_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "branch_admin_id",
            "date",
            name="unique_branch_admin_attendance_per_day"
        ),
    )


# ============================================================
# MESSAGE CONVERSATION
# ============================================================

class MessageConversation(Base):
    __tablename__ = "message_conversations"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    branch_admin_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False,
        unique=True
    )

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )


# ============================================================
# MESSAGE
# ============================================================

class Message(Base):
    __tablename__ = "messages"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    conversation_id = Column(
        Integer,
        ForeignKey(
            "message_conversations.id",
            ondelete="CASCADE"
        ),
        nullable=False
    )

    sender_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    sender_role = Column(
        String,
        nullable=False
    )

    message = Column(
        String,
        nullable=False
    )

    is_read = Column(
        Boolean,
        default=False,
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class StaffSuperAdminConversation(Base):
    __tablename__ = "staff_super_admin_conversations"

    id = Column(Integer, primary_key=True, index=True)
    staff_id = Column(
        Integer,
        ForeignKey("staff.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=False,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class StaffSuperAdminMessage(Base):
    __tablename__ = "staff_super_admin_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("staff_super_admin_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_role = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class StudentStaffConversation(Base):
    __tablename__ = "student_staff_conversations"
    __table_args__ = (
        UniqueConstraint(
            "student_id",
            "staff_id",
            "course_id",
            name="uq_student_staff_course_conversation",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    staff_id = Column(
        Integer,
        ForeignKey("staff.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    course_id = Column(
        Integer,
        ForeignKey("courses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class StudentStaffMessage(Base):
    __tablename__ = "student_staff_messages"

    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(
        Integer,
        ForeignKey("student_staff_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    sender_role = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())