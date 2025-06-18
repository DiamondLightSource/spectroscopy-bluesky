

from pydantic import BaseModel, Field

class PlanParams(BaseModel):
    """
    Parameters for the PlanTemplate.
    """
    plan_name: str = Field(..., description="Name of the plan to be executed.")
    plan_args: dict = Field(default_factory=dict, description="Arguments for the plan.")
    plan_kwargs: dict = Field(default_factory=dict, description="Keyword arguments for the plan.")

    

