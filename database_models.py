from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.sql import func
from database import Base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy import ForeignKey

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    role = Column(String, default="user", nullable=False)
    is_active = Column(Boolean, default=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )

  

class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    duration = Column(String, nullable=False)
    image = Column(String, nullable=True)
    category = Column(String, nullable=True)
    level = Column(String, nullable=True)
    curriculum=Column(JSONB,nullable=True)
    is_active = Column(Boolean, default=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class Enquiry(Base):
    __tablename__ = "enquiries"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    parents_phone = Column(String, nullable=True)
    course = Column(String, nullable=True)
    qualification = Column(String, nullable=True)
    message = Column(String, nullable=True)
    status = Column(String, default="New", nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )


class SystemSettings(Base):
    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    address = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    alt_phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    admissions_email = Column(String, nullable=True)
    working_hours = Column(String, nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )



class Enrollment(Base):
    __tablename__ = "enrollments"

    id = Column(Integer, primary_key=True, index=True)

    user_id = Column(
        Integer,
        ForeignKey("users.id"),
        nullable=False
    )

    course_id = Column(
        Integer,
        ForeignKey("courses.id"),
        nullable=False
    )

    full_name = Column(
        String,
        nullable=False
    )

    email = Column(
        String,
        nullable=False
    )

    phone = Column(
        String,
        nullable=False
    )

    parent_name = Column(
        String,
        nullable=False
    )

    parent_phone = Column(
        String,
        nullable=False
    )

    highest_qualification = Column(
        String,
        nullable=False
    )

    address = Column(
        String,
        nullable=False
    )

    payment_plan = Column(
        String,
        nullable=False
    )

    total_fee = Column(
        Float,
        nullable=False
    )

    status = Column(
        String,
        default="pending",
        nullable=False
    )

    enrolled_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )




class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String, nullable=False)

    message = Column(String, nullable=False)
    image = Column(String, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now()
    )
