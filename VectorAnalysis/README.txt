VectorScraper.py retrieves all closed PR's from https://github.com/openssl/openssl/ and inserts them into a chromadb database. The model used to embed these PR's is "all-MiniLM-L6-v2".

PR's were broken down into chunks based off PR intent (body+description), file diffs, and comments.
Metadata of PR number, author, creation date, etc. was included with each chunk when relevant.
