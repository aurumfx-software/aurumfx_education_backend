from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    AdmissionPayment,
    Branch,
    Course,
    Enrollment,
    EnrollmentInstallment,
    Enquiry,
    User,
)
from routers.auth import get_current_super_admin


router = APIRouter(
    prefix="/super-admin/records",
    tags=["Super Admin Records"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_due_students_report(
    db: Session,
    branch_id: int | None,
    offset: int,
    limit: int,
):
    today = date.today()
    due_filter = [
        EnrollmentInstallment.due_date <= today,
        EnrollmentInstallment.paid_amount < EnrollmentInstallment.amount,
    ]
    if branch_id is not None:
        due_filter.append(Enrollment.branch_id == branch_id)

    totals = (
        db.query(
            func.count(EnrollmentInstallment.id).label("total_due_installments"),
            func.sum(
                EnrollmentInstallment.amount - EnrollmentInstallment.paid_amount
            ).label("total_due_amount"),
            func.count(func.distinct(Enrollment.id)).label("total_due_enrollments"),
            func.count(func.distinct(Enrollment.user_id)).label("total_due_students"),
        )
        .join(
            EnrollmentInstallment,
            EnrollmentInstallment.enrollment_id == Enrollment.id,
        )
        .filter(*due_filter)
        .one()
    )

    due_student_ids = (
        db.query(
            Enrollment.user_id.label("student_id"),
            func.min(EnrollmentInstallment.due_date).label("first_due_date"),
        )
        .join(
            EnrollmentInstallment,
            EnrollmentInstallment.enrollment_id == Enrollment.id,
        )
        .filter(*due_filter)
        .group_by(Enrollment.user_id)
        .order_by(
            func.min(EnrollmentInstallment.due_date).asc(),
            Enrollment.user_id.asc(),
        )
        .offset(offset)
        .limit(limit)
        .all()
    )
    student_ids = [row.student_id for row in due_student_ids]

    students_by_id = {}
    if student_ids:
        rows = (
            db.query(Enrollment, User, Course, Branch, EnrollmentInstallment)
            .join(User, User.id == Enrollment.user_id)
            .join(Course, Course.id == Enrollment.course_id)
            .join(Branch, Branch.id == Enrollment.branch_id)
            .join(
                EnrollmentInstallment,
                EnrollmentInstallment.enrollment_id == Enrollment.id,
            )
            .filter(
                Enrollment.user_id.in_(student_ids),
                *due_filter,
            )
            .order_by(
                Enrollment.name.asc(),
                EnrollmentInstallment.due_date.asc(),
                Enrollment.id.asc(),
            )
            .all()
        )

        for enrollment, user, course, branch, installment in rows:
            student = students_by_id.setdefault(
                user.id,
                {
                    "student_id": user.id,
                    "name": enrollment.name or user.name,
                    "email": enrollment.email or user.email,
                    "phone": enrollment.phone or user.phone,
                    "parent_name": enrollment.parent_name or user.parent_name,
                    "parent_phone": enrollment.parent_phone or user.parent_phone,
                    "highest_qualification": (
                        enrollment.highest_qualification or user.highest_qualification
                    ),
                    "address": enrollment.address or user.address,
                    "account_status": user.status,
                    "total_due_amount": 0.0,
                    "due_enrollments": {},
                },
            )
            due_enrollment = student["due_enrollments"].setdefault(
                enrollment.id,
                {
                    "enrollment_id": enrollment.id,
                    "branch_id": branch.id,
                    "branch_name": branch.name,
                    "branch_location": branch.location,
                    "branch_status": branch.status,
                    "course_id": course.id,
                    "course_title": enrollment.course_title or course.title,
                    "course_duration": course.duration,
                    "total_fee": enrollment.total_fee,
                    "total_paid": enrollment.total_paid or 0,
                    "balance_amount": max(
                        round(
                            enrollment.balance_amount
                            if enrollment.balance_amount is not None
                            else enrollment.total_fee - (enrollment.total_paid or 0),
                            2,
                        ),
                        0,
                    ),
                    "payment_status": enrollment.status,
                    "course_status": enrollment.course_status,
                    "branch_approval_status": enrollment.branch_approval_status,
                    "super_admin_approval_status": enrollment.super_admin_approval_status,
                    "admission_date": enrollment.admission_date,
                    "due_installments": [],
                },
            )
            remaining_amount = round(
                installment.amount - installment.paid_amount,
                2,
            )
            due_enrollment["due_installments"].append(
                {
                    "installment_id": installment.id,
                    "installment_number": installment.installment_number,
                    "amount": installment.amount,
                    "paid_amount": installment.paid_amount,
                    "remaining_amount": remaining_amount,
                    "due_date": installment.due_date,
                    "status": installment.status,
                }
            )
            student["total_due_amount"] = round(
                student["total_due_amount"] + remaining_amount,
                2,
            )

    due_students = []
    for student in students_by_id.values():
        student["due_enrollments"] = list(student["due_enrollments"].values())
        due_students.append(student)

    result = {
        "total_due_students": int(totals.total_due_students or 0),
        "total_due_enrollments": int(totals.total_due_enrollments or 0),
        "total_due_installments": int(totals.total_due_installments or 0),
        "total_due_amount": round(float(totals.total_due_amount or 0), 2),
        "offset": offset,
        "limit": limit,
        "due_students": due_students,
    }
    if branch_id is not None:
        branch = db.query(Branch).filter(Branch.id == branch_id).first()
        result["branch"] = (
            {
                "branch_id": branch.id,
                "branch_name": branch.name,
                "branch_location": branch.location,
                "branch_status": branch.status,
            }
            if branch
            else None
        )
    return result


@router.get("/enquiries")
def get_all_enquiries(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    total = db.query(func.count(Enquiry.id)).scalar() or 0
    pending = (
        db.query(func.count(Enquiry.id))
        .filter(Enquiry.branch_admin_status == "pending")
        .scalar()
        or 0
    )
    rows = (
        db.query(Enquiry, Branch)
        .outerjoin(Branch, Branch.id == Enquiry.branch_id)
        .order_by(Enquiry.created_at.desc(), Enquiry.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "total_enquiries": int(total),
        "pending_enquiries": int(pending),
        "offset": offset,
        "limit": limit,
        "enquiries": [
            {
                "id": enquiry.id,
                "branch_id": enquiry.branch_id,
                "branch_name": branch.name if branch else None,
                "branch_location": branch.location if branch else None,
                "name": enquiry.name,
                "email": enquiry.email,
                "phone": enquiry.phone,
                "course": enquiry.course,
                "qualification": enquiry.qualification,
                "message": enquiry.message,
                "status": enquiry.status,
                "branch_admin_status": enquiry.branch_admin_status,
                "branch_admin_read_at": enquiry.branch_admin_read_at,
                "created_at": enquiry.created_at,
            }
            for enquiry, branch in rows
        ],
    }


@router.get("/branches")
def get_record_branches(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branches = db.query(Branch).order_by(Branch.name.asc()).all()
    return [
        {
            "branch_id": branch.id,
            "branch_name": branch.name,
            "branch_location": branch.location,
            "branch_status": branch.status,
        }
        for branch in branches
    ]


@router.get("/due-students")
def get_all_due_students(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    return build_due_students_report(db, None, offset, limit)


@router.get("/branches/{branch_id}/due-students")
def get_branch_due_students(
    branch_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    if not db.query(Branch.id).filter(Branch.id == branch_id).first():
        raise HTTPException(status_code=404, detail="Branch not found")
    return build_due_students_report(db, branch_id, offset, limit)


@router.get("/students")
def get_all_students(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    total_students = (
        db.query(func.count(User.id))
        .filter(User.role == "user")
        .scalar()
        or 0
    )
    students = (
        db.query(User)
        .filter(User.role == "user")
        .order_by(User.created_at.desc(), User.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    student_ids = [student.id for student in students]

    enrollments_by_student = {student_id: [] for student_id in student_ids}
    if student_ids:
        enrollment_rows = (
            db.query(Enrollment, Course, Branch)
            .join(Course, Course.id == Enrollment.course_id)
            .join(Branch, Branch.id == Enrollment.branch_id)
            .filter(Enrollment.user_id.in_(student_ids))
            .order_by(Enrollment.created_at.desc(), Enrollment.id.desc())
            .all()
        )
        enrollment_ids = [enrollment.id for enrollment, _, _ in enrollment_rows]

        installments_by_enrollment = {enrollment_id: [] for enrollment_id in enrollment_ids}
        if enrollment_ids:
            installments = (
                db.query(EnrollmentInstallment)
                .filter(EnrollmentInstallment.enrollment_id.in_(enrollment_ids))
                .order_by(
                    EnrollmentInstallment.enrollment_id.asc(),
                    EnrollmentInstallment.installment_number.asc(),
                )
                .all()
            )
            for installment in installments:
                installments_by_enrollment[installment.enrollment_id].append(
                    {
                        "id": installment.id,
                        "installment_number": installment.installment_number,
                        "amount": installment.amount,
                        "paid_amount": installment.paid_amount,
                        "remaining_amount": round(
                            installment.amount - installment.paid_amount,
                            2,
                        ),
                        "due_date": installment.due_date,
                        "status": installment.status,
                        "paid_date": installment.paid_date,
                        "cash_amount": installment.cash_amount,
                        "upi_amount": installment.upi_amount,
                    }
                )

        payments_by_enrollment = {enrollment_id: [] for enrollment_id in enrollment_ids}
        if enrollment_ids:
            payments = (
                db.query(AdmissionPayment)
                .filter(AdmissionPayment.enrollment_id.in_(enrollment_ids))
                .order_by(
                    AdmissionPayment.enrollment_id.asc(),
                    AdmissionPayment.payment_date.asc(),
                    AdmissionPayment.id.asc(),
                )
                .all()
            )
            for payment in payments:
                payments_by_enrollment[payment.enrollment_id].append(
                    {
                        "id": payment.id,
                        "installment_id": payment.installment_id,
                        "installment_number": payment.installment_number,
                        "amount": payment.amount,
                        "cash_amount": payment.cash_amount,
                        "upi_amount": payment.upi_amount,
                        "payment_method": payment.payment_method,
                        "payment_date": payment.payment_date,
                        "status": payment.status,
                    }
                )

        for enrollment, course, branch in enrollment_rows:
            enrollments_by_student[enrollment.user_id].append(
                {
                    "enrollment_id": enrollment.id,
                    "branch_id": branch.id,
                    "branch_name": branch.name,
                    "branch_location": branch.location,
                    "course_id": course.id,
                    "course_title": enrollment.course_title or course.title,
                    "course_duration": course.duration,
                    "total_fee": enrollment.total_fee,
                    "total_paid": enrollment.total_paid or 0,
                    "balance_amount": max(
                        round(
                            enrollment.balance_amount
                            if enrollment.balance_amount is not None
                            else enrollment.total_fee - (enrollment.total_paid or 0),
                            2,
                        ),
                        0,
                    ),
                    "payment_status": enrollment.status,
                    "course_status": enrollment.course_status,
                    "branch_approval_status": enrollment.branch_approval_status,
                    "super_admin_approval_status": enrollment.super_admin_approval_status,
                    "admission_date": enrollment.admission_date,
                    "installment_schedule": enrollment.installment_schedule,
                    "installments": installments_by_enrollment[enrollment.id],
                    "payments": payments_by_enrollment[enrollment.id],
                    "razorpay_order_id": enrollment.razorpay_order_id,
                    "razorpay_payment_id": enrollment.razorpay_payment_id,
                    "created_at": enrollment.created_at,
                }
            )

    return {
        "total_students": int(total_students),
        "offset": offset,
        "limit": limit,
        "students": [
            {
                "user_id": student.id,
                "name": student.name,
                "email": student.email,
                "phone": student.phone,
                "parent_name": student.parent_name,
                "parent_phone": student.parent_phone,
                "highest_qualification": student.highest_qualification,
                "address": student.address,
                "status": student.status,
                "created_at": student.created_at,
                "enrollment_count": len(enrollments_by_student[student.id]),
                "enrollments": enrollments_by_student[student.id],
            }
            for student in students
        ],
    }
