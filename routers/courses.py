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
from database_models import Course

from schemas.course import CourseResponse

from routers.auth import get_current_super_admin

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
        .filter(Course.is_active == True)
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
        .filter(Course.id == course_id)
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
# SUPER ADMIN ONLY
# ==========================================

# @router.post(
#     "/",
#     response_model=CourseResponse,
#     tags=["Super Admin"]
# )
# def add_course(
#     title: str = Form(...),
#     description: str = Form(...),
#     price: float = Form(...),
#     duration: str = Form(...),
#     category: str = Form(...),
#     level: str = Form(...),

#     # Curriculum comes as JSON string
#     curriculum: str = Form(...),

#     image: UploadFile = File(...),

#     db: Session = Depends(get_db),
#     admin=Depends(get_current_super_admin)
# ):

#     # ==========================================
#     # CONVERT CURRICULUM JSON STRING
#     # ==========================================

#     try:
#         curriculum_data = json.loads(curriculum)

#     except json.JSONDecodeError:
#         raise HTTPException(
#             status_code=400,
#             detail="Invalid curriculum JSON"
#         )


#     # ==========================================
#     # UPLOAD IMAGE TO DIGITALOCEAN SPACES
#     # ==========================================

#     file_extension = os.path.splitext(
#         image.filename
#     )[1]

#     file_name = (
#         f"courses/{uuid.uuid4()}{file_extension}"
#     )

#     spaces_client.upload_fileobj(
#         image.file,
#         SPACES_BUCKET,
#         file_name,
#         ExtraArgs={
#             "ContentType": image.content_type,
#             "ACL": "public-read"
#         }
#     )

#     image_url = (
#         f"{os.getenv('SPACES_PUBLIC_URL')}/{file_name}"
#     )


#     # ==========================================
#     # SAVE COURSE
#     # ==========================================

#     new_course = Course(
#         title=title,
#         description=description,
#         price=price,
#         duration=duration,
#         category=category,
#         level=level,
#         curriculum=curriculum_data,
#         image=image_url
#     )

#     db.add(new_course)

#     db.commit()

#     db.refresh(new_course)

#     return new_course


# ==========================================
# UPDATE COURSE
# SUPER ADMIN ONLY
# ==========================================

# @router.put(
#     "/{course_id}",
#     response_model=CourseResponse,
#     tags=["Super Admin"]
# )
# def update_course(
#     course_id: int,

#     title: str = Form(...),
#     description: str = Form(...),
#     price: float = Form(...),
#     duration: str = Form(...),
#     category: str = Form(...),
#     level: str = Form(...),

#     curriculum: str = Form(...),

#     image: UploadFile | None = File(None),

#     db: Session = Depends(get_db),
#     admin=Depends(get_current_super_admin)
# ):

#     # ==========================================
#     # FIND COURSE
#     # ==========================================

#     db_course = (
#         db.query(Course)
#         .filter(Course.id == course_id)
#         .first()
#     )

#     if not db_course:
#         raise HTTPException(
#             status_code=404,
#             detail="Course not found"
#         )


#     # ==========================================
#     # CONVERT CURRICULUM
#     # ==========================================

#     try:
#         curriculum_data = json.loads(curriculum)

#     except json.JSONDecodeError:
#         raise HTTPException(
#             status_code=400,
#             detail="Invalid curriculum JSON"
#         )


#     # ==========================================
#     # UPDATE TEXT FIELDS
#     # ==========================================

#     db_course.title = title
#     db_course.description = description
#     db_course.price = price
#     db_course.duration = duration
#     db_course.category = category
#     db_course.level = level
#     db_course.curriculum = curriculum_data


#     # ==========================================
#     # UPDATE IMAGE IF PROVIDED
#     # ==========================================

#     if image:

#         # ------------------------------------------
#         # DELETE OLD IMAGE
#         # ------------------------------------------

#         if db_course.image:

#             public_url = os.getenv(
#                 "SPACES_PUBLIC_URL"
#             )

#             if (
#                 public_url
#                 and db_course.image.startswith(public_url)
#             ):

#                 old_key = db_course.image.replace(
#                     f"{public_url}/",
#                     ""
#                 )

#                 try:

#                     spaces_client.delete_object(
#                         Bucket=SPACES_BUCKET,
#                         Key=old_key
#                     )

#                 except Exception as e:

#                     print(
#                         f"Error deleting old image: {e}"
#                     )


#         # ------------------------------------------
#         # UPLOAD NEW IMAGE
#         # ------------------------------------------

#         file_extension = os.path.splitext(
#             image.filename
#         )[1]

#         file_name = (
#             f"courses/{uuid.uuid4()}{file_extension}"
#         )

#         spaces_client.upload_fileobj(
#             image.file,
#             SPACES_BUCKET,
#             file_name,
#             ExtraArgs={
#                 "ContentType": image.content_type,
#                 "ACL": "public-read"
#             }
#         )

#         image_url = (
#             f"{os.getenv('SPACES_PUBLIC_URL')}/{file_name}"
#         )

#         db_course.image = image_url


#     # ==========================================
#     # SAVE CHANGES
#     # ==========================================

#     db.commit()

#     db.refresh(db_course)

#     return db_course


# ==========================================
# DELETE COURSE
# SUPER ADMIN ONLY
# ==========================================

# @router.delete(
#     "/{course_id}",
#     tags=["Super Admin"]
# )
# def delete_course(
#     course_id: int,

#     db: Session = Depends(get_db),

#     admin=Depends(get_current_super_admin)
# ):

#     # ==========================================
#     # FIND COURSE
#     # ==========================================

#     db_course = (
#         db.query(Course)
#         .filter(Course.id == course_id)
#         .first()
#     )

#     if not db_course:

#         raise HTTPException(
#             status_code=404,
#             detail="Course not found"
#         )


#     # ==========================================
#     # DELETE IMAGE FROM DIGITALOCEAN SPACES
#     # ==========================================

#     if db_course.image:

#         public_url = os.getenv(
#             "SPACES_PUBLIC_URL"
#         )

#         if (
#             public_url
#             and db_course.image.startswith(public_url)
#         ):

#             old_key = db_course.image.replace(
#                 f"{public_url}/",
#                 ""
#             )

#             try:

#                 spaces_client.delete_object(
#                     Bucket=SPACES_BUCKET,
#                     Key=old_key
#                 )

#             except Exception as e:

#                 print(
#                     f"Error deleting image from Spaces: {e}"
#                 )


#     # ==========================================
#     # DELETE COURSE FROM DATABASE
#     # ==========================================

#     db.delete(db_course)

#     db.commit()

#     return {
#         "message": "Course deleted successfully"
#     }