from supabase import create_client, Client
from dotenv import load_dotenv
import os

load_dotenv()

supabase_url = os.getenv("SUPABASE_API_URL")
supabase_key = os.getenv("SUPABASE_SERVICE_KEY")

if not supabase_key or not supabase_url:
    raise ValueError('missing supabase credentials in environment variables')

supabase: Client = create_client(supabase_url,supabase_key) 