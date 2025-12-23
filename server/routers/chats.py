from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from database import supabase
from auth import get_current_user

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
        messages_result = supabase.table('messages').select('*').eq('chat_id',chat_id).order('created_at',desc=True).execute()
        chat['messages'] = messages_result.data or []
        return{
            "message":"Chat retrieved successfully",
            "data": chat
        }
    except Exception as e:
        raise 