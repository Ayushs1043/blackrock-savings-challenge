"""HTTP route layer for challenge, finance, and utility endpoints."""

from time import perf_counter

from fastapi import APIRouter

from app.challenge_schemas import (
    PerformanceResponse,
    ReturnsRequest,
    ReturnsResponse,
    TransactionFilterRequest,
    TransactionFilterResponse,
    TransactionParseRequest,
    TransactionParseResponse,
    TransactionValidateRequest,
    TransactionValidateResponse,
)
from app.schemas import (
    HealthResponse,
    RetirementProjectionRequest,
    RetirementProjectionResponse,
    RoundupProjectionRequest,
    RoundupProjectionResponse,
    SolveRequest,
    SolveResponse,
)
from app.services.challenge import (
    build_performance_report,
    calculate_index_returns,
    calculate_nps_returns,
    filter_transactions,
    parse_transactions,
    validate_transactions,
)
from app.services.finance import project_retirement_corpus, project_roundup_corpus
from app.services.solver import solve_request

router = APIRouter()


@router.get("/", tags=["meta"])
def root() -> dict[str, str]:
    """Return API banner metadata and docs path."""
    return {"message": "BlackRock Hackathon API", "docs": "/docs"}


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Return service health status."""
    return HealthResponse()


@router.post(
    "/solve",
    response_model=SolveResponse,
    tags=["solver"],
)
def solve(req: SolveRequest) -> SolveResponse:
    """Execute non-challenge utility operations."""
    return solve_request(req)


@router.post(
    "/api/v1/retirement/projection",
    response_model=RetirementProjectionResponse,
    tags=["finance"],
)
def retirement_projection(
    req: RetirementProjectionRequest,
) -> RetirementProjectionResponse:
    """Project long-term retirement corpus from monthly investing inputs."""
    return project_retirement_corpus(req)


@router.post(
    "/api/v1/retirement/roundup",
    response_model=RoundupProjectionResponse,
    tags=["finance"],
)
def roundup_projection(req: RoundupProjectionRequest) -> RoundupProjectionResponse:
    """Estimate corpus growth using round-up based micro-investments."""
    return project_roundup_corpus(req)


@router.post(
    "/blackrock/challenge/v1/transactions:parse",
    response_model=TransactionParseResponse,
    tags=["blackrock-challenge"],
)
def transaction_builder(req: TransactionParseRequest) -> TransactionParseResponse:
    """Parse expense rows into normalized transaction entries."""
    return parse_transactions(req)


@router.post(
    "/blackrock/challenge/v1/transactions:validator",
    response_model=TransactionValidateResponse,
    tags=["blackrock-challenge"],
)
def transaction_validator(req: TransactionValidateRequest) -> TransactionValidateResponse:
    """Validate transaction consistency, duplicates, and investment constraints."""
    return validate_transactions(req)


@router.post(
    "/blackrock/challenge/v1/transactions:filter",
    response_model=TransactionFilterResponse,
    tags=["blackrock-challenge"],
)
def temporal_constraints_validator(req: TransactionFilterRequest) -> TransactionFilterResponse:
    """Apply q/p temporal rules and filter transactions by k windows."""
    return filter_transactions(req)


@router.post(
    "/blackrock/challenge/v1/returns:nps",
    response_model=ReturnsResponse,
    tags=["blackrock-challenge"],
)
def returns_nps(req: ReturnsRequest) -> ReturnsResponse:
    """Calculate inflation-adjusted returns using the NPS annual rate and tax benefit."""
    return calculate_nps_returns(req)


@router.post(
    "/blackrock/challenge/v1/returns:index",
    response_model=ReturnsResponse,
    tags=["blackrock-challenge"],
)
def returns_index(req: ReturnsRequest) -> ReturnsResponse:
    """Calculate inflation-adjusted returns using the index annual rate."""
    return calculate_index_returns(req)


@router.get(
    "/blackrock/challenge/v1/performance",
    response_model=PerformanceResponse,
    tags=["blackrock-challenge"],
)
def performance_report() -> PerformanceResponse:
    """Expose simple runtime performance metrics for the current process."""
    start_time = perf_counter()
    return build_performance_report(start_time)
