# Content Agent Architecture

This document describes the new content-based multi-agent architecture that replaces the previous routing-based system.

## Overview

The new architecture transforms the chatbot into a content creation and delivery platform where:
- **Main Chat Agent**: Orchestrates user queries and routes to specialized content agents
- **Content Agents**: Create reusable articles on specific topics (macro, equity, fixed_income, ESG)
- **Content Storage**: Articles are permanently stored in PostgreSQL with metadata
- **Redis Caching**: Fast content retrieval with topic-specific caching
- **Google Search Integration**: Agents research current information before creating articles

## Architecture Components

### 1. Main Chat Agent (`agents/main_chat_agent.py`)

**Purpose**: Primary interface for user interactions

**Features**:
- Customizable prompt templates (global + user-specific)
- Routes queries to appropriate content agents
- Synthesizes responses from content agents

**Prompt Templates**:
- Global template: Applies to all users (admin-editable)
- User-specific template: Overrides global template for individual users
- Stored in `prompt_templates` table with `template_type='main_chat'`

### 2. Content Agents (`agents/content_agent.py`)

**Purpose**: Create and retrieve topic-specific content

**Topics**:
- **Macro**: Macroeconomic indicators, central bank policy, FX markets
- **Equity**: Stock markets, company analysis, valuations
- **Fixed Income**: Bonds, yields, credit markets
- **ESG**: Environmental, social, governance investing

**Workflow**:
1. Receive query from main chat agent
2. Check database for existing relevant content (via `content_service`)
3. If found: Return existing article (increment readership counter)
4. If not found: Research using Google Search API
5. Create new article using LLM (max 1000 words)
6. Store article in database
7. Return article to user

**Prompt Templates**:
- Each content agent has a customizable prompt template
- Admin-editable only (scope='global')
- Stored in `prompt_templates` table with `template_type='content_agent'`

### 3. Database Models (`models.py`)

#### ContentArticle Table
```python
- id: Primary key
- topic: Topic type (macro, equity, fixed_income, esg)
- headline: Article title (max 500 chars)
- content: Article body (max 1000 words)
- readership_count: Number of times article was accessed
- rating: Average user rating (1-5)
- rating_count: Number of ratings received
- keywords: Comma-separated keywords for search
- created_at: Timestamp
- updated_at: Timestamp
- created_by_agent: Agent that created the article
- is_active: Soft delete flag
```

#### ContentRating Table
```python
- id: Primary key
- article_id: Foreign key to content_articles
- user_id: Foreign key to users
- rating: Rating value (1-5)
- created_at: Timestamp
- Unique constraint: (article_id, user_id)
```

#### PromptTemplate Table (Updated)
```python
- id: Primary key
- template_type: 'main_chat' or 'content_agent'
- agent_type: For content_agent: macro, equity, fixed_income, esg
- template_name: Template name (e.g., "default")
- template_text: Actual prompt text
- scope: 'global' or 'user'
- user_id: For user-specific templates (nullable)
- version: Version number
- is_active: Active flag
- created_at, updated_at, created_by, description
```

### 4. Services

#### ContentService (`services/content_service.py`)
- Database operations for content articles
- Integrates with ContentCache for fast retrieval
- Methods:
  - `get_article(db, article_id, increment_readership)`
  - `get_recent_articles(db, topic, limit)`
  - `search_articles(db, topic, query, limit)`
  - `create_article(db, topic, headline, content, keywords, agent_name)`
  - `rate_article(db, article_id, user_id, rating)`
  - `get_top_rated_articles(db, topic, limit)`
  - `get_most_read_articles(db, topic, limit)`

#### ContentCache (`services/content_cache.py`)
- Redis caching layer for content
- Topic-specific caching
- Cache keys:
  - `content:article:{id}`: Individual article
  - `content:topic:{topic}:{limit}`: Topic articles list
  - `content:search:{topic}:{query}`: Search results
- Methods:
  - `get_article(article_id)`, `set_article(article_id, data)`
  - `get_topic_articles(topic, limit)`, `set_topic_articles(topic, articles, limit)`
  - `search_cached_content(topic, query)`, `set_search_results(topic, query, results)`
  - `invalidate_topic(topic)`, `invalidate_article(article_id)`

#### GoogleSearchService (`services/google_search_service.py`)
- Google Custom Search API integration
- Research current information for article creation
- Methods:
  - `search(query, num_results, date_restrict, sort_by)`
  - `search_financial_news(topic, keywords, num_results, recent_only)`
  - `search_by_topic(topic, query_term, num_results)`
- Requires:
  - `GOOGLE_API_KEY` environment variable
  - `GOOGLE_SEARCH_ENGINE_ID` environment variable

#### PromptService (`services/prompt_service.py`) - Updated
- Load and cache prompt templates
- Support for both main_chat and content_agent templates
- Methods:
  - `get_main_chat_template(user_id, template_name)`: Gets user-specific or global
  - `get_content_agent_template(agent_type, template_name)`: Gets agent template
  - `get_default_main_chat_template()`: Hardcoded fallback
  - `get_default_content_agent_template(agent_type)`: Hardcoded fallback
  - `invalidate_cache()`: Clear all caches

#### AgentService (`services/agent_service.py`) - Updated
- High-level orchestration service
- Initializes main chat agent with LLM, Google Search, and database
- Methods:
  - `chat(message)`: Process user message
  - `get_available_agents()`: List content agents
  - `get_agent_descriptions()`: Describe each agent
  - `get_statistics()`: Content agent stats

### 5. API Endpoints

#### Content Endpoints (`api/content.py`)
- `GET /api/content/articles/{topic}`: Get recent articles for topic
- `GET /api/content/articles/{topic}/top-rated`: Get top-rated articles
- `GET /api/content/articles/{topic}/most-read`: Get most-read articles
- `GET /api/content/article/{article_id}`: Get specific article (increments readership)
- `POST /api/content/article/{article_id}/rate`: Rate an article (1-5 stars)
- `GET /api/content/search/{topic}?q={query}`: Search articles by keyword

#### Chat Endpoint (`main.py`)
- `POST /api/chat`: Process chat message through main agent
  - Routes to appropriate content agent
  - Returns response with agent_type and routing_reason

### 6. Migration (`alembic/versions/004_refactor_to_content_agents.py`)

The migration:
1. Creates `content_articles` table
2. Creates `content_ratings` table
3. Updates `prompt_templates` table:
   - Adds `template_type` column
   - Adds `scope` column
   - Adds `user_id` column
   - Migrates existing data to `template_type='content_agent'`
   - Removes old unique constraint
   - Adds new indexes

## Configuration

### Environment Variables (.env)

```bash
# Existing
OPENAI_API_KEY=your_openai_key
OPENAI_MODEL=gpt-4o-mini
DATABASE_URL=postgresql://chatbot_user:chatbot_password@localhost:5432/chatbot
REDIS_HOST=localhost
REDIS_PORT=6379

# New - Required for Google Search
GOOGLE_API_KEY=your_google_api_key
GOOGLE_SEARCH_ENGINE_ID=your_custom_search_engine_id
```

### Dependencies (pyproject.toml)

Added:
```toml
"google-api-python-client>=2.100.0"
```

## Usage Flow

### Example: User asks about inflation

1. **User**: "What's the current inflation outlook?"

2. **Main Chat Agent** (`main_chat_agent.py`):
   - Receives query
   - Routes to 'macro' content agent (macroeconomic topic)

3. **Macro Content Agent** (`content_agent.py`):
   - Searches database for existing articles about "inflation outlook"
   - If found: Returns existing article, increments readership
   - If not found:
     a. Calls Google Search API with query "inflation outlook (macroeconomic OR economy)"
     b. Gets 5 recent news articles from Bloomberg, Reuters, WSJ, etc.
     c. Sends research to LLM with content creation prompt
     d. LLM creates article with headline, keywords, and content (max 1000 words)
     e. Stores article in `content_articles` table
     f. Caches in Redis
     g. Returns article to user

4. **Response to User**:
   ```
   I've researched and created new content on this topic:

   **Inflation Outlook: Central Banks Navigate Complex Economic Landscape**

   [Article content here...]

   ---
   *This is a new article created just for you.*
   ```

5. **Future Users** asking similar questions:
   - Will receive the same article (cached and from database)
   - Readership counter increments
   - Article becomes more discoverable

## Admin Capabilities

### Content Agent Prompt Templates

Admins can customize how content agents create articles:

1. Access prompt template management (requires `admin` scope)
2. Create/update templates in `prompt_templates` table:
   - `template_type`: 'content_agent'
   - `agent_type`: 'macro', 'equity', 'fixed_income', or 'esg'
   - `scope`: 'global'
   - `template_text`: Custom prompt instructions

Example: Make equity agent more technical:
```
You are an equity market content creator specializing in quantitative analysis.

Focus on:
- Technical indicators and chart patterns
- Quant models and factor analysis
- Statistical valuations

Your task is to create data-driven articles (max 1000 words) for quant traders.
Include specific metrics, formulas, and statistical analysis.
```

### Main Chat Prompt Templates

Admins can customize the main chat agent behavior:

1. **Global Template** (applies to all users):
   - `template_type`: 'main_chat'
   - `scope`: 'global'
   - `user_id`: NULL

2. **User-Specific Template** (overrides global for specific user):
   - `template_type`: 'main_chat'
   - `scope`: 'user'
   - `user_id`: {specific_user_id}

## Redis Caching Strategy

### Cache TTL
- Default: 1 hour (configurable via `CACHE_TTL` env var)

### Cache Invalidation
- New article created → Invalidate topic cache
- Article rated → Invalidate article and topic cache
- Manual: `ContentCache.invalidate_topic(topic)`

### Cache Warming
- Popular queries can be pre-cached
- Content agents populate cache on article creation

## Performance Considerations

### Database Indexes
- `content_articles.topic`: Fast topic filtering
- `content_articles.headline`: Fast headline search
- `content_articles.created_at`: Fast recent article queries
- `content_articles.rating`: Fast top-rated queries
- `content_articles.readership_count`: Fast most-read queries

### Query Optimization
- Redis cache reduces database load
- Topic-specific caching prevents cross-contamination
- Search results cached separately

### Article Creation
- Only creates articles when no existing content found
- Google Search limited to 5 results per query
- LLM generates max 1000 words (cost control)

## Future Enhancements

### Planned Features
1. **Data Layer for Plots**: Add chart/graph generation capability
2. **Article Expiration**: Auto-archive outdated articles
3. **Multi-Language Support**: Translate articles to user's language
4. **Article Recommendations**: ML-based content recommendations
5. **Content Quality Scoring**: Automated quality assessment
6. **Collaborative Filtering**: Recommend articles based on similar users

### API Extensions
1. **Admin Content Management**:
   - `POST /api/admin/content/article`: Manually create articles
   - `PUT /api/admin/content/article/{id}`: Edit articles
   - `DELETE /api/admin/content/article/{id}`: Deactivate articles

2. **Analytics**:
   - `GET /api/content/analytics/topic/{topic}`: Topic statistics
   - `GET /api/content/analytics/trends`: Trending topics

## Testing

### Migration Testing
```bash
cd backend
# Run migration
alembic upgrade head

# Verify tables created
psql -U chatbot_user -d chatbot -c "\dt"

# Check for content_articles, content_ratings tables
```

### API Testing
```bash
# Get articles
curl -H "Authorization: Bearer {token}" \
  http://localhost:8000/api/content/articles/macro

# Rate article
curl -X POST -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"rating": 5}' \
  http://localhost:8000/api/content/article/1/rate
```

### Chat Testing
```bash
# Test chat with content creation
curl -X POST -H "Authorization: Bearer {token}" \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the outlook for tech stocks?"}' \
  http://localhost:8000/api/chat
```

## Troubleshooting

### Google Search Not Working
- Check `GOOGLE_API_KEY` is set
- Check `GOOGLE_SEARCH_ENGINE_ID` is set
- Verify Google Custom Search API is enabled
- Check API quota not exceeded

### Redis Cache Issues
- Verify Redis is running: `redis-cli ping`
- Check connection: `REDIS_HOST` and `REDIS_PORT`
- Clear cache manually: `redis-cli -n 1 FLUSHDB`

### No Articles Found
- Check topic is valid: macro, equity, fixed_income, esg
- Verify database connection
- Check `is_active=True` on articles

## Summary

The new content agent architecture provides:
✅ Reusable content across all users
✅ Fast retrieval with Redis caching
✅ Current information via Google Search
✅ Customizable prompts (global + user-specific)
✅ Topic specialization (macro, equity, fixed income, ESG)
✅ User engagement tracking (readership, ratings)
✅ Admin content management capabilities
✅ Scalable architecture for future enhancements
