# from datetime import date as date_type, datetime, time, timedelta

# from fastapi import APIRouter, Depends, HTTPException, Query
# from sqlalchemy.orm import Session

# from database import SessionLocal
# from database_models import (
#     User,
#     Branch,
#     Course,
#     Enrollment
# )

# from routers.auth import get_current_user


# router = APIRouter(
#     prefix="/branch-admin/profit",
#     tags=["Branch Admin Profit"]
# )


# # ============================================================
# # DATABASE DEPENDENCY
# # ============================================================

# def get_db():
#     db = SessionLocal()

#     try:
#         yield db
#     finally:
#         db.close()


# # ============================================================
# # CHECK BRANCH ADMIN
# # ============================================================

# def get_branch_admin(
#     current_user: User,
#     db: Session
# ):

#     if current_user.role != "branch_admin":
#         raise HTTPException(
#             status_code=403,
#             detail="Branch admin access required"
#         )

#     if not current_user.branch_id:
#         raise HTTPException(
#             status_code=400,
#             detail="Branch admin is not assigned to a branch"
#         )

#     branch = (
#         db.query(Branch)
#         .filter(
#             Branch.id == current_user.branch_id
#         )
#         .first()
#     )

#     if not branch:
#         raise HTTPException(
#             status_code=404,
#             detail="Branch not found"
#         )

#     return branch


# # ============================================================
# # ENROLLMENT RESPONSE
# # ============================================================

# def enrollment_to_dict(
#     enrollment: Enrollment,
#     course: Course
# ):

#     return {
#         # ----------------------------------------------------
#         # ENROLLMENT
#         # ----------------------------------------------------

#         "enrollment_id": enrollment.id,

#         "student_id": enrollment.user_id,

#         # ----------------------------------------------------
#         # STUDENT DETAILS
#         # ----------------------------------------------------

#         "name": enrollment.name,
#         "email": enrollment.email,
#         "phone": enrollment.phone,

#         "parent_name": enrollment.parent_name,
#         "parent_phone": enrollment.parent_phone,

#         "highest_qualification": (
#             enrollment.highest_qualification
#         ),

#         "address": enrollment.address,

#         # ----------------------------------------------------
#         # COURSE DETAILS
#         # ----------------------------------------------------

#         "course_id": enrollment.course_id,

#         "course_title": enrollment.course_title,

#         "course_duration": course.duration,

#         # ----------------------------------------------------
#         # PAYMENT / FEE
#         # ----------------------------------------------------

#         "total_fee": float(
#             enrollment.total_fee
#         ),

#         "status": enrollment.status,

#         "course_status": enrollment.course_status,

#         # ----------------------------------------------------
#         # RAZORPAY DETAILS
#         # ----------------------------------------------------

#         "razorpay_order_id": (
#             enrollment.razorpay_order_id
#         ),

#         "razorpay_payment_id": (
#             enrollment.razorpay_payment_id
#         ),

#         # ----------------------------------------------------
#         # DATES
#         # ----------------------------------------------------

#         "created_at": enrollment.created_at,

#         "paid_at": enrollment.paid_at
#     }


# # ============================================================
# # BRANCH PROFIT BY DATE
# # ============================================================

# @router.get("")
# def get_branch_profit(

#     date: date_type | None = Query(
#         default=None,
#         description="Enter date. Format: YYYY-MM-DD"
#     ),

#     db: Session = Depends(get_db),

#     current_user: User = Depends(
#         get_current_user
#     )
# ):

#     # ========================================================
#     # CHECK BRANCH ADMIN
#     # ========================================================

#     branch = get_branch_admin(
#         current_user,
#         db
#     )

#     branch_id = branch.id

#     # ========================================================
#     # DEFAULT DATE = TODAY
#     # ========================================================

#     if date is None:
#         date = date_type.today()

#     # ========================================================
#     # START OF SELECTED DATE
#     # ========================================================

#     start_of_day = datetime.combine(
#         date,
#         time.min
#     )

#     # ========================================================
#     # START OF NEXT DAY
#     # ========================================================

#     end_of_day = (
#         start_of_day + timedelta(days=1)
#     )

#     # ========================================================
#     # GET PAID + APPROVED ENROLLMENTS
#     #
#     # Uses paid_at because this represents
#     # the actual successful payment date.
#     #
#     # Course is joined to get course duration.
#     # ========================================================

#     enrollment_records = (
#         db.query(
#             Enrollment,
#             Course
#         )
#         .join(
#             Course,
#             Course.id == Enrollment.course_id
#         )
#         .filter(
#             Enrollment.branch_id == branch_id,

#             Enrollment.status == "paid",

#             Enrollment.course_status == "approved",

#             Enrollment.paid_at >= start_of_day,

#             Enrollment.paid_at < end_of_day
#         )
#         .order_by(
#             Enrollment.paid_at.desc()
#         )
#         .all()
#     )

#     # ========================================================
#     # TOTAL PROFIT
#     # ========================================================

#     total_profit = sum(
#         enrollment.total_fee
#         for enrollment, course
#         in enrollment_records
#     )

#     # ========================================================
#     # RESPONSE
#     # ========================================================

#     return {
#         "date": date.isoformat(),

#         "total_profit": float(
#             total_profit
#         ),

#         "total_enrollments": len(
#             enrollment_records
#         ),

#         "enrollments": [
#             enrollment_to_dict(
#                 enrollment,
#                 course
#             )
#             for enrollment, course
#             in enrollment_records
#         ]
#     }


# # ============================================================
# # TODAY'S PROFIT
# # ============================================================

# @router.get(
#     "/today-profit",
#     tags=["Branch Admin Today's Profit"]
# )
# def get_today_profit(

#     db: Session = Depends(get_db),

#     current_user: User = Depends(
#         get_current_user
#     )
# ):

#     # ========================================================
#     # CHECK BRANCH ADMIN
#     # ========================================================

#     branch = get_branch_admin(
#         current_user,
#         db
#     )

#     branch_id = branch.id

#     # ========================================================
#     # TODAY'S DATE
#     # ========================================================

#     today = date_type.today()

#     # ========================================================
#     # START OF TODAY
#     # ========================================================

#     start_of_day = datetime.combine(
#         today,
#         time.min
#     )

#     # ========================================================
#     # START OF TOMORROW
#     # ========================================================

#     end_of_day = (
#         start_of_day + timedelta(days=1)
#     )

#     # ========================================================
#     # GET TODAY'S PAID + APPROVED ENROLLMENTS
#     #
#     # Uses paid_at because this is the
#     # actual successful payment date.
#     #
#     # Course is joined to get course duration.
#     # ========================================================

#     enrollment_records = (
#         db.query(
#             Enrollment,
#             Course
#         )
#         .join(
#             Course,
#             Course.id == Enrollment.course_id
#         )
#         .filter(
#             Enrollment.branch_id == branch_id,

#             Enrollment.status == "paid",

#             Enrollment.course_status == "approved",

#             Enrollment.paid_at >= start_of_day,

#             Enrollment.paid_at < end_of_day
#         )
#         .order_by(
#             Enrollment.paid_at.desc()
#         )
#         .all()
#     )

#     # ========================================================
#     # CALCULATE TODAY'S PROFIT
#     # ========================================================

#     today_profit = sum(
#         enrollment.total_fee
#         for enrollment, course
#         in enrollment_records
#     )

#     # ========================================================
#     # RESPONSE
#     # ========================================================

#     return {
#         "date": today.isoformat(),

#         "today_profit": float(
#             today_profit
#         ),

#         "total_enrollments": len(
#             enrollment_records
#         ),

#         "enrollments": [
#             enrollment_to_dict(
#                 enrollment,
#                 course
#             )
#             for enrollment, course
#             in enrollment_records
#         ]
#     }





from datetime import date as date_type, datetime, time, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    User,
    Branch,
    Course,
    Enrollment
)

from routers.auth import get_current_user


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/branch-admin/profit"
)


# ============================================================
# DATABASE DEPENDENCY
# ============================================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ============================================================
# CHECK BRANCH ADMIN
# ============================================================

def get_branch_admin(
    current_user: User,
    db: Session
):

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    branch = (
        db.query(Branch)
        .filter(
            Branch.id == current_user.branch_id
        )
        .first()
    )

    if not branch:
        raise HTTPException(
            status_code=404,
            detail="Branch not found"
        )

    return branch


# ============================================================
# ENROLLMENT RESPONSE
# ============================================================

def enrollment_to_dict(
    enrollment: Enrollment,
    course: Course
):

    return {
        # ----------------------------------------------------
        # ENROLLMENT
        # ----------------------------------------------------

        "enrollment_id": enrollment.id,

        "student_id": enrollment.user_id,

        # ----------------------------------------------------
        # STUDENT DETAILS
        # ----------------------------------------------------

        "name": enrollment.name,
        "email": enrollment.email,
        "phone": enrollment.phone,

        "parent_name": enrollment.parent_name,
        "parent_phone": enrollment.parent_phone,

        "highest_qualification": (
            enrollment.highest_qualification
        ),

        "address": enrollment.address,

        # ----------------------------------------------------
        # COURSE DETAILS
        # ----------------------------------------------------

        "course_id": enrollment.course_id,

        "course_title": enrollment.course_title,

        "course_duration": course.duration,

        # ----------------------------------------------------
        # PAYMENT / FEE
        # ----------------------------------------------------

        "total_fee": float(
            enrollment.total_fee
        ),

        "status": enrollment.status,

        "course_status": enrollment.course_status,

        # ----------------------------------------------------
        # RAZORPAY DETAILS
        # ----------------------------------------------------

        "razorpay_order_id": (
            enrollment.razorpay_order_id
        ),

        "razorpay_payment_id": (
            enrollment.razorpay_payment_id
        ),

        # ----------------------------------------------------
        # DATES
        # ----------------------------------------------------

        "created_at": enrollment.created_at,

        "paid_at": enrollment.paid_at
    }


# ============================================================
# BRANCH PROFIT BY DATE
# ============================================================

@router.get(
    "",
    tags=["Branch Admin Profit"]
)
def get_branch_profit(

    date: date_type | None = Query(
        default=None,
        description="Enter date. Format: YYYY-MM-DD"
    ),

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    )
):

    # ========================================================
    # CHECK BRANCH ADMIN
    # ========================================================

    branch = get_branch_admin(
        current_user,
        db
    )

    branch_id = branch.id

    # ========================================================
    # DEFAULT DATE = TODAY
    # ========================================================

    if date is None:
        date = date_type.today()

    # ========================================================
    # START OF SELECTED DATE
    # ========================================================

    start_of_day = datetime.combine(
        date,
        time.min
    )

    # ========================================================
    # START OF NEXT DAY
    # ========================================================

    end_of_day = (
        start_of_day + timedelta(days=1)
    )

    # ========================================================
    # GET PAID + APPROVED ENROLLMENTS
    # ========================================================

    enrollment_records = (
        db.query(
            Enrollment,
            Course
        )
        .join(
            Course,
            Course.id == Enrollment.course_id
        )
        .filter(
            Enrollment.branch_id == branch_id,

            Enrollment.status == "paid",

            Enrollment.course_status == "approved",

            Enrollment.paid_at >= start_of_day,

            Enrollment.paid_at < end_of_day
        )
        .order_by(
            Enrollment.paid_at.desc()
        )
        .all()
    )

    # ========================================================
    # TOTAL PROFIT
    # ========================================================

    total_profit = sum(
        enrollment.total_fee
        for enrollment, course
        in enrollment_records
    )

    # ========================================================
    # RESPONSE
    # ========================================================

    return {
        "date": date.isoformat(),

        "total_profit": float(
            total_profit
        ),

        "total_enrollments": len(
            enrollment_records
        ),

        "enrollments": [
            enrollment_to_dict(
                enrollment,
                course
            )
            for enrollment, course
            in enrollment_records
        ]
    }


# ============================================================
# TODAY'S PROFIT
# ============================================================

@router.get(
    "/today-profit",
    tags=["Branch Admin Today's Profit"]
)
def get_today_profit(

    db: Session = Depends(get_db),

    current_user: User = Depends(
        get_current_user
    )
):

    # ========================================================
    # CHECK BRANCH ADMIN
    # ========================================================

    branch = get_branch_admin(
        current_user,
        db
    )

    branch_id = branch.id

    # ========================================================
    # TODAY'S DATE
    # ========================================================

    today = date_type.today()

    # ========================================================
    # START OF TODAY
    # ========================================================

    start_of_day = datetime.combine(
        today,
        time.min
    )

    # ========================================================
    # START OF TOMORROW
    # ========================================================

    end_of_day = (
        start_of_day + timedelta(days=1)
    )

    # ========================================================
    # GET TODAY'S PAID + APPROVED ENROLLMENTS
    # ========================================================

    enrollment_records = (
        db.query(
            Enrollment,
            Course
        )
        .join(
            Course,
            Course.id == Enrollment.course_id
        )
        .filter(
            Enrollment.branch_id == branch_id,

            Enrollment.status == "paid",

            Enrollment.course_status == "approved",

            Enrollment.paid_at >= start_of_day,

            Enrollment.paid_at < end_of_day
        )
        .order_by(
            Enrollment.paid_at.desc()
        )
        .all()
    )

    # ========================================================
    # CALCULATE TODAY'S PROFIT
    # ========================================================

    today_profit = sum(
        enrollment.total_fee
        for enrollment, course
        in enrollment_records
    )

    # ========================================================
    # RESPONSE
    # ========================================================

    return {
        "date": today.isoformat(),

        "today_profit": float(
            today_profit
        ),

        "total_enrollments": len(
            enrollment_records
        ),

        "enrollments": [
            enrollment_to_dict(
                enrollment,
                course
            )
            for enrollment, course
            in enrollment_records
        ]
    }