from datetime import date

from dateutil.relativedelta import relativedelta

from fastapi import (
    APIRouter,
    Depends,
    HTTPException
)

from sqlalchemy.orm import Session

from database import SessionLocal

from database_models import (
    User,
    Course,
    Enrollment,
    EnrollmentInstallment,
    AdmissionPayment
)

from routers.auth import get_current_user

from schemas.admission import (
    BranchAdmissionCreate,
    AdmissionPaymentCreate,
    BranchAdmissionResponse,
    AdmissionPaymentResponse
)

from utils.password import hash_password


router = APIRouter(
    prefix="/admissions",
    tags=["Branch Admin Admissions"]
)


# ============================================================
# DATABASE
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

def check_branch_admin(
    current_user: User
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


# ============================================================
# CALCULATE INSTALLMENT DUE DATE
# ============================================================

def calculate_due_date(
    start_date: date,
    installment_number: int,
    schedule: str | None
):

    if schedule == "monthly":

        return start_date + relativedelta(
            months=installment_number - 1
        )

    if schedule == "weekly":

        return start_date + relativedelta(
            weeks=installment_number - 1
        )

    return start_date


# ============================================================
# CREATE INSTALLMENT PLAN
# ============================================================

def create_installment_plan(
    db: Session,
    enrollment: Enrollment,
    course: Course
):

    count = course.installment_count or 0

    # --------------------------------------------------------
    # FULL PAYMENT
    # --------------------------------------------------------

    if count == 0:

        installment = EnrollmentInstallment(

            enrollment_id=enrollment.id,

            installment_number=1,

            amount=course.price,

            paid_amount=0,

            due_date=(
                course.start_date
                or enrollment.admission_date
            ),

            status="pending",

            paid_date=None,

            cash_amount=0,

            upi_amount=0
        )

        db.add(installment)

        return

    # --------------------------------------------------------
    # INSTALLMENT PAYMENT
    # --------------------------------------------------------

    installment_amount = round(
        course.price / count,
        2
    )

    base_date = (
        course.start_date
        or enrollment.admission_date
    )

    for number in range(1, count + 1):

        due_date = calculate_due_date(
            base_date,
            number,
            course.installment_schedule
        )

        # ----------------------------------------------------
        # HANDLE FINAL ROUNDING DIFFERENCE
        # ----------------------------------------------------

        if number == count:

            previous_amount = round(
                installment_amount * (count - 1),
                2
            )

            amount = round(
                course.price - previous_amount,
                2
            )

        else:

            amount = installment_amount

        installment = EnrollmentInstallment(

            enrollment_id=enrollment.id,

            installment_number=number,

            amount=amount,

            paid_amount=0,

            due_date=due_date,

            status="pending",

            paid_date=None,

            cash_amount=0,

            upi_amount=0
        )

        db.add(installment)


# ============================================================
# CREATE PAYMENT
# ============================================================
#
# IMPORTANT:
#
# A payment can cover:
#
#   - part of one installment
#   - one complete installment
#   - multiple installments
#   - part of the next installment
#
# Example:
#
# Course fee = ₹55,000
# 5 installments = ₹11,000 each
#
# Payment = ₹25,000
#
# Term 1 = ₹11,000 paid
# Term 2 = ₹11,000 paid
# Term 3 = ₹3,000 partial
#
# terms_paid = 3
#
# ============================================================

def create_payment(
    db: Session,
    enrollment: Enrollment,
    cash_amount: float,
    upi_amount: float,
    payment_date: date
):

    total_amount = round(
        cash_amount + upi_amount,
        2
    )

    if total_amount <= 0:

        return []


    # ========================================================
    # CHECK BALANCE
    # ========================================================

    if total_amount > enrollment.balance_amount:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Payment cannot exceed balance "
                f"₹{enrollment.balance_amount:.2f}"
            )
        )


    # ========================================================
    # GET PENDING / PARTIAL INSTALLMENTS
    # ========================================================

    installments = (
        db.query(EnrollmentInstallment)
        .filter(
            EnrollmentInstallment.enrollment_id
            == enrollment.id,

            EnrollmentInstallment.status
            != "paid"
        )
        .order_by(
            EnrollmentInstallment.installment_number.asc()
        )
        .all()
    )


    if not installments:

        raise HTTPException(
            status_code=400,
            detail="No pending installment found"
        )


    # ========================================================
    # REMAINING PAYMENT
    # ========================================================

    remaining_payment = round(
        total_amount,
        2
    )

    remaining_cash = round(
        cash_amount,
        2
    )

    remaining_upi = round(
        upi_amount,
        2
    )


    payments = []


    # ========================================================
    # DISTRIBUTE PAYMENT
    # ========================================================

    for installment in installments:

        if remaining_payment <= 0:

            break


        # ----------------------------------------------------
        # REMAINING AMOUNT OF CURRENT INSTALLMENT
        # ----------------------------------------------------

        installment_remaining = round(
            installment.amount
            - installment.paid_amount,
            2
        )


        if installment_remaining <= 0:

            continue


        # ----------------------------------------------------
        # AMOUNT GOING TO THIS INSTALLMENT
        # ----------------------------------------------------

        payment_for_installment = round(
            min(
                remaining_payment,
                installment_remaining
            ),
            2
        )


        if payment_for_installment <= 0:

            continue


        # ====================================================
        # SPLIT CASH / UPI
        # ====================================================

        cash_for_installment = round(
            min(
                remaining_cash,
                payment_for_installment
            ),
            2
        )

        upi_for_installment = round(
            payment_for_installment
            - cash_for_installment,
            2
        )


        # ====================================================
        # UPDATE INSTALLMENT
        # ====================================================

        installment.paid_amount = round(
            installment.paid_amount
            + payment_for_installment,
            2
        )

        installment.cash_amount = round(
            installment.cash_amount
            + cash_for_installment,
            2
        )

        installment.upi_amount = round(
            installment.upi_amount
            + upi_for_installment,
            2
        )


        # ----------------------------------------------------
        # INSTALLMENT STATUS
        # ----------------------------------------------------

        if installment.paid_amount >= installment.amount:

            installment.paid_amount = (
                installment.amount
            )

            installment.status = "paid"

            installment.paid_date = payment_date

        else:

            installment.status = "partial"


        # ====================================================
        # PAYMENT HISTORY
        # ====================================================

        payment = AdmissionPayment(

            enrollment_id=enrollment.id,

            installment_id=installment.id,

            installment_number=(
                installment.installment_number
            ),

            user_id=enrollment.user_id,

            branch_id=enrollment.branch_id,

            amount=payment_for_installment,

            cash_amount=cash_for_installment,

            upi_amount=upi_for_installment,

            payment_date=payment_date,

            status="received"
        )

        db.add(payment)

        payments.append(payment)


        # ====================================================
        # UPDATE REMAINING PAYMENT
        # ====================================================

        remaining_payment = round(
            remaining_payment
            - payment_for_installment,
            2
        )

        remaining_cash = round(
            remaining_cash
            - cash_for_installment,
            2
        )

        remaining_upi = round(
            remaining_upi
            - upi_for_installment,
            2
        )


    # ========================================================
    # UPDATE ENROLLMENT TOTALS
    # ========================================================

    enrollment.total_paid = round(
        enrollment.total_paid
        + total_amount,
        2
    )

    enrollment.balance_amount = round(
        enrollment.total_fee
        - enrollment.total_paid,
        2
    )


    # ========================================================
    # ENROLLMENT STATUS
    # ========================================================

    if enrollment.balance_amount <= 0:

        enrollment.balance_amount = 0

        enrollment.status = "paid"

    else:

        enrollment.status = "pending"


    return payments


# ============================================================
# REGISTER STUDENT
# ============================================================

@router.post(
    "/",
    response_model=BranchAdmissionResponse
)
def create_admission(

    data: BranchAdmissionCreate,

    db: Session = Depends(get_db),

    current_user: User = Depends(get_current_user)
):

    check_branch_admin(current_user)


    # ========================================================
    # VALIDATE PAYMENT STATUS
    # ========================================================

    if data.payment_status not in [
        "received",
        "not_received"
    ]:

        raise HTTPException(
            status_code=400,
            detail=(
                "payment_status must be "
                "'received' or 'not_received'"
            )
        )


    # ========================================================
    # FIND COURSE
    # ========================================================

    course = (
        db.query(Course)
        .filter(

            Course.id == data.course_id,

            Course.branch_id
            == current_user.branch_id,

            Course.is_active == True

        )
        .first()
    )


    if not course:

        raise HTTPException(
            status_code=404,
            detail="Course not found in your branch"
        )


    # ========================================================
    # CHECK EMAIL
    # ========================================================

    existing_email = (
        db.query(User)
        .filter(
            User.email == data.email
        )
        .first()
    )


    if existing_email:

        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )


    # ========================================================
    # CHECK PHONE
    # ========================================================

    existing_phone = (
        db.query(User)
        .filter(
            User.phone == data.phone
        )
        .first()
    )


    if existing_phone:

        raise HTTPException(
            status_code=400,
            detail="Phone number already registered"
        )


    # ========================================================
    # PAYMENT
    # ========================================================

    cash_amount = round(
        data.cash_amount,
        2
    )

    upi_amount = round(
        data.upi_amount,
        2
    )

    first_payment = round(
        cash_amount + upi_amount,
        2
    )


    # ========================================================
    # NOT RECEIVED
    # ========================================================

    if data.payment_status == "not_received":

        if first_payment > 0:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Cash and UPI amount must be 0 "
                    "when payment is not received"
                )
            )


    # ========================================================
    # RECEIVED
    # ========================================================

    if data.payment_status == "received":

        if first_payment <= 0:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Enter cash or UPI amount "
                    "when payment is received"
                )
            )


    # ========================================================
    # NEVER EXCEED COURSE FEE
    # ========================================================

    if first_payment > course.price:

        raise HTTPException(
            status_code=400,
            detail="Payment cannot exceed course fee"
        )


    # ========================================================
    # ADMISSION DATE
    # ========================================================

    admission_date = (
        data.payment_date
        or date.today()
    )


    # ========================================================
    # INSTALLMENT INFORMATION
    # ========================================================

    installment_count = (
        course.installment_count or 0
    )


    # This is kept internally in the Enrollment table.
    # It is NOT returned in BranchAdmissionResponse.

    if installment_count > 0:

        installment_amount = round(
            course.price / installment_count,
            2
        )

    else:

        installment_amount = course.price


    # ========================================================
    # CREATE USER
    # ========================================================

    new_user = User(

        name=data.name,

        email=data.email,

        phone=data.phone,

        parent_name=data.parent_name,

        parent_phone=data.parent_phone,

        highest_qualification=(
            data.highest_qualification
        ),

        address=data.address,

        password_hash=hash_password(
            data.password
        ),

        profile_image=None,

        role="user",

        status="Active"
    )

    db.add(new_user)

    db.flush()


    # ========================================================
    # CREATE ENROLLMENT
    # ========================================================

    enrollment = Enrollment(

        user_id=new_user.id,

        course_id=course.id,

        course_title=course.title,

        branch_id=current_user.branch_id,

        name=data.name,

        email=data.email,

        phone=data.phone,

        parent_name=data.parent_name,

        parent_phone=data.parent_phone,

        highest_qualification=(
            data.highest_qualification
        ),

        address=data.address,

        total_fee=course.price,

        admission_date=admission_date,

        installment_schedule=(
            course.installment_schedule
        ),

        installment_count=installment_count,

        installment_amount=installment_amount,

        total_paid=0,

        balance_amount=course.price,

        status="pending",

        course_status="approved"
    )

    db.add(enrollment)

    db.flush()


    # ========================================================
    # CREATE INSTALLMENT PLAN
    # ========================================================

    create_installment_plan(

        db=db,

        enrollment=enrollment,

        course=course
    )

    db.flush()


    # ========================================================
    # INITIAL PAYMENT
    # ========================================================

    if first_payment > 0:

        create_payment(

            db=db,

            enrollment=enrollment,

            cash_amount=cash_amount,

            upi_amount=upi_amount,

            payment_date=admission_date
        )


    # ========================================================
    # SAVE
    # ========================================================

    db.commit()

    db.refresh(enrollment)


    return build_admission_response(

        db=db,

        enrollment=enrollment
    )


# ============================================================
# ADD PAYMENT TO EXISTING STUDENT
# ============================================================

@router.post(
    "/{enrollment_id}/payments",
    response_model=list[AdmissionPaymentResponse]
)
def add_payment(

    enrollment_id: int,

    data: AdmissionPaymentCreate,

    db: Session = Depends(get_db),

    current_user: User = Depends(get_current_user)
):

    check_branch_admin(current_user)


    # ========================================================
    # FIND ENROLLMENT
    # ========================================================

    enrollment = (
        db.query(Enrollment)
        .filter(

            Enrollment.id == enrollment_id,

            Enrollment.branch_id
            == current_user.branch_id

        )
        .first()
    )


    if not enrollment:

        raise HTTPException(
            status_code=404,
            detail="Enrollment not found"
        )


    # ========================================================
    # CHECK BALANCE
    # ========================================================

    if enrollment.balance_amount <= 0:

        raise HTTPException(
            status_code=400,
            detail="Student has no pending balance"
        )


    # ========================================================
    # PAYMENT AMOUNT
    # ========================================================

    cash_amount = round(
        data.cash_amount,
        2
    )

    upi_amount = round(
        data.upi_amount,
        2
    )

    amount = round(
        cash_amount + upi_amount,
        2
    )


    if amount <= 0:

        raise HTTPException(
            status_code=400,
            detail="Enter a payment amount"
        )


    if amount > enrollment.balance_amount:

        raise HTTPException(
            status_code=400,
            detail=(
                f"Payment cannot exceed "
                f"balance "
                f"₹{enrollment.balance_amount:.2f}"
            )
        )


    # ========================================================
    # PAYMENT DATE
    # ========================================================

    payment_date = (
        data.payment_date
        or date.today()
    )


    # ========================================================
    # SAVE PAYMENT
    # ========================================================

    payments = create_payment(

        db=db,

        enrollment=enrollment,

        cash_amount=cash_amount,

        upi_amount=upi_amount,

        payment_date=payment_date
    )


    db.commit()


    for payment in payments:

        db.refresh(payment)


    return payments


# ============================================================
# GET ALL BRANCH STUDENTS
# ============================================================

@router.get(
    "/",
    response_model=list[BranchAdmissionResponse]
)
def get_branch_admissions(

    db: Session = Depends(get_db),

    current_user: User = Depends(get_current_user)
):

    check_branch_admin(current_user)


    enrollments = (
        db.query(Enrollment)
        .filter(

            Enrollment.branch_id
            == current_user.branch_id

        )
        .order_by(
            Enrollment.created_at.desc()
        )
        .all()
    )


    return [

        build_admission_response(
            db,
            enrollment
        )

        for enrollment in enrollments

    ]


# # ============================================================
# # GET ONE STUDENT
# # ============================================================

# @router.get(
#     "/{enrollment_id}",
#     response_model=BranchAdmissionResponse
# )
# def get_admission(

#     enrollment_id: int,

#     db: Session = Depends(get_db),

#     current_user: User = Depends(get_current_user)
# ):

#     check_branch_admin(current_user)


#     enrollment = (
#         db.query(Enrollment)
#         .filter(

#             Enrollment.id == enrollment_id,

#             Enrollment.branch_id
#             == current_user.branch_id

#         )
#         .first()
#     )


#     if not enrollment:

#         raise HTTPException(
#             status_code=404,
#             detail="Enrollment not found"
#         )


#     return build_admission_response(
#         db,
#         enrollment
#     )


# # ============================================================
# # GET PAYMENT HISTORY
# # ============================================================

# @router.get(
#     "/{enrollment_id}/payments",
#     response_model=list[AdmissionPaymentResponse]
# )
# def get_payment_history(

#     enrollment_id: int,

#     db: Session = Depends(get_db),

#     current_user: User = Depends(get_current_user)
# ):

#     check_branch_admin(current_user)


#     enrollment = (
#         db.query(Enrollment)
#         .filter(

#             Enrollment.id == enrollment_id,

#             Enrollment.branch_id
#             == current_user.branch_id

#         )
#         .first()
#     )


#     if not enrollment:

#         raise HTTPException(
#             status_code=404,
#             detail="Enrollment not found"
#         )


#     return (
#         db.query(AdmissionPayment)
#         .filter(
#             AdmissionPayment.enrollment_id
#             == enrollment_id
#         )
#         .order_by(
#             AdmissionPayment.payment_date.asc()
#         )
#         .all()
#     )


# # ============================================================
# # BUILD RESPONSE
# # ============================================================

# def build_admission_response(
#     db: Session,
#     enrollment: Enrollment
# ):

#     # ========================================================
#     # GET INSTALLMENTS
#     # ========================================================

#     installments = (
#         db.query(EnrollmentInstallment)
#         .filter(

#             EnrollmentInstallment.enrollment_id
#             == enrollment.id

#         )
#         .order_by(
#             EnrollmentInstallment.installment_number.asc()
#         )
#         .all()
#     )


#     # ========================================================
#     # GET PAYMENT HISTORY
#     # ========================================================

#     payments = (
#         db.query(AdmissionPayment)
#         .filter(

#             AdmissionPayment.enrollment_id
#             == enrollment.id

#         )
#         .order_by(
#             AdmissionPayment.payment_date.asc()
#         )
#         .all()
#     )


#     # ========================================================
#     # TERMS PAID
#     # ========================================================
#     #
#     # IMPORTANT:
#     #
#     # Any amount paid toward an installment means
#     # that installment counts as a paid term.
#     #
#     # Example:
#     #
#     # ₹1,000 paid  -> term 1
#     # ₹5,000 paid  -> term 1
#     # ₹10,000 paid -> term 1
#     #
#     # ========================================================

#     terms_paid = sum(

#         1

#         for installment in installments

#         if installment.paid_amount > 0

#     )


#     # ========================================================
#     # PENDING TERMS
#     # ========================================================

#     pending_terms = max(

#         len(installments)
#         - terms_paid,

#         0

#     )


#     # ========================================================
#     # RESPONSE
#     # ========================================================

#     return {

#         "enrollment_id":
#             enrollment.id,

#         "user_id":
#             enrollment.user_id,

#         "name":
#             enrollment.name,

#         "phone":
#             enrollment.phone,

#         "email":
#             enrollment.email,

#         "parent_name":
#             enrollment.parent_name,

#         "parent_phone":
#             enrollment.parent_phone,

#         "highest_qualification":
#             enrollment.highest_qualification,

#         "address":
#             enrollment.address,

#         "course_id":
#             enrollment.course_id,

#         "course_title":
#             enrollment.course_title,

#         "total_fee":
#             enrollment.total_fee,

#         "installment_schedule":
#             enrollment.installment_schedule,

#         "installment_count":
#             enrollment.installment_count or 0,

#         "admission_date":
#             enrollment.admission_date,

#         "total_paid":
#             enrollment.total_paid,

#         "balance_amount":
#             enrollment.balance_amount,

#         "terms_paid":
#             terms_paid,

#         "pending_terms":
#             pending_terms,

#         "status":
#             enrollment.status,

#         "installments":
#             installments,

#         "payments":
#             payments

#     }