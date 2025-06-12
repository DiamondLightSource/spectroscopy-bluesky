import base64

import pandas as pd
import requests
from pydantic import BaseModel


class Visit(BaseModel):
    number: int
    proposalCode: str
    proposalNumber: int


def call_quadratic_workflow(
    table: pd.DataFrame, visit: Visit, graphql_url: str, timeout: int = 10
) -> str:
    """
    Submits the quadratic workflow via GraphQL, encoding the DataFrame as base64.
    Returns the job id from the response, or raises an exception on error.
    """
    try:
        # Convert DataFrame to CSV and encode as base64
        csv_bytes = table.to_csv(index=False).encode("utf-8")
        b64_table = base64.b64encode(csv_bytes).decode("utf-8")

        mutation = f"""
        mutation {{
            submitWorkflowTemplate(
                name: "quadratic-fit",
                parameters: {{table: "{b64_table}"}},
                visit: {{
                    number: {visit.number},
                    proposalCode: "{visit.proposalCode}",
                    proposalNumber: {visit.proposalNumber}
                }}
            ) {{
                id
                name
            }}
        }}
        """

        response = requests.post(
            graphql_url,
            json={"query": mutation},
            timeout=timeout,
        )
        response.raise_for_status()
        result = response.json()

        # Error handling for GraphQL errors
        if "errors" in result:
            raise RuntimeError(f"GraphQL error: {result['errors']}")

        job_id = result.get("data", {}).get("submitWorkflowTemplate", {}).get("id")
        if not job_id:
            raise RuntimeError("No job id returned in response.")

        return job_id

    except Exception as e:
        raise RuntimeError(f"Failed to submit quadratic workflow: {e}")  # noqa: B904
