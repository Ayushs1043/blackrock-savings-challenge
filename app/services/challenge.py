import heapq
import math
import resource
import threading
import time
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from datetime import datetime

from app.challenge_schemas import (
    DateRange,
    ExtraPeriod,
    FixedPeriod,
    InvalidTransaction,
    PerformanceResponse,
    ProcessedTransaction,
    ReturnsRequest,
    ReturnsResponse,
    SavingsByDate,
    Transaction,
    TransactionFilterRequest,
    TransactionFilterResponse,
    TransactionParseRequest,
    TransactionParseResponse,
    TransactionValidateRequest,
    TransactionValidateResponse,
)

NPS_RATE = 0.0711
INDEX_RATE = 0.1449
NPS_MAX_DEDUCTION = 200_000.0
NPS_DEDUCTION_INCOME_RATIO = 0.10
ROUNDING_BASE = 100.0
EPSILON = 1e-9


def _round2(value: float) -> float:
    return round(value + EPSILON, 2)


def _is_multiple_of_100(value: float) -> bool:
    remainder = math.fmod(value, ROUNDING_BASE)
    return abs(remainder) < EPSILON or abs(remainder - ROUNDING_BASE) < EPSILON


def _invalid_from_transaction(transaction: Transaction, message: str) -> InvalidTransaction:
    payload = transaction.model_dump(include={"date", "amount", "ceiling", "remanent"})
    payload["message"] = message
    return InvalidTransaction(**payload)


def _split_transactions(
    transactions: Sequence[Transaction],
    max_investment_amount: float | None = None,
) -> tuple[list[Transaction], list[InvalidTransaction], list[InvalidTransaction]]:
    seen_dates: set[datetime] = set()
    valid: list[Transaction] = []
    invalid: list[InvalidTransaction] = []
    duplicates: list[InvalidTransaction] = []

    for transaction in transactions:
        if transaction.date in seen_dates:
            duplicates.append(
                _invalid_from_transaction(transaction, "Duplicate transaction date.")
            )
            continue

        seen_dates.add(transaction.date)

        if transaction.ceiling + EPSILON < transaction.amount:
            invalid.append(
                _invalid_from_transaction(
                    transaction,
                    "ceiling must be greater than or equal to amount.",
                )
            )
            continue

        if not _is_multiple_of_100(transaction.ceiling):
            invalid.append(
                _invalid_from_transaction(
                    transaction,
                    "ceiling must be a multiple of 100.",
                )
            )
            continue

        expected_remanent = transaction.ceiling - transaction.amount
        if abs(expected_remanent - transaction.remanent) > 0.01:
            invalid.append(
                _invalid_from_transaction(
                    transaction,
                    "remanent must be equal to ceiling - amount.",
                )
            )
            continue

        if max_investment_amount is not None and transaction.remanent > max_investment_amount:
            invalid.append(
                _invalid_from_transaction(
                    transaction,
                    "remanent exceeds maxInvestmentAmount.",
                )
            )
            continue

        valid.append(transaction)

    return valid, invalid, duplicates


def parse_transactions(request: TransactionParseRequest) -> TransactionParseResponse:
    transactions: list[Transaction] = []
    total_amount = 0.0
    total_ceiling = 0.0
    total_remanent = 0.0

    for expense in request.expenses:
        ceiling = math.ceil(expense.amount / request.roundMultiple) * request.roundMultiple
        remanent = max(0.0, ceiling - expense.amount)

        transaction = Transaction(
            date=expense.timestamp,
            amount=_round2(expense.amount),
            ceiling=_round2(ceiling),
            remanent=_round2(remanent),
        )

        transactions.append(transaction)
        total_amount += transaction.amount
        total_ceiling += transaction.ceiling
        total_remanent += transaction.remanent

    return TransactionParseResponse(
        transactions=transactions,
        transactionsTotalAmount=_round2(total_amount),
        transactionsTotalCeiling=_round2(total_ceiling),
        transactionsTotalRemanent=_round2(total_remanent),
    )


def validate_transactions(request: TransactionValidateRequest) -> TransactionValidateResponse:
    valid, invalid, duplicates = _split_transactions(
        request.transactions,
        request.maxInvestmentAmount,
    )
    return TransactionValidateResponse(valid=valid, invalid=invalid, duplicates=duplicates)


def _apply_temporal_rules(
    transactions: Sequence[Transaction],
    q_periods: Sequence[FixedPeriod],
    p_periods: Sequence[ExtraPeriod],
) -> list[ProcessedTransaction]:
    indexed_transactions = sorted(
        enumerate(transactions), key=lambda entry: entry[1].date
    )
    sorted_q_with_index = sorted(
        enumerate(q_periods),
        key=lambda pair: pair[1].start,
    )
    sorted_p = sorted(p_periods, key=lambda period: (period.start, period.end))

    q_heap: list[tuple[float, int, datetime, float]] = []
    p_heap: list[tuple[datetime, float]] = []
    active_p_extra = 0.0

    q_index = 0
    p_index = 0

    results: list[ProcessedTransaction | None] = [None] * len(transactions)

    for original_index, transaction in indexed_transactions:
        current_time = transaction.date

        while (
            q_index < len(sorted_q_with_index)
            and sorted_q_with_index[q_index][1].start <= current_time
        ):
            input_index, period = sorted_q_with_index[q_index]
            start_key = period.start.timestamp()
            heapq.heappush(
                q_heap,
                (-start_key, input_index, period.end, period.fixed),
            )
            q_index += 1

        while q_heap and q_heap[0][2] < current_time:
            heapq.heappop(q_heap)

        while p_index < len(sorted_p) and sorted_p[p_index].start <= current_time:
            period = sorted_p[p_index]
            heapq.heappush(p_heap, (period.end, period.extra))
            active_p_extra += period.extra
            p_index += 1

        while p_heap and p_heap[0][0] < current_time:
            _, extra = heapq.heappop(p_heap)
            active_p_extra -= extra

        effective_remanent = transaction.remanent
        if q_heap:
            effective_remanent = q_heap[0][3]
        effective_remanent += active_p_extra

        results[original_index] = ProcessedTransaction(
            date=transaction.date,
            amount=transaction.amount,
            ceiling=transaction.ceiling,
            remanent=transaction.remanent,
            effectiveRemanent=_round2(max(0.0, effective_remanent)),
        )

    return [entry for entry in results if entry is not None]


def _merge_ranges(ranges: Sequence[DateRange]) -> list[DateRange]:
    if not ranges:
        return []

    sorted_ranges = sorted(ranges, key=lambda item: (item.start, item.end))
    merged: list[DateRange] = [DateRange(start=sorted_ranges[0].start, end=sorted_ranges[0].end)]

    for current in sorted_ranges[1:]:
        last = merged[-1]
        if current.start <= last.end:
            if current.end > last.end:
                merged[-1] = DateRange(start=last.start, end=current.end)
            continue
        merged.append(DateRange(start=current.start, end=current.end))

    return merged


def filter_transactions(request: TransactionFilterRequest) -> TransactionFilterResponse:
    valid, invalid, duplicates = _split_transactions(request.transactions)
    processed = _apply_temporal_rules(valid, request.q, request.p)

    temporal_invalid = list(invalid) + list(duplicates)
    if not request.k:
        return TransactionFilterResponse(valid=processed, invalid=temporal_invalid)

    merged_ranges = _merge_ranges(request.k)
    indexed_processed = sorted(enumerate(processed), key=lambda entry: entry[1].date)

    in_range_by_index = [False] * len(processed)
    range_index = 0
    for process_index, transaction in indexed_processed:
        while (
            range_index < len(merged_ranges)
            and merged_ranges[range_index].end < transaction.date
        ):
            range_index += 1

        in_range = (
            range_index < len(merged_ranges)
            and merged_ranges[range_index].start <= transaction.date <= merged_ranges[range_index].end
        )
        in_range_by_index[process_index] = in_range

    final_valid: list[ProcessedTransaction] = []
    for idx, transaction in enumerate(processed):
        if in_range_by_index[idx]:
            final_valid.append(transaction)
        else:
            temporal_invalid.append(
                _invalid_from_transaction(
                    transaction,
                    "Transaction outside provided k date ranges.",
                )
            )

    return TransactionFilterResponse(valid=final_valid, invalid=temporal_invalid)


def _calculate_tax(income: float) -> float:
    taxable_income = max(0.0, income)
    if taxable_income <= 700_000:
        return 0.0

    tax = 0.0
    if taxable_income <= 1_000_000:
        return (taxable_income - 700_000) * 0.10
    tax += 300_000 * 0.10

    if taxable_income <= 1_200_000:
        return tax + (taxable_income - 1_000_000) * 0.15
    tax += 200_000 * 0.15

    if taxable_income <= 1_500_000:
        return tax + (taxable_income - 1_200_000) * 0.20
    tax += 300_000 * 0.20

    return tax + (taxable_income - 1_500_000) * 0.30


def _calculate_nps_tax_benefit(monthly_wage: float, invested_amount: float) -> float:
    annual_income = monthly_wage * 12.0
    deduction_cap = annual_income * NPS_DEDUCTION_INCOME_RATIO
    deduction = min(invested_amount, deduction_cap, NPS_MAX_DEDUCTION)
    tax_before = _calculate_tax(annual_income)
    tax_after = _calculate_tax(annual_income - deduction)
    return max(0.0, tax_before - tax_after)


def _investment_horizon_years(age: int) -> int:
    if age < 60:
        return 60 - age
    return 5


def _real_return(amount: float, annual_rate: float, inflation: float, years: int) -> float:
    nominal_amount = amount * ((1 + annual_rate) ** years)
    inflation_factor = (1 + inflation / 100.0) ** years
    if inflation_factor == 0:
        return nominal_amount
    return nominal_amount / inflation_factor


def _sum_by_date_range(
    transactions: Sequence[ProcessedTransaction],
    date_ranges: Sequence[DateRange],
) -> list[tuple[DateRange, float]]:
    if not date_ranges:
        return []

    sorted_transactions = sorted(transactions, key=lambda item: item.date)
    transaction_dates = [item.date for item in sorted_transactions]

    prefix: list[float] = [0.0]
    for transaction in sorted_transactions:
        prefix.append(prefix[-1] + transaction.effectiveRemanent)

    sums: list[tuple[DateRange, float]] = []
    for date_range in date_ranges:
        left_index = bisect_left(transaction_dates, date_range.start)
        right_index = bisect_right(transaction_dates, date_range.end)
        amount = prefix[right_index] - prefix[left_index]
        sums.append((date_range, amount))

    return sums


def _calculate_returns(request: ReturnsRequest, annual_rate: float, is_nps: bool) -> ReturnsResponse:
    valid_transactions, _, _ = _split_transactions(request.transactions)
    processed = _apply_temporal_rules(valid_transactions, request.q, request.p)
    grouped_amounts = _sum_by_date_range(processed, request.k)
    years = _investment_horizon_years(request.age)

    savings_by_dates: list[SavingsByDate] = []
    for date_range, amount in grouped_amounts:
        amount = _round2(amount)
        real_return = _round2(_real_return(amount, annual_rate, request.inflation, years))
        profits = _round2(real_return - amount)
        tax_benefit = (
            _round2(_calculate_nps_tax_benefit(request.wage, amount)) if is_nps else 0.0
        )

        savings_by_dates.append(
            SavingsByDate(
                start=date_range.start,
                end=date_range.end,
                amount=amount,
                profits=profits,
                taxBenefit=tax_benefit,
                returnAmount=real_return,
            )
        )

    transactions_total_amount = _round2(sum(item.amount for item in valid_transactions))
    transactions_total_ceiling = _round2(sum(item.ceiling for item in valid_transactions))

    return ReturnsResponse(
        transactionsTotalAmount=transactions_total_amount,
        transactionsTotalCeiling=transactions_total_ceiling,
        savingsByDates=savings_by_dates,
    )


def calculate_nps_returns(request: ReturnsRequest) -> ReturnsResponse:
    return _calculate_returns(request, annual_rate=NPS_RATE, is_nps=True)


def calculate_index_returns(request: ReturnsRequest) -> ReturnsResponse:
    return _calculate_returns(request, annual_rate=INDEX_RATE, is_nps=False)


def build_performance_report(start_time: float | None = None) -> PerformanceResponse:
    elapsed_ms = 0.0
    if start_time is not None:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

    memory_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    memory_mb = memory_kb / 1024.0

    return PerformanceResponse(
        time=f"{elapsed_ms:.3f} ms",
        memory=f"{memory_mb:.2f} MB",
        threads=threading.active_count(),
    )
