# Resources & Document Generation

## Overview

The resource management system handles all supporting content for research articles - images, PDFs, text documents, spreadsheets, tables, and time series data. Resources are stored with **permanent identifiers** enabling stable links that never break, even when resources are renamed or updated. The system also generates publication-ready HTML and PDF versions of articles.

---

## What is a Resource?

A **Resource** is any piece of supporting content that can be:

- Uploaded to the platform (images, PDFs, spreadsheets)
- Created directly in the platform (text, structured tables)
- Attached to articles for reference
- Linked within article content
- Searched semantically (for text-based resources)
- Served via permanent URLs

Think of resources as the data, charts, and supporting documents that analysts reference when writing research articles.

---

## Resource Types

### Supported Formats

| Type | Extensions | Storage Location | Searchable |
|------|------------|------------------|------------|
| **Image** | PNG, JPG, GIF, WebP | File Storage (S3) | No |
| **PDF** | PDF | File Storage (S3) | Yes (text extracted) |
| **Text** | Plain text, Markdown | Database + ChromaDB | Yes |
| **Excel** | XLSX, XLS | File Storage (S3) | No |
| **CSV** | CSV | File Storage (S3) | No |
| **ZIP** | ZIP | File Storage (S3) | No |
| **Table** | JSON structure | Database + ChromaDB | Yes |
| **Timeseries** | Structured data | Database | No |
| **Article** | HTML, PDF (generated) | File Storage (S3) | No |

### Storage Strategy Explained

Different resource types have different storage needs:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      Resource Storage Strategy                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Binary Files (Image, PDF, Excel, CSV, ZIP)                                │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                      │   │
│   │   PostgreSQL: Metadata only                                          │   │
│   │   (name, type, size, hash_id, created_by, etc.)                     │   │
│   │                                                                      │   │
│   │   S3: Actual file content                                            │   │
│   │   (Binary data stored with hash_id as filename)                     │   │
│   │                                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   Text-Based Resources (Text, Table)                                        │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                      │   │
│   │   PostgreSQL: Metadata + content backup                              │   │
│   │   (Full text or JSON stored for durability)                         │   │
│   │                                                                      │   │
│   │   ChromaDB: Semantic index                                           │   │
│   │   (Embedded content for similarity search)                          │   │
│   │                                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   Timeseries Data                                                            │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                                                                      │   │
│   │   PostgreSQL: All data                                               │   │
│   │   (Structured storage with date indexing for efficient queries)     │   │
│   │                                                                      │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Permanent Resource IDs (hash_id)

### The Problem with Regular IDs

Using sequential database IDs (1, 2, 3...) for public URLs creates problems:

- **Predictable**: Users can guess other resource URLs
- **Revealing**: Shows how many resources exist
- **Fragile**: If resources are deleted and recreated, IDs change

### The Solution: Hash-Based IDs

Every resource receives a **32-character hash ID** at creation time:

| Property | Description |
|----------|-------------|
| **Format** | 32 alphanumeric characters (lowercase letters + digits) |
| **Generation** | Random URL-safe characters |
| **Uniqueness** | Guaranteed unique across all resources |
| **Immutability** | Never changes, even if resource is renamed |
| **URL-Safety** | Safe to use directly in URLs |

### How Hash IDs Work

```
Resource Created
        │
        ▼
┌───────────────────────────────────────────────────────────────┐
│ Generate hash_id                                               │
│                                                                │
│ Alphabet: a-z + 0-9 (URL-safe characters)                     │
│ Length: 32 characters                                          │
│ Example: "k7m2x9pqa1b2c3d4e5f6g7h8i9j0k1l2"                   │
└───────────────────────────────────────────────────────────────┘
        │
        ├──► PostgreSQL: resources.hash_id = "k7m2x9pqa1b2c3d4..."
        │
        └──► S3: filename = "k7m2x9pqa1b2c3d4e5f6g7h8i9j0k1l2.pdf"

Permanent URL: /api/resources/content/k7m2x9pqa1b2c3d4e5f6g7h8i9j0k1l2
```

### Benefits of Permanent IDs

| Benefit | Explanation |
|---------|-------------|
| **Stable Links** | URLs work forever, even after renaming |
| **Shareable** | Safe to share externally, won't break |
| **Predictability** | No need to regenerate links after updates |
| **Article Publishing** | Published articles reference stable resource URLs |

---

## Resource Lifecycle

### Upload Flow (Binary Files)

```
User selects file to upload
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Validate File                                                             │
│    • Check file type is allowed                                              │
│    • Verify file size is within limits                                       │
│    • Determine resource type from MIME type                                  │
└───────────────────────────────────────────────────────────────────────────┬─┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Create Database Records                                                   │
│    • Create Resource record with metadata                                    │
│    • Generate unique hash_id                                                 │
│    • Create FileResource record with file details                           │
└───────────────────────────────────────────────────────────────────────────┬─┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Upload to Storage                                                         │
│    • Upload file content to S3                                              │
│    • Use hash_id as filename                                                │
│    • Store checksum for integrity verification                              │
└───────────────────────────────────────────────────────────────────────────┬─┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Index Content (if applicable)                                             │
│    • PDF: Extract text, create ChromaDB embedding                           │
│    • Other binaries: No indexing needed                                      │
└───────────────────────────────────────────────────────────────────────────┬─┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. Link to Article (optional)                                                │
│    • If article_id provided, create article-resource link                   │
│    • Resource becomes attached to the article                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Creation Flow (Text/Table Resources)

```
User creates text or table resource
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Create Database Records                                                   │
│    • Create Resource record with metadata                                    │
│    • Generate unique hash_id                                                 │
│    • Create TextResource or TableResource with content                      │
└───────────────────────────────────────────────────────────────────────────┬─┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Index in ChromaDB                                                         │
│    • Generate embedding from content                                         │
│    • Store with metadata (name, type, hash_id)                              │
│    • Enable semantic search                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Resource Data Models

### Base Resource Record

Every resource has common metadata:

| Field | Description |
|-------|-------------|
| **hash_id** | Permanent 32-character identifier |
| **resource_type** | Type classification (image, pdf, text, etc.) |
| **status** | Draft or Published |
| **name** | Display name for the resource |
| **description** | Optional description |
| **reference** | Source attribution |
| **source** | Data source name |
| **weblink** | External reference URL |
| **group_id** | Topic group (for permissions) |
| **created_by** | User who created it |
| **created_at** | Creation timestamp |
| **is_active** | Soft delete flag |

### Type-Specific Extensions

Each resource type has additional fields:

| Type | Additional Data |
|------|-----------------|
| **File** | filename, file_path, file_size, mime_type, checksum |
| **Text** | content, char_count, word_count, chromadb_id |
| **Table** | table_data (JSON), row_count, column_count, column_names, column_types |
| **Timeseries** | frequency, data_type, unit, columns, start_date, end_date |

---

## Content Serving

### Public Content Endpoint

Resources are served via their permanent hash_id:

```
Request: GET /api/resources/content/{hash_id}
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Look up resource by hash_id                                               │
│    • Query PostgreSQL for resource record                                    │
│    • Verify resource exists and is active                                   │
└───────────────────────────────────────────────────────────────────────────┬─┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Determine content source based on type                                    │
│                                                                              │
│    Image/PDF/Excel/CSV/ZIP:                                                  │
│    └──► Retrieve from S3, stream to client                                  │
│                                                                              │
│    Text:                                                                     │
│    └──► Return content from database as plain text                          │
│                                                                              │
│    Table:                                                                    │
│    └──► Return JSON table structure                                         │
│                                                                              │
└───────────────────────────────────────────────────────────────────────────┬─┘
                    │
                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Set appropriate headers                                                   │
│    • Content-Type: Based on resource type                                   │
│    • Content-Disposition: Inline or attachment                              │
│    • Cache-Control: Long cache for immutable content                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Content Delivery by Type

| Resource Type | Delivery Method | Cache Strategy |
|---------------|-----------------|----------------|
| **Image** | Stream binary with image MIME type | Long-term cache |
| **PDF** | Stream binary, inline display | Long-term cache |
| **Text** | Return as plain text | Short-term cache |
| **Table** | Return as JSON | Short-term cache |
| **Excel/CSV** | Download attachment | Long-term cache |

---

## Article-Resource Relationships

### Linking Resources to Articles

Resources can be connected to articles in two ways:

| Method | Description | Use Case |
|--------|-------------|----------|
| **Attachment** | Resource listed as related to article | Supporting documents, data files |
| **Embedding** | Resource referenced in article content | Inline charts, referenced tables |

### Embedding Syntax

Articles can reference resources in markdown using a special syntax:

```markdown
See the [Q3 Revenue Chart](resource:{hash_id}) for details.
```

This renders differently based on context:

| Context | Rendering |
|---------|-----------|
| **Editor Preview** | Embedded preview (image inline, PDF icon, etc.) |
| **Published HTML** | Embedded preview with clickable link |
| **Published PDF** | Text: "Q3 Revenue Chart (URL)" |

---

## Article Publishing: HTML & PDF Generation

### When Articles Are Published

When an article transitions to "Published" status, the system generates distributable versions:

```
Article approved for publication
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Generate HTML Version                                                     │
│    • Convert Markdown to styled HTML                                         │
│    • Process resource links into embedded previews                          │
│    • Include article metadata (headline, topic, date)                       │
│    • Apply consistent styling                                                │
└───────────────────────────────────────────────────────────────────────────┬─┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Create HTML Resource                                                      │
│    • Generate unique hash_id                                                 │
│    • Upload HTML to S3                                                       │
│    • Create resource record with type "article"                             │
│    • Link to source article                                                  │
└───────────────────────────────────────────────────────────────────────────┬─┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Generate PDF Version                                                      │
│    • Convert Markdown to plain text                                          │
│    • Process resource links into "Name (URL)" format                        │
│    • Build PDF with professional formatting                                  │
│    • Include title, metadata, keywords                                       │
└───────────────────────────────────────────────────────────────────────────┬─┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. Create PDF Resource                                                       │
│    • Generate unique hash_id                                                 │
│    • Upload PDF to S3                                                        │
│    • Create resource record with type "article"                             │
│    • Link to source article                                                  │
└─────────────────────────────────────────────────────────────────────────────┘

Result:
  • Article has two child resources (HTML + PDF)
  • Each has permanent URL for distribution
  • URLs remain stable even if article is updated
```

### PDF Generation Details

The PDF generator creates professional documents with:

| Element | Description |
|---------|-------------|
| **Title** | Article headline in prominent styling |
| **Metadata** | Topic, publication date, ratings |
| **Keywords** | Listed for reference |
| **Body** | Converted from Markdown with paragraph formatting |
| **Resource Links** | Converted to "Name (URL)" text format |
| **Footer** | Generation timestamp |

### Resource Link Processing

When generating output, resource links are processed appropriately:

| Format | Resource Link Handling |
|--------|----------------------|
| **HTML** | Embedded preview based on type (image inline, PDF icon, etc.) |
| **PDF** | Text format: "Resource Name (full URL)" |

---

## Timeseries Resources

### What is Timeseries Data?

Timeseries resources store time-indexed numerical data, common in financial research:

- Stock prices over time
- Economic indicators
- Interest rate history
- Any metric measured at regular intervals

### Timeseries Structure

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Timeseries Resource                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   Metadata:                                                                  │
│   ├── Name: "US Inflation Rate"                                             │
│   ├── Source: "Bureau of Labor Statistics"                                  │
│   ├── Frequency: Monthly                                                     │
│   ├── Data Type: Float                                                       │
│   ├── Unit: Percentage                                                       │
│   ├── Columns: ["CPI_YoY", "Core_CPI_YoY"]                                 │
│   └── Range: 2020-01-01 to 2024-12-01                                       │
│                                                                              │
│   Data Points:                                                               │
│   ┌─────────────┬───────────┬──────────────┐                               │
│   │    Date     │  CPI_YoY  │ Core_CPI_YoY │                               │
│   ├─────────────┼───────────┼──────────────┤                               │
│   │ 2024-12-01  │    2.7    │     3.3      │                               │
│   │ 2024-11-01  │    2.6    │     3.3      │                               │
│   │ 2024-10-01  │    2.4    │     3.3      │                               │
│   │ ...         │   ...     │    ...       │                               │
│   └─────────────┴───────────┴──────────────┘                               │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Frequency Options

| Frequency | Description |
|-----------|-------------|
| **Daily** | One data point per day |
| **Weekly** | One data point per week |
| **Monthly** | One data point per month |
| **Quarterly** | One data point per quarter |
| **Annual** | One data point per year |

---

## File Storage Architecture

### Local vs. Cloud Storage

The system supports both local and cloud storage:

| Mode | When Used | Location |
|------|-----------|----------|
| **Local** | Development | File system directory |
| **S3** | Production | AWS S3 bucket |

### File Organization in S3

```
s3://bucket-name/
├── resources/
│   ├── {hash_id}.png        (image resource)
│   ├── {hash_id}.pdf        (uploaded PDF)
│   ├── {hash_id}.xlsx       (Excel file)
│   └── ...
└── articles/
    ├── {hash_id}.html       (published article HTML)
    ├── {hash_id}.pdf        (published article PDF)
    └── ...
```

### Storage Operations

| Operation | Description |
|-----------|-------------|
| **Save** | Upload file content, return storage path |
| **Get** | Retrieve file content by path |
| **Delete** | Remove file from storage |
| **Check** | Verify file exists |

---

## Permission Model

### Resource Access Rules

| User Role | Can View | Can Create | Can Edit | Can Delete |
|-----------|----------|------------|----------|------------|
| **Reader** | Published only | No | No | No |
| **Editor** | Topic resources | No | No | No |
| **Analyst** | Topic resources | Yes (topic) | Yes (own) | Yes (own) |
| **Admin** | Topic resources | Yes (topic) | Yes (all) | Yes (all) |
| **Global Admin** | All resources | Yes (all) | Yes (all) | Yes (all) |

### Group-Based Ownership

Resources belong to groups (which correspond to topics):

```
Resource created in "macro:admin" group
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ Who can access this resource?                                                │
│                                                                              │
│   ✓ macro:admin   - Full access (owner group)                               │
│   ✓ macro:analyst - View and use in articles                                │
│   ✓ macro:editor  - View only                                               │
│   ✓ macro:reader  - View if linked to published article                     │
│   ✓ global:admin  - Full access (bypasses all)                              │
│   ✗ equity:*      - No access (different topic)                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Search and Discovery

### Semantic Search (Text-Based Resources)

Text and table resources are indexed in ChromaDB for semantic search:

```
User searches: "inflation data 2024"
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. Embed search query                                                        │
│    "inflation data 2024" → 1536-dimensional vector                          │
└───────────────────────────────────────────────────────────────────────────┬─┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. Search ChromaDB resources_collection                                      │
│    • Compare query vector to all resource vectors                           │
│    • Rank by cosine similarity                                              │
└───────────────────────────────────────────────────────────────────────────┬─┘
              │
              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. Return matching resources                                                 │
│    • Text: "Inflation Analysis Q4 2024" (similarity: 0.91)                  │
│    • Table: "CPI Components Breakdown" (similarity: 0.87)                   │
│    • Text: "Core Inflation Trends" (similarity: 0.82)                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Filtering Options

| Filter | Description |
|--------|-------------|
| **By Type** | Only images, only PDFs, etc. |
| **By Topic** | Resources in a specific topic group |
| **By Status** | Draft or published |
| **By Creator** | Resources by specific user |
| **By Date** | Created within date range |

---

## Frontend Integration

### Resource Editor Component

The frontend provides a resource management interface:

| Feature | Description |
|---------|-------------|
| **Upload** | Drag-and-drop file upload |
| **Create** | Text and table creation forms |
| **Preview** | Visual preview for images, PDF pages |
| **Link** | Attach resources to articles |
| **Drag to Insert** | Drag resource into article editor to insert link |

### Drag-and-Drop Linking

Resources can be dragged into the article editor:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Article Editor                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   [Resources Panel]                          [Content Editor]                │
│   ┌───────────────────┐                    ┌───────────────────────────────┐│
│   │                   │     Drag          │                               ││
│   │  📊 Q3 Chart      │ ─────────────────►│  The data shows that         ││
│   │                   │                    │  [Q3 Chart](resource:{id})   ││
│   │  📄 Analysis      │                    │  indicates growth...          ││
│   │                   │                    │                               ││
│   └───────────────────┘                    └───────────────────────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Preview Generation

| Resource Type | Preview |
|---------------|---------|
| **Image** | Thumbnail image |
| **PDF** | First page thumbnail + icon |
| **Text** | First few lines of text |
| **Table** | Column headers + first rows |
| **Other** | Icon based on file type |

---

## API Operations Summary

### Resource Management

| Operation | Description |
|-----------|-------------|
| **List** | Get resources with filtering |
| **Get** | Retrieve resource details |
| **Create Text** | Create text resource |
| **Create Table** | Create table resource |
| **Upload File** | Upload binary file |
| **Update** | Modify resource metadata |
| **Delete** | Soft-delete resource |

### Content Access

| Operation | Description |
|-----------|-------------|
| **Get Content** | Serve resource by hash_id |
| **Download** | Force download headers |
| **Info** | Get resource metadata by hash_id |

### Article Linking

| Operation | Description |
|-----------|-------------|
| **Get Article Resources** | List resources for article |
| **Link** | Attach resource to article |
| **Unlink** | Remove resource from article |

### Timeseries Data

| Operation | Description |
|-----------|-------------|
| **Add Data** | Insert new data points |
| **Query Data** | Get data with date filtering |
| **Update Data** | Modify existing data points |
