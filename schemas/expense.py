from pydantic import BaseModel, Field, field_validator


class BranchExpenseCreate(BaseModel):
    item: str = Field(min_length=1, max_length=255)
    cost: float = Field(ge=0.01, allow_inf_nan=False)

    @field_validator("item")
    @classmethod
    def validate_item(cls, value: str) -> str:
        item = value.strip()
        if not item:
            raise ValueError("Expense item cannot be blank")
        return item
