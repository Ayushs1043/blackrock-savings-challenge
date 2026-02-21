# Test type: API integration tests.
# Validation: Exercises challenge parse, validator, filter, and returns endpoints on representative workflows.
# Command: pytest -q test/test_challenge_api.py

CHALLENGE_BASE = "/blackrock/challenge/v1"


def _build_sample_expenses():
    return [
        {"timestamp": "2023-10-12 20:15:00", "amount": 250.0},
        {"timestamp": "2023-02-28 15:49:00", "amount": 375.0},
        {"timestamp": "2023-07-01 21:59:00", "amount": 620.0},
        {"timestamp": "2023-12-17 08:09:00", "amount": 480.0},
    ]


def _build_qpk():
    return {
        "q": [
            {
                "fixed": 0.0,
                "start": "2023-07-01 00:00:00",
                "end": "2023-07-31 23:59:59",
            }
        ],
        "p": [
            {
                "extra": 25.0,
                "start": "2023-10-01 08:00:00",
                "end": "2023-12-31 19:59:59",
            }
        ],
        "k": [
            {
                "start": "2023-03-01 00:00:00",
                "end": "2023-11-30 23:59:59",
            },
            {
                "start": "2023-01-01 00:00:00",
                "end": "2023-12-31 23:59:59",
            },
        ],
    }


def _parse_transactions(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:parse",
        json={"expenses": _build_sample_expenses()},
    )
    assert response.status_code == 200
    return response.json()["transactions"]


def test_transactions_parse(client):
    response = client.post(
        f"{CHALLENGE_BASE}/transactions:parse",
        json={"expenses": _build_sample_expenses()},
    )
    assert response.status_code == 200
    body = response.json()

    assert body["transactionsTotalAmount"] == 1725.0
    assert body["transactionsTotalCeiling"] == 1900.0
    assert body["transactionsTotalRemanent"] == 175.0

    assert body["transactions"][0]["remanent"] == 50.0
    assert body["transactions"][1]["remanent"] == 25.0
    assert body["transactions"][2]["remanent"] == 80.0
    assert body["transactions"][3]["remanent"] == 20.0


def test_transactions_validator(client):
    transactions = _parse_transactions(client)
    transactions.append(transactions[0].copy())
    transactions[1]["ceiling"] = 390.0

    response = client.post(
        f"{CHALLENGE_BASE}/transactions:validator",
        json={
            "wage": 50000.0,
            "maxInvestmentAmount": 70.0,
            "transactions": transactions,
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert len(body["duplicates"]) == 1
    assert len(body["invalid"]) == 2
    assert len(body["valid"]) == 2


def test_transactions_filter(client):
    transactions = _parse_transactions(client)
    qpk = _build_qpk()

    response = client.post(
        f"{CHALLENGE_BASE}/transactions:filter",
        json={**qpk, "transactions": transactions},
    )
    assert response.status_code == 200
    body = response.json()

    assert len(body["invalid"]) == 0
    assert len(body["valid"]) == 4

    effective_total = sum(item["effectiveRemanent"] for item in body["valid"])
    assert round(effective_total, 2) == 145.0


def test_returns_nps(client):
    transactions = _parse_transactions(client)
    qpk = _build_qpk()

    response = client.post(
        f"{CHALLENGE_BASE}/returns:nps",
        json={
            "age": 29,
            "wage": 50000.0,
            "inflation": 5.5,
            **qpk,
            "transactions": transactions,
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["transactionsTotalAmount"] == 1725.0
    assert body["transactionsTotalCeiling"] == 1900.0
    assert len(body["savingsByDates"]) == 2
    assert body["savingsByDates"][0]["amount"] == 75.0
    assert body["savingsByDates"][1]["amount"] == 145.0
    assert body["savingsByDates"][1]["profits"] > 80
    assert body["savingsByDates"][1]["taxBenefit"] == 0.0


def test_returns_index(client):
    transactions = _parse_transactions(client)
    qpk = _build_qpk()

    response = client.post(
        f"{CHALLENGE_BASE}/returns:index",
        json={
            "age": 29,
            "wage": 50000.0,
            "inflation": 5.5,
            **qpk,
            "transactions": transactions,
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert len(body["savingsByDates"]) == 2
    assert body["savingsByDates"][1]["returnAmount"] > 1800
    assert body["savingsByDates"][1]["taxBenefit"] == 0.0


def test_performance_endpoint(client):
    response = client.get(f"{CHALLENGE_BASE}/performance")
    assert response.status_code == 200
    body = response.json()

    assert isinstance(body["time"], str)
    assert body["memory"].endswith("MB")
    assert isinstance(body["threads"], int)
    assert body["threads"] > 0
