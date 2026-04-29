import logging

db_logger = logging.getLogger(__name__)

def connect():
    db_logger.info("database connection success")