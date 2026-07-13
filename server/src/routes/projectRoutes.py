from fastapi import APIRouter, HTTPException, Depends, Request
from src.services.supabase import supabase
from src.services.clerkAuth import get_current_user_clerk_id
from src.models.index import ProjectCreate, ProjectSettings
from src.models.index import MessageCreate, MessageRole
from src.rag.retrieval.index import retrieve_context
from src.rag.retrieval.utils import prepare_prompt_and_invoke_llm
from src.agents.simple_agent.agent import create_simple_custom_agent
from src.agents.supervisor_agent.agent import create_supervisor_agent
from typing import List, Dict, Any
import json
import uuid
from src.config.index import appConfig
import asyncio
import re
from openai import RateLimitError
from src.agents.supervisor_agent.agent import compact_tabular_ai_message, safe_parse_json

router = APIRouter(tags=["projectRoutes"])


"""
`/api/projects`

  - GET `/api/projects/` ~ List all projects
  - POST `/api/projects/` ~ Create a new project
  - DELETE `/api/projects/{project_id}` ~ Delete a specific project
  
  - GET `/api/projects/{project_id}` ~ Get specific project data
  - GET `/api/projects/{project_id}/chats` ~ Get specific project chats
  - GET `/api/projects/{project_id}/settings` ~ Get specific project settings
  
  - PUT `/api/projects/{project_id}/settings` ~ Update specific project settings
  - POST `/api/projects/{project_id}/chats/{chat_id}/messages` ~ Send a message to a Specific Chat
  
"""


@router.get("/")
@router.get("")
async def get_projects(current_user_clerk_id: str = Depends(get_current_user_clerk_id)):
    """
    ! Logic Flow
    * 1. Get current user clerk_id
    * 2. Query projects table for projects related to the current user
    * 3. Return projects data
    """
    try:
        projects_query_result = (
            supabase.table("projects")
            .select("*")
            .eq("clerk_id", current_user_clerk_id)
            .execute()
        )

        return {
            "message": "Projects retrieved successfully",
            "data": projects_query_result.data or [],
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred while fetching projects: {str(e)}",
        )


@router.post("/")
@router.post("")
async def create_project(
    project_data: ProjectCreate,
    current_user_clerk_id: str = Depends(get_current_user_clerk_id),
):
    """
    ! Logic Flow
    * 1. Get current user clerk_id
    * 2. Insert new project into database
    * 3. Check if project creation failed, then return error
    * 4. Create default project settings for the new project
    * 5. Check if project settings creation failed, then rollback the project creation
    * 6. Return newly created project data
    """
    try:
        # Insert new project into database
        project_insert_data = {
            "name": project_data.name,
            "description": project_data.description,
            "clerk_id": current_user_clerk_id,
        }

        project_creation_result = (
            supabase.table("projects").insert(project_insert_data).execute()
        )

        if not project_creation_result.data:
            raise HTTPException(
                status_code=422,
                detail="Failed to create project - invalid data provided",
            )

        newly_created_project = project_creation_result.data[0]

        # Create default project settings for the new project
        project_settings_data = {
            "project_id": newly_created_project["id"],
            "embedding_model": "text-embedding-3-large",
            "rag_strategy": "basic",
            "agent_type": "agentic",
            "chunks_per_search": 10,
            "final_context_size": 5,
            "similarity_threshold": 0.3,
            "number_of_queries": 5,
            "reranking_enabled": True,
            "reranking_model": "reranker-english-v3.0",
            "vector_weight": 0.7,
            "keyword_weight": 0.3,
        }

        project_settings_creation_result = (
            supabase.table("project_settings").insert(project_settings_data).execute()
        )

        if not project_settings_creation_result.data:
            # Rollback: Delete the project if settings creation fails
            supabase.table("projects").delete().eq(
                "id", newly_created_project["id"]
            ).execute()
            raise HTTPException(
                status_code=422,
                detail="Failed to create project settings - project creation rolled back",
            )

        return {
            "message": "Project created successfully",
            "data": newly_created_project,
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred while creating project: {str(e)}",
        )


@router.delete("/{project_id}")
async def delete_project(
    project_id: str, current_user_clerk_id: str = Depends(get_current_user_clerk_id)
):
    """
    ! Logic Flow
    * 1. Get current user clerk_id
    * 2. Verify if the project exists and belongs to the current user
    * 3. Delete project - CASCADE will automatically delete all related data:
    * 4. Check if project deletion failed, then return error
    * 5. Return successfully deleted project data
    """
    try:
        # Verify if the project exists and belongs to the current user
        project_ownership_verification_result = (
            supabase.table("projects")
            .select("id")
            .eq("id", project_id)
            .eq("clerk_id", current_user_clerk_id)
            .execute()
        )

        if not project_ownership_verification_result.data:
            raise HTTPException(
                status_code=404,  # Not Found - project doesn't exist or doesn't belong to user
                detail="Project not found or you don't have permission to delete it",
            )

        # Delete project ~ "CASCADE" will automatically delete all related data: project_settings, project_documents, document_chunks, chats, messages, etc.
        project_deletion_result = (
            supabase.table("projects")
            .delete()
            .eq("id", project_id)
            .eq("clerk_id", current_user_clerk_id)
            .execute()
        )

        if not project_deletion_result.data:
            raise HTTPException(
                status_code=500,  # Internal Server Error - deletion failed unexpectedly
                detail="Failed to delete project - please try again",
            )

        successfully_deleted_project = project_deletion_result.data[0]

        return {
            "message": "Project deleted successfully",
            "data": successfully_deleted_project,
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred while deleting project: {str(e)}",
        )


@router.get("/{project_id}")
async def get_project(
    project_id: str, current_user_clerk_id: str = Depends(get_current_user_clerk_id)
):
    """
    ! Logic Flow
    * 1. Get current user clerk_id
    * 2. Verify if the project exists and belongs to the current user
    * 3. Return project data
    """
    try:
        project_result = (
            supabase.table("projects")
            .select("*")
            .eq("id", project_id)
            .eq("clerk_id", current_user_clerk_id)
            .execute()
        )

        if not project_result.data:
            raise HTTPException(
                status_code=404,
                detail="Project not found or you don't have permission to access it",
            )

        return {
            "message": "Project retrieved successfully",
            "data": project_result.data[0],
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred while retrieving project: {str(e)}",
        )


@router.get("/{project_id}/chats")
async def get_project_chats(
    project_id: str, current_user_clerk_id: str = Depends(get_current_user_clerk_id)
):
    """
    ! Logic Flow
    * 1. Get current user clerk_id
    * 2. Verify if the project exists and belongs to the current user
    * 3. Return project chats data
    """
    try:
        project_chats_result = (
            supabase.table("chats")
            .select("*")
            .eq("project_id", project_id)
            .eq("clerk_id", current_user_clerk_id)
            .order("created_at", desc=True)
            .execute()
        )

        # * If there are no chats for the project, return an empty list
        # * A User may or may not have any chats for a project

        return {
            "message": "Project chats retrieved successfully",
            "data": project_chats_result.data or [],
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred while retrieving project {project_id} chats: {str(e)}",
        )


@router.get("/{project_id}/settings")
async def get_project_settings(
    project_id: str, current_user_clerk_id: str = Depends(get_current_user_clerk_id)
):
    """
    ! Logic Flow
    * 1. Get current user clerk_id
    * 2. Verify if the project exists and belongs to the current user
    * 3. Check if the project settings exists for the project
    * 4. Return project settings data
    """
    try:
        project_settings_result = (
            supabase.table("project_settings")
            .select("*")
            .eq("project_id", project_id)
            .execute()
        )

        if not project_settings_result.data:
            raise HTTPException(
                status_code=404,
                detail="Project settings not found or you don't have permission to access it",
            )

        return {
            "message": "Project settings retrieved successfully",
            "data": project_settings_result.data[0],
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred while retrieving project {project_id} settings: {str(e)}",
        )


@router.put("/{project_id}/settings")
async def update_project_settings(
    project_id: str,
    settings: ProjectSettings,
    current_user_clerk_id: str = Depends(get_current_user_clerk_id),
):
    """
    ! Logic Flow
    * 1. Get current user clerk_id
    * 2. Verify if the project exists and belongs to the current user
    * 3. Verify if the project settings exist for the project
    * 4. Update project settings
    * 5. Check if project settings update failed, then return error
    * 6. Return successfully updated project settings data
    """
    try:
        project_ownership_verification_result = (
            supabase.table("projects")
            .select("id")
            .eq("id", project_id)
            .eq("clerk_id", current_user_clerk_id)
            .execute()
        )

        if not project_ownership_verification_result.data:
            raise HTTPException(
                status_code=404,
                detail="Project not found or you don't have permission to update its settings",
            )

        project_settings_ownership_verification_result = (
            supabase.table("project_settings")
            .select("id")
            .eq("project_id", project_id)
            .execute()
        )

        if not project_settings_ownership_verification_result.data:
            raise HTTPException(
                status_code=404,
                detail="Project settings not found for this project",
            )

        project_settings_update_data = (
            settings.model_dump()  # Pydantic modal to dictionary conversion
        )
        project_settings_update_result = (
            supabase.table("project_settings")
            .update(project_settings_update_data)
            .eq("project_id", project_id)
            .execute()
        )

        if not project_settings_update_result.data:
            raise HTTPException(
                status_code=422, detail="Failed to update project settings"
            )

        return {
            "message": "Project settings updated successfully",
            "data": project_settings_update_result.data[0],
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred while updating project {project_id} settings: {str(e)}",
        )

def format_structured_ai_content(msg: Dict[str, Any]) -> Dict[str, Any]:

    # parsed = safe_parse_json(msg.get("content", ""))

    if not isinstance(msg, dict):
        return {}
    # print("parsed:", parsed)
    parts = {}

    answer = msg.get("answer")

    if isinstance(answer, str) and answer.strip():
        parts["answer"] = answer.strip()

    tabular_message = compact_tabular_ai_message(msg)
    print("tabular_message:", tabular_message)
    compact_content = json.loads(tabular_message["content"])

    parts["blocks"] = compact_content["blocks"]
    print("parts:", parts)
    return parts



    
    

def get_chat_history(chat_id:str, exclude_message_id:str =None)-> List[Dict[str,str]]:
    """
        Retrieves the last 10 messages (5 user + 5 assistant) from the chat,
        excluding the current message being processed.
        
        Args:
            chat_id: The ID of the chat
            exclude_message_id: Optional message ID to exclude from history
            
        Returns:
            List of message dictionaries with 'role' and 'content' keys
    """
    print("inside get_chat_history")
    try:
        query = (
            supabase.table("messages")
            .select("id, role, content")
            .eq("chat_id", chat_id)
            .order("created_at", desc=False)
        )
        
        # Exclude current message if provided
        if exclude_message_id:
            query = query.neq("id", exclude_message_id)
        
        messages_result = query.execute()
        
        if not messages_result.data:
            return []
        
        # Get last 10 messages (limit to 10 total messages)
        recent_messages = messages_result.data[-10:]
        # print("recent_messages:", recent_messages)
        # # Format messages for agent
        # formatted_history = []
        # for msg in recent_messages:
        #     if msg.get('role') == 'assistant':
        #         aimessage_content = format_structured_ai_content(msg)
        #         formatted_history.append({
        #             "role": msg.get("role", "assistant"),
        #             "content": aimessage_content
        #         })
        #     else:
        #         formatted_history.append({
        #             "role": msg.get("role", "user"),
        #             "content": msg.get("content", "")
        #         })
        # return formatted_history
        return recent_messages
    except Exception:
        # If history retrieval fails, return empty list
        return []

def get_retry_after_seconds(error: Exception, default: float = 8.0) -> float:
    match = re.search(r"Please try again in ([0-9.]+)s", str(error))
    return float(match.group(1)) if match else default


# async def invoke_agent_with_retry(agent, payload, config, max_retries: int = 3):
#     last_error = None

#     for attempt in range(max_retries):
#         try:
#             return await agent.ainvoke(payload, config=config)

#         except RateLimitError as e:
#             last_error = e
#             wait = get_retry_after_seconds(e) + 1
#             print(f"Rate limit hit. Attempt {attempt + 1}/{max_retries}. Retrying in {wait:.2f}s...")
#             await asyncio.sleep(wait)

#     raise last_error

async def invoke_agent_with_retry(
    agent,
    payload,
    config,
    max_retries: int = 3,
):
    last_error = None

    for attempt in range(max_retries):
        try:
            if attempt == 0:
                # Start the graph with the new user message.
                return await agent.ainvoke(
                    payload,
                    config=config,
                )

            # Resume from the last successful checkpoint.
            # Do not append the user message again.
            return await agent.ainvoke(
                None,
                config=config,
            )

        except RateLimitError as e:
            last_error = e

            if attempt == max_retries - 1:
                break

            wait = get_retry_after_seconds(e) + 1

            print(
                f"Rate limit hit. "
                f"Attempt {attempt + 1}/{max_retries}. "
                f"Retrying in {wait:.2f}s..."
            )

            await asyncio.sleep(wait)

    raise last_error

import json
from typing import Any, Dict


def merge_image_data_into_final_response(
    final_response: str,
    analysis_result: Dict[str, Any],
) -> str:
    """
    Replace placeholder image data in the final LLM response with the actual
    Base64 image data stored in analysis_result.

    Matching priority:
    1. Image title + format
    2. Image title
    3. Image position/order
    """
    if not final_response:
        return final_response

    try:
        parsed_response = json.loads(final_response)
    except (json.JSONDecodeError, TypeError):
        # The final response is plain text, so there are no JSON blocks to update.
        return final_response

    if not isinstance(parsed_response, dict):
        return final_response

    response_blocks = parsed_response.get("blocks", [])
    analysis_blocks = analysis_result.get("blocks", [])

    if not isinstance(response_blocks, list) or not isinstance(analysis_blocks, list):
        return final_response

    actual_image_blocks = [
        block
        for block in analysis_blocks
        if isinstance(block, dict)
        and block.get("type") == "image"
        and block.get("data")
    ]

    if not actual_image_blocks:
        return final_response

    used_image_indexes = set()

    for response_block in response_blocks:
        if not isinstance(response_block, dict):
            continue

        if response_block.get("type") != "image":
            continue

        matching_index = None

        # First try matching by both title and format.
        for index, analysis_block in enumerate(actual_image_blocks):
            if index in used_image_indexes:
                continue

            if (
                analysis_block.get("title") == response_block.get("title")
                and analysis_block.get("format") == response_block.get("format")
            ):
                matching_index = index
                break

        # Fall back to matching only by title.
        if matching_index is None:
            for index, analysis_block in enumerate(actual_image_blocks):
                if index in used_image_indexes:
                    continue

                if analysis_block.get("title") == response_block.get("title"):
                    matching_index = index
                    break

        # Final fallback: use the next unused image.
        if matching_index is None:
            for index in range(len(actual_image_blocks)):
                if index not in used_image_indexes:
                    matching_index = index
                    break

        if matching_index is None:
            continue

        response_block["data"] = actual_image_blocks[matching_index]["data"]
        response_block["encoding"] = actual_image_blocks[matching_index].get(
            "encoding",
            response_block.get("encoding", "base64"),
        )
        response_block["format"] = actual_image_blocks[matching_index].get(
            "format",
            response_block.get("format"),
        )

        used_image_indexes.add(matching_index)

    return json.dumps(parsed_response)

@router.post("/{project_id}/chats/{chat_id}/messages")
async def send_message(
    request: Request,
    project_id: str,
    chat_id: str,
    message: MessageCreate,
    current_user_clerk_id: str = Depends(get_current_user_clerk_id),
):
    """
    ! Logic Flow:
    * 1. Get current user clerk_id
    * 2. Insert the message into the database.
    * 3. Retrieval
    * 4. Generation (Retrieved Context + User Message)
    * 5. Insert the AI Response into the database.
    """
    try:
        # Step 1 : Insert the message into the database.
        message_content = message.content
        message_insert_data = {
            "content": message_content,
            "chat_id": chat_id,
            "clerk_id": current_user_clerk_id,
            "role": MessageRole.USER.value,
        }
        message_creation_result = (
            supabase.table("messages").insert(message_insert_data).execute()
        )

        if not message_creation_result.data:
            raise HTTPException(status_code=422, detail="Failed to create message")

        current_message_id = message_creation_result.data[0]["id"]

        # Step 2: Get project settings to retrieve agent_type
        try: 
            project_settings = await get_project_settings(project_id, current_user_clerk_id)
            agent_type = project_settings["data"].get("agent_type","simple")
        except Exception as e:
            agent_type = "simple"

        chat_history = get_chat_history(chat_id, exclude_message_id = current_message_id)

        if agent_type == "simple":
            agent = create_simple_custom_agent(
                project_id=project_id,
                # model="gpt-4o",
                chat_history=chat_history
            )
        elif agent_type == "agentic":
            checkpointer = request.app.state.checkpointer
            agent = create_supervisor_agent(
                project_id=project_id,
                # model="gpt-4o",
                chat_history=chat_history,
                checkpointer=checkpointer
            )

        print("agent_type: ", agent_type)
        print("message_content: ", message_content)
        # result = await agent.ainvoke({
        #     "messages": [HumanMessage(content=message_content)]
        # })
        trace_id = str(uuid.uuid4())
        if agent_type == "simple":
            try:
                config = {
                    "configurable": {
                        "thread_id": f"{chat_id}:{current_message_id}"
                    },
                    "run_id": trace_id
                }
                result = await agent.ainvoke({
                    "messages": [
                        {"role": "user", "content": message_content}
                    ]
                })
            except Exception as e:
                print(f"ALARM: Agent failed with error: {str(e)}")
                import traceback
                traceback.print_exc()

                raise HTTPException(
                    status_code=500,
                    detail=f"Agent failed while generating response: {str(e)}"
                )
        elif agent_type == "agentic":
            try:
                config = {
                    "configurable": {
                        "thread_id": f"{chat_id}:{current_message_id}"
                    },
                    "run_id": trace_id
                }

                payload = {
                    "messages": [
                        {"role": "user", "content": message_content}
                    ]
                }

                result = await invoke_agent_with_retry(
                    agent=agent,
                    payload=payload,
                    config=config,
                )
            except Exception as e:
                print(f"ALARM: Agent failed with error: {str(e)}")
                import traceback
                traceback.print_exc()

                raise HTTPException(
                    status_code=500,
                    detail=f"Agent failed while generating response: {str(e)}"
                )
        # # Step 3 : Retrieval
        # texts, images, tables, citations = retrieve_context(project_id, message)

        # # Step 4 : Generation (Retrived Context + User Message)
        # final_response = prepare_prompt_and_invoke_llm(
        #     user_query=message, texts=texts, images=images, tables=tables
        # )
        # final_response = result["messages"][-1].content
        print("agent result:", result)
        analysis_result = result.get("analysis_result", {})
        citations = result.get("citations",[])
        messages = result.get("messages", [])

        # if analysis_result:
        #     final_response = json.dumps(analysis_result)
        # else:
        #     final_response = result["messages"][-1].content
    
        raw_final_response = messages[-1].content

        final_response = merge_image_data_into_final_response(
            final_response=raw_final_response,
            analysis_result=analysis_result,
        )

        print("raw final response:", raw_final_response)
        print("final response:", final_response)
        # Step 5: Insert the AI Response into the database.
        ai_response_insert_data = {
            "content": final_response,
            "chat_id": chat_id,
            "clerk_id": current_user_clerk_id,
            "role": MessageRole.ASSISTANT.value,
            "citations": citations,
            "trace_id": trace_id,
        }
        ai_response_creation_result = (
            supabase.table("messages").insert(ai_response_insert_data).execute()
        )
        if not ai_response_creation_result.data:
            raise HTTPException(status_code=422, detail="Failed to create AI response")

        return {
            "message": "Message created successfully",
            "data": {
                "userMessage": message_creation_result.data[0],
                "aiMessage": ai_response_creation_result.data[0],
            },
        }

    except HTTPException as e:
        raise e

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An internal server error occurred while creating message: {str(e)}",
        )


@router.get('/{project_id}/documents/{document_id}/chunks/{chunk_id}')
async def get_chunk(
    project_id: str,
    chunk_id: str,
    document_id: str,
    clerk_id: str = Depends(get_current_user_clerk_id) 
):
    try:
        # Fetch chunk from Supabase where chunk_id AND document_id match
        chunk_result = (
            supabase.table("document_chunks")
            .select("*")
            .eq("id", chunk_id)
            .eq("document_id", document_id)
            .execute()
        )

        if not chunk_result.data:
            raise HTTPException(status_code=404, detail="Chunk not found for the given document")

        return {
            "message": "Chunk fetched successfully",
            "data": chunk_result.data[0]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch chunk: {str(e)}")