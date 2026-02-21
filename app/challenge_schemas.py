"""Pydantic schemas and validators for the BlackRock challenge workflows."""

import math
from datetime import datetime, timezone
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DATETIME_ACCEPTED_FORMATS = (DATETIME_FORMAT, "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S")


def _normalize_datetime(value: datetime) -> datetime:
    """Normalize timestamps to UTC-naive values with second-level precision."""
    normalized = value
    if normalized.tzinfo is not None:
        normalized = normalized.astimezone(timezone.utc).replace(tzinfo=None)
    return normalized.replace(microsecond=0)


def _parse_datetime(value: Any) -> datetime:
    """Parse supported datetime formats into normalized `datetime` objects."""
    if isinstance(value, datetime):
        return _normalize_datetime(value)
    if not isinstance(value, str):
        raise ValueError("Datetime must be a string in format YYYY-MM-DD HH:mm:ss.")

    for fmt in DATETIME_ACCEPTED_FORMATS:
        try:
            return _normalize_datetime(datetime.strptime(value, fmt))
        except ValueError:
            continue

    # Swagger examples commonly use RFC3339/ISO-8601 date-times with fractions and timezone (e.g. "...Z").
    try:
        iso_candidate = value.replace("Z", "+00:00")
        return _normalize_datetime(datetime.fromisoformat(iso_candidate))
    except ValueError:
        pass

    raise ValueError("Invalid datetime format. Expected YYYY-MM-DD HH:mm:ss.")


def _parse_number(value: Any, *, field_name: str) -> float:
    """Parse and validate numeric inputs while rejecting bool/NaN/Infinity values."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a numeric value.")
    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        raise ValueError(f"{field_name} must be finite.")
    return numeric_value


class ChallengeBaseModel(BaseModel):
    """Base schema config: strict fields and stable datetime serialization."""
    model_config = ConfigDict(
        extra="forbid",
        json_encoders={datetime: lambda dt: dt.strftime(DATETIME_FORMAT)},
    )


class Expense(ChallengeBaseModel):
    """Incoming expense row used by `transactions:parse`."""
    timestamp: datetime = Field(validation_alias=AliasChoices("timestamp", "date"))
    amount: float = Field(..., ge=0, lt=500_000)

    @field_validator("timestamp", mode="before")
    @classmethod
    def parse_timestamp(cls, value: Any) -> datetime:
        return _parse_datetime(value)

    @field_validator("amount", mode="before")
    @classmethod
    def parse_amount(cls, value: Any) -> float:
        return _parse_number(value, field_name="amount")


class Transaction(ChallengeBaseModel):
    """Normalized transaction format shared across challenge APIs."""
    date: datetime = Field(validation_alias=AliasChoices("date", "timestamp"))
    amount: float = Field(..., ge=0, lt=500_000)
    ceiling: float = Field(..., ge=0)
    remanent: float = Field(..., ge=0)

    @field_validator("date", mode="before")
    @classmethod
    def parse_date(cls, value: Any) -> datetime:
        return _parse_datetime(value)

    @field_validator("amount", "ceiling", "remanent", mode="before")
    @classmethod
    def parse_numeric_fields(cls, value: Any, info) -> float:
        return _parse_number(value, field_name=info.field_name)


class InvalidTransaction(Transaction):
    """Transaction plus validation failure reason."""
    message: str


class ProcessedTransaction(Transaction):
    """Transaction including remanent after q/p temporal transformations."""
    effectiveRemanent: float = Field(..., ge=0)


class DateRange(ChallengeBaseModel):
    """Inclusive temporal range used by q/p/k rules."""
    start: datetime
    end: datetime

    @field_validator("start", "end", mode="before")
    @classmethod
    def parse_range_datetime(cls, value: Any) -> datetime:
        return _parse_datetime(value)

    @model_validator(mode="after")
    def validate_range(self) -> "DateRange":
        if self.start > self.end:
            raise ValueError("start must be less than or equal to end.")
        return self


class FixedPeriod(DateRange):
    fixed: float = Field(..., ge=0, lt=500_000)

    @field_validator("fixed", mode="before")
    @classmethod
    def parse_fixed(cls, value: Any) -> float:
        return _parse_number(value, field_name="fixed")


class ExtraPeriod(DateRange):
    extra: float = Field(..., ge=0, lt=500_000)

    @field_validator("extra", mode="before")
    @classmethod
    def parse_extra(cls, value: Any) -> float:
        return _parse_number(value, field_name="extra")


class TransactionParseRequest(ChallengeBaseModel):
    """Input payload for expense parsing into transaction records."""
    expenses: list[Expense] = Field(default_factory=list, max_length=1_000_000)
    roundMultiple: float = Field(default=100.0, gt=0, le=100_000)

    @field_validator("roundMultiple", mode="before")
    @classmethod
    def parse_round_multiple(cls, value: Any) -> float:
        return _parse_number(value, field_name="roundMultiple")


class TransactionParseResponse(ChallengeBaseModel):
    transactions: list[Transaction]
    transactionsTotalAmount: float
    transactionsTotalCeiling: float
    transactionsTotalRemanent: float


class TransactionValidateRequest(ChallengeBaseModel):
    """Input payload for transaction structural/business validation."""
    wage: float = Field(..., ge=0, lt=50_000_000)
    maxInvestmentAmount: float | None = Field(default=None, ge=0, le=500_000)
    transactions: list[Transaction] = Field(default_factory=list, max_length=1_000_000)

    @field_validator("wage", mode="before")
    @classmethod
    def parse_wage(cls, value: Any) -> float:
        return _parse_number(value, field_name="wage")

    @field_validator("maxInvestmentAmount", mode="before")
    @classmethod
    def parse_max_investment_amount(cls, value: Any) -> float | None:
        if value is None:
            return None
        return _parse_number(value, field_name="maxInvestmentAmount")


class TransactionValidateResponse(ChallengeBaseModel):
    valid: list[Transaction]
    invalid: list[InvalidTransaction]
    duplicates: list[InvalidTransaction]


class TransactionFilterRequest(ChallengeBaseModel):
    """Input payload for q/p transformation and k-window filtering."""
    q: list[FixedPeriod] = Field(default_factory=list, max_length=1_000_000)
    p: list[ExtraPeriod] = Field(default_factory=list, max_length=1_000_000)
    k: list[DateRange] = Field(default_factory=list, max_length=1_000_000)
    transactions: list[Transaction] = Field(default_factory=list, max_length=1_000_000)


class TransactionFilterResponse(ChallengeBaseModel):
    valid: list[ProcessedTransaction]
    invalid: list[InvalidTransaction]


class ReturnsRequest(ChallengeBaseModel):
    """Input payload for return calculators (`returns:nps`, `returns:index`)."""
    age: int = Field(..., ge=0, le=120)
    wage: float = Field(..., ge=0, lt=50_000_000)
    inflation: float = Field(..., ge=0, le=100)
    q: list[FixedPeriod] = Field(default_factory=list, max_length=1_000_000)
    p: list[ExtraPeriod] = Field(default_factory=list, max_length=1_000_000)
    k: list[DateRange] = Field(default_factory=list, max_length=1_000_000)
    transactions: list[Transaction] = Field(default_factory=list, max_length=1_000_000)

    @field_validator("wage", "inflation", mode="before")
    @classmethod
    def parse_returns_numeric(cls, value: Any, info) -> float:
        return _parse_number(value, field_name=info.field_name)


class SavingsByDate(ChallengeBaseModel):
    start: datetime
    end: datetime
    amount: float
    profits: float
    taxBenefit: float
    returnAmount: float

    @field_validator("start", "end", mode="before")
    @classmethod
    def parse_savings_datetime(cls, value: Any) -> datetime:
        return _parse_datetime(value)


class ReturnsResponse(ChallengeBaseModel):
    transactionsTotalAmount: float
    transactionsTotalCeiling: float
    savingsByDates: list[SavingsByDate]


class PerformanceResponse(ChallengeBaseModel):
    time: str
    memory: str
    threads: int
