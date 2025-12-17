from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from dotenv import load_dotenv
import os
from routers import users

load_dotenv()

supabase_url = os.getenv("SUPABASE_API_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

if not supabase_key or not supabase_url:
    raise ValueError('missing supabase credentials in environment variables')

supabase: Client = create_client(supabase_url,supabase_key) 

app = FastAPI(
    title = "RAG Application",
    description = "Backend API for RAG Application",
    version = "1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["http://localhost:3000"],
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
)
app.include_router(users.router)

@app.get("/")
async def root():
    return {"message":"RAG Application running"}

@app.get("/health")
async def health_check():
    return{
        "status": "healthy",
        "version": "1.0.0"
    }

@app.get('/posts')
async def get_all_posts():
    try:
        result = supabase.table("posts").select("*").order("created_at",desc = True).execute()
        return result.data
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,host="0.0.0.0",port = 8000, reload=True)


    