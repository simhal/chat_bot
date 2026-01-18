"""Vector database service using ChromaDB for semantic search."""

import chromadb
from chromadb.config import Settings as ChromaSettings
from typing import List, Dict, Optional
import logging
from openai import OpenAI

from config import settings

logger = logging.getLogger("uvicorn")

# Lazy initialization
_chroma_client = None
_collection = None
_openai_client = None
_vectordb_initialized = False
_vectordb_failed = False


def _get_chroma_client():
    """Lazy initialization of ChromaDB client."""
    global _chroma_client, _collection, _vectordb_initialized, _vectordb_failed

    if _vectordb_initialized:
        return _chroma_client, _collection

    if _vectordb_failed:
        return None, None

    try:
        logger.info("Vector DB: Initializing ChromaDB connection")
        logger.info(f"  Host: {settings.chroma_host}")
        logger.info(f"  Port: {settings.chroma_port}")

        _chroma_client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(
                anonymized_telemetry=False
            )
        )

        # Test connection
        _chroma_client.heartbeat()

        # Get or create collection
        _collection = _chroma_client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={
                "description": "Research articles with semantic embeddings",
                "hnsw:space": "cosine"  # Cosine similarity for embeddings
            }
        )

        _vectordb_initialized = True
        logger.info(f"✓ Vector DB: ChromaDB connected successfully")
        logger.info(f"  Collection: {settings.chroma_collection_name}")
        logger.info(f"  Documents: {_collection.count()}")

        return _chroma_client, _collection

    except Exception as e:
        logger.error(f"✗ Vector DB: ChromaDB connection failed: {e}")
        logger.warning("  Semantic search will be disabled")
        _vectordb_failed = True
        _vectordb_initialized = True
        return None, None


def _get_openai_client():
    """Lazy initialization of OpenAI client for embeddings."""
    global _openai_client

    if _openai_client:
        return _openai_client

    if not settings.openai_api_key:
        logger.warning("OpenAI API key not configured - embeddings unavailable")
        return None

    try:
        _openai_client = OpenAI(api_key=settings.openai_api_key)
        logger.info(f"✓ OpenAI embeddings initialized: {settings.openai_embedding_model}")
        return _openai_client
    except Exception as e:
        logger.error(f"✗ OpenAI client initialization failed: {e}")
        return None


class VectorService:
    """Service for vector database operations."""

    @staticmethod
    def _generate_embedding(text: str) -> Optional[List[float]]:
        """Generate embedding vector for text using OpenAI."""
        client = _get_openai_client()
        if not client:
            return None

        try:
            response = client.embeddings.create(
                input=text,
                model=settings.openai_embedding_model
            )
            return response.data[0].embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            return None

    @staticmethod
    def _make_document_id(article_id: int) -> str:
        """Create consistent document ID from article ID."""
        return f"article_{article_id}"

    @staticmethod
    def add_article(
        article_id: int,
        headline: str,
        content: str,
        metadata: Dict
    ) -> bool:
        """
        Add article to vector database.

        Args:
            article_id: Article ID from PostgreSQL
            headline: Article headline
            content: Article content
            metadata: Additional metadata (topic, author, editor, etc.)

        Returns:
            True if successful, False otherwise
        """
        _, collection = _get_chroma_client()
        if collection is None:
            logger.warning(f"Vector DB unavailable - skipping article {article_id}")
            return False

        try:
            # Combine headline and content for embedding
            text_to_embed = f"{headline}\n\n{content}"

            # Generate embedding
            embedding = VectorService._generate_embedding(text_to_embed)
            if not embedding:
                logger.error(f"Failed to generate embedding for article {article_id}")
                return False

            # Add to collection
            doc_id = VectorService._make_document_id(article_id)
            collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[{
                    "article_id": article_id,
                    "headline": headline,
                    "topic": metadata.get("topic", ""),
                    "author": metadata.get("author") or "",
                    "editor": metadata.get("editor") or "",
                    "keywords": metadata.get("keywords") or "",
                    "created_at": str(metadata.get("created_at", "")),
                    "updated_at": str(metadata.get("updated_at", "")),
                }]
            )

            logger.info(f"✓ Added article {article_id} to vector DB")
            return True

        except Exception as e:
            logger.error(f"Error adding article {article_id} to vector DB: {e}")
            return False

    @staticmethod
    def update_article(
        article_id: int,
        headline: str,
        content: str,
        metadata: Dict
    ) -> bool:
        """Update article in vector database."""
        _, collection = _get_chroma_client()
        if collection is None:
            return False

        try:
            # Delete old version
            VectorService.delete_article(article_id)

            # Add new version
            return VectorService.add_article(article_id, headline, content, metadata)

        except Exception as e:
            logger.error(f"Error updating article {article_id} in vector DB: {e}")
            return False

    @staticmethod
    def delete_article(article_id: int) -> bool:
        """Delete article from vector database."""
        _, collection = _get_chroma_client()
        if collection is None:
            return False

        try:
            doc_id = VectorService._make_document_id(article_id)
            collection.delete(ids=[doc_id])
            logger.info(f"✓ Deleted article {article_id} from vector DB")
            return True
        except Exception as e:
            logger.error(f"Error deleting article {article_id} from vector DB: {e}")
            return False

    @staticmethod
    def semantic_search(
        query: str,
        topic: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Perform semantic search using vector similarity.

        Args:
            query: Search query
            topic: Optional topic filter
            limit: Maximum results

        Returns:
            List of article IDs with similarity scores
        """
        _, collection = _get_chroma_client()
        if collection is None:
            return []

        try:
            # Generate query embedding
            query_embedding = VectorService._generate_embedding(query)
            if not query_embedding:
                return []

            # Build where filter for topic
            where_filter = {"topic": topic} if topic else None

            # Query collection
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=limit,
                where=where_filter
            )

            # Format results
            articles = []
            if results['ids'] and len(results['ids']) > 0:
                for i, doc_id in enumerate(results['ids'][0]):
                    article_id = int(doc_id.replace('article_', ''))
                    articles.append({
                        'article_id': article_id,
                        'similarity_score': 1 - results['distances'][0][i],  # Convert distance to similarity
                        'metadata': results['metadatas'][0][i]
                    })

            logger.info(f"✓ Semantic search: {len(articles)} results for '{query[:50]}'")
            return articles

        except Exception as e:
            logger.error(f"Semantic search error: {e}")
            return []

    @staticmethod
    def hybrid_search(
        query: str,
        keyword_results: List[Dict],
        topic: Optional[str] = None,
        limit: int = 10,
        semantic_weight: float = 0.6
    ) -> List[Dict]:
        """
        Combine semantic and keyword search results.

        Args:
            query: Search query
            keyword_results: Results from SQL LIKE search
            topic: Optional topic filter
            limit: Maximum results
            semantic_weight: Weight for semantic score (0-1)

        Returns:
            Merged and ranked results
        """
        # Get semantic results
        semantic_results = VectorService.semantic_search(query, topic, limit * 2)

        # If no semantic results, return keyword results
        if not semantic_results:
            return keyword_results[:limit]

        # Create score maps
        keyword_weight = 1 - semantic_weight

        # Keyword scores (based on position)
        keyword_scores = {}
        for i, article in enumerate(keyword_results):
            # Higher rank = higher score
            score = 1.0 - (i / max(len(keyword_results), 1))
            keyword_scores[article['id']] = score

        # Semantic scores
        semantic_scores = {}
        for result in semantic_results:
            semantic_scores[result['article_id']] = result['similarity_score']

        # Combine scores
        combined = {}
        all_ids = set(keyword_scores.keys()) | set(semantic_scores.keys())

        for article_id in all_ids:
            kw_score = keyword_scores.get(article_id, 0)
            sem_score = semantic_scores.get(article_id, 0)
            combined[article_id] = (kw_score * keyword_weight) + (sem_score * semantic_weight)

        # Sort by combined score
        sorted_ids = sorted(combined.items(), key=lambda x: x[1], reverse=True)

        # Return article IDs in ranked order
        return [{'article_id': aid, 'score': score} for aid, score in sorted_ids[:limit]]

    @staticmethod
    def get_article_content(article_id: int) -> Optional[str]:
        """
        Get article content from vector database by article ID.

        Args:
            article_id: Article ID from PostgreSQL

        Returns:
            Article content string, or None if not found
        """
        _, collection = _get_chroma_client()
        if collection is None:
            logger.error(f"Vector DB unavailable - cannot retrieve content for article {article_id}")
            return None

        try:
            doc_id = VectorService._make_document_id(article_id)
            result = collection.get(
                ids=[doc_id],
                include=["documents"]
            )

            if result['documents'] and len(result['documents']) > 0:
                return result['documents'][0]

            logger.warning(f"Article {article_id} not found in vector DB")
            return None

        except Exception as e:
            logger.error(f"Error retrieving article {article_id} from vector DB: {e}")
            return None

    @staticmethod
    def get_article_data(article_id: int) -> Optional[Dict]:
        """
        Get full article data (content + metadata) from vector database.

        Args:
            article_id: Article ID from PostgreSQL

        Returns:
            Dict with content and metadata, or None if not found
        """
        _, collection = _get_chroma_client()
        if collection is None:
            logger.error(f"Vector DB unavailable - cannot retrieve data for article {article_id}")
            return None

        try:
            doc_id = VectorService._make_document_id(article_id)
            result = collection.get(
                ids=[doc_id],
                include=["documents", "metadatas"]
            )

            if result['documents'] and len(result['documents']) > 0:
                return {
                    "content": result['documents'][0],
                    "metadata": result['metadatas'][0] if result['metadatas'] else {}
                }

            logger.warning(f"Article {article_id} not found in vector DB")
            return None

        except Exception as e:
            logger.error(f"Error retrieving article {article_id} data from vector DB: {e}")
            return None

    @staticmethod
    def search_articles(
        query: str,
        topic: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """
        Search articles and return full article data.

        Combines semantic search with article data retrieval to return
        complete article information for each match.

        Args:
            query: Search query
            topic: Optional topic filter
            limit: Maximum results

        Returns:
            List of article dictionaries with full data and similarity scores
        """
        # First do semantic search to get matching article IDs
        search_results = VectorService.semantic_search(query, topic, limit)

        if not search_results:
            return []

        # Get full article data for each result
        articles = []
        for result in search_results:
            article_id = result.get('article_id')
            if article_id:
                article_data = VectorService.get_article_data(article_id)
                if article_data:
                    # Flatten the data structure for easy access
                    metadata = article_data.get('metadata', {})
                    flattened = {
                        'article_id': metadata.get('article_id', article_id),
                        'headline': metadata.get('headline', ''),
                        'topic': metadata.get('topic', ''),
                        'author': metadata.get('author', ''),
                        'editor': metadata.get('editor', ''),
                        'keywords': metadata.get('keywords', ''),
                        'content': article_data.get('content', ''),
                        'similarity_score': result.get('similarity_score', 0)
                    }
                    articles.append(flattened)

        logger.info(f"✓ Article search: {len(articles)} results for '{query[:50]}'")
        return articles

    @staticmethod
    def get_collection_stats() -> Dict:
        """Get statistics about the vector collection."""
        _, collection = _get_chroma_client()
        if collection is None:
            return {"available": False, "error": "ChromaDB not available"}

        try:
            return {
                "available": True,
                "count": collection.count(),
                "name": settings.chroma_collection_name,
                "embedding_model": settings.openai_embedding_model
            }
        except Exception as e:
            return {"available": False, "error": str(e)}
