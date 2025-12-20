from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from database import supabase, s3_client, BUCKET_NAME
from auth import get_current_user
import uuid


router = APIRouter(
    tags = ['files']
)

class FileUploadRequest(BaseModel):
    filename: str
    file_size: int
    file_type: str

class UrlAddRequest(BaseModel):
    url:str

@router.get('/api/projects/{project_id}/files')
async def get_project_files(
    project_id:str,
    clerk_id:str = Depends(get_current_user)
):
    try: 
        # get all files for this project 
        result = supabase.table("project_documents").select("*").eq("project_id", project_id).eq("clerk_id", clerk_id).order("created_at",desc=True).execute()

        return {
            "message": "Project files retrieved successfully",
            "data": result.data or []
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get project files: {str(e)}")

@router.post("/api/projects/{project_id}/files/upload-url")
async def get_upload_url(
    project_id: str,
    file_request: FileUploadRequest,
    clerk_id: str = Depends(get_current_user)
):
    try:
        # verify project exists and belongs to the user
        projects_result = supabase.table('projects').select("id").eq("id",project_id).eq("clerk_id",clerk_id).execute()
        
        if not projects_result.data:
            raise HTTPException(status_code=400, detail="Project not found or access denied")
        
        # generate unique S3 key
        file_extension = file_request.filename.split('.')[-1] if '.' in file_request.filename else ''
        unique_id = str(uuid.uuid4())
        s3_key = f"projects/{project_id}/documents/{unique_id}.{file_extension}"
        
        # generate presigned url(expire in 1 hr)
        presigned_url = s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": BUCKET_NAME,
                "Key": s3_key,
                "ContentType": file_request.file_type
            },
            ExpiresIn=3600
        )

        # create db record with processing_status="uploading" status
        document_result = supabase.table("project_documents").insert({
            "project_id":project_id,
            "filename": file_request.filename,
            "s3_key": s3_key,
            "file_size": file_request.file_size,
            "file_type": file_request.file_type,
            "processing_status":"uploading",
            "clerk_id": clerk_id
        }).execute()

        if not document_result.data:
            raise HTTPException(status_code=500, detail="Failed to create document record")
        return {
            "message": "Upload URL generated successfully",
            "data": {
                "upload_url": presigned_url,
                "s3_key": s3_key,
                "document": document_result.data[0]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate the presigned URL: {str(e)}")


@router.post('/api/projects/{project_id}/files/confirm')
async def confirm_file_upload(
    project_id: str,
    confirm_request: dict,
    clerk_id: str = Depends(get_current_user)
):
    try:
        s3_key = confirm_request.get("s3_key")
        if not s3_key:
            raise HTTPException(status_code=400, detail="s3_key is required")

        result = supabase.table("project_documents").update({
            "processing_status":"queued"
        }).eq("s3_key",s3_key).eq("project_id",project_id).eq('clerk_id',clerk_id).execute()

        document = result.data[0]

        if not result.data:
            raise HTTPException(status_code-404, detail="Document not found or access denied")

        return {
            "message": "Uploaded confirmed, processing started with Celery",
            "data": document
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to confirm upload:{str(e)}")

@router.post('/api/projects/{project_id}/urls')
async def add_website_url(
    project_id: str,
    url_request: UrlAddRequest,
    clerk_id: str = Depends(get_current_user)
):
    try: 
        url = url_request.url.strip()
        if not url.startswith(('http://','https://')):
            url = "https://" + url
        
        result = supabase.table('project_documents').insert({
            "project_id":project_id,
            "filename": url,
            "s3_key": "",
            "file_size": 0,
            "file_type": "text/html",
            "processing_status":"queued",
            "clerk_id": clerk_id,
            "source_url":url,
            "source_type":"url"
        }).execute()

        if not result.data:
            raise HTTPException(status_code=500, detail="Failed tp create URL record")
        
        # start backgroung processing

        return {
            "message":"url added successfully",
            "data": result.data[0]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add URL: {str(e)}")

@router.delete("/api/projects/{project_id}/files/{file_id}")
async def delete_file(
    project_id: str,
    file_id: str,
    clerk_id: str = Depends(get_current_user)
):
    try:
        file_result = supabase.table("project_documents").select("*").eq("id",file_id).eq("clerk_id",clerk_id).eq("project_id",project_id).execute()
        if not file_result.data:
            raise HTTPException(status_code=4-4, detail="File not found or access denied")

        file_record = file_result.data[0]
        s3_key = file_record["s3_key"]

        # delete from s3 for files not urls
        if s3_key:
            try:
                s3_client.delete_object(Bucket=BUCKET_NAME, Key=s3_key)
                print(f"Deleted from S3:{s3_key}")
            except Exception as s3_error:
                print(f"Failed to delete from S3")

        # delete document from DB
        delete_result = (
            supabase.table("project_documents")
            .delete()
            .eq("id", file_id)
            .execute()
        )
        if not delete_result.data:
            raise HTTPException(status_code=500, detail="Failed to delete file")
        return{
            "message": "File deleted successfully",
            "data": delete_result.data[0]
        }
    except Exception as e:
        raise Exception(status_code=500, detail=f"Failed to delete file:{str(e)}")

