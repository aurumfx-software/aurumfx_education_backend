import os
import json
import uuid

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form
)

from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Course, User, Branch

from schemas.course import CourseResponse

from routers.auth import get_current_user

from utils.spaces import (
    spaces_client,
    SPACES_BUCKET
)


router = APIRouter(
    prefix="/courses"
)


# ==========================================
# DATABASE DEPENDENCY
# ==========================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ==========================================
# BRANCH ADMIN AUTHENTICATION
# ==========================================

def get_current_branch_admin(
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Allow only active branch admins.
    """

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    if current_user.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Branch admin account is inactive"
        )

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    # ==========================================
    # CHECK BRANCH
    # ==========================================

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

    if branch.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Branch is inactive"
        )

    return current_user


# ==========================================
# GET ALL COURSES
# PUBLIC
# ==========================================

@router.get(
    "/",
    response_model=list[CourseResponse],
    tags=["Courses"]
)
def get_all_courses(
    db: Session = Depends(get_db)
):

    courses = (
        db.query(Course)
        .filter(
            Course.is_active == True
        )
        .all()
    )

    return courses


# ==========================================
# GET COURSE BY ID
# PUBLIC
# ==========================================

@router.get(
    "/{course_id}",
    response_model=CourseResponse,
    tags=["Courses"]
)
def get_course(
    course_id: int,
    db: Session = Depends(get_db)
):

    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.is_active == True
        )
        .first()
    )

    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course not found"
        )

    return course


# ==========================================
# ADD COURSE
# BRANCH ADMIN ONLY
# ==========================================

@router.post(
    "/",
    response_model=CourseResponse,
    tags=["Branch Admin"]
)
def add_course(

    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    duration: str = Form(...),
    category: str = Form(...),
    level: str = Form(...),

    # Curriculum comes as JSON string
    curriculum: str = Form(...),

    image: UploadFile = File(...),

    db: Session = Depends(get_db),

    branch_admin=Depends(get_current_branch_admin)
):

    # ==========================================
    # CONVERT CURRICULUM JSON STRING
    # ==========================================

    try:

        curriculum_data = json.loads(
            curriculum
        )

    except json.JSONDecodeError:

        raise HTTPException(
            status_code=400,
            detail="Invalid curriculum JSON"
        )


    # ==========================================
    # UPLOAD IMAGE TO DIGITALOCEAN SPACES
    # ==========================================

    file_extension = os.path.splitext(
        image.filename
    )[1]

    file_name = (
        f"courses/{uuid.uuid4()}{file_extension}"
    )

    spaces_client.upload_fileobj(
        image.file,
        SPACES_BUCKET,
        file_name,
        ExtraArgs={
            "ContentType": image.content_type,
            "ACL": "public-read"
        }
    )

    image_url = (
        f"{os.getenv('SPACES_PUBLIC_URL')}/{file_name}"
    )


    # ==========================================
    # SAVE COURSE
    # ==========================================

    new_course = Course(

        # IMPORTANT:
        # Automatically assign logged-in
        # branch admin's branch
        branch_id=branch_admin.branch_id,

        title=title,
        description=description,
        price=price,
        duration=duration,
        category=category,
        level=level,
        curriculum=curriculum_data,
        image=image_url,
        is_active=True
    )

    db.add(new_course)

    db.commit()

    db.refresh(new_course)

    return new_course


# ==========================================
# GET BRANCH ADMIN COURSES
# BRANCH ADMIN ONLY
# ==========================================

@router.get(
    "/branch-admin/my-courses",
    response_model=list[CourseResponse],
    tags=["Branch Admin"]
)
def get_my_courses(

    db: Session = Depends(get_db),

    branch_admin=Depends(get_current_branch_admin)
):

    courses = (
        db.query(Course)
        .filter(
            Course.branch_id == branch_admin.branch_id,
            Course.is_active == True
        )
        .all()
    )

    return courses


# ==========================================
# GET BRANCH ADMIN COURSE BY ID
# BRANCH ADMIN ONLY
# ==========================================

@router.get(
    "/branch-admin/{course_id}",
    response_model=CourseResponse,
    tags=["Branch Admin"]
)
def get_my_course(

    course_id: int,

    db: Session = Depends(get_db),

    branch_admin=Depends(get_current_branch_admin)
):

    course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == branch_admin.branch_id,
            Course.is_active == True
        )
        .first()
    )

    if not course:

        raise HTTPException(
            status_code=404,
            detail="Course not found in your branch"
        )

    return course


# ==========================================
# UPDATE COURSE
# BRANCH ADMIN ONLY
# ==========================================

@router.put(
    "/branch-admin/{course_id}",
    response_model=CourseResponse,
    tags=["Branch Admin"]
)
def update_course(

    course_id: int,

    title: str = Form(...),
    description: str = Form(...),
    price: float = Form(...),
    duration: str = Form(...),
    category: str = Form(...),
    level: str = Form(...),

    curriculum: str = Form(...),

    image: UploadFile | None = File(None),

    db: Session = Depends(get_db),

    branch_admin=Depends(get_current_branch_admin)
):

    # ==========================================
    # FIND COURSE
    # ONLY FROM ADMIN'S BRANCH
    # ==========================================

    db_course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == branch_admin.branch_id
        )
        .first()
    )

    if not db_course:

        raise HTTPException(
            status_code=404,
            detail="Course not found in your branch"
        )


    # ==========================================
    # CHECK ACTIVE
    # ==========================================

    if not db_course.is_active:

        raise HTTPException(
            status_code=404,
            detail="Course is inactive"
        )


    # ==========================================
    # CONVERT CURRICULUM
    # ==========================================

    try:

        curriculum_data = json.loads(
            curriculum
        )

    except json.JSONDecodeError:

        raise HTTPException(
            status_code=400,
            detail="Invalid curriculum JSON"
        )


    # ==========================================
    # UPDATE TEXT FIELDS
    # ==========================================

    db_course.title = title

    db_course.description = description

    db_course.price = price

    db_course.duration = duration

    db_course.category = category

    db_course.level = level

    db_course.curriculum = curriculum_data


    # ==========================================
    # UPDATE IMAGE IF PROVIDED
    # ==========================================

    if image:

        # ------------------------------------------
        # DELETE OLD IMAGE
        # ------------------------------------------

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
                    ""
                )

                try:

                    spaces_client.delete_object(
                        Bucket=SPACES_BUCKET,
                        Key=old_key
                    )

                except Exception as e:

                    print(
                        f"Error deleting old image: {e}"
                    )


        # ------------------------------------------
        # UPLOAD NEW IMAGE
        # ------------------------------------------

        file_extension = os.path.splitext(
            image.filename
        )[1]

        file_name = (
            f"courses/{uuid.uuid4()}{file_extension}"
        )

        spaces_client.upload_fileobj(
            image.file,
            SPACES_BUCKET,
            file_name,
            ExtraArgs={
                "ContentType": image.content_type,
                "ACL": "public-read"
            }
        )

        image_url = (
            f"{os.getenv('SPACES_PUBLIC_URL')}/{file_name}"
        )

        db_course.image = image_url


    # ==========================================
    # SAVE CHANGES
    # ==========================================

    db.commit()

    db.refresh(db_course)

    return db_course


# ==========================================
# DELETE COURSE
# BRANCH ADMIN ONLY
# ==========================================

@router.delete(
    "/branch-admin/{course_id}",
    tags=["Branch Admin"]
)
def delete_course(

    course_id: int,

    db: Session = Depends(get_db),

    branch_admin=Depends(get_current_branch_admin)
):

    # ==========================================
    # FIND COURSE
    # ONLY FROM ADMIN'S BRANCH
    # ==========================================

    db_course = (
        db.query(Course)
        .filter(
            Course.id == course_id,
            Course.branch_id == branch_admin.branch_id
        )
        .first()
    )

    if not db_course:

        raise HTTPException(
            status_code=404,
            detail="Course not found in your branch"
        )


    # ==========================================
    # DELETE IMAGE FROM DIGITALOCEAN SPACES
    # ==========================================

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
                ""
            )

            try:

                spaces_client.delete_object(
                    Bucket=SPACES_BUCKET,
                    Key=old_key
                )

            except Exception as e:

                print(
                    f"Error deleting image from Spaces: {e}"
                )


    # ==========================================
    # DELETE COURSE FROM DATABASE
    # ==========================================

    db.delete(db_course)

    db.commit()

    return {
        "message": "Course deleted successfully"
    }