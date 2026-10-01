from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    AdmissionPayment,
    Branch,
    BranchAdminAttendance,
    Course,
    Enrollment,
    Enquiry,
    Staff,
    StaffAttendance,
    User,
)
from routers.auth import get_current_super_admin


router = APIRouter(
    prefix="/super-admin/dashboard",
    tags=["Super Admin Dashboard"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def rows_by_branch(rows):
    return {row.branch_id: row for row in rows}


@router.get("/overview")
def get_super_admin_dashboard(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    today = date.today()
    branches = (
        db.query(Branch)
        .filter(Branch.status == "Active")
        .order_by(Branch.name.asc())
        .all()
    )
    branch_ids = [branch.id for branch in branches]

    if not branch_ids:
        return {
            "date": today.isoformat(),
            "overview": {
                "total_branches": 0,
                "active_branches": 0,
                "total_courses": 0,
                "active_courses": 0,
                "total_students": 0,
                "total_enrollments": 0,
                "paid_enrollments": 0,
                "pending_enrollments": 0,
                "total_staff": 0,
                "total_branch_admins": 0,
                "total_enquiries": 0,
                "today_enquiries": 0,
                "total_received": 0,
                "today_received": 0,
                "staff_attendance_today": 0,
                "branch_admin_attendance_today": 0,
            },
            "payment_methods": {},
            "branches": [],
        }

    courses = rows_by_branch(
        db.query(
            Course.branch_id.label("branch_id"),
            func.count(Course.id).label("total_courses"),
            func.sum(case((Course.is_active == True, 1), else_=0)).label(
                "active_courses"
            ),
        )
        .filter(Course.branch_id.in_(branch_ids))
        .group_by(Course.branch_id)
        .all()
    )

    enrollments = rows_by_branch(
        db.query(
            Enrollment.branch_id.label("branch_id"),
            func.count(Enrollment.id).label("total_enrollments"),
            func.count(func.distinct(Enrollment.user_id)).label("total_students"),
            func.sum(case((Enrollment.status == "paid", 1), else_=0)).label(
                "paid_enrollments"
            ),
            func.sum(case((Enrollment.status == "pending", 1), else_=0)).label(
                "pending_enrollments"
            ),
            func.sum(
                case(
                    (func.date(Enrollment.created_at) == today, 1),
                    else_=0,
                )
            ).label("today_enrollments"),
        )
        .filter(Enrollment.branch_id.in_(branch_ids))
        .group_by(Enrollment.branch_id)
        .all()
    )

    total_students = (
        db.query(func.count(func.distinct(Enrollment.user_id)))
        .filter(Enrollment.branch_id.in_(branch_ids))
        .scalar()
        or 0
    )

    staff = rows_by_branch(
        db.query(
            Staff.branch_id.label("branch_id"),
            func.count(Staff.id).label("total_staff"),
        )
        .filter(
            Staff.branch_id.in_(branch_ids),
            Staff.status == "Active",
        )
        .group_by(Staff.branch_id)
        .all()
    )

    branch_admins = rows_by_branch(
        db.query(
            User.branch_id.label("branch_id"),
            func.count(User.id).label("total_branch_admins"),
        )
        .filter(
            User.branch_id.in_(branch_ids),
            User.role == "branch_admin",
            User.status == "Active",
        )
        .group_by(User.branch_id)
        .all()
    )

    enquiries = rows_by_branch(
        db.query(
            Enquiry.branch_id.label("branch_id"),
            func.count(Enquiry.id).label("total_enquiries"),
            func.sum(
                case((func.date(Enquiry.created_at) == today, 1), else_=0)
            ).label("today_enquiries"),
        )
        .filter(Enquiry.branch_id.in_(branch_ids))
        .group_by(Enquiry.branch_id)
        .all()
    )

    payments = rows_by_branch(
        db.query(
            AdmissionPayment.branch_id.label("branch_id"),
            func.sum(AdmissionPayment.amount).label("total_received"),
            func.sum(
                case(
                    (AdmissionPayment.payment_date == today, AdmissionPayment.amount),
                    else_=0,
                )
            ).label("today_received"),
        )
        .filter(
            AdmissionPayment.branch_id.in_(branch_ids),
            AdmissionPayment.status == "received",
        )
        .group_by(AdmissionPayment.branch_id)
        .all()
    )

    payment_method_rows = (
        db.query(
            AdmissionPayment.branch_id.label("branch_id"),
            func.sum(
                case(
                    (
                        AdmissionPayment.payment_method.in_(["cash", "cash_upi"]),
                        AdmissionPayment.cash_amount,
                    ),
                    else_=0,
                )
            ).label("cash_amount"),
            func.sum(
                case(
                    (
                        AdmissionPayment.payment_method.in_(["upi", "cash_upi"]),
                        AdmissionPayment.upi_amount,
                    ),
                    else_=0,
                )
            ).label("upi_amount"),
            func.sum(
                case(
                    (AdmissionPayment.payment_method == "razorpay", AdmissionPayment.amount),
                    else_=0,
                )
            ).label("razorpay_amount"),
            func.sum(
                case(
                    (
                        AdmissionPayment.payment_method == "unknown",
                        AdmissionPayment.amount,
                    ),
                    else_=0,
                )
            ).label("unknown_amount"),
        )
        .filter(
            AdmissionPayment.branch_id.in_(branch_ids),
            AdmissionPayment.status == "received",
        )
        .group_by(AdmissionPayment.branch_id)
        .all()
    )
    payment_method_keys = ("cash", "upi", "razorpay", "unknown")
    payment_methods_by_branch = {
        branch_id: {method: 0.0 for method in payment_method_keys}
        for branch_id in branch_ids
    }
    overall_payment_methods = {method: 0.0 for method in payment_method_keys}
    for row in payment_method_rows:
        amounts = {
            "cash": float(row.cash_amount or 0),
            "upi": float(row.upi_amount or 0),
            "razorpay": float(row.razorpay_amount or 0),
            "unknown": float(row.unknown_amount or 0),
        }
        payment_methods_by_branch[row.branch_id] = amounts
        for method, amount in amounts.items():
            overall_payment_methods[method] += amount

    staff_attendance = rows_by_branch(
        db.query(
            StaffAttendance.branch_id.label("branch_id"),
            func.count(StaffAttendance.id).label("attendance_today"),
        )
        .filter(
            StaffAttendance.branch_id.in_(branch_ids),
            StaffAttendance.date == today,
        )
        .group_by(StaffAttendance.branch_id)
        .all()
    )

    branch_admin_attendance = rows_by_branch(
        db.query(
            BranchAdminAttendance.branch_id.label("branch_id"),
            func.count(BranchAdminAttendance.id).label("attendance_today"),
        )
        .filter(
            BranchAdminAttendance.branch_id.in_(branch_ids),
            BranchAdminAttendance.date == today,
        )
        .group_by(BranchAdminAttendance.branch_id)
        .all()
    )

    branch_summaries = []
    for branch in branches:
        course_stats = courses.get(branch.id)
        enrollment_stats = enrollments.get(branch.id)
        staff_stats = staff.get(branch.id)
        branch_admin_stats = branch_admins.get(branch.id)
        enquiry_stats = enquiries.get(branch.id)
        payment_stats = payments.get(branch.id)
        staff_attendance_stats = staff_attendance.get(branch.id)
        branch_admin_attendance_stats = branch_admin_attendance.get(branch.id)

        branch_summaries.append(
            {
                "branch_id": branch.id,
                "branch_name": branch.name,
                "location": branch.location,
                "status": branch.status,
                "total_courses": int(course_stats.total_courses or 0) if course_stats else 0,
                "active_courses": int(course_stats.active_courses or 0) if course_stats else 0,
                "total_students": int(enrollment_stats.total_students or 0) if enrollment_stats else 0,
                "total_enrollments": int(enrollment_stats.total_enrollments or 0) if enrollment_stats else 0,
                "paid_enrollments": int(enrollment_stats.paid_enrollments or 0) if enrollment_stats else 0,
                "pending_enrollments": int(enrollment_stats.pending_enrollments or 0) if enrollment_stats else 0,
                "today_enrollments": int(enrollment_stats.today_enrollments or 0) if enrollment_stats else 0,
                "total_staff": int(staff_stats.total_staff or 0) if staff_stats else 0,
                "total_branch_admins": int(branch_admin_stats.total_branch_admins or 0) if branch_admin_stats else 0,
                "total_enquiries": int(enquiry_stats.total_enquiries or 0) if enquiry_stats else 0,
                "today_enquiries": int(enquiry_stats.today_enquiries or 0) if enquiry_stats else 0,
                "total_received": float(payment_stats.total_received or 0) if payment_stats else 0.0,
                "today_received": float(payment_stats.today_received or 0) if payment_stats else 0.0,
                "payment_methods": payment_methods_by_branch[branch.id],
                "staff_attendance_today": int(staff_attendance_stats.attendance_today or 0) if staff_attendance_stats else 0,
                "branch_admin_attendance_today": int(branch_admin_attendance_stats.attendance_today or 0) if branch_admin_attendance_stats else 0,
            }
        )

    overview = {
        "total_branches": len(branches),
        "active_branches": len(branches),
        "total_courses": sum(row["total_courses"] for row in branch_summaries),
        "active_courses": sum(row["active_courses"] for row in branch_summaries),
        "total_students": int(total_students),
        "total_enrollments": sum(row["total_enrollments"] for row in branch_summaries),
        "paid_enrollments": sum(row["paid_enrollments"] for row in branch_summaries),
        "pending_enrollments": sum(row["pending_enrollments"] for row in branch_summaries),
        "total_staff": sum(row["total_staff"] for row in branch_summaries),
        "total_branch_admins": sum(row["total_branch_admins"] for row in branch_summaries),
        "total_enquiries": sum(row["total_enquiries"] for row in branch_summaries),
        "today_enquiries": sum(row["today_enquiries"] for row in branch_summaries),
        "total_received": round(sum(row["total_received"] for row in branch_summaries), 2),
        "today_received": round(sum(row["today_received"] for row in branch_summaries), 2),
        "staff_attendance_today": sum(row["staff_attendance_today"] for row in branch_summaries),
        "branch_admin_attendance_today": sum(row["branch_admin_attendance_today"] for row in branch_summaries),
    }

    return {
        "date": today.isoformat(),
        "overview": overview,
        "payment_methods": overall_payment_methods,
        "branches": branch_summaries,
    }
