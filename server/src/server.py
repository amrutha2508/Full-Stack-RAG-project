from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.routes.userRoutes import router as userRoutes
from src.routes.projectRoutes import router as projectRoutes
from src.routes.projectFilesRoutes import router as projectFilesRoutes
from src.routes.chatRoutes import router as chatRoutes
from contextlib import asynccontextmanager
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from src.config.index import appConfig

checkpointer = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global checkpointer
    async with AsyncPostgresSaver.from_conn_string(
        appConfig["SUPABASE_POSTGRES_CONNECTION_STRING"]
    ) as saver:
        await saver.setup()
        checkpointer = saver
        app.state.checkpointer = checkpointer
        yield

app = FastAPI(
    title = "RAG Application",
    description = "Backend API for RAG Application",
    version = "1.0.0",
    redirect_slashes=False,
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins = ["*"],
    allow_credentials = True,
    allow_methods = ["*"],
    allow_headers = ["*"],
)

app.include_router(userRoutes, prefix="/api/user")
app.include_router(projectRoutes, prefix="/api/projects")
app.include_router(projectFilesRoutes, prefix="/api/projects")
app.include_router(chatRoutes, prefix="/api/chats")

# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app,host="0.0.0.0",port = 8000, reload=True)
