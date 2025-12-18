"""Add resource management tables

Revision ID: 012
Revises: 011
Create Date: 2024-12-18

This migration adds:
- resource_type_enum, timeseries_freq_enum, timeseries_dtype_enum
- resources (base table with global ID and common metadata)
- article_resources (many-to-many link between articles and resources)
- file_resources (for images, PDFs, Excel, ZIP, CSV)
- text_resources (for text files with ChromaDB embedding)
- table_resources (for small tables as JSON with ChromaDB embedding)
- timeseries_metadata (timeseries descriptor)
- timeseries_data (actual timeseries data points)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '012_add_resources'
down_revision = '011_add_prompt_modules'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()

    # Create enums if they don't exist
    # resource_type_enum
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'resource_type_enum') THEN
                CREATE TYPE resource_type_enum AS ENUM ('image', 'pdf', 'text', 'excel', 'zip', 'csv', 'table', 'timeseries');
            END IF;
        END$$;
    """))

    # timeseries_freq_enum
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'timeseries_freq_enum') THEN
                CREATE TYPE timeseries_freq_enum AS ENUM ('tick', 'minute', 'hourly', 'daily', 'weekly', 'monthly', 'quarterly', 'yearly');
            END IF;
        END$$;
    """))

    # timeseries_dtype_enum
    conn.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'timeseries_dtype_enum') THEN
                CREATE TYPE timeseries_dtype_enum AS ENUM ('float', 'integer', 'string');
            END IF;
        END$$;
    """))

    # Create resources table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS resources (
            id SERIAL PRIMARY KEY,
            resource_type resource_type_enum NOT NULL,
            name VARCHAR(255) NOT NULL,
            description TEXT,
            group_id INTEGER REFERENCES groups(id) ON DELETE SET NULL,
            created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            modified_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        );
    """))

    # Create indexes for resources
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_resources_id ON resources(id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_resources_resource_type ON resources(resource_type);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_resources_name ON resources(name);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_resources_group_id ON resources(group_id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_resources_created_by ON resources(created_by);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_resources_created_at ON resources(created_at);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_resources_is_active ON resources(is_active);"))

    # Create article_resources table (many-to-many)
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS article_resources (
            id SERIAL PRIMARY KEY,
            article_id INTEGER NOT NULL REFERENCES content_articles(id) ON DELETE CASCADE,
            resource_id INTEGER NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uix_article_resource UNIQUE (article_id, resource_id)
        );
    """))

    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_article_resources_article_id ON article_resources(article_id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_article_resources_resource_id ON article_resources(resource_id);"))

    # Create file_resources table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS file_resources (
            id SERIAL PRIMARY KEY,
            resource_id INTEGER NOT NULL UNIQUE REFERENCES resources(id) ON DELETE CASCADE,
            filename VARCHAR(500) NOT NULL,
            file_path VARCHAR(1000) NOT NULL UNIQUE,
            file_size INTEGER NOT NULL,
            mime_type VARCHAR(100) NOT NULL,
            checksum VARCHAR(64)
        );
    """))

    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_file_resources_id ON file_resources(id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_file_resources_resource_id ON file_resources(resource_id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_file_resources_mime_type ON file_resources(mime_type);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_file_resources_checksum ON file_resources(checksum);"))

    # Create text_resources table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS text_resources (
            id SERIAL PRIMARY KEY,
            resource_id INTEGER NOT NULL UNIQUE REFERENCES resources(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            encoding VARCHAR(50) NOT NULL DEFAULT 'utf-8',
            char_count INTEGER,
            word_count INTEGER,
            chromadb_id VARCHAR(100)
        );
    """))

    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_text_resources_id ON text_resources(id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_text_resources_resource_id ON text_resources(resource_id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_text_resources_chromadb_id ON text_resources(chromadb_id);"))

    # Create table_resources table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS table_resources (
            id SERIAL PRIMARY KEY,
            resource_id INTEGER NOT NULL UNIQUE REFERENCES resources(id) ON DELETE CASCADE,
            table_data TEXT NOT NULL,
            row_count INTEGER NOT NULL,
            column_count INTEGER NOT NULL,
            column_names TEXT NOT NULL,
            column_types TEXT,
            chromadb_id VARCHAR(100)
        );
    """))

    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_table_resources_id ON table_resources(id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_table_resources_resource_id ON table_resources(resource_id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_table_resources_chromadb_id ON table_resources(chromadb_id);"))

    # Create timeseries_metadata table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS timeseries_metadata (
            id SERIAL PRIMARY KEY,
            resource_id INTEGER NOT NULL UNIQUE REFERENCES resources(id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            source VARCHAR(255),
            description TEXT,
            frequency timeseries_freq_enum NOT NULL,
            data_type timeseries_dtype_enum NOT NULL DEFAULT 'float',
            columns TEXT NOT NULL,
            start_date TIMESTAMP WITH TIME ZONE,
            end_date TIMESTAMP WITH TIME ZONE,
            data_point_count INTEGER NOT NULL DEFAULT 0,
            unit VARCHAR(50)
        );
    """))

    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_metadata_id ON timeseries_metadata(id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_metadata_resource_id ON timeseries_metadata(resource_id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_metadata_name ON timeseries_metadata(name);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_metadata_source ON timeseries_metadata(source);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_metadata_frequency ON timeseries_metadata(frequency);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_metadata_start_date ON timeseries_metadata(start_date);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_metadata_end_date ON timeseries_metadata(end_date);"))

    # Create timeseries_data table
    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS timeseries_data (
            id SERIAL PRIMARY KEY,
            tsid INTEGER NOT NULL REFERENCES timeseries_metadata(id) ON DELETE CASCADE,
            date TIMESTAMP WITH TIME ZONE NOT NULL,
            column_name VARCHAR(100) NOT NULL,
            value DOUBLE PRECISION,
            value_str VARCHAR(500),
            revision_time TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uix_ts_date_col_rev UNIQUE (tsid, date, column_name, revision_time)
        );
    """))

    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_data_id ON timeseries_data(id);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_data_tsid ON timeseries_data(tsid);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_data_date ON timeseries_data(date);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_data_column_name ON timeseries_data(column_name);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_timeseries_data_revision_time ON timeseries_data(revision_time);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_tsdata_tsid_date ON timeseries_data(tsid, date);"))
    conn.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_tsdata_tsid_col ON timeseries_data(tsid, column_name);"))


def downgrade():
    conn = op.get_bind()

    # Drop tables in reverse order (respecting foreign key constraints)
    conn.execute(sa.text("DROP TABLE IF EXISTS timeseries_data CASCADE;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS timeseries_metadata CASCADE;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS table_resources CASCADE;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS text_resources CASCADE;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS file_resources CASCADE;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS article_resources CASCADE;"))
    conn.execute(sa.text("DROP TABLE IF EXISTS resources CASCADE;"))

    # Drop enums
    conn.execute(sa.text("DROP TYPE IF EXISTS timeseries_dtype_enum;"))
    conn.execute(sa.text("DROP TYPE IF EXISTS timeseries_freq_enum;"))
    conn.execute(sa.text("DROP TYPE IF EXISTS resource_type_enum;"))
