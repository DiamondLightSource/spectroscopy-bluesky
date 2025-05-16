query = """
mutation {
    submitWorkflowTemplate(name: "numpy-benchmark", parameters: {size: 2000, memory: "20Gi"}, visit:  {
    number: 1,
    proposalCode: "mg",
    proposalNumber: 36964
    } ){
        name
    }
}
"""
