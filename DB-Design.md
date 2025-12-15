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


## RLS policies

**UPDATE is the operation where BOTH `USING` and `WITH CHECK` are evaluated**, and that’s exactly why it’s confusing. Let’s make it very concrete and step-by-step.

---

### The key idea (one sentence)

> **UPDATE = select existing rows (`USING`) + validate new row values (`WITH CHECK`)**

Think of UPDATE as **two separate questions** the database asks.

---

### Step-by-step: what happens during UPDATE

When a user runs:

```sql
UPDATE clients
SET user_id = 'some-other-user'
WHERE id = 'row-123';
```

Postgres evaluates **RLS in two phases**.

---

#### 🔹 Phase 1: `USING` — *Can I target this row?*

```sql
USING (auth.uid() = user_id)
```

This answers:

> “Am I allowed to touch this existing row?”

* Checks the **current row values**
* Happens **before** any changes
* If this fails → row is invisible → update is skipped

📌 If `USING` fails, the row behaves as if it doesn’t exist.

---

#### 🔹 Phase 2: `WITH CHECK` — *Is the updated row valid?*

```sql
WITH CHECK (auth.uid() = user_id)
```

This answers:

> “After the update, is this row allowed to exist?”

* Checks the **new row values**
* Happens **after** the update expression is applied
* If this fails → update is rejected

📌 Prevents users from changing protected fields.

---

### Why UPDATE needs both (very important)

#### ❌ Only `USING` (dangerous)

```sql
FOR UPDATE
USING (auth.uid() = user_id);
```

User owns the row → update allowed
But they can do this:

```sql
UPDATE clients
SET user_id = 'attacker-id';
```

Because:

* `USING` checks **old value**
* No check on the **new value**

❌ Ownership hijack

---

#### ❌ Only `WITH CHECK` (insufficient)

```sql
FOR UPDATE
WITH CHECK (auth.uid() = user_id);
```

Postgres still needs to know:

> “Which rows can I update?”

Without `USING`, the row may not even be visible to update.

---

#### ✅ Correct UPDATE policy

```sql
FOR UPDATE
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);
```

Meaning:

* You can update **only your rows**
* You cannot change them to belong to someone else

---

### INSERT vs UPDATE vs DELETE (clear comparison)

| Operation | USING | WITH CHECK | Why                    |
| --------- | ----- | ---------- | ---------------------- |
| SELECT    | ✅     | ❌          | Only reading           |
| INSERT    | ❌     | ✅          | No existing row        |
| UPDATE    | ✅     | ✅          | Existing row + new row |
| DELETE    | ✅     | ❌          | Row disappears         |

---

### Visual mental model

```text
UPDATE request
   |
   v
[ USING ]  → Can I see & target this row?
   |
   v
Apply changes
   |
   v
[ WITH CHECK ] → Is the final row allowed?
```

Both must pass.

---

### One more concrete example (teams)

```sql
FOR UPDATE
USING (user_id IN (SELECT user_id FROM team_members WHERE team_id = clients.team_id))
WITH CHECK (user_id IN (SELECT user_id FROM team_members WHERE team_id = clients.team_id));
```

This ensures:

* Only team members can update
* The row can’t be reassigned to another team

---

### TL;DR (remember this)

* **USING** → checks the **old row**
* **WITH CHECK** → checks the **new row**
* **UPDATE uses BOTH**
* Missing either causes security bugs


