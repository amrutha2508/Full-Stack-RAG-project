from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import os
from routers import users, projects, files, chats

load_dotenv()

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
app.include_router(projects.router)
app.include_router(files.router)
app.include_router(chats.router)

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


    