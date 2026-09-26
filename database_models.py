from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime,Date
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import ForeignKey,UniqueConstraint


# ==========================================
# USER
# ==========================================

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

    # ==========================================
    # BRANCH ADMIN ID
    # ==========================================

    branch_admin_id = Column(
        String,
        unique=True,
        nullable=True
    )

    # ==========================================
    # BRANCH
    # ==========================================

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=True
    )

    # ==========================================
    # USER PROFILE
    # ==========================================

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

    # ==========================================
    # ROLE
    # ==========================================

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


# ==========================================
# BRANCH
# ==========================================

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


# ==========================================
# COURSE
# ==========================================
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

    duration = Column(
        String,
        nullable=False
    )

    # --------------------------------------------------------
    # COURSE PERIOD
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # INSTALLMENT DETAILS
    # --------------------------------------------------------

    installment_schedule = Column(
        String,
        nullable=True
    )

    installment_count = Column(
        Integer,
        nullable=True
    )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    is_active = Column(
        Boolean,
        default=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
# ==========================================
# ENQUIRY
# ==========================================

class Enquiry(Base):
    __tablename__ = "enquiries"

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
        nullable=False
    )

    phone = Column(
        String,
        nullable=True
    )

    parents_phone = Column(
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

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# ==========================================
# SYSTEM SETTINGS
# ==========================================

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


# ==========================================
# ANNOUNCEMENT
# ==========================================

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

    image = Column(
        String,
        nullable=True
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# ==========================================
# ENROLLMENT
# ==========================================

class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    # ==========================================
    # USER
    # ==========================================

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    # ==========================================
    # COURSE
    # ==========================================

    course_id = Column(
        Integer,
        ForeignKey("courses.id"),
        nullable=False
    )

    # Course title snapshot
    course_title = Column(
        String,
        nullable=True
    )

    # ==========================================
    # BRANCH
    # ==========================================

    branch_id = Column(
        Integer,
        ForeignKey("branches.id"),
        nullable=False
    )

    # ==========================================
    # STUDENT DETAILS
    # ==========================================

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

    # ==========================================
    # COURSE FEE
    # ==========================================

    total_fee = Column(
        Float,
        nullable=False
    )

    # ==========================================
    # PAYMENT STATUS
    # pending / paid
    # ==========================================

    status = Column(
        String,
        default="pending",
        nullable=False
    )

    # ==========================================
    # COURSE STATUS
    # pending / approved
    # ==========================================

    course_status = Column(
        String,
        default="pending",
        nullable=False
    )

    # ==========================================
    # RAZORPAY
    # ==========================================

    razorpay_order_id = Column(
        String,
        nullable=True
    )

    razorpay_payment_id = Column(
        String,
        nullable=True
    )

    # ==========================================
    # PAYMENT DATE
    # ==========================================

    paid_at = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # ==========================================
    # CREATED DATE
    # ==========================================

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )







# ==========================================
# STAFF
# ==========================================
class Staff(Base):
    __tablename__ = "staff"

    id = Column(Integer, primary_key=True, index=True)

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

    course_id = Column(
        Integer,
        ForeignKey("courses.id"),
        nullable=False
    )

    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)

    address = Column(String, nullable=True)
    salary = Column(Float, nullable=False)


    status = Column(
        String,
        default="Active",
        nullable=False
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )



# ==========================================
# STAFF ATTENDANCE
# ==========================================
class StaffAttendance(Base):
    __tablename__ = "staff_attendance"

    id = Column(Integer, primary_key=True, index=True)

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




# ==========================================
# BRANCH ADMIN ATTENDANCE
# ==========================================


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






# ==========================================
# MESSAGE CONVERSATION
# ==========================================

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


# ==========================================
# MESSAGE
# ==========================================

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