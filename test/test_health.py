# Test type: API smoke test.
# Validation: Confirms health endpoint availability and response payload.
# Command: pytest -q test/test_health.py

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
