from datetime import date, datetime
from pydantic import BaseModel, EmailStr, Field


class EnrollmentInstallmentDetail(BaseModel):
    installment_id: int
    installment_number: int
    amount: float
    paid_amount: float
    remaining_amount: float
    is_due: bool
    due_date: date
    status: str
    paid_date: date | None = None


class EnrollmentInstallmentUpdate(BaseModel):
    installment_number: int = Field(ge=1)
    amount: float = Field(gt=0)
    due_date: date


class EnrollmentPaymentDetail(BaseModel):
    id: int
    enrollment_id: int
    installment_id: int | None
    installment_number: int
    amount: float
    cash_amount: float
    upi_amount: float
    payment_method: str
    payment_date: date
    status: str

    class Config:
        from_attributes = True


class BranchAdminEnrollmentUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    parent_name: str | None = None
    parent_phone: str | None = None
    highest_qualification: str | None = None
    address: str | None = None
    installments: list[EnrollmentInstallmentUpdate] | None = None


# ==========================================
# STUDENT ENROLLMENT RESPONSE
# ==========================================

class EnrollmentResponse(BaseModel):
    id: int
    user_id: int
    course_id: int
    branch_id: int

    name: str
    email: str
    phone: str

    parent_name: str | None = None
    parent_phone: str | None = None

    highest_qualification: str | None = None
    address: str | None = None

    course_title: str
    course_image: str | None = None
    course_duration: str

    total_fee: float
    total_paid: float = 0
    balance_amount: float = 0
    installment_count: int = 0
    paid_installment_count: int = 0
    remaining_installment_count: int = 0
    due_installment_count: int = 0
    installments: list[EnrollmentInstallmentDetail] = Field(default_factory=list)

    # Payment status
    status: str

    # Branch approval status
    course_status: str
    branch_approval_status: str = "pending"
    super_admin_approval_status: str = "pending"

    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None

    created_at: datetime

    class Config:
        from_attributes = True


# ==========================================
# BRANCH ADMIN ENROLLMENT RESPONSE
# ==========================================

class AdminEnrollmentResponse(BaseModel):
    enrollment_id: int
    user_id: int
    course_id: int
    branch_id: int

    name: str
    email: str
    phone: str

    parent_name: str | None = None
    parent_phone: str | None = None

    highest_qualification: str | None = None
    address: str | None = None

    course_title: str
    course_image: str | None = None
    course_duration: str

    total_fee: float
    total_paid: float = 0
    balance_amount: float = 0
    installment_count: int = 0
    paid_installment_count: int = 0
    remaining_installment_count: int = 0
    due_installment_count: int = 0
    installments: list[EnrollmentInstallmentDetail] = Field(default_factory=list)
    payments: list[EnrollmentPaymentDetail] = Field(default_factory=list)

    # Payment status
    status: str

    # Branch approval status
    course_status: str
    branch_approval_status: str = "pending"
    super_admin_approval_status: str = "pending"

    razorpay_order_id: str | None = None
    razorpay_payment_id: str | None = None

    created_at: datetime