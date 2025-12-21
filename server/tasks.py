from celery import Celery
from database import supabase
import time

# create Celery app
celery_app = Celery(
    'document_processor',# name of Celery app
    broker="redis://localhost:6379/0", # port where redis(broker) is listening to - where tasks are queued
    backend="redis://localhost:6379/0" # location where we want to store the result of a particular task 
)

@celery_app.task
def process_document(document_id:str):
    """
        simple test task
    """
    # step1: update status to processing

    supabase.table('project_documents').update({
        "processing_status": "processing"
    }).eq("id",document_id).execute()
    print(f"Processing document {document_id}")

    # step2: simulate actual work
    time.sleep(5)

    # step3: update status to completed
    supabase.table('project_documents').update({
        "processing_status": "completed"
    }).eq("id",document_id).execute()
    print(f"Celery task completed for document: {document_id}")
    
    return{
        "status": "success",
        "document_id": document_id
    }
