from typing import Any, List, Dict, Optional
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

# MCP relevant
# from langchain_mcp_adapters.client import MultiServerMCPClient
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters
from langchain_mcp_adapters.tools import load_mcp_tools 

LOCAL_CACHE_DIR = Path("/tmp/agent_tabular_cache")
LOCAL_CACHE_DIR.mkdir(parents=True, exist_ok=True)

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
    
    base_prompt = f"""You are an intelligent supervisor assistant that coordinates between two specialized agents:

    **Current Date: {current_date}**

    ### Available Agents

    1. **Project Documents Agent** (rag_search):
    - Searches internal project documents using RAG
    - Use for project-specific queries, internal documentation, uploaded files

    2. **Web Search Agent** (search_web):
    - Searches the internet for current information
    - Use for current events, general knowledge, external information
    - ONLY use this tool if asked by the user or mentioned in the question

    3. **Tabular Data Analysis Agent** (tabular_data_analysis):
    - Connects directly to spreadsheet data, CSV configurations, and SQL databases (.csv, .sqlite).
    - Use this whenever the user asks for exact math, computing averages, generating graphical charts, filtering database rows, analyzing metrics within tables or general data information.

    ### Core Responsibilities

    - Analyze user queries and determine which agent(s) to use
    - Route queries to the appropriate agent(s) — you MUST NOT answer substantive questions directly
    - For complex queries, coordinate multiple agents in sequence
    - Synthesize results from multiple agents into coherent answers
    - Prioritize project documents for project-specific questions
    - Use web search ONLY if asked by the user or mentioned in the question
    - Use the chat history to understand the context and references in the current question

    ### Query Routing Rules

    **ALWAYS use tools for:**
    - Any question requiring factual information
    - Project-specific queries
    - Technical questions
    - Current events or news
    - General knowledge questions
    - Analysis or research requests

    **Direct response permitted ONLY for:**
    - Simple greetings (hi, hello, how are you)
    - Acknowledgments (thanks, ok, got it)
    - Basic clarification requests about your capabilities
    - Farewell messages (goodbye, bye)

    **ALWAYS use the RAG tool for the questions**
    **Return as much information that is given from the RAG tool as possible to the user**

    For all other queries, you MUST route to the appropriate agent(s) and synthesize their responses. Your role is coordination and synthesis, not direct knowledge provision.
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

def create_tabular_analysis_tool(project_id: str, model: str = "gpt-4o"):
    """
    Spawns a decoupled MCP client connection on-demand to execute tasks against a standalone tabular data analysis service.
    """

    @tool
    async def tabular_data_analysis(
        query: str,
        # model: str,
        tool_call_id: Annotated[str, InjectedToolCallId]
    ) -> Command:
        """
        Analyze structured, tabular data files (like CSVs or SQLite databases) inside the project.
        Use this tool whenever the user asks for calculations, mathematical trends, row filtering, 
        summaries, statistical analysis, or charts regarding structured data files.
        
        Args:
            query: The specific question or analysis instruction for the datasets.
            tool_call_id: Injected tool call ID for message tracking.
        """
        try:
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
            
            # 1. Configure the parameters for your local stdio server
            server_params = StdioServerParameters(
                command="uv",
                args=[
                    "--directory", "/Users/amruthakaruturi/gitrepos/Full-Stack-RAG-project/mcps/tabular_mcp",
                    "run", "server.py"
                ]
            )
            # DEBUG LOGS
            print("=" * 80)
            print("Starting MCP server...")
            print("PWD:", os.getcwd())
            print("UV PATH:", shutil.which("uv"))
            print(
                "MCP DIR EXISTS:",
                os.path.exists(
                    "/Users/amruthakaruturi/gitrepos/Full-Stack-RAG-project/mcps/tabular_mcp"
                )
            )
            print("SERVER PARAMS:", server_params)
            print("=" * 80)

            # 2. Use the standard stdio_client context manager
            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    
                    # Initialize the MCP connection handshake
                    await session.initialize()
                    print("1. MCP initialized")
                    # 3. Retrieve the raw tools declared by your FastMCP server
                    # list_tools_result = await session.list_tools()
                    # mcp_tools = list_tools_result.tools
                    mcp_tools = await load_mcp_tools(session)
                    print("2. list_tools completed")
                    print("3. tools:", [t.name for t in mcp_tools])
                    # Build contextual system prompt injecting the cached scratch disk string configurations
                    system_instruction = (
                        "You are an isolated computational analyst worker. You have access to raw data tools. "
                        "The target project environment files have been synchronized for your execution path:\n"
                        + "\n".join(available_files_context) + "\n\n"
                        "Pass these exact string file paths into your data tools to analyze rows and solve the query."
                    )
                    print("TOOLS COUNT:", len(mcp_tools))
                    try:
                        print("Creating agent...")

                        tabular_agent = create_agent(
                            model=model,
                            tools=mcp_tools,
                            system_prompt=system_instruction,
                            state_schema=CustomAgentState
                        )

                        print("Agent created successfully")

                    except Exception as e:
                        import traceback

                        print("CREATE_AGENT FAILED")
                        print("TYPE:", type(e))
                        print("ERROR:", repr(e))
                        traceback.print_exc()

                        raise
                    print("4. agent created")

                    agent_result = await tabular_agent.ainvoke({
                        "messages": [{"role": "user", "content": query}]
                    })
                    print("5. invoke completed")

                    final_response = agent_result["messages"][-1]
                    content = final_response.content if hasattr(final_response, 'content') else str(final_response)
                    citations = agent_result.get("citations", [])
                    
                    return Command(update={
                        "messages": [ToolMessage(content=content, tool_call_id=tool_call_id)], 
                        "citations": citations
                    })
        except ExceptionGroup as eg:
            # Python 3.11+ syntax to catch a TaskGroup failure
            # Extract the actual errors that happened inside the group
            error_messages = []
            for exc in eg.exceptions:
                error_messages.append(f"[{type(exc).__name__}]: {str(exc)}")
            
            combined_error = " | ".join(error_messages)
            return Command(update={"messages": [ToolMessage(f"MCP TaskGroup Error: {combined_error}", tool_call_id=tool_call_id)]})

        except Exception as e:
            # Fallback for standard top-level exceptions or older Python versions
            if "TaskGroup" in str(e) and hasattr(e, "__exceptions__"):
                # Some backports of ExceptionGroup store sub-exceptions here
                error_messages = [f"[{type(err).__name__}]: {str(err)}" for err in e.__exceptions__]
                return Command(update={"messages": [ToolMessage(f"MCP TaskGroup Error: {' | '.join(error_messages)}", tool_call_id=tool_call_id)]})
                
            return Command(update={"messages": [ToolMessage(f"MCP Client Tool Execution Error: {str(e)}", tool_call_id=tool_call_id)]})
        
    return tabular_data_analysis

def create_supervisor_tools(project_id: str, model: str = "gpt-4o"):
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

    tabular_tool = create_tabular_analysis_tool(project_id, model)
    
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
    chat_history: Optional[List[Dict[str, str]]] = None
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
    llm = openAI["chat_llm"]
    # Get the supervisor tools (wrapped agents)
    tools = create_supervisor_tools(project_id, model=llm)

    # Get the system prompt with optional chat history
    system_prompt = get_supervisor_system_prompt(chat_history=chat_history)
    
    supervisor = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        state_schema=CustomAgentState
    ).with_config({"recursion_limit": 10})
    
    return supervisor
        