# Full-Stack-RAG-project

I will be building a Full stack RAG project where the users can upload pdfs, docx, ppts, txt, webscraping files and communicate with a RAG pipeline to get relevant answers.

1. clerk : used as 3rd party authentication service.

## Requirements:
1. As a user, I want to be able to create seperate projects. I should be able to name the project and give it a description.
2. Multi-format document processing: should be able to upload PDFs, DOCX files, PPTs, as well as entire websites, and all this data shoudl be available to chat with.
3. Complete processing transparency: "show how many documents are processed. If AI can't answer a question from the documents, I should ve able to debug easily."
4. Accuracy Vs Speed control: give options to prioritize either quick ansers ot thorough results.



## pgvector: extension required for vector search in PostgreSQL
1. it provides a new data type: vector(n) - in out case n=1536 for OpenAIEmbeddings
2. it provides cosine similarity operator
3. it provides new indexes for fast vector search
### indexes
1. ivfflat - inverted file with flat compression - good for small datasets, faster build time
2. hnsw(most preferable ) - hierarchical navigable samll world - better for larger datasets, more accurate but slower build time.

## tsvector :  for keyword search built into postgreSQL core
1. data type: tsvector, tsquery
2. provides 
### built-in functions:
    1. to_tsvector(config,text):convert text to tsvector - tsvector(stemmed, normalized, positioned) - ex: tsvector('english','your sentence')
    2. websearch_to_tsquery(config, query) - convert web search-style to tsquery config="english"
    3. td_rank(tsvector, tsquery) - calculate relevance ranking
3. provides an index to do full-text-search - gin(Generalized Inverted Index)


## Server-side:
1. Install Poetry as our python manager - run poetry init inside server folder.
2. pyproject.toml - keeps track of all dependencies we install. - poetry add fastapi uvicorn
3. FastAPI
    1. Main class used to create your web application
    2. Handles:Request routing, Dependency injection, Validation (via Pydantic), Automatic OpenAPI/Swagger docs
4. CORSMiddleware
    1. Middleware that implements CORS (Cross-Origin Resource Sharing)
    2. Needed when: Your frontend and backend run on different origins. Example: **Frontend: http://localhost:3000**, **Backend: http://localhost:8000**. Without this middleware, browsers block requests for security reasons.
5. poetry env info --path : exact location of virtual env for this project.
6. Poetry works like this:
    Uses an existing Python interpreter (often Conda’s)
    Creates a virtual environment for your project
    Activates it only when you tell it to
7. Always run poetry add you cmd to run commands using the poetry virtual env. Ex: "**poetry add uvicorn main:app --reload --port:8000**"



## Client-side:
1. install node.js because next.js uses node.js for frontend framework. next.js requires node.js v18+.
2. cmd for creating app using nextjs framework- npx create-next-app@latest
3. to run the client side - **npm run dev**


## supabase db set up
1. you will require docker desktop to run instances of supabase locally.
2. run npx supabase init - creates configuration supabase files for server-side project-> press "N" for Deno and IntelliJ settings
3. npx supabase start - this command 
    1. spind up dockers containers with poSTGREsql, Auth, APIs.
    2. creates supabase backend-service
    3. Gives you the URL and key for supabase.
4. create a .env file with supabase api url and supabse service key(or secret key)
5. install supabase python-dotenv -> cmd: "poetry add supabase python-dotenv"

## Running the DB Migration:
1. create a migration file - each migration file should represent a local change to the database structure. - in our case the tables, indexes, extension creations.
2. we can create a migration by running : supabase migration new [migration_name]
3. add the db schema sql to this migration sql file
4. run the migration : cmd - supabase db reset.
    1. it stops local db.
    2. destroys current db
    3. creates fresh db.
    4. runs all migrations from scratch in order.

## NextJS:
### Conventions to nextJS Routing:
1. All routes must live inside the app folder.
2. Route files myst be named page.js or page.tsx
3. Each folder represents a segment of the URL path.






