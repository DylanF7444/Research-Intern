import sqlite3
from neo4j import GraphDatabase
import re

# Connect
NEO4J_URI = "neo4j://127.0.0.1:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "Think305"

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# SQLite setup
conn = sqlite3.connect("DataBase.db")
cursor = conn.cursor()
rows = cursor.execute("SELECT * FROM pulls").fetchall()
columns = [col[0] for col in cursor.description]

def normalize_number(s):
    return int(str(s).replace("−", "-").replace("+", "").replace(",", "").strip())

# insert PullRequest data
def insert_pull(tx, pull):
    added = normalize_number(pull["added"])
    removed = normalize_number(pull["removed"])
    tx.run("""
        MERGE (p:PullRequest {id: $id})
        SET p.comments = $comments,
            p.added = $added,
            p.removed = $removed,
            p.commits = $commits,
            p.files = $files,
            p.links = $links
    """, 
    id=int(pull["pullNumber"]),
    comments=pull["comments"],
    added=added,
    removed=removed,
    commits=pull["commits"],
    files=pull["files"],
    links=pull["links"]
    )
    source_id=int(pull["pullNumber"])
    linked_ids = [
        int(match) for match in re.findall(r"\b\d+\b", pull.get("links", ""))
    ]

    for target_id in linked_ids:
        tx.run("""
            MERGE (target:PullRequest {id: $target_id})
            MERGE (source:PullRequest {id: $source_id})
            MERGE (source)-[:REFERS_TO]->(target)
        """, {
            "source_id": source_id,
            "target_id": target_id
        })


# Load each row into Neo4j
with driver.session() as session:
    for row in rows:
        pull = dict(zip(columns, row))
        session.execute_write(insert_pull, pull)


driver.close()
conn.close()
