# Test type: API matrix tests (positive, negative, edge, stress, fuzz).
# Validation: Verifies deterministic challenge behavior, interval rules, error handling, and performance stability.
# Command: pytest -q test/test_challenge_matrix.py

import math
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app

CHALLENGE_BASE = "/blackrock/challenge/v1"
VALIDATION_STATUS = 422
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
# Keep heavy tests disabled by default for local/CI stability.
RUN_STRESS = True
RUN_FUZZ = True
INDEX_RATE = 0.1449
NPS_RATE = 0.0711


def assert_json_response(response, status_code=200):
    assert response.status_code == status_code
    assert response.headers["content-type"].startswith("application/json")


def sample_expenses():
    return [
        {"timestamp": "2026-01-05 10:00:00", "amount": 1519.0},
        {"timestamp": "2026-01-15 10:00:00", "amount": 1499.0},
        {"timestamp": "2026-01-20 10:00:00", "amount": 1201.0},
    ]


def sample_transactions():
    return [
        {"date": "2026-01-05 10:00:00", "amount": 1519.0, "ceiling": 1600.0, "remanent": 81.0},
        {"date": "2026-01-15 10:00:00", "amount": 1499.0, "ceiling": 1500.0, "remanent": 1.0},
        {"date": "2026-01-20 10:00:00", "amount": 1201.0, "ceiling": 1300.0, "remanent": 99.0},
    ]


def round2(value: float) -> float:
    return round(value + 1e-9, 2)


def calc_tax(annual_income: float) -> float:
    income = max(0.0, annual_income)
    if income <= 700_000:
        return 0.0

    tax = 0.0
    if income <= 1_000_000:
        return (income - 700_000) * 0.10
    tax += 300_000 * 0.10

    if income <= 1_200_000:
        return tax + (income - 1_000_000) * 0.15
    tax += 200_000 * 0.15

    if income <= 1_500_000:
        return tax + (income - 1_200_000) * 0.20
    tax += 300_000 * 0.20

    return tax + (income - 1_500_000) * 0.30


def nps_tax_benefit(monthly_wage: float, invested: float) -> float:
    annual_income = monthly_wage * 12.0
    deduction = min(invested, annual_income * 0.10, 200_000.0)
    return round2(calc_tax(annual_income) - calc_tax(annual_income - deduction))


def compute_effective_remanent(tx, q_periods, p_periods):
    tx_time = datetime.strptime(tx["date"], "%Y-%m-%d %H:%M:%S")
    base = tx["remanent"]

    q_matches = []
    for index, period in enumerate(q_periods):
        start = datetime.strptime(period["start"], "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(period["end"], "%Y-%m-%d %H:%M:%S")
        if start <= tx_time <= end:
            q_matches.append((start, index, period["fixed"]))

    if q_matches:
        best = max(q_matches, key=lambda item: (item[0], -item[1]))
        base = best[2]

    p_extra = 0.0
    for period in p_periods:
        start = datetime.strptime(period["start"], "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(period["end"], "%Y-%m-%d %H:%M:%S")
        if start <= tx_time <= end:
            p_extra += period["extra"]

    return round2(base + p_extra)


def parse_transactions(client, expenses):
    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json={"expenses": expenses})
    assert_json_response(response, 200)
    return response.json()["transactions"]


def test_parse_basic_rounding(client):
    transactions = parse_transactions(
        client, [{"timestamp": "2026-01-01 10:00:00", "amount": 1519}]
    )
    assert transactions[0]["ceiling"] == 1600.0
    assert transactions[0]["remanent"] == 81.0


def test_parse_exact_multiple(client):
    transactions = parse_transactions(
        client, [{"timestamp": "2026-01-01 10:00:00", "amount": 1500}]
    )
    assert transactions[0]["ceiling"] == 1500.0
    assert transactions[0]["remanent"] == 0.0


def test_parse_smallest_values(client):
    payload = {
        "expenses": [
            {"timestamp": "2026-01-01 10:00:00", "amount": 0},
            {"timestamp": "2026-01-01 10:01:00", "amount": 1},
            {"timestamp": "2026-01-01 10:02:00", "amount": 99},
            {"timestamp": "2026-01-01 10:03:00", "amount": 100},
        ]
    }
    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    assert_json_response(response, 200)
    remanents = [item["remanent"] for item in response.json()["transactions"]]
    assert remanents == [0.0, 99.0, 1.0, 0.0]


def test_parse_unordered_dates_set_equivalence(client):
    payload = {
        "expenses": [
            {"timestamp": "2026-01-05 10:00:00", "amount": 251},
            {"timestamp": "2026-01-01 10:00:00", "amount": 111},
            {"timestamp": "2026-01-03 10:00:00", "amount": 444},
        ]
    }
    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    assert_json_response(response, 200)
    actual = {(t["date"], t["ceiling"], t["remanent"]) for t in response.json()["transactions"]}
    expected = {
        ("2026-01-05 10:00:00", 300.0, 49.0),
        ("2026-01-01 10:00:00", 200.0, 89.0),
        ("2026-01-03 10:00:00", 500.0, 56.0),
    }
    assert actual == expected


def test_parse_accepts_swagger_iso_timestamp(client):
    payload = {"expenses": [{"timestamp": "2026-02-21T08:11:19.871Z", "amount": 499999}]}
    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    assert_json_response(response, 200)
    tx = response.json()["transactions"][0]
    assert tx["date"] == "2026-02-21 08:11:19"


@pytest.mark.parametrize(
    "payload",
    [
        {"expenses": [{"amount": 100}]},
        {"expenses": [{"timestamp": "2026-01-01 10:00:00"}]},
    ],
)
def test_parse_missing_required_fields(client, payload):
    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    assert_json_response(response, VALIDATION_STATUS)
    assert response.json()["error"] == "validation_error"


@pytest.mark.parametrize("bad_date", ["2026/01/01", "not-a-date"])
def test_parse_bad_date(client, bad_date):
    payload = {"expenses": [{"timestamp": bad_date, "amount": 100}]}
    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    assert_json_response(response, VALIDATION_STATUS)


@pytest.mark.parametrize("bad_amount", ["1000", None, {}, []])
def test_parse_non_numeric_amount(client, bad_amount):
    payload = {"expenses": [{"timestamp": "2026-01-01 10:00:00", "amount": bad_amount}]}
    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    assert_json_response(response, VALIDATION_STATUS)


def test_parse_negative_amount_rejected(client):
    payload = {"expenses": [{"timestamp": "2026-01-01 10:00:00", "amount": -5}]}
    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    assert_json_response(response, VALIDATION_STATUS)


def test_parse_many_decimals_policy(client):
    payload = {"expenses": [{"timestamp": "2026-01-01 10:00:00", "amount": 12.3456789}]}
    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    assert_json_response(response, 200)
    tx = response.json()["transactions"][0]
    assert tx["amount"] == 12.35
    assert tx["ceiling"] == 100.0
    assert tx["remanent"] == 87.65


def test_parse_large_supported_amount(client):
    payload = {"expenses": [{"timestamp": "2026-01-01 10:00:00", "amount": 499999.99}]}
    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    assert_json_response(response, 200)
    tx = response.json()["transactions"][0]
    assert tx["ceiling"] == 500000.0
    assert tx["remanent"] == 0.01


@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_parse_nan_and_inf_rejected(client, token):
    body = f'{{"expenses":[{{"timestamp":"2026-01-01 10:00:00","amount":{token}}}]}}'
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:parse",
        content=body.encode(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code in (400, VALIDATION_STATUS)


def test_parse_duplicate_timestamps_allowed_before_validator(client):
    payload = {
        "expenses": [
            {"timestamp": "2026-01-01 10:00:00", "amount": 101},
            {"timestamp": "2026-01-01 10:00:00", "amount": 111},
        ]
    }
    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    assert_json_response(response, 200)
    assert len(response.json()["transactions"]) == 2


def test_parse_is_deterministic_and_idempotent(client):
    payload = {"expenses": sample_expenses()}
    one = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    two = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
    assert_json_response(one, 200)
    assert_json_response(two, 200)
    assert one.json() == two.json()


def test_validator_all_valid(client):
    transactions = parse_transactions(client, sample_expenses())
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:validator",
        json={"wage": 50000, "maxInvestmentAmount": 100.0, "transactions": transactions},
    )
    assert_json_response(response, 200)
    body = response.json()
    assert len(body["valid"]) == len(transactions)
    assert body["invalid"] == []
    assert body["duplicates"] == []


def test_validator_boundary_max_invest(client):
    transactions = parse_transactions(client, sample_expenses())
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:validator",
        json={"wage": 50000, "maxInvestmentAmount": 99.0, "transactions": transactions},
    )
    assert_json_response(response, 200)
    body = response.json()
    assert len(body["valid"]) == len(transactions)


def test_validator_duplicate_timestamp(client):
    transactions = parse_transactions(client, sample_expenses())
    transactions.append(transactions[0].copy())
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:validator",
        json={"wage": 50000, "maxInvestmentAmount": 100.0, "transactions": transactions},
    )
    assert_json_response(response, 200)
    body = response.json()
    assert len(body["duplicates"]) == 1
    assert len(body["valid"]) == len(transactions) - 1


def test_validator_exceeds_max_invest(client):
    transactions = parse_transactions(client, sample_expenses())
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:validator",
        json={"wage": 50000, "maxInvestmentAmount": 80.0, "transactions": transactions},
    )
    assert_json_response(response, 200)
    body = response.json()
    assert len(body["invalid"]) == 2
    assert body["invalid"][0]["message"] == "remanent exceeds maxInvestmentAmount."


@pytest.mark.parametrize("bad_wage", [None, "50000", -1])
def test_validator_invalid_wage(client, bad_wage):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:validator",
        json={"wage": bad_wage, "transactions": sample_transactions()},
    )
    assert_json_response(response, VALIDATION_STATUS)


def test_validator_empty_transactions(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:validator",
        json={"wage": 50000, "transactions": []},
    )
    assert_json_response(response, 200)
    assert response.json() == {"valid": [], "invalid": [], "duplicates": []}


def test_filter_no_q_no_p_single_k(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"}],
            "transactions": sample_transactions(),
        },
    )
    assert_json_response(response, 200)
    body = response.json()
    assert len(body["invalid"]) == 0
    assert [row["effectiveRemanent"] for row in body["valid"]] == [81.0, 1.0, 99.0]


def test_filter_single_q_override(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={
            "q": [{"fixed": 10, "start": "2026-01-01 00:00:00", "end": "2026-01-16 00:00:00"}],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"}],
            "transactions": sample_transactions(),
        },
    )
    assert_json_response(response, 200)
    effective = [item["effectiveRemanent"] for item in response.json()["valid"]]
    assert effective == [10.0, 10.0, 99.0]


def test_filter_multiple_p_stacking(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={
            "q": [],
            "p": [
                {"extra": 5, "start": "2026-01-15 00:00:00", "end": "2026-01-15 23:59:59"},
                {"extra": 7, "start": "2026-01-10 00:00:00", "end": "2026-01-20 23:59:59"},
            ],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"}],
            "transactions": sample_transactions(),
        },
    )
    assert_json_response(response, 200)
    effective = [item["effectiveRemanent"] for item in response.json()["valid"]]
    assert effective == [81.0, 13.0, 106.0]


def test_filter_q_then_p(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={
            "q": [{"fixed": 20, "start": "2026-01-15 00:00:00", "end": "2026-01-15 23:59:59"}],
            "p": [{"extra": 7, "start": "2026-01-15 00:00:00", "end": "2026-01-15 23:59:59"}],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"}],
            "transactions": sample_transactions(),
        },
    )
    assert_json_response(response, 200)
    effective = [item["effectiveRemanent"] for item in response.json()["valid"]]
    assert effective == [81.0, 27.0, 99.0]


def test_filter_q_overlap_latest_start_priority(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={
            "q": [
                {"fixed": 10, "start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"},
                {"fixed": 30, "start": "2026-01-10 00:00:00", "end": "2026-01-31 23:59:59"},
            ],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"}],
            "transactions": sample_transactions(),
        },
    )
    assert_json_response(response, 200)
    effective = [item["effectiveRemanent"] for item in response.json()["valid"]]
    assert effective == [10.0, 30.0, 30.0]


def test_filter_q_tie_first_in_input_list(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={
            "q": [
                {"fixed": 10, "start": "2026-01-10 00:00:00", "end": "2026-01-31 23:59:59"},
                {"fixed": 50, "start": "2026-01-10 00:00:00", "end": "2026-01-31 23:59:59"},
            ],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"}],
            "transactions": sample_transactions(),
        },
    )
    assert_json_response(response, 200)
    effective = [item["effectiveRemanent"] for item in response.json()["valid"]]
    assert effective == [81.0, 10.0, 10.0]


def test_filter_k_windows_inclusive_boundaries(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-05 10:00:00", "end": "2026-01-20 10:00:00"}],
            "transactions": sample_transactions(),
        },
    )
    assert_json_response(response, 200)
    assert len(response.json()["valid"]) == 3
    assert len(response.json()["invalid"]) == 0


def test_filter_invalid_interval_rejected(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={
            "q": [{"fixed": 1, "start": "2026-01-02 00:00:00", "end": "2026-01-01 00:00:00"}],
            "p": [],
            "k": [],
            "transactions": sample_transactions(),
        },
    )
    assert_json_response(response, VALIDATION_STATUS)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "q": [{"start": "2026-01-01 00:00:00", "end": "2026-01-10 00:00:00"}],
            "p": [],
            "k": [],
            "transactions": sample_transactions(),
        },
        {
            "q": [],
            "p": [{"start": "2026-01-01 00:00:00", "end": "2026-01-10 00:00:00"}],
            "k": [],
            "transactions": sample_transactions(),
        },
    ],
)
def test_filter_missing_period_fields(client, payload):
    response = client.post(f"{CHALLENGE_BASE}/transactions:filter", json=payload)
    assert_json_response(response, VALIDATION_STATUS)


@pytest.mark.parametrize(
    "q_value,p_value",
    [("10", 5), (10, "5"), (None, 2), (3, None)],
)
def test_filter_non_numeric_fixed_extra(client, q_value, p_value):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={
            "q": [{"fixed": q_value, "start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"}],
            "p": [{"extra": p_value, "start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"}],
            "k": [],
            "transactions": sample_transactions(),
        },
    )
    assert_json_response(response, VALIDATION_STATUS)


def test_filter_negative_fixed_extra_rejected(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={
            "q": [{"fixed": -1, "start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"}],
            "p": [{"extra": -1, "start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"}],
            "k": [],
            "transactions": sample_transactions(),
        },
    )
    assert_json_response(response, VALIDATION_STATUS)


def test_filter_no_k_provided_returns_processed_transactions(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={"q": [], "p": [], "k": [], "transactions": sample_transactions()},
    )
    assert_json_response(response, 200)
    assert len(response.json()["valid"]) == 3


def test_returns_index_zero_contributions(client):
    response = client.post(
        f"{CHALLENGE_BASE}/returns:index",
        json={
            "age": 40,
            "wage": 50000,
            "inflation": 5.0,
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}],
            "transactions": [],
        },
    )
    assert_json_response(response, 200)
    row = response.json()["savingsByDates"][0]
    assert row["amount"] == 0.0
    assert row["profits"] == 0.0
    assert row["returnAmount"] == 0.0


def test_returns_index_one_year_math(client):
    transactions = [
        {"date": "2026-01-01 12:00:00", "amount": 900.0, "ceiling": 1000.0, "remanent": 100.0}
    ]
    response = client.post(
        f"{CHALLENGE_BASE}/returns:index",
        json={
            "age": 59,
            "wage": 50000,
            "inflation": 0.0,
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}],
            "transactions": transactions,
        },
    )
    assert_json_response(response, 200)
    row = response.json()["savingsByDates"][0]
    expected_return = round2(100.0 * (1 + INDEX_RATE))
    assert row["returnAmount"] == expected_return
    assert row["profits"] == round2(expected_return - 100.0)


def test_returns_index_multi_year_with_inflation(client):
    transactions = [
        {"date": "2026-01-01 12:00:00", "amount": 900.0, "ceiling": 1000.0, "remanent": 100.0}
    ]
    response = client.post(
        f"{CHALLENGE_BASE}/returns:index",
        json={
            "age": 50,
            "wage": 50000,
            "inflation": 5.5,
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}],
            "transactions": transactions,
        },
    )
    assert_json_response(response, 200)
    years = 10
    expected = round2(100.0 * ((1 + INDEX_RATE) ** years) / ((1 + 0.055) ** years))
    row = response.json()["savingsByDates"][0]
    assert row["returnAmount"] == expected


def test_returns_nps_tax_benefit_formula(client):
    invested = 120_000.0
    transactions = [
        {"date": "2026-01-01 12:00:00", "amount": 0.0, "ceiling": 120000.0, "remanent": invested}
    ]
    response = client.post(
        f"{CHALLENGE_BASE}/returns:nps",
        json={
            "age": 59,
            "wage": 100000.0,
            "inflation": 0.0,
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}],
            "transactions": transactions,
        },
    )
    assert_json_response(response, 200)
    row = response.json()["savingsByDates"][0]
    assert row["taxBenefit"] == nps_tax_benefit(100000.0, invested)


def test_returns_nps_deduction_capped_by_2l(client):
    invested = 300_000.0
    transactions = [
        {"date": "2026-01-01 12:00:00", "amount": 0.0, "ceiling": 300000.0, "remanent": invested}
    ]
    response = client.post(
        f"{CHALLENGE_BASE}/returns:nps",
        json={
            "age": 59,
            "wage": 300000.0,
            "inflation": 0.0,
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}],
            "transactions": transactions,
        },
    )
    assert_json_response(response, 200)
    row = response.json()["savingsByDates"][0]
    assert row["taxBenefit"] == nps_tax_benefit(300000.0, invested)


@pytest.mark.parametrize(
    "payload",
    [
        {"age": 30, "wage": 50000, "q": [], "p": [], "k": [], "transactions": []},
        {"age": 30, "wage": "50000", "inflation": 5.5, "q": [], "p": [], "k": [], "transactions": []},
        {"age": 30, "wage": 50000, "inflation": -1, "q": [], "p": [], "k": [], "transactions": []},
    ],
)
def test_returns_invalid_payloads(client, payload):
    response = client.post(f"{CHALLENGE_BASE}/returns:nps", json=payload)
    assert_json_response(response, VALIDATION_STATUS)


def test_returns_tax_slab_boundary(client):
    invested = 1.0
    transactions = [
        {"date": "2026-01-01 12:00:00", "amount": 999.0, "ceiling": 1000.0, "remanent": invested}
    ]

    response = client.post(
        f"{CHALLENGE_BASE}/returns:nps",
        json={
            "age": 59,
            "wage": 700001.0 / 12.0,
            "inflation": 0.0,
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}],
            "transactions": transactions,
        },
    )
    assert_json_response(response, 200)
    benefit = response.json()["savingsByDates"][0]["taxBenefit"]
    assert benefit >= 0.0


def test_returns_large_years_remains_finite(client):
    transactions = [
        {"date": "2026-01-01 12:00:00", "amount": 900.0, "ceiling": 1000.0, "remanent": 100.0}
    ]
    response = client.post(
        f"{CHALLENGE_BASE}/returns:index",
        json={
            "age": 0,
            "wage": 50000,
            "inflation": 5.5,
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}],
            "transactions": transactions,
        },
    )
    assert_json_response(response, 200)
    value = response.json()["savingsByDates"][0]["returnAmount"]
    assert math.isfinite(value)


def test_returns_endpoint_deterministic(client):
    payload = {
        "age": 29,
        "wage": 50000,
        "inflation": 5.5,
        "q": [{"fixed": 0, "start": "2026-01-01 00:00:00", "end": "2026-01-31 23:59:59"}],
        "p": [{"extra": 25, "start": "2026-01-15 00:00:00", "end": "2026-01-31 23:59:59"}],
        "k": [{"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}],
        "transactions": sample_transactions(),
    }
    one = client.post(f"{CHALLENGE_BASE}/returns:index", json=payload)
    two = client.post(f"{CHALLENGE_BASE}/returns:index", json=payload)
    assert_json_response(one, 200)
    assert_json_response(two, 200)
    assert one.json() == two.json()


def test_e2e_simple_pipeline(client):
    parsed = client.post(f"{CHALLENGE_BASE}/transactions:parse", json={"expenses": sample_expenses()})
    assert_json_response(parsed, 200)

    validated = client.post(
        f"{CHALLENGE_BASE}/transactions:validator",
        json={"wage": 50000, "transactions": parsed.json()["transactions"]},
    )
    assert_json_response(validated, 200)
    assert validated.json()["invalid"] == []

    filtered = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}],
            "transactions": validated.json()["valid"],
        },
    )
    assert_json_response(filtered, 200)
    assert len(filtered.json()["valid"]) == 3

    returns = client.post(
        f"{CHALLENGE_BASE}/returns:index",
        json={
            "age": 29,
            "wage": 50000,
            "inflation": 5.5,
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}],
            "transactions": validated.json()["valid"],
        },
    )
    assert_json_response(returns, 200)
    assert len(returns.json()["savingsByDates"]) == 1


def test_e2e_duplicate_timestamp_flow(client):
    parsed = client.post(
        f"{CHALLENGE_BASE}/transactions:parse",
        json={
            "expenses": [
                {"timestamp": "2026-01-01 10:00:00", "amount": 101},
                {"timestamp": "2026-01-01 10:00:00", "amount": 151},
                {"timestamp": "2026-01-02 10:00:00", "amount": 251},
            ]
        },
    )
    assert_json_response(parsed, 200)

    validated = client.post(
        f"{CHALLENGE_BASE}/transactions:validator",
        json={"wage": 50000, "transactions": parsed.json()["transactions"]},
    )
    assert_json_response(validated, 200)
    assert len(validated.json()["duplicates"]) == 1

    returns = client.post(
        f"{CHALLENGE_BASE}/returns:index",
        json={
            "age": 30,
            "wage": 50000,
            "inflation": 5.0,
            "q": [],
            "p": [],
            "k": [{"start": "2026-01-01 00:00:00", "end": "2026-12-31 23:59:59"}],
            "transactions": validated.json()["valid"],
        },
    )
    assert_json_response(returns, 200)
    assert len(returns.json()["savingsByDates"]) == 1


@pytest.mark.stress
def test_stress_large_parse_payload(client):
    if not RUN_STRESS:
        pytest.skip("Enable RUN_STRESS in test_challenge_matrix.py to run stress tests.")

    base_time = datetime(2026, 1, 1, 0, 0, 0)
    expenses = []
    for index in range(20_000):
        timestamp = (base_time + timedelta(seconds=index)).strftime("%Y-%m-%d %H:%M:%S")
        expenses.append({"timestamp": timestamp, "amount": (index % 2000) + 0.5})

    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json={"expenses": expenses})
    assert_json_response(response, 200)
    assert len(response.json()["transactions"]) == len(expenses)


@pytest.mark.stress
def test_stress_large_intervals_filter(client):
    if not RUN_STRESS:
        pytest.skip("Enable RUN_STRESS in test_challenge_matrix.py to run stress tests.")

    base_time = datetime(2026, 1, 1, 0, 0, 0)
    transactions = []
    for index in range(2000):
        date = (base_time + timedelta(minutes=index)).strftime("%Y-%m-%d %H:%M:%S")
        amount = float((index % 900) + 100)
        ceiling = math.ceil(amount / 100.0) * 100.0
        transactions.append(
            {"date": date, "amount": amount, "ceiling": ceiling, "remanent": round2(ceiling - amount)}
        )

    q = [
        {
            "fixed": float(index % 25),
            "start": (base_time + timedelta(minutes=index)).strftime("%Y-%m-%d %H:%M:%S"),
            "end": (base_time + timedelta(minutes=index + 120)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for index in range(2000)
    ]
    p = [
        {
            "extra": float((index % 7) + 1),
            "start": (base_time + timedelta(minutes=index // 2)).strftime("%Y-%m-%d %H:%M:%S"),
            "end": (base_time + timedelta(minutes=(index // 2) + 60)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for index in range(2000)
    ]
    k = [
        {
            "start": (base_time + timedelta(minutes=index)).strftime("%Y-%m-%d %H:%M:%S"),
            "end": (base_time + timedelta(minutes=index + 180)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for index in range(1000)
    ]

    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={"q": q, "p": p, "k": k, "transactions": transactions},
    )
    assert_json_response(response, 200)
    assert len(response.json()["valid"]) + len(response.json()["invalid"]) == len(transactions)


@pytest.mark.stress
def test_stress_concurrent_requests():
    if not RUN_STRESS:
        pytest.skip("Enable RUN_STRESS in test_challenge_matrix.py to run stress tests.")

    payload = {"expenses": [{"timestamp": "2026-01-01 00:00:00", "amount": 1519}]}

    def send_one():
        with TestClient(app) as local_client:
            response = local_client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
            return response.status_code

    with ThreadPoolExecutor(max_workers=25) as executor:
        results = list(executor.map(lambda _: send_one(), range(100)))

    assert all(code == 200 for code in results)


@pytest.mark.fuzz
def test_fuzz_parse_structure_never_500(client):
    if not RUN_FUZZ:
        pytest.skip("Enable RUN_FUZZ in test_challenge_matrix.py to run fuzz tests.")

    random.seed(7)
    for _ in range(200):
        payload = {"expenses": []}
        size = random.randint(0, 10)
        for index in range(size):
            expense = {
                "timestamp": f"2026-01-{(index % 28) + 1:02d} 10:00:00",
                "amount": random.uniform(-500, 2000),
            }
            mutation = random.randint(0, 6)
            if mutation == 0:
                expense.pop("timestamp", None)
            elif mutation == 1:
                expense["timestamp"] = "bad-date"
            elif mutation == 2:
                expense["amount"] = "abc"
            elif mutation == 3:
                expense["amount"] = []
            elif mutation == 4:
                expense["unknownField"] = 1
            payload["expenses"].append(expense)

        response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json=payload)
        assert response.status_code in (200, VALIDATION_STATUS)


@pytest.mark.fuzz
def test_fuzz_semantic_q_and_p_properties(client):
    if not RUN_FUZZ:
        pytest.skip("Enable RUN_FUZZ in test_challenge_matrix.py to run fuzz tests.")

    random.seed(21)
    base = datetime(2026, 1, 1, 0, 0, 0)

    for _ in range(80):
        tx_count = random.randint(1, 8)
        transactions = []
        for idx in range(tx_count):
            ts = (base + timedelta(days=idx, minutes=random.randint(0, 1000))).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            amount = float(random.randint(0, 999))
            ceiling = math.ceil(amount / 100.0) * 100.0
            transactions.append(
                {
                    "date": ts,
                    "amount": amount,
                    "ceiling": ceiling,
                    "remanent": round2(ceiling - amount),
                }
            )

        q_count = random.randint(0, 4)
        p_count = random.randint(0, 4)
        q = []
        p = []
        for idx in range(q_count):
            start = base + timedelta(days=random.randint(0, tx_count))
            end = start + timedelta(days=random.randint(0, 3))
            q.append(
                {
                    "fixed": float(random.randint(0, 120)),
                    "start": start.strftime(DATETIME_FORMAT),
                    "end": end.strftime(DATETIME_FORMAT),
                }
            )
            if idx == q_count - 1 and q_count > 1:
                q[-1]["start"] = q[0]["start"]
                tied_start = datetime.strptime(q[-1]["start"], DATETIME_FORMAT)
                tied_end = datetime.strptime(q[-1]["end"], DATETIME_FORMAT)
                if tied_end < tied_start:
                    q[-1]["end"] = tied_start.strftime(DATETIME_FORMAT)

        for _ in range(p_count):
            start = base + timedelta(days=random.randint(0, tx_count))
            end = start + timedelta(days=random.randint(0, 3))
            p.append(
                {
                    "extra": float(random.randint(0, 20)),
                    "start": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "end": end.strftime("%Y-%m-%d %H:%M:%S"),
                }
            )

        response = client.post(
            f"{CHALLENGE_BASE}/transactions:filter",
            json={"q": q, "p": p, "k": [], "transactions": transactions},
        )
        assert_json_response(response, 200)
        actual = response.json()["valid"]

        for tx_in, tx_out in zip(transactions, actual):
            expected = compute_effective_remanent(tx_in, q, p)
            assert tx_out["effectiveRemanent"] == expected


@pytest.mark.fuzz
def test_fuzz_parse_remanent_bounds_property(client):
    if not RUN_FUZZ:
        pytest.skip("Enable RUN_FUZZ in test_challenge_matrix.py to run fuzz tests.")

    random.seed(31)
    expenses = []
    for index in range(500):
        timestamp = f"2026-02-{(index % 28) + 1:02d} 12:00:00"
        amount = round(random.uniform(0, 50_000), 2)
        expenses.append({"timestamp": timestamp, "amount": amount})

    response = client.post(f"{CHALLENGE_BASE}/transactions:parse", json={"expenses": expenses})
    assert_json_response(response, 200)
    for tx in response.json()["transactions"]:
        assert 0.0 <= tx["remanent"] < 100.0
