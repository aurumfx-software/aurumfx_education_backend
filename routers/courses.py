









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


# ============================================================
# ROUTER
# ============================================================

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
# PAYMENT PLAN HELPER
# ============================================================

def build_payment_plan(
    payment_type: str,
    payment_plan: str,
    course_price: float,
):
    """
    Build and validate the payment plan.

    Supported payment types:
    - full
    - installment

    Full payment:

    {
        "type": "full"
    }

    Installment payment:

    {
        "type": "installment",
        "frequency": "monthly",
        "installments": [
            {
                "term": 1,
                "amount": 20000
            },
            {
                "term": 2,
                "amount": 15000
            }
        ]
    }

    Frequency:
    - monthly
    - weekly
    """

    # --------------------------------------------------------
    # Validate payment type
    # --------------------------------------------------------

    if payment_type not in ["full", "installment"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid payment type. Use full or installment",
        )

    # --------------------------------------------------------
    # Parse JSON
    # --------------------------------------------------------

    try:
        payment_plan_data = json.loads(payment_plan)

    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid payment plan JSON",
        )

    # Make sure the parsed value is an object
    if not isinstance(payment_plan_data, dict):
        raise HTTPException(
            status_code=400,
            detail="Payment plan must be a JSON object",
        )

    # --------------------------------------------------------
    # FULL PAYMENT
    # --------------------------------------------------------

    if payment_type == "full":

        return {
            "type": "full"
        }

    # --------------------------------------------------------
    # INSTALLMENT PAYMENT
    # --------------------------------------------------------

    frequency = payment_plan_data.get("frequency")

    if frequency not in ["monthly", "weekly"]:
        raise HTTPException(
            status_code=400,
            detail="Installment frequency must be monthly or weekly",
        )

    installments = payment_plan_data.get("installments")

    if not isinstance(installments, list) or not installments:
        raise HTTPException(
            status_code=400,
            detail="At least one installment term is required",
        )

    total_amount = 0.0
    cleaned_installments = []

    # --------------------------------------------------------
    # Validate each term
    # --------------------------------------------------------

    for index, installment in enumerate(
        installments,
        start=1,
    ):

        if not isinstance(installment, dict):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid installment term {index}",
            )

        amount = installment.get("amount")

        if amount is None:
            raise HTTPException(
                status_code=400,
                detail=f"Amount is required for term {index}",
            )

        # ----------------------------------------------------
        # Convert amount
        # ----------------------------------------------------

        try:
            amount = float(amount)

        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid amount for term {index}",
            )

        # ----------------------------------------------------
        # Validate amount
        # ----------------------------------------------------

        if amount <= 0:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Amount for term {index} "
                    f"must be greater than 0"
                ),
            )

        # ----------------------------------------------------
        # Add amount to total
        # ----------------------------------------------------

        total_amount += amount

        cleaned_installments.append(
            {
                "term": index,
                "amount": amount,
            }
        )

    # --------------------------------------------------------
    # Total installment amount must equal course price
    # --------------------------------------------------------

    if round(total_amount, 2) != round(course_price, 2):

        raise HTTPException(
            status_code=400,
            detail=(
                f"Installment total ({total_amount:.2f}) "
                f"must equal course fee "
                f"({course_price:.2f})"
            ),
        )

    # --------------------------------------------------------
    # Return cleaned payment plan
    # --------------------------------------------------------

    return {
        "type": "installment",
        "frequency": frequency,
        "installments": cleaned_installments,
    }


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

    # --------------------------------------------------------
    # CHECK ROLE
    # --------------------------------------------------------

    if current_user.role != "branch_admin":
        raise HTTPException(
            status_code=403,
            detail="Branch admin access required",
        )

    # --------------------------------------------------------
    # CHECK USER STATUS
    # --------------------------------------------------------

    if current_user.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Branch admin account is inactive",
        )

    # --------------------------------------------------------
    # CHECK BRANCH ASSIGNMENT
    # --------------------------------------------------------

    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch",
        )

    # --------------------------------------------------------
    # CHECK BRANCH
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # CHECK BRANCH STATUS
    # --------------------------------------------------------

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

    # --------------------------------------------------------
    # COURSE DATES
    # --------------------------------------------------------

    start_date: date = Form(...),
    end_date: date = Form(...),

    # --------------------------------------------------------
    # CURRICULUM
    # --------------------------------------------------------

    curriculum: str = Form(...),

    # --------------------------------------------------------
    # PAYMENT PLAN
    # --------------------------------------------------------

    payment_type: str = Form(...),

    payment_plan: str = Form(
        '{"type":"full"}'
    ),

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

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
    # CONVERT CURRICULUM JSON STRING
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
    # BUILD PAYMENT PLAN
    # ========================================================

    payment_plan_data = build_payment_plan(
        payment_type=payment_type,
        payment_plan=payment_plan,
        course_price=price,
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

        # Automatically assign logged-in
        # branch admin's branch

        branch_id=branch_admin.branch_id,

        title=title,
        description=description,
        price=price,
        duration=duration,

        category=category,
        level=level,

        start_date=start_date,
        end_date=end_date,

        curriculum=curriculum_data,

        payment_plan=payment_plan_data,

        image=image_url,

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

    # --------------------------------------------------------
    # COURSE DATES
    # --------------------------------------------------------

    start_date: date = Form(...),
    end_date: date = Form(...),

    # --------------------------------------------------------
    # CURRICULUM
    # --------------------------------------------------------

    curriculum: str = Form(...),

    # --------------------------------------------------------
    # PAYMENT PLAN
    # --------------------------------------------------------

    payment_type: str = Form(...),

    payment_plan: str = Form(
        '{"type":"full"}'
    ),

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

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
    # CONVERT CURRICULUM
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
    # BUILD PAYMENT PLAN
    # ========================================================

    payment_plan_data = build_payment_plan(
        payment_type=payment_type,
        payment_plan=payment_plan,
        course_price=price,
    )

    # ========================================================
    # UPDATE TEXT FIELDS
    # ========================================================

    db_course.title = title

    db_course.description = description

    db_course.price = price

    db_course.duration = duration

    db_course.category = category

    db_course.level = level

    db_course.start_date = start_date

    db_course.end_date = end_date

    db_course.curriculum = curriculum_data

    db_course.payment_plan = payment_plan_data

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


# ============================================================
# ROUTER
# ============================================================

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
# PAYMENT PLAN HELPER
# ============================================================

def build_payment_plan(
    payment_type: str,
    payment_frequency: str,
    installment_terms: str,
    course_price: float,
):
    """
    Build and validate the payment plan.

    Payment type:
    - full
    - installment

    Payment frequency:
    - monthly
    - weekly

    Example installment_terms:

    [
        {
            "amount": 20000
        },
        {
            "amount": 15000
        },
        {
            "amount": 15000
        }
    ]

    The backend automatically converts this into:

    {
        "type": "installment",
        "frequency": "monthly",
        "installments": [
            {
                "term": 1,
                "amount": 20000
            },
            {
                "term": 2,
                "amount": 15000
            },
            {
                "term": 3,
                "amount": 15000
            }
        ]
    }
    """

    # ========================================================
    # VALIDATE PAYMENT TYPE
    # ========================================================

    if payment_type not in [
        "full",
        "installment",
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid payment type. "
                "Use full or installment"
            ),
        )

    # ========================================================
    # FULL PAYMENT
    # ========================================================

    if payment_type == "full":

        return {
            "type": "full"
        }

    # ========================================================
    # INSTALLMENT PAYMENT
    # ========================================================

    # --------------------------------------------------------
    # Validate frequency
    # --------------------------------------------------------

    if payment_frequency not in [
        "monthly",
        "weekly",
    ]:
        raise HTTPException(
            status_code=400,
            detail=(
                "Payment frequency must be "
                "monthly or weekly"
            ),
        )

    # --------------------------------------------------------
    # Parse installment terms JSON
    # --------------------------------------------------------

    try:

        installment_data = json.loads(
            installment_terms
        )

    except json.JSONDecodeError:

        raise HTTPException(
            status_code=400,
            detail="Invalid installment terms JSON",
        )

    # --------------------------------------------------------
    # Validate terms list
    # --------------------------------------------------------

    if (
        not isinstance(installment_data, list)
        or not installment_data
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one installment "
                "term is required"
            ),
        )

    total_amount = 0.0

    cleaned_installments = []

    # ========================================================
    # PROCESS EACH INSTALLMENT TERM
    # ========================================================

    for index, term in enumerate(
        installment_data,
        start=1,
    ):

        # ----------------------------------------------------
        # Validate object
        # ----------------------------------------------------

        if not isinstance(term, dict):

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid installment "
                    f"term {index}"
                ),
            )

        # ----------------------------------------------------
        # Get amount
        # ----------------------------------------------------

        amount = term.get("amount")

        if amount is None:

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Amount is required "
                    f"for term {index}"
                ),
            )

        # ----------------------------------------------------
        # Convert amount
        # ----------------------------------------------------

        try:

            amount = float(amount)

        except (
            TypeError,
            ValueError,
        ):

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid amount "
                    f"for term {index}"
                ),
            )

        # ----------------------------------------------------
        # Validate amount
        # ----------------------------------------------------

        if amount <= 0:

            raise HTTPException(
                status_code=400,
                detail=(
                    f"Amount for term {index} "
                    f"must be greater than 0"
                ),
            )

        # ----------------------------------------------------
        # Add to total
        # ----------------------------------------------------

        total_amount += amount

        # ----------------------------------------------------
        # Create cleaned term
        # ----------------------------------------------------

        cleaned_installments.append(
            {
                "term": index,
                "amount": amount,
            }
        )

    # ========================================================
    # VALIDATE TOTAL
    # ========================================================

    if round(total_amount, 2) != round(
        course_price,
        2,
    ):

        raise HTTPException(
            status_code=400,
            detail=(
                f"Installment total "
                f"({total_amount:.2f}) "
                f"must equal course fee "
                f"({course_price:.2f})"
            ),
        )

    # ========================================================
    # RETURN FINAL PAYMENT PLAN
    # ========================================================

    return {
        "type": "installment",
        "frequency": payment_frequency,
        "installments": cleaned_installments,
    }


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

    # ========================================================
    # CHECK ROLE
    # ========================================================

    if current_user.role != "branch_admin":

        raise HTTPException(
            status_code=403,
            detail="Branch admin access required",
        )

    # ========================================================
    # CHECK USER STATUS
    # ========================================================

    if current_user.status != "Active":

        raise HTTPException(
            status_code=403,
            detail="Branch admin account is inactive",
        )

    # ========================================================
    # CHECK BRANCH ASSIGNMENT
    # ========================================================

    if not current_user.branch_id:

        raise HTTPException(
            status_code=400,
            detail=(
                "Branch admin is not "
                "assigned to a branch"
            ),
        )

    # ========================================================
    # CHECK BRANCH
    # ========================================================

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

    # ========================================================
    # CHECK BRANCH STATUS
    # ========================================================

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

    # ========================================================
    # COURSE PERIOD
    # ========================================================

    start_date: date = Form(...),

    end_date: date = Form(...),

    # ========================================================
    # CURRICULUM
    # ========================================================

    curriculum: str = Form(...),

    # ========================================================
    # PAYMENT
    # ========================================================

    payment_type: str = Form(...),

    payment_frequency: str = Form(
        "monthly"
    ),

    installment_terms: str = Form(
        "[]"
    ),

    # ========================================================
    # IMAGE
    # ========================================================

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
    # BUILD PAYMENT PLAN
    # ========================================================

    payment_plan_data = build_payment_plan(
        payment_type=payment_type,
        payment_frequency=payment_frequency,
        installment_terms=installment_terms,
        course_price=price,
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

        # ----------------------------------------------------
        # BRANCH
        # ----------------------------------------------------

        branch_id=branch_admin.branch_id,

        # ----------------------------------------------------
        # COURSE INFORMATION
        # ----------------------------------------------------

        title=title,

        description=description,

        price=price,

        duration=duration,

        category=category,

        level=level,

        # ----------------------------------------------------
        # COURSE PERIOD
        # ----------------------------------------------------

        start_date=start_date,

        end_date=end_date,

        # ----------------------------------------------------
        # CURRICULUM
        # ----------------------------------------------------

        curriculum=curriculum_data,

        # ----------------------------------------------------
        # PAYMENT PLAN
        # ----------------------------------------------------

        payment_plan=payment_plan_data,

        # ----------------------------------------------------
        # IMAGE
        # ----------------------------------------------------

        image=image_url,

        # ----------------------------------------------------
        # STATUS
        # ----------------------------------------------------

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

    # ========================================================
    # COURSE PERIOD
    # ========================================================

    start_date: date = Form(...),

    end_date: date = Form(...),

    # ========================================================
    # CURRICULUM
    # ========================================================

    curriculum: str = Form(...),

    # ========================================================
    # PAYMENT
    # ========================================================

    payment_type: str = Form(...),

    payment_frequency: str = Form(
        "monthly"
    ),

    installment_terms: str = Form(
        "[]"
    ),

    # ========================================================
    # IMAGE
    # ========================================================

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
    # CONVERT CURRICULUM
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
    # BUILD PAYMENT PLAN
    # ========================================================

    payment_plan_data = build_payment_plan(
        payment_type=payment_type,
        payment_frequency=payment_frequency,
        installment_terms=installment_terms,
        course_price=price,
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
    # UPDATE PAYMENT PLAN
    # ========================================================

    db_course.payment_plan = payment_plan_data

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