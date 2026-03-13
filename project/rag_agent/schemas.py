from typing import List, Literal
from pydantic import BaseModel, Field


class QueryAnalysis(BaseModel):
    is_clear: bool = Field(
        description="Indicates if the user's question is clear and answerable."
    )
    questions: List[str] = Field(
        description="List of rewritten, self-contained questions."
    )
    clarification_needed: str = Field(
        description="Explanation if the question is unclear."
    )


# --- Intent routing ---

IntentName = Literal["document", "market", "fusion", "general"]


class IntentRoute(BaseModel):
    intent: IntentName = Field(
        description=(
            "Routing intent for the question. "
            "document=answer from provided documents; "
            "market=use market data tools; "
            "fusion=needs both docs + market; "
            "general=not finance/docs-related (answer without tools, no sources)."
        )
    )
    rationale: str = Field(description="Short justification for why this intent was chosen.")


class IntentRouting(BaseModel):
    routes: List[IntentRoute] = Field(description="One intent route per rewritten question.")
