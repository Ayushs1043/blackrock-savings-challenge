from app.schemas import Operation, SolveRequest, SolveResponse
from app.services.finance import project_retirement_corpus, project_roundup_corpus


def solve_request(request: SolveRequest) -> SolveResponse:
    if request.operation == Operation.reverse_text:
        return SolveResponse(operation=request.operation, result=(request.text or "")[::-1])

    if request.operation == Operation.retirement_projection:
        projection = project_retirement_corpus(request.retirement)  # type: ignore[arg-type]
        return SolveResponse(operation=request.operation, result=projection.model_dump())

    if request.operation == Operation.roundup_projection:
        projection = project_roundup_corpus(request.roundup)  # type: ignore[arg-type]
        return SolveResponse(operation=request.operation, result=projection.model_dump())

    # Defensive fallback for future operations.
    return SolveResponse(operation=request.operation, result={})

