# server/notebooks/agents/test_mcp.py

import asyncio
import json
import sys
from pathlib import Path


# ---------------------------------------------------------
# Fix Python import path
# test_mcp.py is in: server/notebooks/agents/
# project server root is: server/
# ---------------------------------------------------------
SERVER_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SERVER_ROOT))


from src.agents.supervisor_agent.agent import TabularMCPManager, extract_tabular_result, tabular_result_to_frontend_response



async def main():
    model = "gpt-4o"
    project_id = ""
    tabular_mcp = TabularMCPManager()

    dataset_context = """
Available datasets:

Dataset Name: sample_sales.csv available at path: /Users/amruthakaruturi/gitrepos/Full-Stack-RAG-project/server/notebooks/agents/sample_sales.csv
"""

    query = "Give me the description of the sample_sales.csv dataset."

    try:
        print("Initializing Tabular MCP...")
        await tabular_mcp.initialize(model=model)
        print("MCP initialized successfully.")

        print("\nAvailable MCP tools:")
        for tool in tabular_mcp.tools:
            print("-", tool.name)

        print("\nInvoking tabular agent...")

        agent_result = await asyncio.wait_for(
            tabular_mcp.agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"""
{dataset_context}

User Request:
{query}

Use the provided dataset paths when calling tools.
"""
                        }
                    ]
                }
            ),
            timeout=120,
        )

        print("\nAgent result messages:")
        for msg in agent_result.get("messages", []):
            print("=" * 80)
            print(type(msg).__name__)
            print(getattr(msg, "content", msg))
        
        print("="*80)
        structured_result = extract_tabular_result(agent_result)
        print("Structured result:")
        print(json.dumps(structured_result, indent=2))

        citations = agent_result.get("citations", [])
        print("="*80)
        frontend_response = tabular_result_to_frontend_response(structured_result)
        print("Frontend response:")
        print(json.dumps(frontend_response, indent=2))
        final_msg = agent_result["messages"][-1]
        final_content = getattr(final_msg, "content", str(final_msg))

        print("="*80)
        print("\nFinal answer:")
        print(final_content)

    finally:
        if hasattr(tabular_mcp, "shutdown"):
            print("\nShutting down MCP...")
            await tabular_mcp.shutdown()
            print("MCP shutdown complete.")
        else:
            print("\nNo shutdown() method found on TabularMCPManager.")


if __name__ == "__main__":
    asyncio.run(main())