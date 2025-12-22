# Storage Architecture

## Overview

The platform uses a **three-tier storage architecture** that separates structured relational data, semantic content, and binary files. Each storage layer is optimized for its specific use case.

| Storage | Role | Strength |
|---------|------|----------|
| **PostgreSQL** | Relational data & metadata | Fast filtering, indexing, relationships |
| **ChromaDB** | Content & vector embeddings | Semantic search, similarity matching, AI context |
| **File Storage (S3)** | Binary files & generated documents | Permanent URLs, CDN delivery, large file handling |

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Backend Services                                │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
│     PostgreSQL      │  │      ChromaDB       │  │   File Storage      │
│ (Relational Database)│  │  (Vector Database)  │  │      (S3)          │
├─────────────────────┤  ├─────────────────────┤  ├─────────────────────┤
│                     │  │                     │  │                     │
│ • User accounts     │  │ • Article full text │  │ • Images (png/jpg)  │
│ • Group memberships │  │ • 1536-dim vectors  │  │ • PDF documents     │
│ • Article metadata  │  │ • Semantic index    │  │ • Published HTML    │
│ • Resource records  │  │ • Resource text     │  │ • Excel/CSV files   │
│ • Ratings & counts  │  │ • Similarity search │  │ • ZIP archives      │
│ • Foreign keys      │  │                     │  │                     │
└─────────────────────┘  └─────────────────────┘  └─────────────────────┘
         │                          │                          │
     article_id              article_{id}               {hash_id}.ext
     resource.id             embedding vector           permanent URL
```

---

## Why Three Storage Layers?

### PostgreSQL Excels At:
- **Structured queries**: Filter by status, topic, date ranges
- **Relationships**: Users → Groups → Resources → Articles
- **Aggregations**: Counts, ratings, statistics
- **Transactions**: ACID compliance for data integrity
- **Indexing**: Fast lookups on specific fields

### ChromaDB Excels At:
- **Semantic understanding**: "Find articles about economic growth" (not just keyword match)
- **Similarity search**: Find articles similar to a given text
- **AI context**: Retrieve relevant background for chatbot responses
- **Vector operations**: Cosine similarity across 1536 dimensions
- **Embedding storage**: Efficient storage of high-dimensional vectors

### File Storage (S3) Excels At:
- **Binary content**: Images, PDFs, office documents that can't be stored in databases
- **Permanent URLs**: Hash-based IDs (`{hash_id}.pdf`) that never change
- **CDN delivery**: Fast global access via CloudFront or similar
- **Large files**: No database size limits for uploaded content
- **Published output**: HTML and PDF versions of articles for distribution

---

## Core Concepts: Articles & Resources

### What is an Article?

An **Article** is the primary content unit - a research piece written by analysts on topics like Macro, Equity, Fixed Income, or ESG. Articles progress through a workflow:

```
Draft → Editor Review → Published
```

| Attribute | Storage | Description |
|-----------|---------|-------------|
| Metadata | PostgreSQL | ID, topic, headline, author, status, timestamps, ratings |
| Full Text | ChromaDB | Content body with semantic embedding for AI search |
| Published Output | S3 | HTML and PDF versions (only when published) |

### What is a Resource?

A **Resource** is any supporting content that can be attached to articles or used independently. Resources are **reusable** - one resource can be linked to multiple articles.

| Resource Type | Binary File (S3) | Searchable (ChromaDB) |
|---------------|------------------|----------------------|
| **image** | Yes (png, jpg, gif) | No |
| **pdf** | Yes | No |
| **text** | No (stored in PostgreSQL) | Yes |
| **table** | No (JSON in PostgreSQL) | Yes |
| **excel** | Yes | No |
| **csv** | Yes | No |
| **timeseries** | No (structured in PostgreSQL) | No |
| **article** | Yes (HTML + PDF) | No |

### The Permanent Resource ID (hash_id)

Every resource receives a unique 32-character **hash_id** at creation. This ID is:

- **Immutable**: Never changes, even if the resource is renamed or updated
- **URL-safe**: Lowercase letters + digits, safe for use directly in URLs
- **Cross-system**: Links PostgreSQL records to S3 files

```
Resource Created
      │
      ▼
Generate hash_id (32 chars, e.g., "k7m2x9pqa1b2c3d4e5f6g7h8i9j0k1l2")
      │
      ├──► PostgreSQL: resources.hash_id = "k7m2x9pqa1b2c3d4..."
      │
      └──► S3: filename = "k7m2x9pqa1b2c3d4e5f6g7h8i9j0k1l2.pdf"
                         │
                         ▼
              Permanent URL: /api/resources/content/{hash_id}
```

### Article-Resource Relationships

Resources can be **linked** to articles in two ways:

1. **Embedded in Content**: Markdown syntax `[Chart Name](resource:{hash_id})` renders as embedded preview
2. **Attached**: Listed as related resources for the article

When an article is **published**, it automatically generates two child resources:

```
Published Article (id: 42)
      │
      ├──► HTML Resource (hash_id: 32 chars, type: "article")
      │         └── S3: {hash_id}.html
      │
      └──► PDF Resource (hash_id: 32 chars, type: "article")
                └── S3: {hash_id}.pdf
```

These generated resources are linked back to the article via `article_resources`, creating permanent distribution URLs that never change even if the article is updated.

### Resource Linking in Markdown

Articles can reference resources using the syntax:

```markdown
See the [Q3 Revenue Chart](resource:{hash_id}) for details.
```

This renders differently based on context:

| Context | Rendering |
|---------|-----------|
| **Editor Preview** | Embedded preview (image inline, PDF icon, etc.) |
| **Published HTML** | Embedded preview with clickable link |
| **Published PDF** | Text: "Q3 Revenue Chart (https://...)" |

---

## Data Distribution

### What Lives in PostgreSQL

| Category | Tables | Purpose |
|----------|--------|---------|
| **Identity** | `users`, `groups`, `user_groups` | Authentication, authorization, membership |
| **Content Metadata** | `content_articles` | Status, topic, author, timestamps, ratings |
| **Resources** | `resources`, `file_resources`, `text_resources`, `table_resources` | File metadata, resource types, ownership |
| **Relationships** | `article_resources`, `content_ratings` | Links between entities |
| **Configuration** | `prompt_modules` | System prompts, tonality settings |
| **Time Series** | `timeseries_metadata`, `timeseries_data` | Structured numeric data |

### What Lives in ChromaDB

| Collection | Contents | Use Case |
|------------|----------|----------|
| `research_articles` | Article text + embedding + metadata | AI context, semantic search |
| `resources_collection` | Text/table content + embedding | Resource search |

### What Lives in File Storage (S3)

| File Type | Naming Convention | Purpose |
|-----------|-------------------|---------|
| **Images** | `{hash_id}.{ext}` | Charts, diagrams, photos uploaded as resources |
| **PDFs** | `{hash_id}.pdf` | Uploaded documents and published article PDFs |
| **HTML** | `{hash_id}.html` | Published article HTML for web distribution |
| **Excel/CSV** | `{hash_id}.{ext}` | Spreadsheet data files |
| **ZIP** | `{hash_id}.zip` | Archive bundles |

**Permanent Link IDs**: Each resource gets a 32-character hash ID generated at creation time. This ID:
- Never changes, even if the resource is renamed
- Forms the basis of all public URLs: `/api/resources/content/{hash_id}`
- Enables stable links in published articles and external references
- Is stored in PostgreSQL (`resources.hash_id`) and used as the S3 filename

---

## Data Flow Examples

### Creating an Article

```
1. User creates article
        │
        ▼
2. PostgreSQL: Insert metadata
   (topic, status=draft, author, timestamps)
        │
        ▼
3. ChromaDB: Store content + generate embedding
   (full text, headline, keywords → 1536-dim vector)
```

### Searching for Articles

```
1. User searches: "inflation trends in Europe"
        │
        ├──► PostgreSQL: Filter by topic, status=published
        │
        └──► ChromaDB: Semantic search on query embedding
                │
                ▼
        Combine: Filtered results ranked by similarity
```

### Chat Context Retrieval

```
1. User asks chatbot a question
        │
        ▼
2. ChromaDB: Embed question, find similar articles
        │
        ▼
3. PostgreSQL: Check article status (must be published)
        │
        ▼
4. Return top 3-5 relevant articles as context for LLM
```

---

## Synchronization

The three storage layers stay synchronized through the backend services:

| Operation | PostgreSQL | ChromaDB | File Storage (S3) |
|-----------|------------|----------|-------------------|
| **Create Article** | Insert metadata | Store content + embed | — |
| **Update Article** | Update metadata | Re-embed if changed | — |
| **Publish Article** | Status → published | Status updated | Generate HTML + PDF |
| **Delete Article** | Remove record | Remove from collection | Remove HTML + PDF |
| **Upload Resource** | Insert record + hash_id | Embed (if text) | Store binary file |
| **Delete Resource** | Remove record | Remove embedding | Delete file |

**Key Principles**:
- PostgreSQL is the source of truth for existence, status, and relationships
- ChromaDB stores searchable content and enables semantic operations
- File Storage holds binary content accessible via permanent hash-based URLs

---

## Entity Relationships (PostgreSQL)

```
┌──────────┐     ┌─────────────┐     ┌──────────┐
│  users   │────►│ user_groups │◄────│  groups  │
└──────────┘     └─────────────┘     └──────────┘
     │
     │  ┌─────────────────┐     ┌────────────────────┐
     └─►│ content_ratings │────►│  content_articles  │
        └─────────────────┘     └─────────┬──────────┘
                                          │
                                          ▼
                                ┌────────────────────┐
                                │ article_resources  │
                                └─────────┬──────────┘
                                          │
                                          ▼
┌───────────────┐               ┌────────────────────┐
│file_resources │◄──────────────│     resources      │
│text_resources │               └────────────────────┘
│table_resources│
└───────────────┘
```

---

## Graceful Degradation

When ChromaDB is unavailable:
- Article creation continues (PostgreSQL only, no semantic search)
- Semantic search returns empty results
- Article retrieval falls back to PostgreSQL metadata
- System logs warnings but continues operating

When File Storage (S3) is unavailable:
- Resource uploads fail
- Publishing articles fails (cannot generate HTML/PDF)
- Existing permanent URLs return errors
- Core chat and search functionality continues

When PostgreSQL is unavailable:
- System cannot operate (critical dependency)
- All operations fail with database connection error

---

## Debugging

### PostgreSQL
- Access via `docker-compose exec` with psql client
- Useful queries: table sizes, active connections, long-running queries
- Check container logs for connection issues

### ChromaDB
- Heartbeat endpoint to verify service is running
- Collections endpoint to list available vector stores
- Check container logs for embedding errors

### File Storage (S3)
- Verify bucket accessibility and permissions
- Check file existence using hash_id
- Review CloudWatch logs for access patterns and errors

---

## Migrations (PostgreSQL)

Database schema changes are managed with Alembic:

```bash
# Create new migration
cd backend && uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback one step
uv run alembic downgrade -1

# Show current version
uv run alembic current
```

---

## Related Services

| Service | Storage Used | Purpose |
|---------|--------------|---------|
| `ContentService` | PostgreSQL + ChromaDB | Article CRUD, coordinating databases |
| `ArticleResourceService` | All three | Publishing articles to HTML/PDF |
| `VectorService` | ChromaDB | Embedding operations, similarity search |
| `UserService` | PostgreSQL | User management, authentication |
| `ResourceService` | PostgreSQL + S3 | Resource upload and retrieval |
| `MainChatAgent` | ChromaDB | Context retrieval for AI responses |
