# workflows readme

## how it works

```mermaid
%%{init: { 'theme': 'base', 'themeVariables': { 'primaryColor': '#3b82f6', 'edgeLabelBackground':'#ffffff', 'primaryTextColor': '#000' } } }%%
flowchart LR
    user_client[User Client] -->|Defines templates| github_repo[GitHub Repo]
    github_repo -->|Holds templates| cluster[Cluster]
    cluster -->|Launches workflows| workflows[Running Workflows]
    workflows -->|Updates status| web_ui[Web UI - Monitor State]
    workflows -->|Provides results| results_view[View Results]
    webhooks[Webhook API] -->|Trigger workflows| cluster
    graphql[GraphQL API] -->|Trigger workflows| cluster
    web_ui_trigger[Web UI - Launch] -->|Trigger workflows| cluster
    python_client[Python Client] -->|Triggers workflows and awaits results| cluster
    python_client -->|Receives results| results_view
```

# we use workflows as here

using this visit
cm40636-2

<https://diamondlightsource.github.io/workflows/docs/tutorials/ptypy-workflows/>

## for auth

```export TOKEN=$(kubectl oidc-login get-token --oidc-issuer-url=https://authn.diamond.ac.uk/realms/master --oidc-client-id=workflows-cluster --grant-type=password --oidc-use-access-token | jq -r '.status.token')```

```jq -Rs '{query: .}' test.graphql | \
curl -X POST https://workflows.diamond.ac.uk/graphql \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d @-
```
