import chromadb

client = chromadb.PersistentClient(path="./chroma_data")  # same path you used to store data

collection = client.get_collection("openssl_openssl_prs")

from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")
embedding = model.encode(["memory leak"]).tolist()

results = collection.query(
    query_embeddings=embedding,
    n_results=5,
    

)


for doc, metadata, id_ in zip(results['documents'][0], results['metadatas'][0], results['ids'][0]):
    print(f"\n--- Result {id_} ---")
    print("Document:", doc[:300])  # truncate for display
    print("Metadata:", metadata)
