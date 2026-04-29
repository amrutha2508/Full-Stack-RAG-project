import logging
# import database
# from fastapi import FastAPI


# =============================================================
# HANDLERS
# handlers - are objects that decide where to send log messages
# streamhandler - sends logs to terminal/console
# FileHandler - sends logs to a file
# =============================================================

# console_handler = logging.StreamHandler()
# file_handler = logging.FileHandler("app.log")

# # logging.basicConfig(level=logging.WARNING)
# logging.basicConfig(
#     level=logging.DEBUG, 
#     format="%(asctime)s %(levelname)s %(message)s",
#     # filename="app.log"
#     handlers=[console_handler, file_handler] 
# )

# logging.debug("debug")
# logging.info("info")
# logging.warning("warning")
# logging.error("error")
# logging.critical("critical")


# =============================================================
# CUSTOM/CHILD LOGGERS
# =============================================================

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(name)s %(asctime)s- %(levelname)s - %(message)s"
# )

# logger = logging.getLogger(__name__) # child/custom logger - it inherits config properties from the root - takes it from the module/file name

# logger.info("Application started")
# database.connect()
# logger.info("Application ended")

# =============================================================
# EXCEPTION HANDLING
# =============================================================

# app = FastAPI()

# @app.get("/divide")
# def divide(a:int, b:int):
#     try:
#         result = a/b
#         return{"result":result}
#     except Exception as e:
#         # logger.error("Division Failed", exc_info = True) # provides full traceback info of the error
#         logger.exception("Division Failed")

# =============================================================
# STRUCTURED LOGGING (JSON) :
# prefered for filtering aggregation operations
# context binding
# =============================================================
import structlog

structlog.configure(
    processors = [ # chain of functions that transform the log entries
        # structlog.processors.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ]
)
logger = structlog.getLogger()
app = FastAPI()

# syntax - logger.info("event_name", user_id = user_id, .... as many key values pairs can be provided for context)
@app.get("/users/{user_id}")
async def root():
    logger.info("USER logged In",user_id = user_id)
    return {"user_id":user_id, "name":"John"}

# =============================================================
# CONTEXT BINDING
# Python contextvars = contex variables to automatically share context across your entire request
# =============================================================

structlog.contextvars.clear_contextvars()
structlog.contextvars.bind_contextvars(user_id=user_id)