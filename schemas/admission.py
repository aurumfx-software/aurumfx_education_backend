from datetime import date

from pydantic import BaseModel, Field


# ============================================================
# BRANCH ADMIN - REGISTER STUDENT
# ============================================================

class BranchAdmissionCreate(BaseModel):

    # STUDENT DETAILS
    name: str
    phone: str
    email: str

    # GUARDIAN DETAILS
    parent_name: str
    parent_phone: str

    # STUDENT PROFILE
    highest_qualification: str
    address: str

    # PASSWORD
    password: str

    # COURSE
    course_id: int

    # PAYMENT
    payment_status: str = "not_received"

    cash_amount: float = Field(
        default=0,
        ge=0
    )

    upi_amount: float = Field(
        default=0,
        ge=0
    )

    payment_date: date | None = None


# ============================================================
# ADD FUTURE PAYMENT
# ============================================================

class AdmissionPaymentCreate(BaseModel):

    cash_amount: float = Field(
        default=0,
        ge=0
    )

    upi_amount: float = Field(
        default=0,
        ge=0
    )

    payment_date: date | None = None


# ============================================================
# INSTALLMENT RESPONSE
# ============================================================

class InstallmentResponse(BaseModel):

    id: int

    installment_number: int

    amount: float

    paid_amount: float

    due_date: date

    status: str

    paid_date: date | None

    cash_amount: float

    upi_amount: float

    class Config:
        from_attributes = True


# ============================================================
# PAYMENT RESPONSE
# ============================================================

class AdmissionPaymentResponse(BaseModel):

    id: int

    enrollment_id: int

    installment_id: int | None

    installment_number: int

    amount: float

    cash_amount: float

    upi_amount: float

    payment_date: date

    status: str

    class Config:
        from_attributes = True


# ============================================================
# ADMISSION RESPONSE
# ============================================================
class BranchAdmissionResponse(BaseModel):
    enrollment_id: int
    user_id: int

    name: str
    phone: str
    email: str

    parent_name: str
    parent_phone: str
    highest_qualification: str
    address: str

    course_id: int
    course_title: str

    start_date: date | None
    end_date: date | None

    total_fee: float

    installment_schedule: str | None
    installment_count: int

    admission_date: date | None

    total_paid: float
    balance_amount: float

    terms_paid: int
    pending_terms: int

    status: str

    payments: list[AdmissionPaymentResponse]