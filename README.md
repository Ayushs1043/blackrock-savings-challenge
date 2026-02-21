# BlackRock Savings Challenge - Investment Simulation API

A production-ready backend implementation for the BlackRock Hackathon Challenge.

This project implements a deterministic financial savings engine that:

- Converts expenses into micro-investments via rounding logic
- Applies temporal financial constraints (`q` / `p` / `k` rules)
- Computes long-term investment returns (NPS / Index Fund)
- Provides Dockerized deployment for evaluation
- Includes automated testing and performance instrumentation

The system is designed for correctness, scalability, reproducibility, and evaluator convenience.

---

## 1) Problem Overview

The challenge models a real-world fintech automation system:

1. Every expense is rounded up to the nearest INR 100.
2. The difference (`remanent`) is saved.
3. Temporal rules modify savings:
   - `q` periods: fixed override savings
   - `p` periods: additional savings
   - `k` periods: evaluation windows
4. Savings are invested into:
   - National Pension Scheme (NPS)
   - Index Fund
5. Final returns are computed with compounding and inflation adjustment.

This simulates automated savings plus investment optimization.

---

## 2) Architecture Overview

```text
Expense Input
  -> Transaction Parser
  -> Validation Engine
  -> Temporal Rule Processor (q/p/k)
  -> Investment Calculator
  -> Performance and Monitoring APIs
```

### Core Components

| Component | Responsibility |
|---|---|
| Parser | Expense to remanent transformation |
| Validator | Input validation and business rule enforcement |
| Temporal Engine | Applies q/p/k logic with deterministic resolution |
| Returns Engine | Calculates NPS and Index fund returns |
| Performance API | Reports runtime resource metrics |

---

## 3) API Endpoints

Base URL:

`http://localhost:5477`

Swagger Documentation:

`http://localhost:5477/docs`

Endpoints:

1. Parse Transactions  
`POST /blackrock/challenge/v1/transactions:parse`  
Converts raw expenses into savings transactions.

2. Validate Transactions  
`POST /blackrock/challenge/v1/transactions:validator`  
Validates duplicates, business rules, and investment constraints.

3. Apply Temporal Rules  
`POST /blackrock/challenge/v1/transactions:filter`  
Applies q-period overrides, p-period additions, and k-period evaluation windows.

Deterministic overlap handling:
- Overlapping `q`: latest `start` wins; tie uses first in input list
- Overlapping `p`: sum all matching `extra`
- Interval boundaries are inclusive

4. Calculate NPS Returns  
`POST /blackrock/challenge/v1/returns:nps`  
Calculates annual compounding (7.11%), tax deduction (`min(investment, 10% income, INR 200000)`), separate tax benefit, and inflation-adjusted real value.

5. Calculate Index Returns  
`POST /blackrock/challenge/v1/returns:index`  
Calculates annual compounding (14.49%) and inflation-adjusted real value.

6. Performance Monitoring  
`GET /blackrock/challenge/v1/performance`  
Returns execution time, memory usage, and thread count.

---

## 4) Deployment (Hackathon Compliant)

### Build Docker Image

```bash
docker build -t blk-hacking-ind-{name-lastname} .
```

### Run Container

```bash
docker run -d -p 5477:5477 blk-hacking-ind-{name-lastname}
```

### Health Check

```bash
curl http://localhost:5477/health
```

### Docker Compose Deployment

```bash
docker compose -f compose.yaml up --build -d api
```

### Docker Compose Dev Mode

```bash
docker compose -f compose.yaml --profile dev up --build api-dev
```

---

## 5) Local Development Setup

Requirements:

1. Python 3.11+
2. Docker
3. Linux or WSL (recommended)

Run locally (without Docker):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 5477 --reload
```

Access:

`http://localhost:5477/docs`

---

## 6) Testing Strategy

All tests are located under:

`test/`

Coverage includes:

- Positive tests
- Negative validation tests
- Edge case tests
- Temporal overlap tests
- Investment calculation tests
- Stress and matrix tests

Run all tests:

```bash
pytest -q
```

Run specific files:

```bash
pytest -q test/test_challenge_api.py
pytest -q test/test_challenge_matrix.py
```

---

## 7) Algorithmic Approach

Designed for scalability and determinism.

Key principles:

- Deterministic interval resolution
- Efficient temporal constraint handling
- Avoidance of quadratic scans where possible
- Stable numeric precision
- Inclusive boundary handling

Correctness and reproducibility are prioritized over micro-optimizations.

---

## 8) Performance and Reliability

The system includes:

- Health monitoring endpoint
- Deterministic responses
- Docker reproducibility
- Performance metrics API
- Structured error handling
- Extensive input validation

---

## 9) Design Decisions

Why deterministic resolution?  
To ensure consistent behavior under overlapping temporal constraints.

Why interval-first processing?  
To avoid ambiguous savings calculations.

Why separate NPS and Index endpoints?  
To keep tax-aware and non-tax return logic clearly separated.

---

## 10) Future Scope

Product enhancements:

- User authentication and portfolio accounts
- Multi-instrument portfolio simulation
- Real-time market data integration
- Advanced tax computation engine
- Configurable compounding strategies

Engineering enhancements:

- Horizontal scaling
- Distributed processing
- Caching layer for interval aggregation
- Prometheus plus Grafana observability
- CI/CD automation

---

## 11) Contributor Development Workflow

Use WSL Ubuntu workspace:

```bash
cd /home/dev/hackathons/blackrock
```

For containerized development with hot reload:

```bash
docker compose -f compose.yaml --profile dev up --build api-dev
```

Development docs URL:

`http://localhost:5478/docs`

Quality gate before push:

```bash
ruff check .
pytest -q
```

---

## 12) Contributing

To contribute:

1. Fork the repository
2. Create a feature branch
3. Add or update corresponding tests
4. Submit a pull request

Areas open for contribution:

- Additional investment calculators
- Performance optimization
- Financial modeling enhancements
- API documentation improvements
