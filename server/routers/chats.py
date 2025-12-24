from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import supabase
from auth import get_current_user
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

# initialize llm for response 
llm = ChatOpenAI(model = "gpt-4o", temperature=0)

router = APIRouter(
    tags = ["chats"]
)

class ChatCreate(BaseModel):
    title: str
    project_id: str


@router.post('/api/chats')
async def create_chat(
    chat: ChatCreate,
    clerk_id:str = Depends(get_current_user)
):
    try: 
        # get all files for this project 
        result = supabase.table("chats").insert({
            "title":chat.title,
            "project_id":chat.project_id,
            "clerk_id":clerk_id
        }).execute()

        return {
            "message": "chat created successfully",
            "data": result.data[0]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create chat: {str(e)}")

@router.delete('/api/chats/{chat_id}')
async def delete_chat(
    chat_id: str,
    clerk_id: str = Depends(get_current_user)
):
    try:
        deleted_result = supabase.table('chats').delete().eq("id",chat_id).eq('clerk_id',clerk_id).execute()
        if not deleted_result:
            raise HTTPException(status_code=404, detail="Chat not found or access denied")
        return {
            "message":"chat deleted successfully",
            "data": deleted_result.data[0]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete chat: {str(e)}")

@router.get('/api/chats/{chat_id}')
async def get_chat(
    chat_id :str,
    clerk_id: str = Depends(get_current_user)
):
    try: 
        result = supabase.table('chats').select('*').eq('id',chat_id).eq('clerk_id',clerk_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="chat not found or access denied")
        chat = result.data[0]
        messages_result = supabase.table('messages').select('*').eq('chat_id',chat_id).order('created_at',desc=False).execute()
        chat['messages'] = messages_result.data or []
        return{
            "message":"Chat retrieved successfully",
            "data": chat
        }
    except Exception as e:
        raise 
class sendMessageRequest(BaseModel):
    content: str

@router.post('/api/projects/{projectId}/chats/{chat_id}/messages')
async def send_message(
    chat_id: str,
    request: sendMessageRequest,
    clerk_id: str = Depends(get_current_user)
):
    try:
        message = request.content
        print(f"new message: {message[:50]}...")
        print("saving user message...")
        user_message_result = supabase.table('messages').insert({
            "chat_id": chat_id,
            "content": message,
            "role": "user",
            "clerk_id": clerk_id
        }).execute()

        user_message = user_message_result.data[0]
        print(f"user message saved: {user_message['id']}")

        print(f"calling llm...")
        messages = [
            SystemMessage(content="You are a helpful AI assistant. Provide clear, concise, and accurate responses."),
            HumanMessage(content=message)
        ]
        response = llm.invoke(messages)
        ai_response = response.content

        ai_message_result = supabase.table('messages').insert({
            "chat_id":chat_id,
            "content":ai_response,
            "role":"assistant",
            "clerk_id":clerk_id
        }).execute()

        ai_message = ai_message_result.data[0]
        return{
            "message": "message sent successfully",
            "data": {
                "userMessage": user_message,
                "aiMessage": ai_message
            }
        }
    except Exception as e:
        print(f" Error in send_message:{str(e)}")
        raise HTTPException(status_code=500, detaile=str(e))