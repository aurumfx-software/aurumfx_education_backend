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
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    User,
    Branch,
    Course,
    Enrollment,
    AdmissionPayment,
    EnrollmentInstallment,
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
    db: Session,
    enrollment: Enrollment,
    course: Course,
    amount_paid_on_date: float,
):
    installments = (
        db.query(EnrollmentInstallment)
        .filter(EnrollmentInstallment.enrollment_id == enrollment.id)
        .order_by(EnrollmentInstallment.installment_number.asc())
        .all()
    )
    paid_installment_count = sum(
        installment.status == "paid" for installment in installments
    )
    due_installments = [
        installment
        for installment in installments
        if installment.due_date <= date_type.today()
        and installment.amount - installment.paid_amount > 0
    ]

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

        "total_paid": float(enrollment.total_paid or 0),

        "amount_paid_on_date": float(amount_paid_on_date),

        "balance_amount": max(
            round(
                enrollment.balance_amount
                if enrollment.balance_amount is not None
                else enrollment.total_fee - (enrollment.total_paid or 0),
                2,
            ),
            0,
        ),

        "installment_count": len(installments),

        "paid_installment_count": paid_installment_count,

        "remaining_installment_count": (
            len(installments) - paid_installment_count
        ),

        "due_installment_count": len(due_installments),

        "installments": [
            {
                "installment_id": installment.id,
                "installment_number": installment.installment_number,
                "amount": installment.amount,
                "paid_amount": installment.paid_amount,
                "remaining_amount": round(
                    installment.amount - installment.paid_amount, 2
                ),
                "due_date": installment.due_date,
                "is_due": (
                    installment.due_date <= date_type.today()
                    and installment.amount - installment.paid_amount > 0
                ),
                "status": installment.status,
                "paid_date": installment.paid_date,
            }
            for installment in installments
        ],

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


def get_paid_enrollment_records(
    db: Session,
    branch_id: int,
    payment_date: date_type,
):
    start_of_day = datetime.combine(payment_date, time.min)
    end_of_day = start_of_day + timedelta(days=1)
    daily_payments = (
        db.query(
            AdmissionPayment.enrollment_id.label("enrollment_id"),
            func.sum(AdmissionPayment.amount).label("amount_paid_on_date"),
        )
        .filter(
            AdmissionPayment.branch_id == branch_id,
            AdmissionPayment.payment_date == payment_date,
            AdmissionPayment.status == "received",
        )
        .group_by(AdmissionPayment.enrollment_id)
        .subquery()
    )

    return (
        db.query(
            Enrollment,
            Course,
            func.coalesce(
                daily_payments.c.amount_paid_on_date,
                Enrollment.total_fee,
            ).label("amount_paid_on_date"),
        )
        .join(Course, Course.id == Enrollment.course_id)
        .outerjoin(
            daily_payments,
            daily_payments.c.enrollment_id == Enrollment.id,
        )
        .filter(
            Enrollment.branch_id == branch_id,
            Enrollment.course_status == "approved",
            or_(
                daily_payments.c.enrollment_id.isnot(None),
                and_(
                    Enrollment.status == "paid",
                    Enrollment.paid_at >= start_of_day,
                    Enrollment.paid_at < end_of_day,
                ),
            ),
        )
        .order_by(Enrollment.paid_at.desc())
        .all()
    )


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
    # GET APPROVED ENROLLMENTS WITH PAYMENTS ON SELECTED DATE
    # ========================================================

    enrollment_records = get_paid_enrollment_records(
        db=db,
        branch_id=branch_id,
        payment_date=date,
    )

    # ========================================================
    # TOTAL PROFIT
    # ========================================================

    total_profit = sum(
        amount_paid_on_date
        for enrollment, course, amount_paid_on_date
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
                db,
                enrollment,
                course,
                amount_paid_on_date,
            )
            for enrollment, course, amount_paid_on_date
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
    # GET APPROVED ENROLLMENTS WITH PAYMENTS TODAY
    # ========================================================

    enrollment_records = get_paid_enrollment_records(
        db=db,
        branch_id=branch_id,
        payment_date=today,
    )

    # ========================================================
    # CALCULATE TODAY'S PROFIT
    # ========================================================

    today_profit = sum(
        amount_paid_on_date
        for enrollment, course, amount_paid_on_date
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
                db,
                enrollment,
                course,
                amount_paid_on_date,
            )
            for enrollment, course, amount_paid_on_date
            in enrollment_records
        ]
    }