from math import ceil

from app.schemas import (
    RetirementProjectionRequest,
    RetirementProjectionResponse,
    RoundupProjectionRequest,
    RoundupProjectionResponse,
)


def _future_value_of_monthly_investment(
    monthly_investment: float,
    monthly_rate: float,
    months: int,
) -> float:
    if months <= 0:
        return 0.0

    if monthly_rate == 0:
        return monthly_investment * months

    growth_factor = (1 + monthly_rate) ** months
    return monthly_investment * ((growth_factor - 1) / monthly_rate)


def _future_value_of_lumpsum(principal: float, monthly_rate: float, months: int) -> float:
    if months <= 0:
        return principal
    return principal * ((1 + monthly_rate) ** months)


def _adjust_for_inflation(value: float, annual_inflation_rate: float, years: int) -> float:
    inflation_factor = (1 + (annual_inflation_rate / 100.0)) ** years
    if inflation_factor == 0:
        return value
    return value / inflation_factor


def project_retirement_corpus(
    request: RetirementProjectionRequest,
) -> RetirementProjectionResponse:
    years_to_retirement = request.retirement_age - request.current_age
    months = years_to_retirement * 12
    monthly_rate = request.annual_return_rate / 100.0 / 12.0

    future_current_corpus = _future_value_of_lumpsum(
        request.current_corpus, monthly_rate, months
    )
    future_monthly_investments = _future_value_of_monthly_investment(
        request.monthly_investment, monthly_rate, months
    )

    nominal = future_current_corpus + future_monthly_investments
    real = _adjust_for_inflation(nominal, request.inflation_rate, years_to_retirement)

    return RetirementProjectionResponse(
        years_to_retirement=years_to_retirement,
        monthly_investment=request.monthly_investment,
        annual_return_rate=request.annual_return_rate,
        inflation_rate=request.inflation_rate,
        projected_corpus_nominal=round(nominal, 2),
        projected_corpus_real=round(real, 2),
    )


def _round_up_amount(value: float, base: float) -> float:
    return ceil(value / base) * base


def project_roundup_corpus(request: RoundupProjectionRequest) -> RoundupProjectionResponse:
    monthly_roundup_investment = sum(
        _round_up_amount(expense, request.roundup_base) - expense
        for expense in request.monthly_expenses
    )
    monthly_rate = request.annual_return_rate / 100.0 / 12.0
    months = request.years * 12

    nominal = _future_value_of_monthly_investment(
        monthly_roundup_investment, monthly_rate, months
    )
    real = _adjust_for_inflation(nominal, request.inflation_rate, request.years)

    return RoundupProjectionResponse(
        monthly_roundup_investment=round(monthly_roundup_investment, 2),
        annual_return_rate=request.annual_return_rate,
        inflation_rate=request.inflation_rate,
        years=request.years,
        projected_corpus_nominal=round(nominal, 2),
        projected_corpus_real=round(real, 2),
    )

