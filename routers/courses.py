import os
import json
import uuid

from datetime import date

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
)

from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Course, User, Branch

from schemas.course import CourseResponse

from routers.auth import get_current_user

from utils.spaces import (
    spaces_client,
    SPACES_BUCKET,
)


router = APIRouter(
    prefix="/courses"
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
# INSTALLMENT VALIDATION
# ============================================================

def validate_installment_details(
    installment_schedule: str,
    installment_count: int,
):
    """
    Validate installment schedule and installment count.

    Rules:

    installment_count = 0
        -> Full payment

    installment_count > 0
        -> Installment payment

    Allowed schedules:
        - monthly
        - weekly
    """

    if installment_count < 0:
        raise HTTPException(
            status_code=400,
            detail="Installment count cannot be negative",
        )

    # Full payment
    if installment_count == 0:
        return None, 0

    # Installment payment
    if installment_schedule not in [
        "monthly",
        "weekly",
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Installment schedule must be "
                "monthly or weekly"
            ),
        )

    return installment_schedule, installment_count


# ============================================================
# BRANCH ADMIN AUTHENTICATION
# ============================================================

def get_current_branch_admin(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Allow only active branch admins.
    """

    # Check role
    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required",
        )

    # Check user status
    if current_user.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Branch admin account is inactive",
        )

    # Check branch assignment
    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "Branch admin is not "
                "assigned to a branch"
            ),
        )

    # Check branch
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
            detail="Branch not found",
        )

    # Check branch status
    if branch.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Branch is inactive",
        )

    return current_user


# ============================================================
# GET COURSE BY ID
# PUBLIC
# ============================================================

@router.get(
    "/{course_id}",
    response_model=CourseResponse,
    tags=["Student Courses"],
)
def get_course(
    course_id: int,
    db: Session = Depends(get_db),
):
    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.is_active == True,
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found",
        )

    return course


# ============================================================
# ADD COURSE
# BRANCH ADMIN ONLY
# ============================================================

@router.post(
    "/",
    response_model=CourseResponse,
    tags=["Branch Admin Courses"],
)
def add_course(
    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    duration: str = Form(...),

    category: str = Form(...),
    level: str = Form(...),

    # COURSE PERIOD
    start_date: date = Form(...),
    end_date: date = Form(...),

    # CURRICULUM
    curriculum: str = Form(...),

    # INSTALLMENT DETAILS
    installment_schedule: str = Form("monthly"),
    installment_count: int = Form(0),

    # IMAGE
    image: UploadFile = File(...),

    db: Session = Depends(get_db),

    branch_admin=Depends(
        get_current_branch_admin
    ),
):

    # ========================================================
    # VALIDATE PRICE
    # ========================================================

    if price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Course price must be greater than 0",
        )

    # ========================================================
    # VALIDATE COURSE DATES
    # ========================================================

    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="Start date cannot be after end date",
        )

    # ========================================================
    # CONVERT CURRICULUM JSON
    # ========================================================

    try:
        curriculum_data = json.loads(
            curriculum
        )

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid curriculum JSON",
        )

    # ========================================================
    # VALIDATE INSTALLMENT DETAILS
    # ========================================================

    (
        installment_schedule_data,
        installment_count_data,
    ) = validate_installment_details(
        installment_schedule=installment_schedule,
        installment_count=installment_count,
    )

    # ========================================================
    # UPLOAD IMAGE TO DIGITALOCEAN SPACES
    # ========================================================

    file_extension = os.path.splitext(
        image.filename or ""
    )[1]

    file_name = (
        f"courses/{uuid.uuid4()}"
        f"{file_extension}"
    )

    try:
        spaces_client.upload_fileobj(
            image.file,
            SPACES_BUCKET,
            file_name,
            ExtraArgs={
                "ContentType": image.content_type,
                "ACL": "public-read",
            },
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Image upload failed: {str(e)}",
        )

    image_url = (
        f"{os.getenv('SPACES_PUBLIC_URL')}"
        f"/{file_name}"
    )

    # ========================================================
    # SAVE COURSE
    # ========================================================

    new_course = Course(

        # BRANCH
        branch_id=branch_admin.branch_id,

        # COURSE INFORMATION
        title=title,
        description=description,
        price=price,
        duration=duration,

        category=category,
        level=level,

        # COURSE PERIOD
        start_date=start_date,
        end_date=end_date,

        # CURRICULUM
        curriculum=curriculum_data,

        # INSTALLMENT DETAILS
        installment_schedule=installment_schedule_data,
        installment_count=installment_count_data,

        # IMAGE
        image=image_url,

        # STATUS
        is_active=True,
    )

    db.add(new_course)

    db.commit()

    db.refresh(new_course)

    return new_course


# ============================================================
# GET BRANCH ADMIN COURSES
# BRANCH ADMIN ONLY
# ============================================================

@router.get(
    "/branch-admin/my-courses",
    response_model=list[CourseResponse],
    tags=["Branch Admin Courses"],
)
def get_my_courses(
    db: Session = Depends(get_db),

    branch_admin=Depends(
        get_current_branch_admin
    ),
):

    courses = (
        db.query(Course)
        .filter(
            Course.branch_id == branch_admin.branch_id,
            Course.is_active == True,
        )
        .all()
    )

    return courses


# ============================================================
# GET BRANCH ADMIN COURSE BY ID
# BRANCH ADMIN ONLY
# ============================================================

@router.get(
    "/branch-admin/{course_id}",
    response_model=CourseResponse,
    tags=["Branch Admin Courses"],
)
def get_my_course(
    course_id: int,

    db: Session = Depends(get_db),

    branch_admin=Depends(
        get_current_branch_admin
    ),
):

    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == branch_admin.branch_id,
            Course.is_active == True,
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found in your branch",
        )

    return course


# ============================================================
# UPDATE COURSE
# BRANCH ADMIN ONLY
# ============================================================

@router.put(
    "/branch-admin/{course_id}",
    response_model=CourseResponse,
    tags=["Branch Admin Courses"],
)
def update_course(
    course_id: int,

    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    duration: str = Form(...),

    category: str = Form(...),
    level: str = Form(...),

    # COURSE PERIOD
    start_date: date = Form(...),
    end_date: date = Form(...),

    # CURRICULUM
    curriculum: str = Form(...),

    # INSTALLMENT DETAILS
    installment_schedule: str = Form("monthly"),
    installment_count: int = Form(0),

    # IMAGE
    image: UploadFile | None = File(None),

    db: Session = Depends(get_db),

    branch_admin=Depends(
        get_current_branch_admin
    ),
):

    # ========================================================
    # FIND COURSE
    # ONLY FROM ADMIN'S BRANCH
    # ========================================================

    db_course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == branch_admin.branch_id,
        )
        .first()
    )

    if not db_course:
        raise HTTPException(
            status_code=404,
            detail="Course not found in your branch",
        )

    # ========================================================
    # CHECK ACTIVE
    # ========================================================

    if not db_course.is_active:
        raise HTTPException(
            status_code=404,
            detail="Course is inactive",
        )

    # ========================================================
    # VALIDATE PRICE
    # ========================================================

    if price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Course price must be greater than 0",
        )

    # ========================================================
    # VALIDATE COURSE DATES
    # ========================================================

    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="Start date cannot be after end date",
        )

    # ========================================================
    # CONVERT CURRICULUM JSON
    # ========================================================

    try:
        curriculum_data = json.loads(
            curriculum
        )

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid curriculum JSON",
        )

    # ========================================================
    # VALIDATE INSTALLMENT DETAILS
    # ========================================================

    (
        installment_schedule_data,
        installment_count_data,
    ) = validate_installment_details(
        installment_schedule=installment_schedule,
        installment_count=installment_count,
    )

    # ========================================================
    # UPDATE COURSE INFORMATION
    # ========================================================

    db_course.title = title

    db_course.description = description

    db_course.price = price

    db_course.duration = duration

    db_course.category = category

    db_course.level = level

    # ========================================================
    # UPDATE COURSE PERIOD
    # ========================================================

    db_course.start_date = start_date

    db_course.end_date = end_date

    # ========================================================
    # UPDATE CURRICULUM
    # ========================================================

    db_course.curriculum = curriculum_data

    # ========================================================
    # UPDATE INSTALLMENT DETAILS
    # ========================================================

    db_course.installment_schedule = (
        installment_schedule_data
    )

    db_course.installment_count = (
        installment_count_data
    )

    # ========================================================
    # UPDATE IMAGE IF PROVIDED
    # ========================================================

    if image:

        # ----------------------------------------------------
        # DELETE OLD IMAGE
        # ----------------------------------------------------

        if db_course.image:

            public_url = os.getenv(
                "SPACES_PUBLIC_URL"
            )

            if (
                public_url
                and db_course.image.startswith(
                    public_url
                )
            ):

                old_key = db_course.image.replace(
                    f"{public_url}/",
                    "",
                )

                try:
                    spaces_client.delete_object(
                        Bucket=SPACES_BUCKET,
                        Key=old_key,
                    )

                except Exception as e:
                    print(
                        f"Error deleting old image: {e}"
                    )

        # ----------------------------------------------------
        # UPLOAD NEW IMAGE
        # ----------------------------------------------------

        file_extension = os.path.splitext(
            image.filename or ""
        )[1]

        file_name = (
            f"courses/{uuid.uuid4()}"
            f"{file_extension}"
        )

        try:
            spaces_client.upload_fileobj(
                image.file,
                SPACES_BUCKET,
                file_name,
                ExtraArgs={
                    "ContentType": image.content_type,
                    "ACL": "public-read",
                },
            )

        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Image upload failed: {str(e)}",
            )

        image_url = (
            f"{os.getenv('SPACES_PUBLIC_URL')}"
            f"/{file_name}"
        )

        db_course.image = image_url

    # ========================================================
    # SAVE CHANGES
    # ========================================================

    db.commit()

    db.refresh(db_course)

    return db_course


# ============================================================
# DELETE COURSE
# BRANCH ADMIN ONLY
# ============================================================

@router.delete(
    "/branch-admin/{course_id}",
    tags=["Branch Admin Courses"],
)
def delete_course(
    course_id: int,

    db: Session = Depends(get_db),

    branch_admin=Depends(
        get_current_branch_admin
    ),
):

    # ========================================================
    # FIND COURSE
    # ONLY FROM ADMIN'S BRANCH
    # ========================================================

    db_course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == branch_admin.branch_id,
        )
        .first()
    )

    if not db_course:
        raise HTTPException(
            status_code=404,
            detail="Course not found in your branch",
        )

    # ========================================================
    # DELETE IMAGE FROM DIGITALOCEAN SPACES
    # ========================================================

    if db_course.image:

        public_url = os.getenv(
            "SPACES_PUBLIC_URL"
        )

        if (
            public_url
            and db_course.image.startswith(
                public_url
            )
        ):

            old_key = db_course.image.replace(
                f"{public_url}/",
                "",
            )

            try:
                spaces_client.delete_object(
                    Bucket=SPACES_BUCKET,
                    Key=old_key,
                )

            except Exception as e:
                print(
                    f"Error deleting image from Spaces: {e}"
                )

    # ========================================================
    # DELETE COURSE FROM DATABASE
    # ========================================================

    db.delete(db_course)

    db.commit()

    return {
        "message": "Course deleted successfully"
    }