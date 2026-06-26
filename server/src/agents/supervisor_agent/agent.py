from typing import Any, List, Dict, Optional, Union
from typing_extensions import Annotated
from datetime import datetime
import os
import shutil
from langchain.agents import create_agent
from langchain.tools import tool
from langchain_community.tools import DuckDuckGoSearchRun
from langchain_tavily import TavilySearch
from langchain_core.tools.base import InjectedToolCallId
from langchain_core.messages import ToolMessage
from langgraph.graph import MessagesState
from langgraph.types import Command
from langgraph.prebuilt import create_react_agent

from src.rag.retrieval.index import retrieve_context
from src.rag.retrieval.utils import prepare_prompt_and_invoke_llm
from src.services.llm import openAI
from src.services.awsS3 import s3_client
from src.services.supabase import supabase
from src.config.index import appConfig

import boto3
from pathlib import Path


# =============================================================================
# MCP RELATED CODE
# =============================================================================

# from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from langchain_mcp_adapters.tools import load_mcp_tools 
import asyncio



LOCAL_CACHE_DIR = Path("/tmp/agent_tabular_cache")
LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

from pydantic import BaseModel, Field
import json
import asyncio

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional, Literal
from langgraph.checkpoint.base import BaseCheckpointSaver


# class FrontendTable(BaseModel):
#     type: Literal["table"] = "table"
#     title: str
#     columns: List[str] = Field(default_factory=list)
#     rows: List[Dict[str, Any]] = Field(default_factory=list)


# class FrontendImage(BaseModel):
#     type: Literal["image"] = "image"
#     title: str
#     format: str = "png"
#     encoding: Literal["base64"] = "base64"
#     data: str


# class FrontendMarkdown(BaseModel):
#     type: Literal["markdown"] = "markdown"
#     content: str


# FrontendBlock = Union[
#     FrontendMarkdown,
#     FrontendTable,
#     FrontendImage
# ]

# class FrontendResponse(BaseModel):
#     answer: str
#     blocks: List[Dict[FrontendBlock]] = Field(default_factory=list)
#     citations: List[Dict[str, Any]] = Field(default_factory=list)



class TableBlock(BaseModel):
    title: str
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)


class ChartBlock(BaseModel):
    title: str
    chart_type: str
    image_base64: Optional[str] = None
    data: Optional[Dict[str, Any]] = None


class TabularAnalysisResult(BaseModel):
    summary: str
    tables: List[TableBlock] = Field(default_factory=list)
    charts: List[ChartBlock] = Field(default_factory=list)
    insights: List[str] = Field(default_factory=list)
    raw_tool_outputs: List[Dict[str, Any]] = Field(default_factory=list)


class TabularMCPManager:

    def __init__(self):
        self.session = None
        self.tools = None
        self.agent = None
        self._lock = asyncio.Lock()

    async def initialize(self, model="gpt-4o"):

        async with self._lock:

            if self.agent:
                return

            server_params = StdioServerParameters(
                command="uv",
                args=[
                    "--directory",
                    "/Users/amruthakaruturi/gitrepos/Full-Stack-RAG-project/mcps/tabular_mcp",
                    "run",
                    "server.py"
                ]
            )

            self._stdio_ctx = stdio_client(server_params)

            self.read_stream, self.write_stream = (
                await self._stdio_ctx.__aenter__()
            )

            self._session_ctx = ClientSession(
                self.read_stream,
                self.write_stream
            )

            self.session = await self._session_ctx.__aenter__()

            await self.session.initialize()

            self.tools = await load_mcp_tools(self.session)
            TABULAR_SYSTEM_PROMPT = """
            You are a tabular data analysis specialist.

            You have access to MCP tools for:
            - describing datasets
            - querying SQLite databases
            - filtering rows
            - grouping and aggregating
            - creating pivot tables
            - computing correlations
            - detecting anomalies
            - generating charts
            - analyzing time series
            - producing data quality reports
            - generating auto insights

            Rules:
            1. Always use tools for actual calculations.
            2. Never invent numbers, rows, column names, or chart data.
            3. First inspect the dataset with describe_dataset or list_tables unless the required schema is already clear.
            4. Use the exact file paths provided in the user request.
            5. When the user asks for a chart, call generate_chart.
            6. When the user asks for grouped metrics, use group_aggregate or create_pivot_table.
            7. When the user asks about SQLite data, use list_tables first, then query_sqlite.
            8. Keep the final answer concise because the outer tool will separately extract tables, charts, and insights from tool outputs.
            """

            self.agent = create_agent(
                model=model,
                tools=self.tools,
                system_prompt=TABULAR_SYSTEM_PROMPT,
                state_schema=CustomAgentState
            )

            print("MCP initialized")
        
    async def shutdown(self):

        if self._session_ctx:
            await self._session_ctx.__aexit__(
                None, None, None
            )

        if self._stdio_ctx:
            await self._stdio_ctx.__aexit__(
                None, None, None
            )

        self.session = None
        self.agent = None
        self.tools = None

        print("MCP shutdown complete")

tabular_mcp = TabularMCPManager()

# =============================================================================
# STATE DEFINITION
# =============================================================================

class CustomAgentState(MessagesState):
    """
    Extended agent state with citations tracking.
    
    This state extends the standard MessagesState to include a citations field
    that accumulates across tool calls, allowing the supervisor and sub-agents
    to track which documents were used to answer questions.
    
    Attributes:
        citations: List of citation dictionaries that accumulate across tool calls
    """
    citations: Annotated[List[Dict[str, Any]], lambda x, y: x + y] = []
    analysis_result: Optional[Dict[str, Any]] = None
    # frontend_response: Optional[Dict[str, Any]] = None

# =============================================================================
# PROMPTS
# =============================================================================

def format_chat_history(chat_history: List[Dict[str, str]]) -> str:
    """
    Format chat history into a readable string for the system prompt.
    
    Args:
        chat_history: List of message dictionaries with 'role' and 'content' keys
        
    Returns:
        Formatted string representation of the chat history
        
    Example:
        >>> history = [
        ...     {"role": "user", "content": "What is attention?"},
        ...     {"role": "assistant", "content": "Attention is a mechanism..."}
        ... ]
        >>> formatted = format_chat_history(history)
        >>> print(formatted)
        User Message: What is attention?
        AI Message: Attention is a mechanism...
    """
    if not chat_history:
        return ""
    
    formatted_messages = []
    for msg in chat_history:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        # Format: "User Message: message" or "AI Message: message"
        role_label = "User Message" if role.lower() == "user" else "AI Message"
        formatted_messages.append(f"{role_label}: {content}")
    
    return "\n\n".join(formatted_messages)

def get_supervisor_system_prompt(chat_history: Optional[List[Dict[str, str]]] = None) -> str:
    """
    Get the system prompt for the supervisor agent, optionally including chat history.
    
    Args:
        chat_history: Optional list of previous messages with 'role' and 'content' keys.
                      If provided, the chat history will be included in the system prompt.
        
    Returns:
        The system prompt string, with chat history appended if provided
        
    Example:
        >>> # Without history
        >>> prompt = get_supervisor_system_prompt()
        
        >>> # With history
        >>> history = [{"role": "user", "content": "What is X?"}]
        >>> prompt = get_supervisor_system_prompt(chat_history=history)
    """
    current_date = datetime.now().strftime("%B %d, %Y")
    
    base_prompt = f"""You are an intelligent supervisor assistant that coordinates between specialized tools and returns frontend-renderable structured responses.

    **Current Date: {current_date}**

    ### Available Agents

    1. **Project Documents Agent** (`rag_search`)
    - Searches internal project documents using RAG.
    - Use for project-specific queries, internal documentation, uploaded files, and content from project documents.
    - This tool may return text, citations, tables, or extracted document context.

    2. **Web Search Agent** (`search_web`)
    - Searches the internet for current information.
    - Use for current events, general knowledge, external information, or anything requiring up-to-date public data.
    - ONLY use this tool if asked by the user or if the question explicitly requires external/current information.

    3. **Tabular Data Analysis Agent** (`tabular_data_analysis`)
    - Connects directly to CSV files, SQLite databases, and tabular project data.
    - Use this whenever the user asks for calculations, averages, counts, grouping, filtering, correlations, trends, charts, graphs, data quality, anomalies, pivot tables, or exact analysis over rows/columns.
    - This tool returns structured JSON containing markdown, tables, images, insights, and citations.

    ### Core Responsibilities

    - Analyze the user's query and decide which tool(s) to call.
    - Route substantive questions to the correct tool; do not answer factual/project/data questions directly.
    - For complex queries, coordinate multiple tools in sequence.
    - Synthesize tool results into one final structured response.
    - Preserve structured blocks returned by tools, especially tables and base64 images.
    - Use chat history to understand context and references in the current question.

    ### Query Routing Rules

    Use `tabular_data_analysis` as the FIRST choice when the user mentions:
    - a `.csv`, `.sqlite`, `.db`, spreadsheet, table, dataframe, dataset, rows, columns, schema, sample rows, or data file
    - dataset description, dataset overview, column description, data preview, missing values, statistics, shape, or data quality
    - exact math over tabular data
    - counts, averages, sums, min/max, statistics
    - row filtering, sorting, grouping, aggregation, pivot tables
    - charts, graphs, visualizations
    - trends, correlations, anomalies, or time-series analysis

    Important:
    - If the user names a file ending in `.csv`, `.sqlite`, `.db`, or `.xlsx`, you MUST call `tabular_data_analysis`, not `rag_search`.
    - If the user asks to describe a dataset, inspect a dataset, preview a dataset, list columns, show sample rows, or explain tabular data, you MUST call `tabular_data_analysis`.
    - Do NOT use `rag_search` for CSV/database analysis unless the user is asking about documentation describing that dataset.


    Use `rag_search` when the user asks for:
    - Information from uploaded/project documents
    - Internal project-specific knowledge
    - Document summaries, explanations, or citations

    Use `search_web` when the user asks for:
    - Current events
    - Public/external information
    - Recent or live information
    - Internet search explicitly

    ### Direct Response Rules

    Direct response is permitted ONLY for:
    - Simple greetings
    - Acknowledgments
    - Basic clarification about your capabilities
    - Farewell messages

    For all other queries, you MUST use one or more tools.

    ### Tool Fallback Policy

    You may call more than one tool when needed.

    If `rag_search` returns no relevant context, no chunks, no citations, or says it could not find information, you must reconsider the query and call another appropriate tool before answering.

    Fallback rules:
    - If the query mentions `.csv`, `.sqlite`, `.db`, `.xlsx`, dataset, rows, columns, schema, sample rows, statistics, chart, or data analysis, then after an empty or insufficient `rag_search` result, call `tabular_data_analysis`.
    - If the query asks for current or external public information and `rag_search` is insufficient, call `search_web`.
    - Do not give a final answer after an empty tool result if another tool could answer the query.
    - Only return a final response after either:
    1. one tool gives enough information, or
    2. all relevant tools have been tried and are insufficient.

    ### Required Final Output Format

    You MUST return ONLY valid JSON.

    Do not wrap the JSON in markdown fences.
    Do not include commentary outside the JSON.

    The final response must match this structure:

    {{
    
    "blocks": [
        {{
        "type": "markdown",
        "content": "Markdown text to render in the frontend."
        }},
        {{
        "type": "table",
        "title": "Table title",
        "columns": ["column_1", "column_2"],
        "rows": [
            {{
            "column_1": "value",
            "column_2": "value"
            }}
        ]
        }},
        {{
        "type": "image",
        "title": "Chart or image title",
        "format": "png",
        "encoding": "base64",
        "data": "base64_encoded_image_string"
        }}
    ],
    "citations": []
    }}

    ### Structured Output Rules

    - Always include `blocks`, and `citations`.
    - `blocks` should contain renderable frontend sections.
    - Use `markdown` blocks for normal explanation text.
    - Use `table` blocks for tabular data.
    - Use `image` blocks for base64 charts or images.
    - If a tool returns JSON with `blocks`, preserve those blocks exactly unless you need to combine duplicate markdown.
    - Never convert tables into markdown if a table block is available.
    - Never remove or summarize away base64 image data.
    - Never invent table rows, columns, image data, or citations.
    - If no tables or images are returned, use only markdown blocks.
    - If the tool result cannot answer the query, return a markdown block explaining what is missing.

    ### Important

    Your final answer must be frontend-ready JSON, not a normal chat response.
    """

    if chat_history:
        formatted_history = format_chat_history(chat_history)
        if formatted_history:
            base_prompt += "\n\n### Previous Conversation Context\n"
            base_prompt += "The following is the recent conversation history for context:\n\n"
            base_prompt += formatted_history
            base_prompt += "\n\nUse this conversation history to understand context and references in the current question."
    
    return base_prompt



# =============================================================================
# RAG AGENT
# =============================================================================

def create_rag_tool(project_id: str):
    """
    Create a RAG search tool bound to a specific project.
    
    This factory function creates a tool that is bound to a specific project_id,
    allowing the agent to search through that project's documents.
    
    Args:
        project_id: The UUID of the project whose documents should be searchable
        
    Returns:
        A LangChain tool configured for RAG search on the specified project
    """
    
    @tool
    def rag_search(
        query: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """
        Search through project documents using RAG (Retrieval-Augmented Generation).
        This tool retrieves relevant context from the current project's documents based on the query.
        
        Args:
            query: The search query or question to find relevant information
            tool_call_id: Injected tool call ID for message tracking
            
        Returns:
            A Command object with updated messages and citations
        """
        try:
            # Retrieve context using the existing RAG pipeline
            texts, images, tables, citations = retrieve_context(project_id, query)
            
            # If no context found, return a message
            if not texts and not images and not tables:
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                "No relevant information found in the project documents for this query.",
                                tool_call_id=tool_call_id
                            )
                        ]
                    }
                )
                
            # Prepare the response using the existing LLM preparation function
            response = prepare_prompt_and_invoke_llm(
                user_query=query,
                texts=texts,
                images=images,
                tables=tables
            )
        
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=response,
                            tool_call_id=tool_call_id
                        )
                    ],
                    "citations": citations
                }
            )
        except Exception as e:

            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            f"Error retrieving information: {str(e)}",
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )

    return rag_search 

def create_rag_agent(project_id: str, model: str = "gpt-4o"):
    """
    Create a RAG agent for searching project-specific documents.
    
    This agent is specialized for searching through internal project documents
    using RAG (Retrieval-Augmented Generation). It will be used as a sub-agent
    by the supervisor.
    
    Args:
        project_id: The UUID of the project whose documents should be searchable
        model: The OpenAI model to use (default: "gpt-4o")
        
    Returns:
        A configured LangGraph agent for RAG search
    """
    tools = [create_rag_tool(project_id)]
    
    system_prompt = """You are a helpful AI assistant with access to a RAG (Retrieval-Augmented Generation) tool that searches project-specific documents.

    For every user question:

    1. Do not assume any question is purely conceptual or general.  
    2. Use the `rag_search` tool immediately with a clear and relevant query derived from the user's question.  
    3. Carefully review the retrieved documents and base your entire answer on the RAG results.  
    4. If the retrieved information fully answers the user's question, respond clearly and completely using that information.  
    5. If the retrieved information is insufficient or incomplete, explicitly state that and provide helpful suggestions or guidance based on what you found.  
    6. Always present answers in a clear, well-structured, and conversational manner.

    **Never answer without first querying the RAG tool. This ensures every response is grounded in project-specific context and documentation.**"""
    
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        state_schema=CustomAgentState
    )
    
    return agent

# =============================================================================
# WEB SEARCH AGENT
# =============================================================================

def create_web_search_agent(model: str = "gpt-4o", use_tavily: bool = True):
    """
    Create an agent with web search capabilities.
    
    This agent is specialized for searching the internet for current information.
    It supports both Tavily (paid, higher quality) and DuckDuckGo (free) as
    search backends.
    
    Args:
        model: The OpenAI model to use (default: "gpt-4o")
        use_tavily: Whether to use Tavily search (if API key available) or
                    fall back to DuckDuckGo (default: True)
        
    Returns:
        A configured LangGraph agent for web search
    """
    # Choose search tool based on availability
    if use_tavily and os.getenv("TAVILY_API_KEY"):
        search_tool = TavilySearch(max_results=5, search_depth="advanced")
    else:
        # Use DuckDuckGo as free alternative
        search_tool = DuckDuckGoSearchRun()
    
    tools = [search_tool]

    current_date = datetime.now().strftime("%B %d, %Y")
    
    system_prompt = f"""You are a specialized web search assistant.
Your job is to search the internet for current information and provide accurate, up-to-date answers.

**Current Date: {current_date}**

For every query you receive:
1. **Reformulate vague queries into specific search terms** before searching
2. Use the web search tool with clear, specific queries
3. Synthesize information from multiple search results when possible
4. Provide clear, factual answers with context
5. Indicate the recency and reliability of information when relevant

**Query Reformulation Examples:**
- "What's trending on social media today?" → Try: "Twitter trending topics today" OR "viral news today"
- "Today's top headlines" → Try: "breaking news today" OR "top news stories {current_date}"
- "What's happening in tech?" → Try: "latest tech news today" OR "technology headlines today"
- Add date context when relevant (e.g., "news {current_date}")

**If initial search returns insufficient or irrelevant results:**
1. Rephrase the query with more specific terms (e.g., add location, date, or focus area)
2. Try searching with alternative keywords or synonyms
3. Make 2-3 search attempts with different query formulations if needed
4. If still unsuccessful, clearly state what you found vs. what was requested

Focus on current events, general knowledge, and information not available in internal documents.
Never fabricate information - only use what's found in search results."""
    
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        state_schema=CustomAgentState
    )
    
    return agent

    
# =============================================================================
# Tabular MCP tool
# =============================================================================

import json
from typing import List, Dict, Any


def safe_parse_json(content: str):
    try:
        return json.loads(content)
    except Exception:
        return None

def compact_tabular_ai_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    parsed = safe_parse_json(msg.get("content", ""))

    if not isinstance(parsed, dict):
        return msg

    compact_blocks = []

    for block in parsed.get("blocks", []):
        if block.get("type") == "markdown":
            compact_blocks.append(block)

        elif block.get("type") == "table":
            compact_blocks.append({
                "type": "table",
                "title": block.get("title"),
                "columns": block.get("columns", []),
                "row_count": len(block.get("rows", []))
            })

        elif block.get("type") == "image":
            compact_blocks.append({
                "type": "image",
                "title": block.get("title"),
            })

    return {
        "role": msg.get("role"),
        "content": json.dumps({
            # "answer": parsed.get("answer", ""),
            "blocks": compact_blocks,
            "citations": parsed.get("citations", []),
        })
    }

def is_tabular_ai_message(msg: Dict[str, Any]) -> bool:
    if msg.get("role") not in ("assistant", "ai"):
        return False

    parsed = safe_parse_json(msg.get("content", ""))

    if not isinstance(parsed, dict):
        return False

    blocks = parsed.get("blocks", [])

    if not isinstance(blocks, list):
        return False

    return any(
        isinstance(block, dict)
        and block.get("type") in ("table", "image")
        for block in blocks
    ) 

def extract_tabular_history(chat_history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    tabular_history = []

    for i, msg in enumerate(chat_history):
        if is_tabular_ai_message(msg):
            if i > 0 and chat_history[i - 1].get("role") == "user":
                tabular_history.append(chat_history[i - 1])

            tabular_history.append(compact_tabular_ai_message(msg))

    return tabular_history


def parse_tool_content(content):
    if isinstance(content, str):
        return json.loads(content)

    if isinstance(content, dict):
        if content.get("type") == "text" and "text" in content:
            return json.loads(content["text"])
        return content

    if isinstance(content, list):
        if not content:
            return None

        first = content[0]

        if isinstance(first, dict) and first.get("type") == "text" and "text" in first:
            return json.loads(first["text"])

        return first

    return None
def extract_tabular_result(agent_result: Dict[str, Any]) -> Dict[str, Any]:
    tables = []
    charts = []
    insights = []
    raw_tool_outputs = []

    for msg in agent_result.get("messages", []):
        print("message type:", msg.__class__.__name__)
        if msg.__class__.__name__ != "ToolMessage":
            continue
        print("*"*80)
        print("recieved tool message:", msg.__class__.__name__)
        content = getattr(msg, "content", None)
        print("message content:", content)
        try:
            parsed = parse_tool_content(content)
        except Exception as e:
            print("Failed to parse tool content:", e)
            continue
        if not isinstance(parsed, dict):
            continue
        print("="*80)
        print("PARSED TOOL MESSAGE CONTENT:", parsed)
        raw_tool_outputs.append(parsed)

        # query_sqlite output
        if "rows" in parsed and "columns" in parsed:
            tables.append({
                "title": "SQL Query Result",
                "columns": parsed.get("columns", []),
                "rows": parsed.get("rows", []),
            })

        # filter_rows output
        elif "rows" in parsed and "filter_applied" in parsed:
            rows = parsed.get("rows", [])
            tables.append({
                "title": f"Filtered Rows: {parsed.get('filter_applied')}",
                "columns": list(rows[0].keys()) if rows else [],
                "rows": rows,
            })

        # group_aggregate output
        elif "result" in parsed and "group_by" in parsed:
            rows = parsed.get("result", [])
            tables.append({
                "title": "Grouped Aggregation Result",
                "columns": list(rows[0].keys()) if rows else [],
                "rows": rows,
            })

        # pivot table output
        elif "pivot_table" in parsed:
            rows = parsed.get("pivot_table", [])
            tables.append({
                "title": "Pivot Table",
                "columns": list(rows[0].keys()) if rows else [],
                "rows": rows,
            })

        # describe_dataset output
        elif "sample" in parsed and "columns" in parsed:
            sample = parsed.get("sample", [])
            tables.append({
                "title": "Dataset Sample",
                "columns": list(sample[0].keys()) if sample else list(parsed.get("columns", {}).keys()),
                "rows": sample,
            })

            insights.append(
                f"Dataset has {parsed.get('shape', {}).get('rows')} rows and "
                f"{parsed.get('shape', {}).get('columns')} columns."
            )

        # generate_chart output
        elif parsed.get("encoding") == "base64" and "image_data" in parsed:
            charts.append({
                "title": "Generated Chart",
                "chart_type": parsed.get("chart_type", "chart"),
                "image_base64": parsed.get("image_data"),
                "data": None,
            })

        # auto_insights output
        elif "insights" in parsed:
            for item in parsed.get("insights", []):
                if isinstance(item, dict):
                    insights.append(item.get("insight", str(item)))
                else:
                    insights.append(str(item))

        # correlation output
        elif "top_correlations" in parsed:
            rows = parsed.get("top_correlations", [])
            tables.append({
                "title": "Top Correlations",
                "columns": list(rows[0].keys()) if rows else [],
                "rows": rows,
            })

        # data_quality_report output
        elif "overall_quality" in parsed:
            oq = parsed["overall_quality"]
            insights.append(
                f"Data quality score is {oq.get('score')} ({oq.get('grade')}): "
                f"{oq.get('recommendation')}"
            )

    final_message = agent_result["messages"][-1]
    summary = final_message.content if hasattr(final_message, "content") else str(final_message)
    print("summary:", summary)
    print("tables:", tables)
    print("charts:", charts)
    print("insights:", insights)
    print("raw_tool_outputs:", raw_tool_outputs)
    return TabularAnalysisResult(
        summary=summary,
        tables=tables,
        charts=charts,
        insights=insights,
        raw_tool_outputs=raw_tool_outputs,
    ).model_dump()

def tabular_result_to_frontend_response(structured_result: Dict[str, Any]) -> Dict[str, Any]:
    blocks = []

    if structured_result.get("summary"):
        blocks.append({
            "type": "markdown",
            "content": structured_result["summary"],
        })

    for table in structured_result.get("tables", []):
        blocks.append({
            "type": "table",
            "title": table.get("title", "Table"),
            "columns": table.get("columns", []),
            "rows": table.get("rows", []),
        })

    for chart in structured_result.get("charts", []):
        if chart.get("image_base64"):
            blocks.append({
                "type": "image",
                "title": chart.get("title", "Chart"),
                "format": "png",
                "encoding": "base64",
                "data": chart["image_base64"],
            })

    if structured_result.get("insights"):
        blocks.append({
            "type": "markdown",
            "content": "\n".join(
                f"- {insight}" for insight in structured_result["insights"]
            ),
        })

    return {
        # "answer": structured_result.get("summary", ""),
        "blocks": blocks,
        "citations": [],
    }

def strip_image_data_for_llm(frontend_response: Dict[str, Any]) -> Dict[str, Any]:
    llm_response = {
        "blocks": [],
        "citations": frontend_response.get("citations", []),
    }

    for block in frontend_response.get("blocks", []):
        if block.get("type") == "image":
            llm_response["blocks"].append({
                "type": "image",
                "title": block.get("title", "Generated Chart"),
                "format": block.get("format", "png"),
                "encoding": block.get("encoding", "base64"),
                "data": "[image data hidden from LLM]"
            })
        else:
            llm_response["blocks"].append(block)

    return llm_response

def create_tabular_analysis_tool(project_id: str, model: str = "gpt-4o", tabular_history: List[Dict[str, Any]] = None):
    """
    Spawns a decoupled MCP client connection on-demand to execute tasks against a standalone tabular data analysis service.
    """

    @tool
    async def tabular_data_analysis(
        query: str,
        tool_call_id: Annotated[str, InjectedToolCallId]
    ) -> Command:
        """
        Analyze structured tabular data files such as CSV, SQLite, DB, and spreadsheet-like datasets.

        Use this tool whenever the user asks about:
        - a file ending in .csv, .sqlite, or .db
        - dataset description or overview
        - columns, schema, dtypes, shape, sample rows
        - missing values, data quality, statistics
        - calculations, averages, counts, sums
        - filtering, grouping, pivot tables
        - charts, graphs, visualizations
        - correlations, anomalies, trends, time series

        This tool should be preferred over RAG when the user mentions a dataset or tabular file.

        
        Args:
            query: The specific question or analysis instruction for the datasets.
            tool_call_id: Injected tool call ID for message tracking.
        """

        db_result = (
            supabase.table("project_documents")
            .select("id, filename, s3_key")
            .eq("project_id", project_id)
            .execute()
        )
        if not db_result.data:
            return Command(update={"messages": [ToolMessage("No relevant documents found in this project.")]})
        
        tabular_files = [f for f in db_result.data if f["filename"].lower().endswith((".csv", ".sqlite", ".db"))]
        if not tabular_files:
            return Command(update={"messages": ToolMessage("No relevant tabular files found in this project.")})
        
        # Stage targets files locally
        available_files_context = []
        for file_info in tabular_files:
            s3_key = file_info["s3_key"]
            filename = file_info["filename"]
            local_file_path = LOCAL_CACHE_DIR/f"{project_id}_{filename}"

            if not local_file_path.exists():
                s3_client.download_file(
                    Bucket = appConfig["s3_bucket_name"],
                    Key = s3_key,
                    Filename = str(local_file_path)
                )
            available_files_context.append(
                f"Dataset Name: {filename} available at path: {str(local_file_path)}"
            )
        await tabular_mcp.initialize(model=model)

        dataset_context = (
            "Available datasets:\n\n"
            + "\n".join(available_files_context)
        )
        print("dataset_context:", dataset_context)
        tabular_history_text = format_chat_history(tabular_history or [])
        agent_result = await asyncio.wait_for(
            tabular_mcp.agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": f"""
            {dataset_context}

            Previous relevant tabular context:
            {tabular_history_text}

            User Request:
            {query}

            Use the provided dataset paths when calling tools.
            """
                        }
                    ]
                }
            ),
            timeout=120
        )
        print("*"*20, "agent_result", "="*20)
        print(agent_result)
        structured_result = extract_tabular_result(agent_result)
        print("*"*20, "structured_result", "="*20)
        print( structured_result)
        print("*"*20, "structured_result", "="*20)
        citations = agent_result.get("citations", [])
        print("*"*20, "frontend_response", "="*20)
        frontend_response = tabular_result_to_frontend_response(structured_result)
        llm_visible_response = strip_image_data_for_llm(frontend_response)
        return Command(update={
            "messages": [
                ToolMessage(
                    content=json.dumps(llm_visible_response),
                    tool_call_id=tool_call_id,
                )
            ],
            "analysis_result": frontend_response,
            "citations": citations,
        })

    return tabular_data_analysis

def create_supervisor_tools(project_id: str, model: str = "gpt-4o", tabular_history: List[Dict[str, Any]] = None):
    """
    Create supervisor tools that wrap the specialized agents.
    
    This function creates two tools for the supervisor:
    1. rag_search: Wraps the RAG agent for project document search
    2. search_web: Wraps the web search agent for internet queries
    
    The supervisor will use these tools to delegate work to specialized agents.
    
    Args:
        project_id: The UUID of the project for the RAG agent
        model: The OpenAI model to use for both agents (default: "gpt-4o")
        
    Returns:
        List of tools (rag_search and search_web) for the supervisor
    """
    # Create the specialized agents
    rag_agent = create_rag_agent(project_id, model)
    web_agent = create_web_search_agent(model)

    tabular_tool = create_tabular_analysis_tool(project_id, model, tabular_history)
    
    @tool
    def rag_search(
        query: str,
        tool_call_id: Annotated[str, InjectedToolCallId],
    ) -> Command:
        """Search internal project documents using RAG.
        
        Use this when the user asks about:
        - Project-specific information
        - Internal documentation
        - Previously uploaded files and documents
        - Company/project-specific data
        - Technical specifications from project files
        
        Args:
            query: Natural language query about project documents
            tool_call_id: Injected tool call ID for message tracking
            
        Returns:
            Command with relevant information from project documents and citations
        """
        result = rag_agent.invoke({
            "messages": [{"role": "user", "content": query}]
        })

        # Extract the final response
        final_message = result["messages"][-1]
        content = final_message.content if hasattr(final_message, 'content') else str(final_message)
        citations = result.get("citations", [])
        
        # Return Command that updates both messages AND citations
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=content,
                        tool_call_id=tool_call_id
                    )
                ],
                "citations": citations  # Propagate citations to supervisor state
            }
        )
    @tool
    def search_web(query: str) -> str:
        """Search the internet for current information.
        
        Use this when the user asks about:
        - Current events or recent news
        - General knowledge not in project documents
        - External information or public data
        - Market trends or industry news
        - Any information that requires up-to-date web sources
        
        Args:
            query: Natural language query for web search
            
        Returns:
            Relevant information from web search results
        """
        result = web_agent.invoke({
            "messages": [{"role": "user", "content": query}]
        })
        
        # Extract the final response
        final_message = result["messages"][-1]
        if hasattr(final_message, 'content'):
            return final_message.content
        return str(final_message)


    return [rag_search, search_web, tabular_tool]



# =============================================================================
# SUPERVISOR AGENT CREATION
# =============================================================================

def create_supervisor_agent(
    project_id: str,
    # model: str = "gpt-4o",
    chat_history: Optional[List[Dict[str, str]]] = None,
    checkpointer: BaseCheckpointSaver | None = None
):
    """
    Create a supervisor agent that coordinates RAG and web search agents.
    
    The supervisor is responsible for:
    1. Analyzing user queries to determine which agent(s) to use
    2. Routing queries to the appropriate specialized agent(s)
    3. Coordinating multiple agents for complex queries
    4. Synthesizing results from multiple agents into coherent answers
    5. Using chat history to understand context and references
    
    The supervisor has access to two tools:
    - rag_search: For searching project documents
    - search_web: For searching the internet
    
    Args:
        project_id: The UUID of the project for the RAG agent
        model: The OpenAI model to use (default: "gpt-4o")
        chat_history: Optional list of previous messages with 'role' and 'content' keys.
                     If provided, the chat history will be included in the system prompt
                     to provide conversation context.
        
    Returns:
        A configured supervisor agent that can coordinate sub-agents
            
    Example:
        >>> # Basic usage without history
        >>> supervisor = create_supervisor_agent("123e4567-e89b-12d3-a456-426614174000")
        >>> result = supervisor.invoke({
        ...     "messages": [{"role": "user", "content": "What does our documentation say about X?"}]
        ... })
        
        >>> # With chat history
        >>> history = [
        ...     {"role": "user", "content": "What is attention mechanism?"},
        ...     {"role": "assistant", "content": "Attention is a mechanism that..."}
        ... ]
        >>> supervisor = create_supervisor_agent(
        ...     project_id="123e4567-e89b-12d3-a456-426614174000",
        ...     chat_history=history
        ... )
        >>> result = supervisor.invoke({
        ...     "messages": [{"role": "user", "content": "Tell me more about it"}]
        ... })
        >>> print(result["messages"][-1].content)
        >>> print(result.get("citations", []))
    """
    tabular_history = extract_tabular_history(chat_history)

    llm = openAI["chat_llm"]
    # Get the supervisor tools (wrapped agents)
    tools = create_supervisor_tools(project_id, model=llm, tabular_history=tabular_history)

    # Get the system prompt with optional chat history
    system_prompt = get_supervisor_system_prompt(chat_history=chat_history)
    
    supervisor = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        state_schema=CustomAgentState,
        checkpointer=checkpointer,
        # response_format=FrontendResponse
    ).with_config({"recursion_limit": 10})
    
    return supervisor
        