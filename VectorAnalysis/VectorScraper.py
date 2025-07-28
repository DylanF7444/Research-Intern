import os
import json
import requests
from sentence_transformers import SentenceTransformer
import chromadb
from tqdm import tqdm



GITHUB_TOKEN = "your_token"
REPO_OWNER = "openssl"
REPO_NAME = "openssl"
PER_PAGE = 50
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
PROGRESS_FILE = "processed_prs.json"



headers = {"Authorization": f"token {GITHUB_TOKEN}"} if GITHUB_TOKEN else {}
model = SentenceTransformer(EMBEDDING_MODEL_NAME)
client = chromadb.PersistentClient(path="./chroma_data")  # Or another path

collection = client.get_or_create_collection(name=f"{REPO_OWNER}_{REPO_NAME}_prs")


if os.path.exists(PROGRESS_FILE):
    with open(PROGRESS_FILE, "r") as f:
        processed_prs = set(json.load(f))
else:
    processed_prs = set()



def get_all_prs():
    prs = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls"
        params = {"state": "all", "per_page": PER_PAGE, "page": page}
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        if not data:
            break
        prs.extend(data)
        page += 1
        print(page)

    return prs

def get_pr_files(pr_number):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}/files"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()

def get_pr_issue_comments(pr_number):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues/{pr_number}/comments"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()

def get_pr_review_comments(pr_number):
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/pulls/{pr_number}/comments"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()

def sanitize_metadata(raw_meta):
    clean_meta = {}
    for key, value in raw_meta.items():
        if isinstance(value, list):
            clean_meta[key] = ", ".join(map(str, value))
        elif isinstance(value, (str, int, float, bool)):
            clean_meta[key] = value
        elif value is None:
            clean_meta[key] = "null"  # or skip: continue
        else:
            clean_meta[key] = str(value)
    return clean_meta

def chunk_intent(pr):
    title = pr.get("title") or ""
    body = pr.get("body") or ""
    content = f"Title: {title}\n\n{body}"
    metadata = sanitize_metadata({
        "pr_id": pr["number"],
        "repo": f"{REPO_OWNER}/{REPO_NAME}",
        "type": "intent",
        "state": pr.get("state"),
        "merged": pr.get("merged_at") is not None,
        "author": pr["user"]["login"] if pr.get("user") else None,
        "files_changed": [f["filename"] for f in pr.get("files", [])],
        "num_comments": pr.get("comments", 0),
        "referenced_prs": [],  # Optional future feature
    })
    return {"id": f"{pr['number']}-intent", "document": content, "metadata": metadata}

def chunk_diff(pr_number, pr_files):
    chunks = []
    for file in pr_files:
        patch = file.get("patch")
        if not patch:
            continue
        doc = f"Diff for file {file['filename']}:\n{patch}"
        metadata = sanitize_metadata({
            "pr_id": pr_number,
            "repo": f"{REPO_OWNER}/{REPO_NAME}",
            "type": "diff",
            "file": file["filename"],
            "state": None,
            "author": None,
        })
        chunk = {
            "id": f"{pr_number}-diff-{file['filename'].replace('/', '_')}",
            "document": doc,
            "metadata": metadata
        }
        chunks.append(chunk)
    return chunks

def chunk_comments(pr_number, issue_comments, review_comments):
    chunks = []
    for i, comment in enumerate(issue_comments):
        doc = comment.get("body", "")
        if not doc.strip():
            continue
        metadata = sanitize_metadata({
            "pr_id": pr_number,
            "repo": f"{REPO_OWNER}/{REPO_NAME}",
            "type": "comment",
            "state": None,
            "author": comment.get("user", {}).get("login"),
            "comment_type": "issue_comment",
            "created_at": comment.get("created_at"),
        })
        chunks.append({
            "id": f"{pr_number}-issue-comment-{i}",
            "document": doc,
            "metadata": metadata
        })

    for i, comment in enumerate(review_comments):
        doc = comment.get("body", "")
        if not doc.strip():
            continue
        metadata = sanitize_metadata({
            "pr_id": pr_number,
            "repo": f"{REPO_OWNER}/{REPO_NAME}",
            "type": "comment",
            "state": None,
            "author": comment.get("user", {}).get("login"),
            "comment_type": "review_comment",
            "created_at": comment.get("created_at"),
            "path": comment.get("path"),
            "position": comment.get("position"),
        })
        chunks.append({
            "id": f"{pr_number}-review-comment-{i}",
            "document": doc,
            "metadata": metadata
        })

    return chunks
def check_data():
    client = chromadb.PersistentClient(path="./chroma_data")
    collection = client.get_collection("openssl_openssl_prs")

    # Query some data
    results = collection.query(
        query_texts=["test"],  # sample query text
        n_results=5
    )

    print(results)

# --- Main Loop ---

def main():
    print("Fetching all PRs...")
    prs = get_all_prs()
    print(f"Found {len(prs)} PRs.")

    for pr in tqdm(prs):
        pr_number = pr["number"]

        if pr_number in processed_prs:
            continue

        try:
            pr_files = get_pr_files(pr_number)
            pr["files"] = pr_files
            issue_comments = get_pr_issue_comments(pr_number)
            review_comments = get_pr_review_comments(pr_number)

            # Build chunks
            chunks = []
            chunks.append(chunk_intent(pr))
            chunks.extend(chunk_diff(pr_number, pr_files))
            chunks.extend(chunk_comments(pr_number, issue_comments, review_comments))

            # Embed and add to DB
            documents = [c["document"] for c in chunks]
            embeddings = model.encode(documents).tolist()
            metadatas = [c["metadata"] for c in chunks]
            ids = [c["id"] for c in chunks]

            collection.add(
                documents=documents,
                embeddings=embeddings,
                metadatas=metadatas,
                ids=ids
            )


            # Save progress
            processed_prs.add(pr_number)
            with open(PROGRESS_FILE, "w") as f:
                json.dump(list(processed_prs), f)

        except Exception as e:
            print(f"\n⚠️ Error processing PR #{pr_number}: {e}")
            continue

if __name__ == "__main__":
    main()
