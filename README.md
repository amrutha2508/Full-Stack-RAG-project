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





