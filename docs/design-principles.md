# Internal Builder Playbook: Design Principles for Problem Solving

This document is for the hackathon builders (you + Codex), not end users of the API.
Use it as a framework during implementation and as your submission narrative.

## 1. Problem Framing

- Restate the prompt in one sentence.
- Write exact input/output format.
- List explicit assumptions.
- Identify constraints (time, space, data size, API latency).

## 2. Domain Modeling

- Define clear request/response schemas before business logic.
- Validate mandatory fields, ranges, and cross-field rules.
- Keep model names business-oriented, not generic.

## 3. Algorithm Design

- Write 2-3 candidate approaches first.
- Choose one with justified tradeoffs:
  - time complexity
  - space complexity
  - implementation risk under hackathon time
- Mention why rejected options were inferior for current constraints.

## 4. Correctness Strategy

- Handle edge cases explicitly:
  - empty or malformed inputs
  - boundary values
  - large inputs
  - invalid combinations of fields
- Fail fast with clear error messages.

## 5. API Design Principles

- Keep endpoints single-purpose and deterministic.
- Use versioned paths for domain APIs (`/api/v1/...`).
- Separate health and business routes.
- Return consistent error envelopes for client predictability.

## 6. Security and Safety

- Apply strict input bounds.
- Protect business endpoints (API key if required).
- Avoid leaking internals in error details.
- Keep dependencies pinned and images minimal.

## 7. Testing Strategy

- Minimum categories:
  - happy path
  - edge cases
  - invalid input / validation
  - auth/security behavior
- Prefer small deterministic tests over broad flaky tests.

## 8. Operational Readiness

- Dockerized service on required port (`5477`).
- Health check endpoint and container health check.
- One-command run path (`docker compose up --build`).

## 9. Maintainability

- Keep a layered structure:
  - routes (transport)
  - schemas (contracts)
  - services (business logic)
- Use meaningful naming and keep functions small.

## 10. Demo / Submission Narrative (3-5 minutes)

1. Problem and assumptions.
2. Architecture and algorithm choice with complexity.
3. Validation and security handling.
4. Test evidence.
5. Docker run and API walkthrough.

## 60-Second Judge Checklist

- Is the approach clearly explained with tradeoffs?
- Are constraints reflected in design choices?
- Is input validation complete and explicit?
- Are errors predictable and readable?
- Are tests covering risk, not only success?
- Is deployment reproducible with Docker?
