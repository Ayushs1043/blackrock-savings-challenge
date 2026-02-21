# Test type: API functional tests.
# Validation: Verifies solver and retirement endpoints for valid and invalid inputs.
# Command: pytest -q test/test_solver.py

def test_solve_reverse_text(client):
    response = client.post("/solve", json={"operation": "reverse_text", "text": "blackrock"})
    assert response.status_code == 200
    assert response.json() == {"operation": "reverse_text", "result": "kcorkcalb"}


def test_solve_reverse_text_missing_text(client):
    response = client.post("/solve", json={"operation": "reverse_text"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "validation_error"


def test_retirement_projection_endpoint(client):
    payload = {
        "current_age": 30,
        "retirement_age": 60,
        "monthly_investment": 10000,
        "annual_return_rate": 12,
        "current_corpus": 500000,
        "inflation_rate": 6,
    }
    response = client.post("/api/v1/retirement/projection", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["years_to_retirement"] == 30
    assert body["projected_corpus_nominal"] > body["projected_corpus_real"] > 0


def test_roundup_projection_endpoint(client):
    payload = {
        "monthly_expenses": [123.0, 255.5, 999.9],
        "roundup_base": 100,
        "annual_return_rate": 12,
        "years": 20,
        "inflation_rate": 6,
    }
    response = client.post("/api/v1/retirement/roundup", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["monthly_roundup_investment"] == 121.6
    assert body["projected_corpus_nominal"] > body["projected_corpus_real"] > 0


def test_solve_endpoint_open_access(client):
    response = client.post(
        "/solve",
        json={"operation": "reverse_text", "text": "abc"},
    )
    assert response.status_code == 200
    assert response.json()["result"] == "cba"
