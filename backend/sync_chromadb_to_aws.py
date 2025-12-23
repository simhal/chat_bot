#!/usr/bin/env python3
"""
Sync articles from local ChromaDB to AWS ChromaDB via the admin API.

Usage:
    python sync_chromadb_to_aws.py --api-url https://chat.aiqufin.com --token <jwt_token>
"""

import requests
import json
import argparse
from typing import List, Dict


def get_local_chromadb_articles() -> List[Dict]:
    """Fetch all articles from local ChromaDB."""
    # Get collection info
    collections_url = "http://localhost:8001/api/v2/tenants/default_tenant/databases/default_database/collections"
    resp = requests.get(collections_url)
    collections = resp.json()

    # Find research_articles collection
    research_collection = None
    for col in collections:
        if col["name"] == "research_articles":
            research_collection = col
            break

    if not research_collection:
        print("research_articles collection not found")
        return []

    collection_id = research_collection["id"]

    # Fetch all documents
    get_url = f"http://localhost:8001/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/get"
    resp = requests.post(get_url, json={
        "limit": 100,
        "include": ["documents", "metadatas"]
    })

    data = resp.json()

    articles = []
    for i, doc_id in enumerate(data.get("ids", [])):
        article_id = int(doc_id.replace("article_", ""))
        content = data["documents"][i] if data.get("documents") else ""
        metadata = data["metadatas"][i] if data.get("metadatas") else {}

        articles.append({
            "article_id": article_id,
            "headline": metadata.get("headline", ""),
            "content": content,
            "topic": metadata.get("topic", ""),
            "author": metadata.get("author", ""),
            "editor": metadata.get("editor", ""),
            "keywords": metadata.get("keywords", ""),
            "status": metadata.get("status", "published")
        })

    return articles


def sync_to_aws(articles: List[Dict], api_url: str, token: str) -> Dict:
    """Sync articles to AWS via the admin API."""
    url = f"{api_url}/api/content/admin/sync-articles-bulk"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    payload = {"articles": articles}

    print(f"Syncing {len(articles)} articles to {url}")
    resp = requests.post(url, json=payload, headers=headers)

    if resp.status_code == 200:
        return resp.json()
    else:
        print(f"Error: {resp.status_code}")
        print(resp.text)
        return {"error": resp.text}


def main():
    parser = argparse.ArgumentParser(description="Sync ChromaDB articles to AWS")
    parser.add_argument("--api-url", required=True, help="AWS API URL (e.g., https://chat.aiqufin.com)")
    parser.add_argument("--token", required=True, help="JWT authentication token")
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be synced")

    args = parser.parse_args()

    print("Fetching articles from local ChromaDB...")
    articles = get_local_chromadb_articles()

    print(f"Found {len(articles)} articles:")
    for article in articles:
        print(f"  - ID {article['article_id']}: {article['headline'][:50]}... (topic: {article['topic']})")

    if args.dry_run:
        print("\nDry run - not syncing to AWS")
        return

    print("\nSyncing to AWS...")
    result = sync_to_aws(articles, args.api_url, args.token)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
