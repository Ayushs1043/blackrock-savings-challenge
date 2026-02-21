from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class Operation(str, Enum):
    reverse_text = "reverse_text"
    retirement_projection = "retirement_projection"
    roundup_projection = "roundup_projection"


class HealthResponse(BaseModel):
    status: str = "ok"


class RetirementProjectionRequest(BaseModel):
    current_age: int = Field(..., ge=18, le=80)
    retirement_age: int = Field(..., ge=19, le=90)
    monthly_investment: float = Field(..., ge=0, le=10_000_000)
    annual_return_rate: float = Field(..., ge=0, le=30)
    current_corpus: float = Field(default=0, ge=0, le=1_000_000_000)
    inflation_rate: float = Field(default=6, ge=0, le=20)

    @model_validator(mode="after")
    def validate_age_order(self) -> "RetirementProjectionRequest":
        if self.retirement_age <= self.current_age:
            raise ValueError("retirement_age must be greater than current_age.")
        return self


class RetirementProjectionResponse(BaseModel):
    years_to_retirement: int
    monthly_investment: float
    annual_return_rate: float
    inflation_rate: float
    projected_corpus_nominal: float
    projected_corpus_real: float


class RoundupProjectionRequest(BaseModel):
    monthly_expenses: list[float] = Field(..., min_length=1, max_length=5_000)
    roundup_base: float = Field(default=100, gt=0, le=1_000)
    annual_return_rate: float = Field(default=12, ge=0, le=30)
    years: int = Field(default=20, ge=1, le=60)
    inflation_rate: float = Field(default=6, ge=0, le=20)

    @model_validator(mode="after")
    def validate_expenses(self) -> "RoundupProjectionRequest":
        if any(expense <= 0 for expense in self.monthly_expenses):
            raise ValueError("monthly_expenses must contain only values greater than 0.")
        return self


class RoundupProjectionResponse(BaseModel):
    monthly_roundup_investment: float
    annual_return_rate: float
    inflation_rate: float
    years: int
    projected_corpus_nominal: float
    projected_corpus_real: float


class SolveRequest(BaseModel):
    operation: Operation = Field(default=Operation.reverse_text)
    text: str | None = Field(default=None, min_length=1, max_length=20_000)
    retirement: RetirementProjectionRequest | None = None
    roundup: RoundupProjectionRequest | None = None

    @model_validator(mode="after")
    def validate_payload(self) -> "SolveRequest":
        if self.operation == Operation.reverse_text and self.text is None:
            raise ValueError("text is required when operation is reverse_text.")
        if self.operation == Operation.retirement_projection and self.retirement is None:
            raise ValueError("retirement is required when operation is retirement_projection.")
        if self.operation == Operation.roundup_projection and self.roundup is None:
            raise ValueError("roundup is required when operation is roundup_projection.")
        return self


class SolveResponse(BaseModel):
    operation: Operation
    result: dict[str, Any] | str

