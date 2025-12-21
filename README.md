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
7. Always run poetry run you cmd to run commands using the poetry virtual env. Ex: "**poetry run uvicorn main:app --reload --port 8000**"



## Client-side:
1. install node.js because next.js uses node.js for frontend framework. next.js requires node.js v18+.
2. cmd for creating app using nextjs framework- npx create-next-app@latest
3. to run the client side - **npm run dev**


## supabase db set up
1. you will require docker desktop to run instances of supabase locally.
2. run npx supabase init - creates configuration supabase files for server-side project-> press "N" for Deno and IntelliJ settings
3. **npx supabase start** - this command 
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

## Auth Provider:Clerk
Clerk = “Auth-as-a-service” that plugs directly into your frontend and backend. If we are not using clerk we have to implement
1. Password hashing and validation.
2. JWT token generation and verification.
3. Session Management.
4. Email verification flows.
5. Password reset functionality.
6. Social OAuth integrations.
7. Security Best Practices

### Implementation:
1. Install @clerk/nextjs inside client directory
2. set clerk api keys in .env inside client folder.
3. Add middleware.ts file inside of the src directory - it helps enable authentication and is where you will configure your protected routes. It runs everytime your page loads. It sits between users request and pages response.
4. add clerkprovider component to your root layout - root layout(layout.tsx) is the first entry point for the entire nextjs application. If we wrap the components with this clerk provider component, it means that all of clerks methods are going to be available to use in all the different next js files we will write in the future.

### SignIn and SignUp pages
1. Think of [[...sign-in]] as: “Give me /sign-in and any deeper route under it, and I’ll handle it myself.”
2. create api endpoint toc reate a user record on user signup - clerk-webhooks - notifies backend-server whenever a event occurs(create/update/delete an account).
3. webhook is a way for one sistem to notify another system when something happens- backend-only communication
#### What does “provide an endpoint to Clerk webhook” mean?
It means two separate things must exist:
1. You write an API endpoint in your backend code
2. You register that endpoint URL in the Clerk Dashboard
3. Inside your code (main.py) - This is where you define the endpoint. This does only one thing, it tells your server:
“If an HTTP POST comes to /create-user, run this function.”
4. nside the Clerk Dashboard - This is where you tell Clerk: “Whenever a certain event happens, send it to THIS URL.”

### routes files:
1. we will create a routes folder to arrange all the api files.
2. inrder to be able to import from this routes folder we have to convert it inot a package which can be done by adding a file __init__.py in the folder  

### some points regarding the client folders
1. import { Sidebar } from "@/components/layout/Sidebar"; the @ directs towards app directory folder
2. the "children" found in the layout.tsx refers to the page component(page.tsx)
3. Before letting the user access the children component we are checking if the usr is logged in using auth in the layout.tsx.

### JWT
1. for managing JWT related stuff install clerk_backend_api - poetry add clerk_backend_api
2. const { getToken, isLoaded, isSignedIn, sessionId, userId } = useAuth() - this hook gives us access to the jwt token, we an make the api calls to the server only if we have this token as it will be checking for authentication befor the api calls  

## HTTP requests
### What is headers in fetch?
1. headers is metadata sent along with the HTTP request.
2. Think of it like the envelope around a letter 📩:
    1. The body = the letter (actual data)
    2. Headers = instructions about how to read the letter and who sent it

Ex: POST /api/projects
Authorization: Bearer eyJhbGci...
Content-Type: application/json
### Why headers are initialized differently in get vs post
1. GET usually does not send a body, So you don’t need Content-Type, You only add Authorization if needed
2. POST sends data in the body, The server must know how to parse it
3. method- HTTP verb -Tells backend what action, GET → read, POST → create, DELETE → remove, FastAPI routes are mapped to these verbs.
4. headers, Metadata about the request, Auth info, Content format, Language, cookies, etc.
5. body, Actual data being sent, Must be a string for JSON, Parsed by backend using Content-Type

## nextjs react server and client components:
React components can now be server components or client components depending on where they execute.
1. Server components = render HTML safely and efficiently on the server.
2. Client components = handle interactive behavior in the browser.
You still use React to build the UI for both. Next.js just lets you decide which components run where, for performance and security.
3. A callback function is a function that is passed as an argument to another function or component and is called later when something happens. Ex: onClose={()=>setSelectedDocumentId(null)}

## S3 
1. We will be using S3 providers(tigris) instead of aws S3. This we behave same like S3 with all access keys and methods.
2. Inorder to get presigned urls we need the generate presigned url method provided by the aws SDK (Boto3 - an aws SDK for python that allows developers to write code to interact with AWS services like S3 and EC2).

## Background processing stack (Redis, celery, fastapi)
1. **celery**: most popular python task queue. works seemlessly with FastAPI, handles retries, failurews and task schedulun automatically. easy to monitor and debug, scales from 1 worker to 1000+ workers
2. **Redis**: redis is a superfast notepad that lives in your computers memory. it is a simple db that stores key-value pairs. everything is on RAM not on disk. reading/writing is nearly instant. can be used for caching, message queues(real time messages between programs), real time counters.
3. summary:
    1. Celery is the executor of the tasks.
    2. Redis provides a queue data structure that is perfect for storing tasks to be taken up. This can ve thought of as the middleware or the broker between fastapi and celery.
    3. As soon as celery worker finished with a task, the result can be stored either in redis itself or postgres. 
4. installations
    1. redis is not a python package, it is a separate service that needs to run on its own = 
    brew install redis (in terminal)
    2. poetry add redis - celery app can use this to connect to redis server.
    3. Celery is a python package = 
    "poetry add celery" , to start a celery worker = "celery -A tasks worker --loglevel=info --pool=threads"
5. the task_item's(that is going to be put inside of redis) structure is:
    task_data = {
        "task" : "process_document",
        "args" : [file_path],
        "id" : "abc-123-def"
    }
    this is created by "delay" method ex:process_document.delay(document_id)
6. What does .delay() do (.delay() comes from celery)? task_id = process_document.delay(document_id)
    1. it Enqueue the Celery task
    2. This line: ❌ Does NOT execute process_document, ✅ Sends a message to Redis, ✅ Returns immediately
    3. Internally, Celery does:         
        1. Serialize: Task name (process_document) Args (document_id)
        2. Publish message to Redis queue
        3. Return an AsyncResult
7. whenever we make changes to celery app code we have to manually stoop and restarte the celery server for the changes to be reflected unlike fastapi where the changes are reflected automatically.

