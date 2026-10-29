from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    Branch,
    Course,
    CourseReview,
    Enrollment,
    User,
)
from routers.auth import get_current_super_admin, get_current_user
from routers.courses import get_current_branch_admin
from schemas.course_review import CourseReviewCreate, CourseReviewResponse


router = APIRouter(tags=["Course Reviews"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def review_response(
    review: CourseReview,
    student: User,
    course: Course,
    branch: Branch,
):
    return {
        "id": review.id,
        "student_id": student.id,
        "student_name": student.name,
        "course_id": course.id,
        "course_title": course.title,
        "branch_id": branch.id,
        "branch_name": branch.name,
        "review": review.review,
        "rating": review.rating,
        "created_at": review.created_at,
    }


def review_rows(
    db: Session,
    branch_id: int | None = None,
    user_id: int | None = None,
    course_id: int | None = None,
):
    query = (
        db.query(CourseReview, User, Course, Branch)
        .join(User, User.id == CourseReview.user_id)
        .join(Course, Course.id == CourseReview.course_id)
        .join(Branch, Branch.id == CourseReview.branch_id)
    )
    if branch_id is not None:
        query = query.filter(CourseReview.branch_id == branch_id)
    if user_id is not None:
        query = query.filter(CourseReview.user_id == user_id)
    if course_id is not None:
        query = query.filter(CourseReview.course_id == course_id)
    return query.order_by(CourseReview.created_at.desc(), CourseReview.id.desc()).all()


@router.post(
    "/student/reviews",
    response_model=CourseReviewResponse,
    status_code=201,
)
def create_course_review(
    review_data: CourseReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="Student access required")

    enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.user_id == current_user.id,
            Enrollment.course_id == review_data.course_id,
            Enrollment.course_status == "approved",
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(
            status_code=403,
            detail="You can review only an approved enrolled course",
        )

    if (
        db.query(CourseReview)
        .filter(
            CourseReview.user_id == current_user.id,
            CourseReview.course_id == review_data.course_id,
        )
        .first()
    ):
        raise HTTPException(
            status_code=409,
            detail="You have already reviewed this course",
        )

    course = db.query(Course).filter(Course.id == enrollment.course_id).first()
    branch = db.query(Branch).filter(Branch.id == enrollment.branch_id).first()
    if not course or not branch:
        raise HTTPException(status_code=404, detail="Enrolled course not found")

    review = CourseReview(
        user_id=current_user.id,
        course_id=course.id,
        branch_id=branch.id,
        review=review_data.review.strip(),
        rating=review_data.rating,
    )
    if not review.review:
        raise HTTPException(status_code=400, detail="Review cannot be empty")

    db.add(review)
    db.commit()
    db.refresh(review)
    return review_response(review, current_user, course, branch)


@router.get(
    "/student/reviews",
    response_model=list[CourseReviewResponse],
)
def get_student_reviews(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="Student access required")
    return [
        review_response(review, student, course, branch)
        for review, student, course, branch in review_rows(
            db,
            user_id=current_user.id,
        )
    ]


@router.get(
    "/branch-admin/reviews",
    response_model=list[CourseReviewResponse],
)
def get_branch_reviews(
    course_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    branch_admin=Depends(get_current_branch_admin),
):
    return [
        review_response(review, student, course, branch)
        for review, student, course, branch in review_rows(
            db,
            branch_id=branch_admin.branch_id,
            course_id=course_id,
        )
    ]


@router.get(
    "/super-admin/reviews",
    response_model=list[CourseReviewResponse],
)
def get_super_admin_reviews(
    branch_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    if branch_id is not None and not db.query(Branch).filter(
        Branch.id == branch_id
    ).first():
        raise HTTPException(status_code=404, detail="Branch not found")
    return [
        review_response(review, student, course, branch)
        for review, student, course, branch in review_rows(
            db,
            branch_id=branch_id,
        )
    ]


@router.get(
    "/public/reviews",
    response_model=list[CourseReviewResponse],
)
def get_public_reviews(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return [
        review_response(review, student, course, branch)
        for review, student, course, branch in review_rows(db)[:limit]
    ]
