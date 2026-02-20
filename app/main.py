from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="BlackRock Hackathon API", version="1.0")

class SolveRequest(BaseModel):
    input: str = Field(..., min_length=1, max_length=20000)

class SolveResponse(BaseModel):
    output: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/solve", response_model=SolveResponse)
def solve(req: SolveRequest):
    # TODO: replace with your real algorithm tomorrow
    return SolveResponse(output=req.input[::-1])