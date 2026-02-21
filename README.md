# BlackRock Challenge API

API solution for the BlackRock hackathon challenge.

## 1) Challenge Deployment and Evaluation (PDF-Aligned)

This section is written for judges/reviewers first.

### 1.1 Deployment Requirements and Compliance

Requirement: Dockerized server with business logic.
Status: Implemented with `Dockerfile` (deployment image) and `Dockerfile.dev` (development image).

Requirement: Application must run on port `5477` inside container.
Status: Implemented. Uvicorn runs on `--port 5477`.

Requirement: Docker mapping must support `-p 5477:5477`.
Status: Implemented for deployment service and documented below.

Requirement: Dockerfile must expose port `5477`.
Status: Implemented with `EXPOSE 5477`.

Requirement: OS must be Linux-based and selection criteria must be commented.
Status: Implemented. Base image is `python:3.11-slim` (Debian Linux) with rationale comment in Dockerfiles.

Requirement: First line of Dockerfile must include build command with naming convention `blk-hacking-ind-{name-lastname}`.
Status: Implemented in `Dockerfile` first line comment.

Requirement: If dependencies/services exist, include Docker Compose YAML named `compose.yaml`.
Status: Implemented. `compose.yaml` includes deployment and development service definitions.

### 1.2 Deployment Commands (Exact)

Build deployment image:
```bash
docker build -t blk-hacking-ind-{name-lastname} .
```

Run deployment container (required mapping):
```bash
docker run -d -p 5477:5477 blk-hacking-ind-{name-lastname}
```

Verify health:
```bash
curl http://localhost:5477/health
```

Compose deployment run:
```bash
docker compose -f compose.yaml up --build -d api
```

### 1.3 Testing Requirements and Compliance

Requirement: tests must be under a folder named `test`.
Status: Implemented (`test/` folder).

Requirement: each test file must include comments for:
1. Test type
2. Validation executed
3. Command with arguments to execute

Status: Implemented in challenge and API test files.

Run all tests:
```bash
pytest -q
```

Run key suites:
```bash
pytest -q test/test_challenge_api.py
pytest -q test/test_challenge_matrix.py
```

### 1.4 Evaluation Criteria Mapping

Algorithm:
- Deterministic transaction parse/validate/filter logic and return calculation services.

API:
- Challenge endpoints exposed under `/blackrock/challenge/v1`.
- OpenAPI docs enabled at `/docs`.

Validations:
- Structured request validation and business rule validation.
- Negative, edge, stress, and fuzz-style checks in matrix tests.

Deployment:
- Linux-based Docker image, port `5477`, `compose.yaml`, healthcheck, reproducible run commands.

Testing:
- Automated test coverage under `test/` with explicit execution metadata comments.

### 1.5 Submission Checklist

Before submission, ensure the default branch contains:
1. Full source code
2. `Dockerfile`
3. `compose.yaml`
4. `test/` automation
5. This `README.md` with configure/run/test instructions

Publish the repository as public and share that public URL.

## 2) API Reference

Base URL (deployment): `http://localhost:5477`

Endpoints:
1. `POST /blackrock/challenge/v1/transactions:parse`
2. `POST /blackrock/challenge/v1/transactions:validator`
3. `POST /blackrock/challenge/v1/transactions:filter`
4. `POST /blackrock/challenge/v1/returns:nps`
5. `POST /blackrock/challenge/v1/returns:index`
6. `GET /blackrock/challenge/v1/performance`

Swagger UI:
- `http://localhost:5477/docs`

## 3) Development Process (For Contributors)

This section is for someone who wants to develop or extend this repository.

### 3.1 Recommended Environment (WSL Ubuntu)

Use your WSL Ubuntu workspace:
```bash
cd /home/dev/hackathons/blackrock
```

Prerequisites:
1. Python 3.11+
2. Docker + Docker Compose

### 3.2 Local Python Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 5477 --reload
```

### 3.3 Docker Development Flow

Run hot-reload development container:
```bash
docker compose -f compose.yaml --profile dev up --build api-dev
```

Development URL:
- `http://localhost:5478`
- `http://localhost:5478/docs`

### 3.4 Quality Gate Before Push

```bash
ruff check .
pytest -q
```

### 3.5 Configuration Policy for This Hackathon

- No API keys, secrets, or environment variables are required to run the baseline solution.
- Keep setup simple and reproducible for evaluator convenience.

## 4) Future Scope

1. Add authentication/authorization for production-grade security.
2. Add observability (metrics, tracing, audit logs).
3. Add extensible modules for more instruments/rules and regional tax logic.
