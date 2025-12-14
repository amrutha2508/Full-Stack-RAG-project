# DB design
## Tables
1. users {
  id uuid pk
  clerk_id string unique "not null"
  created_at timestamp
}

2. projects {
  id uuid pk
  name string "not null"
  description string
  clerk_id string fk "not null"
  create_at timestamp
}

3. project_settings {
  id uuid pk
  project_id uuid fk "not null"
  embedding_model string "not null"
  rag_strategy string "not null"
  agent_type string "not null"
  chunks_per_search integer "not null"
  final_context_size integer "not null"
  similarity_threshold decimal "not null"
  number_of_queries integer "not null"
  vector_weight decimal "not null"
  keyword_weight decimal "not null"
  reranking_enabled boolean "not null"
  reranking_model string "not null"
  created_at timestamp "not null"
}

4. project_documents {
  id uuid pk
  project_id uuid fk "not null"
  filename string "not null"
  s3_key string "not null"
  file_size integer "not null"
  file_type string "not null"
  processing_status string "default: 'pending"
  processing_details json
  task_id string
  source_type string "default: 'file"
  source_url string
  clerk_id string fk "not null"
  created_at timestamp
}

5. document_chunks {
  id uuid pk
  document_id uuid fk "not null"
  content string "not null"
  chunk_index integer "not null"
  page_number integer 
  char_count integer "not null"
  type json "not null"
  original_content json "not null"
  embeddings "vector(1536)"
  fts tsvector
  created_at timestamp
}

6. chats {
  id uuid pk 
  title string "not null"
  project_id uuid fk "not null"
  clerk_id string fk "not null"
  created_at timestamp
}

7. messages {
  id uuid pk
  content string "not null"
  role string "default: 'user'"
  chat_id uuid fk "not null"
  clerk_id string fk "not null"
  citations json "default: '[]'"
  trace_id string 
  created_at timestamp
}

## fk relations
users.clerk_id < projects.clerk_id
users.clerk_id < chats.clerk_id
users.clerk_id < messages.clerk_id
users.clerk_id < project_documents.clerk_id
projects.id - project_settings.project_id
projects.id < project_documents.project_documents
projects.id < chats.project_id
project_documents.id < document_chunks.document_id
chats.id < messages.chat_id


![Alt text]('./images/DB-Design.md')
