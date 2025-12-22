"""Resource management service for handling all resource types."""

import json
import hashlib
import os
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
import logging

from models import (
    Resource, ResourceType, ResourceStatus, FileResource, TextResource, TableResource,
    TimeseriesMetadata, TimeseriesData, TimeseriesFrequency, TimeseriesDataType,
    ContentArticle, Group, article_resources
)
from services.vector_service import VectorService, _get_chroma_client, vector_settings

logger = logging.getLogger("uvicorn")


# Resource collection name in ChromaDB
RESOURCE_COLLECTION_NAME = "resources"

# Lazy initialization for resource collection
_resource_collection = None


def _get_resource_collection():
    """Get or create the resources collection in ChromaDB."""
    global _resource_collection

    if _resource_collection is not None:
        return _resource_collection

    client, _ = _get_chroma_client()
    if client is None:
        return None

    try:
        _resource_collection = client.get_or_create_collection(
            name=RESOURCE_COLLECTION_NAME,
            metadata={
                "description": "Resource embeddings for text and table content",
                "hnsw:space": "cosine"
            }
        )
        logger.info(f"✓ Resource collection initialized: {RESOURCE_COLLECTION_NAME}")
        return _resource_collection
    except Exception as e:
        logger.error(f"Failed to get resource collection: {e}")
        return None


class ResourceService:
    """Service for managing resources of all types."""

    # ==========================================================================
    # CHROMADB OPERATIONS
    # ==========================================================================

    @staticmethod
    def _make_resource_doc_id(resource_id: int, resource_type: str) -> str:
        """Create consistent document ID for ChromaDB."""
        return f"resource_{resource_type}_{resource_id}"

    @staticmethod
    def _add_to_chromadb(
        resource_id: int,
        resource_type: str,
        content: str,
        metadata: Dict[str, Any]
    ) -> Optional[str]:
        """
        Add resource content to ChromaDB for semantic search.

        Returns the chromadb_id if successful, None otherwise.
        """
        collection = _get_resource_collection()
        if collection is None:
            logger.warning(f"ChromaDB unavailable - skipping resource {resource_id}")
            return None

        try:
            # Generate embedding
            embedding = VectorService._generate_embedding(content)
            if not embedding:
                logger.error(f"Failed to generate embedding for resource {resource_id}")
                return None

            doc_id = ResourceService._make_resource_doc_id(resource_id, resource_type)

            # Clean metadata - ChromaDB requires string/int/float/bool values
            clean_metadata = {}
            for k, v in metadata.items():
                if v is None:
                    clean_metadata[k] = ""
                elif isinstance(v, (str, int, float, bool)):
                    clean_metadata[k] = v
                else:
                    clean_metadata[k] = str(v)

            collection.add(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[clean_metadata]
            )

            logger.info(f"✓ Added resource {resource_id} to ChromaDB")
            return doc_id

        except Exception as e:
            logger.error(f"Error adding resource {resource_id} to ChromaDB: {e}")
            return None

    @staticmethod
    def _update_in_chromadb(
        resource_id: int,
        resource_type: str,
        content: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """Update resource content in ChromaDB."""
        collection = _get_resource_collection()
        if collection is None:
            return False

        try:
            # Delete old and add new
            doc_id = ResourceService._make_resource_doc_id(resource_id, resource_type)
            collection.delete(ids=[doc_id])
            new_id = ResourceService._add_to_chromadb(
                resource_id, resource_type, content, metadata
            )
            return new_id is not None
        except Exception as e:
            logger.error(f"Error updating resource {resource_id} in ChromaDB: {e}")
            return False

    @staticmethod
    def _delete_from_chromadb(resource_id: int, resource_type: str) -> bool:
        """Delete resource from ChromaDB."""
        collection = _get_resource_collection()
        if collection is None:
            return False

        try:
            doc_id = ResourceService._make_resource_doc_id(resource_id, resource_type)
            collection.delete(ids=[doc_id])
            logger.info(f"✓ Deleted resource {resource_id} from ChromaDB")
            return True
        except Exception as e:
            logger.error(f"Error deleting resource {resource_id} from ChromaDB: {e}")
            return False

    # ==========================================================================
    # RESOURCE CRUD OPERATIONS
    # ==========================================================================

    @staticmethod
    def create_resource(
        db: Session,
        resource_type: ResourceType,
        name: str,
        created_by: int,
        description: Optional[str] = None,
        group_id: Optional[int] = None,
        status: ResourceStatus = ResourceStatus.DRAFT,
        parent_id: Optional[int] = None
    ) -> Resource:
        """Create base resource record.

        Args:
            parent_id: Optional parent resource ID for derived resources
                      (e.g., text extracted from a PDF)
        """
        resource = Resource(
            resource_type=resource_type,
            name=name,
            description=description,
            group_id=group_id,
            created_by=created_by,
            modified_by=created_by,
            status=status,
            is_active=True,
            parent_id=parent_id
        )
        db.add(resource)
        db.flush()  # Get the ID without committing
        return resource

    @staticmethod
    def create_file_resource(
        db: Session,
        name: str,
        resource_type: ResourceType,
        filename: str,
        file_path: str,
        file_size: int,
        mime_type: str,
        created_by: int,
        checksum: Optional[str] = None,
        description: Optional[str] = None,
        group_id: Optional[int] = None,
        parent_id: Optional[int] = None
    ) -> Tuple[Resource, FileResource]:
        """
        Create a file-based resource (image, pdf, excel, zip, csv).

        Args:
            db: Database session
            name: Resource display name
            resource_type: One of IMAGE, PDF, EXCEL, ZIP, CSV
            filename: Original filename
            file_path: Relative path on filesystem
            file_size: File size in bytes
            mime_type: MIME type
            created_by: User ID
            checksum: Optional SHA-256 checksum
            description: Optional description
            group_id: Optional group for sharing
            parent_id: Optional parent resource ID for derived resources

        Returns:
            Tuple of (Resource, FileResource)
        """
        # Validate resource type
        if resource_type not in [ResourceType.IMAGE, ResourceType.PDF, ResourceType.EXCEL,
                                  ResourceType.ZIP, ResourceType.CSV]:
            raise ValueError(f"Invalid resource type for file: {resource_type}")

        # Create base resource
        resource = ResourceService.create_resource(
            db, resource_type, name, created_by, description, group_id,
            parent_id=parent_id
        )

        # Create file resource
        file_resource = FileResource(
            resource_id=resource.id,
            filename=filename,
            file_path=file_path,
            file_size=file_size,
            mime_type=mime_type,
            checksum=checksum
        )
        db.add(file_resource)
        db.commit()
        db.refresh(resource)
        db.refresh(file_resource)

        return resource, file_resource

    @staticmethod
    def create_text_resource(
        db: Session,
        name: str,
        content: str,
        created_by: int,
        encoding: str = "utf-8",
        description: Optional[str] = None,
        group_id: Optional[int] = None,
        parent_id: Optional[int] = None
    ) -> Tuple[Resource, TextResource]:
        """
        Create a text resource with ChromaDB embedding.

        Args:
            db: Database session
            name: Resource display name
            content: Text content
            created_by: User ID
            encoding: Text encoding (default utf-8)
            description: Optional description
            group_id: Optional group for sharing
            parent_id: Optional parent resource ID for derived resources

        Returns:
            Tuple of (Resource, TextResource)
        """
        # Create base resource
        resource = ResourceService.create_resource(
            db, ResourceType.TEXT, name, created_by, description, group_id,
            parent_id=parent_id
        )

        # Calculate stats
        char_count = len(content)
        word_count = len(content.split())

        # Create text resource
        text_resource = TextResource(
            resource_id=resource.id,
            content=content,
            encoding=encoding,
            char_count=char_count,
            word_count=word_count
        )
        db.add(text_resource)
        db.flush()

        # Add to ChromaDB
        chromadb_id = ResourceService._add_to_chromadb(
            resource.id,
            ResourceType.TEXT.value,
            content,
            {
                "resource_id": resource.id,
                "name": name,
                "type": ResourceType.TEXT.value,
                "char_count": char_count,
                "word_count": word_count,
                "parent_id": parent_id if parent_id else ""
            }
        )
        text_resource.chromadb_id = chromadb_id

        db.commit()
        db.refresh(resource)
        db.refresh(text_resource)

        return resource, text_resource

    @staticmethod
    def create_table_resource(
        db: Session,
        name: str,
        table_data: Dict[str, Any],
        created_by: int,
        description: Optional[str] = None,
        group_id: Optional[int] = None,
        column_types: Optional[Dict[str, str]] = None,
        parent_id: Optional[int] = None
    ) -> Tuple[Resource, TableResource]:
        """
        Create a table resource with ChromaDB embedding.

        Args:
            db: Database session
            name: Resource display name
            table_data: Dict with "columns" and "data" keys
                       {"columns": ["col1", "col2"], "data": [[v1, v2], [v3, v4]]}
            created_by: User ID
            description: Optional description
            group_id: Optional group for sharing
            column_types: Optional column type mapping {"col1": "string", ...}
            parent_id: Optional parent resource ID for derived resources

        Returns:
            Tuple of (Resource, TableResource)
        """
        # Validate table data structure
        if "columns" not in table_data or "data" not in table_data:
            raise ValueError("table_data must have 'columns' and 'data' keys")

        columns = table_data["columns"]
        data = table_data["data"]

        # Create base resource
        resource = ResourceService.create_resource(
            db, ResourceType.TABLE, name, created_by, description, group_id,
            parent_id=parent_id
        )

        # Serialize table data
        table_json = json.dumps(table_data)
        column_names_json = json.dumps(columns)
        column_types_json = json.dumps(column_types) if column_types else None

        # Create table resource
        table_resource = TableResource(
            resource_id=resource.id,
            table_data=table_json,
            row_count=len(data),
            column_count=len(columns),
            column_names=column_names_json,
            column_types=column_types_json
        )
        db.add(table_resource)
        db.flush()

        # Create text representation for ChromaDB
        # Format: column names + first few rows as text
        text_repr = f"Table: {name}\nColumns: {', '.join(columns)}\n"
        for i, row in enumerate(data[:10]):  # First 10 rows
            text_repr += f"Row {i+1}: {', '.join(str(v) for v in row)}\n"
        if len(data) > 10:
            text_repr += f"... and {len(data) - 10} more rows"

        # Add to ChromaDB
        chromadb_id = ResourceService._add_to_chromadb(
            resource.id,
            ResourceType.TABLE.value,
            text_repr,
            {
                "resource_id": resource.id,
                "name": name,
                "type": ResourceType.TABLE.value,
                "row_count": len(data),
                "column_count": len(columns),
                "columns": column_names_json,
                "parent_id": parent_id if parent_id else ""
            }
        )
        table_resource.chromadb_id = chromadb_id

        db.commit()
        db.refresh(resource)
        db.refresh(table_resource)

        return resource, table_resource

    @staticmethod
    def create_timeseries_resource(
        db: Session,
        name: str,
        columns: List[str],
        frequency: TimeseriesFrequency,
        created_by: int,
        source: Optional[str] = None,
        description: Optional[str] = None,
        group_id: Optional[int] = None,
        data_type: TimeseriesDataType = TimeseriesDataType.FLOAT,
        unit: Optional[str] = None,
        parent_id: Optional[int] = None
    ) -> Tuple[Resource, TimeseriesMetadata]:
        """
        Create a timeseries resource (metadata only, data added separately).

        Args:
            db: Database session
            name: Timeseries name
            columns: List of column/variable names
            frequency: Data frequency
            created_by: User ID
            source: Data source
            description: Optional description
            group_id: Optional group for sharing
            data_type: Type of values (float, integer, string)
            unit: Unit of measurement
            parent_id: Optional parent resource ID for derived resources

        Returns:
            Tuple of (Resource, TimeseriesMetadata)
        """
        # Create base resource
        resource = ResourceService.create_resource(
            db, ResourceType.TIMESERIES, name, created_by, description, group_id,
            parent_id=parent_id
        )

        # Create timeseries metadata
        ts_metadata = TimeseriesMetadata(
            resource_id=resource.id,
            name=name,
            source=source,
            description=description,
            frequency=frequency,
            data_type=data_type,
            columns=json.dumps(columns),
            unit=unit,
            data_point_count=0
        )
        db.add(ts_metadata)
        db.commit()
        db.refresh(resource)
        db.refresh(ts_metadata)

        return resource, ts_metadata

    # ==========================================================================
    # TIMESERIES DATA OPERATIONS
    # ==========================================================================

    @staticmethod
    def add_timeseries_data(
        db: Session,
        tsid: int,
        data_points: List[Dict[str, Any]],
        user_id: int
    ) -> int:
        """
        Add data points to a timeseries.

        Args:
            db: Database session
            tsid: Timeseries metadata ID
            data_points: List of dicts with date, column_name, value/value_str
            user_id: User making the change

        Returns:
            Number of data points added
        """
        # Verify timeseries exists
        ts_meta = db.query(TimeseriesMetadata).filter(TimeseriesMetadata.id == tsid).first()
        if not ts_meta:
            raise ValueError(f"Timeseries with id {tsid} not found")

        revision_time = datetime.utcnow()
        count = 0
        min_date = None
        max_date = None

        for dp in data_points:
            date = dp.get("date")
            if isinstance(date, str):
                date = datetime.fromisoformat(date.replace("Z", "+00:00"))

            ts_data = TimeseriesData(
                tsid=tsid,
                date=date,
                column_name=dp.get("column_name"),
                value=dp.get("value"),
                value_str=dp.get("value_str"),
                revision_time=revision_time
            )
            db.add(ts_data)
            count += 1

            # Track date range
            if min_date is None or date < min_date:
                min_date = date
            if max_date is None or date > max_date:
                max_date = date

        # Update metadata
        ts_meta.data_point_count += count
        if min_date and (ts_meta.start_date is None or min_date < ts_meta.start_date):
            ts_meta.start_date = min_date
        if max_date and (ts_meta.end_date is None or max_date > ts_meta.end_date):
            ts_meta.end_date = max_date

        # Update resource modified_by
        resource = db.query(Resource).filter(Resource.id == ts_meta.resource_id).first()
        if resource:
            resource.modified_by = user_id

        db.commit()
        return count

    @staticmethod
    def get_timeseries_data(
        db: Session,
        tsid: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        columns: Optional[List[str]] = None,
        latest_revision_only: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Get timeseries data points.

        Args:
            db: Database session
            tsid: Timeseries metadata ID
            start_date: Filter start
            end_date: Filter end
            columns: Filter to specific columns
            latest_revision_only: Only get latest revision for each date/column

        Returns:
            List of data points as dicts
        """
        query = db.query(TimeseriesData).filter(TimeseriesData.tsid == tsid)

        if start_date:
            query = query.filter(TimeseriesData.date >= start_date)
        if end_date:
            query = query.filter(TimeseriesData.date <= end_date)
        if columns:
            query = query.filter(TimeseriesData.column_name.in_(columns))

        if latest_revision_only:
            # Subquery to get latest revision for each date/column
            from sqlalchemy import func
            subq = db.query(
                TimeseriesData.tsid,
                TimeseriesData.date,
                TimeseriesData.column_name,
                func.max(TimeseriesData.revision_time).label('max_rev')
            ).filter(
                TimeseriesData.tsid == tsid
            ).group_by(
                TimeseriesData.tsid,
                TimeseriesData.date,
                TimeseriesData.column_name
            ).subquery()

            query = query.join(
                subq,
                and_(
                    TimeseriesData.tsid == subq.c.tsid,
                    TimeseriesData.date == subq.c.date,
                    TimeseriesData.column_name == subq.c.column_name,
                    TimeseriesData.revision_time == subq.c.max_rev
                )
            )

        query = query.order_by(TimeseriesData.date, TimeseriesData.column_name)

        results = []
        for dp in query.all():
            results.append({
                "id": dp.id,
                "tsid": dp.tsid,
                "date": dp.date.isoformat() if dp.date else None,
                "column_name": dp.column_name,
                "value": dp.value,
                "value_str": dp.value_str,
                "revision_time": dp.revision_time.isoformat() if dp.revision_time else None
            })

        return results

    # ==========================================================================
    # RESOURCE RETRIEVAL
    # ==========================================================================

    @staticmethod
    def get_resource(db: Session, resource_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a resource by ID with its specialized data.

        Returns dict with resource data and type-specific data.
        """
        resource = db.query(Resource).filter(
            Resource.id == resource_id,
            Resource.is_active == True
        ).first()

        if not resource:
            return None

        result = {
            "id": resource.id,
            "hash_id": resource.hash_id,
            "resource_type": resource.resource_type.value if hasattr(resource.resource_type, 'value') else resource.resource_type,
            "status": resource.status.value if hasattr(resource.status, 'value') else resource.status,
            "name": resource.name,
            "description": resource.description,
            "group_id": resource.group_id,
            "parent_id": resource.parent_id,
            "created_by": resource.created_by,
            "modified_by": resource.modified_by,
            "created_at": resource.created_at.isoformat() if resource.created_at else None,
            "updated_at": resource.updated_at.isoformat() if resource.updated_at else None,
            "is_active": resource.is_active
        }

        # Add children info if this resource has children
        if hasattr(resource, 'children') and resource.children:
            result["children"] = [
                {
                    "id": child.id,
                    "hash_id": child.hash_id,
                    "resource_type": child.resource_type.value if hasattr(child.resource_type, 'value') else child.resource_type,
                    "name": child.name
                }
                for child in resource.children if child.is_active
            ]

        # Add type-specific data
        rt = resource.resource_type
        if isinstance(rt, str):
            rt = ResourceType(rt)

        if rt in [ResourceType.IMAGE, ResourceType.PDF, ResourceType.EXCEL,
                  ResourceType.ZIP, ResourceType.CSV]:
            if resource.file_resource:
                result["file_data"] = {
                    "filename": resource.file_resource.filename,
                    "file_path": resource.file_resource.file_path,
                    "file_size": resource.file_resource.file_size,
                    "mime_type": resource.file_resource.mime_type,
                    "checksum": resource.file_resource.checksum
                }

        elif rt == ResourceType.TEXT:
            if resource.text_resource:
                result["text_data"] = {
                    "content": resource.text_resource.content,
                    "encoding": resource.text_resource.encoding,
                    "char_count": resource.text_resource.char_count,
                    "word_count": resource.text_resource.word_count,
                    "chromadb_id": resource.text_resource.chromadb_id
                }

        elif rt == ResourceType.TABLE:
            if resource.table_resource:
                result["table_data"] = {
                    "data": json.loads(resource.table_resource.table_data),
                    "row_count": resource.table_resource.row_count,
                    "column_count": resource.table_resource.column_count,
                    "column_names": json.loads(resource.table_resource.column_names),
                    "column_types": json.loads(resource.table_resource.column_types) if resource.table_resource.column_types else None,
                    "chromadb_id": resource.table_resource.chromadb_id
                }

        elif rt == ResourceType.TIMESERIES:
            if resource.timeseries_metadata:
                result["timeseries_data"] = {
                    "tsid": resource.timeseries_metadata.id,
                    "name": resource.timeseries_metadata.name,
                    "source": resource.timeseries_metadata.source,
                    "frequency": resource.timeseries_metadata.frequency.value if hasattr(resource.timeseries_metadata.frequency, 'value') else resource.timeseries_metadata.frequency,
                    "data_type": resource.timeseries_metadata.data_type.value if hasattr(resource.timeseries_metadata.data_type, 'value') else resource.timeseries_metadata.data_type,
                    "columns": json.loads(resource.timeseries_metadata.columns),
                    "start_date": resource.timeseries_metadata.start_date.isoformat() if resource.timeseries_metadata.start_date else None,
                    "end_date": resource.timeseries_metadata.end_date.isoformat() if resource.timeseries_metadata.end_date else None,
                    "data_point_count": resource.timeseries_metadata.data_point_count,
                    "unit": resource.timeseries_metadata.unit
                }

        return result

    @staticmethod
    def get_resource_by_hash_id(db: Session, hash_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a resource by its public hash_id.

        This method is used for public-facing URLs like /resource/{hash_id}
        to serve resource content without exposing internal database IDs.

        Args:
            db: Database session
            hash_id: Public hash identifier

        Returns:
            Dict with resource data and type-specific data, or None if not found
        """
        resource = db.query(Resource).filter(
            Resource.hash_id == hash_id,
            Resource.is_active == True
        ).first()

        if not resource:
            return None

        # Use get_resource to get full resource data
        return ResourceService.get_resource(db, resource.id)

    @staticmethod
    def get_resource_file_path(db: Session, hash_id: str) -> Optional[Tuple[str, str, str]]:
        """
        Get the file path and MIME type for a file-based resource by hash_id.

        Used for serving file content directly via URL.

        Args:
            db: Database session
            hash_id: Public hash identifier

        Returns:
            Tuple of (relative_file_path, mime_type, filename) or None if not found/not a file
            Note: Returns relative path for use with StorageService (works with both local and S3)
        """
        resource = db.query(Resource).filter(
            Resource.hash_id == hash_id,
            Resource.is_active == True
        ).first()

        if not resource:
            return None

        rt = resource.resource_type
        if isinstance(rt, str):
            rt = ResourceType(rt)

        # Only file-based resources can be served
        # ARTICLE resources now store popup HTML as a file in S3
        # HTML resources are standalone HTML files (e.g., sortable tables from published tables)
        if rt not in [ResourceType.IMAGE, ResourceType.PDF, ResourceType.EXCEL,
                      ResourceType.ZIP, ResourceType.CSV, ResourceType.ARTICLE, ResourceType.HTML]:
            return None

        if not resource.file_resource:
            return None

        # Return relative path (StorageService handles actual path/S3 key resolution)
        return (
            resource.file_resource.file_path,
            resource.file_resource.mime_type,
            resource.file_resource.filename
        )

    @staticmethod
    def list_resources(
        db: Session,
        resource_type: Optional[ResourceType] = None,
        group_id: Optional[int] = None,
        created_by: Optional[int] = None,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
        global_only: bool = False,
        exclude_article_linked: bool = False
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        List resources with filtering.

        Args:
            global_only: If True, only return resources with group_id = NULL (global resources)
            exclude_article_linked: If True, exclude resources that are linked to any article

        Returns tuple of (list of resource dicts, total count).
        """
        query = db.query(Resource).filter(Resource.is_active == True)

        if resource_type:
            query = query.filter(Resource.resource_type == resource_type)
        if global_only:
            query = query.filter(Resource.group_id == None)
        elif group_id:
            query = query.filter(Resource.group_id == group_id)
        if created_by:
            query = query.filter(Resource.created_by == created_by)
        if exclude_article_linked:
            # Exclude resources that are linked to any article, EXCEPT for ARTICLE type resources
            # ARTICLE resources represent published articles and should always be visible
            from sqlalchemy import exists, select
            linked_subquery = select(article_resources.c.resource_id).where(
                article_resources.c.resource_id == Resource.id
            ).exists()
            # Include resource if: NOT linked to article OR is an ARTICLE type resource
            query = query.filter(
                or_(
                    ~linked_subquery,
                    Resource.resource_type == ResourceType.ARTICLE
                )
            )
        if search:
            search_pattern = f"%{search}%"
            query = query.filter(
                or_(
                    Resource.name.ilike(search_pattern),
                    Resource.description.ilike(search_pattern)
                )
            )

        total = query.count()
        resources = query.order_by(desc(Resource.created_at)).offset(offset).limit(limit).all()

        results = []
        for r in resources:
            results.append({
                "id": r.id,
                "hash_id": r.hash_id,
                "resource_type": r.resource_type.value if hasattr(r.resource_type, 'value') else r.resource_type,
                "status": r.status.value if hasattr(r.status, 'value') else r.status,
                "name": r.name,
                "description": r.description,
                "group_id": r.group_id,
                "parent_id": r.parent_id,
                "created_by": r.created_by,
                "modified_by": r.modified_by,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                "is_active": r.is_active
            })

        return results, total

    # ==========================================================================
    # RESOURCE UPDATE/DELETE
    # ==========================================================================

    @staticmethod
    def update_resource(
        db: Session,
        resource_id: int,
        user_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        group_id: Optional[int] = None
    ) -> Optional[Resource]:
        """Update resource metadata."""
        resource = db.query(Resource).filter(
            Resource.id == resource_id,
            Resource.is_active == True
        ).first()

        if not resource:
            return None

        if name is not None:
            resource.name = name
        if description is not None:
            resource.description = description
        if group_id is not None:
            resource.group_id = group_id

        resource.modified_by = user_id
        db.commit()
        db.refresh(resource)

        return resource

    @staticmethod
    def update_text_content(
        db: Session,
        resource_id: int,
        content: str,
        user_id: int,
        encoding: str = "utf-8"
    ) -> Optional[Resource]:
        """Update text resource content."""
        resource = db.query(Resource).filter(
            Resource.id == resource_id,
            Resource.is_active == True,
            Resource.resource_type == ResourceType.TEXT
        ).first()

        if not resource or not resource.text_resource:
            return None

        # Update text content
        resource.text_resource.content = content
        resource.text_resource.encoding = encoding
        resource.text_resource.word_count = len(content.split())
        resource.text_resource.char_count = len(content)
        resource.modified_by = user_id

        # Update ChromaDB embedding
        ResourceService._update_chromadb(
            resource_id=resource_id,
            resource_type="text",
            content=content,
            metadata={
                "resource_id": resource_id,
                "name": resource.name,
                "type": "text"
            }
        )

        db.commit()
        db.refresh(resource)

        logger.info(f"Text resource {resource_id} content updated")
        return resource

    @staticmethod
    def update_table_content(
        db: Session,
        resource_id: int,
        table_data: dict,
        user_id: int,
        column_types: Optional[dict] = None
    ) -> Optional[Resource]:
        """Update table resource content."""
        resource = db.query(Resource).filter(
            Resource.id == resource_id,
            Resource.is_active == True,
            Resource.resource_type == ResourceType.TABLE
        ).first()

        if not resource or not resource.table_resource:
            return None

        columns = table_data.get("columns", [])
        data = table_data.get("data", [])

        # Update table content
        resource.table_resource.columns = columns
        resource.table_resource.data = data
        resource.table_resource.row_count = len(data)
        resource.table_resource.column_count = len(columns)
        if column_types:
            resource.table_resource.column_types = column_types
        resource.modified_by = user_id

        # Create text representation for ChromaDB
        text_content = f"Table: {resource.name}\nColumns: {', '.join(columns)}\n"
        for row in data[:10]:  # First 10 rows for embedding
            text_content += " | ".join(str(cell) for cell in row) + "\n"

        ResourceService._update_chromadb(
            resource_id=resource_id,
            resource_type="table",
            content=text_content,
            metadata={
                "resource_id": resource_id,
                "name": resource.name,
                "type": "table",
                "row_count": len(data),
                "column_count": len(columns)
            }
        )

        db.commit()
        db.refresh(resource)

        logger.info(f"Table resource {resource_id} content updated ({len(data)} rows)")
        return resource

    @staticmethod
    def update_timeseries_data(
        db: Session,
        resource_id: int,
        data: List[dict],
        user_id: int
    ) -> Optional[Resource]:
        """Update timeseries data."""
        from models import TimeseriesData

        resource = db.query(Resource).filter(
            Resource.id == resource_id,
            Resource.is_active == True,
            Resource.resource_type == ResourceType.TIMESERIES
        ).first()

        if not resource or not resource.timeseries_metadata:
            return None

        metadata = resource.timeseries_metadata

        # Clear existing data
        db.query(TimeseriesData).filter(
            TimeseriesData.metadata_id == metadata.id
        ).delete()

        # Insert new data
        for row in data:
            ts_data = TimeseriesData(
                metadata_id=metadata.id,
                timestamp=row.get("timestamp"),
                values=row.get("values", {})
            )
            db.add(ts_data)

        # Update metadata stats
        metadata.data_points = len(data)
        if data:
            timestamps = [row.get("timestamp") for row in data if row.get("timestamp")]
            if timestamps:
                metadata.start_date = min(timestamps)
                metadata.end_date = max(timestamps)

        resource.modified_by = user_id
        db.commit()
        db.refresh(resource)

        logger.info(f"Timeseries resource {resource_id} data updated ({len(data)} points)")
        return resource

    @staticmethod
    def _update_chromadb(
        resource_id: int,
        resource_type: str,
        content: str,
        metadata: Dict[str, Any]
    ) -> bool:
        """Update resource content in ChromaDB."""
        collection = _get_resource_collection()
        if collection is None:
            return False

        try:
            doc_id = ResourceService._make_resource_doc_id(resource_id, resource_type)

            # Generate new embedding
            embedding = VectorService._generate_embedding(content)
            if not embedding:
                return False

            # Clean metadata
            clean_metadata = {}
            for k, v in metadata.items():
                if v is None:
                    clean_metadata[k] = ""
                elif isinstance(v, (str, int, float, bool)):
                    clean_metadata[k] = v
                else:
                    clean_metadata[k] = str(v)

            # Update in ChromaDB
            collection.upsert(
                ids=[doc_id],
                embeddings=[embedding],
                documents=[content[:10000]],
                metadatas=[clean_metadata]
            )

            return True
        except Exception as e:
            logger.error(f"Failed to update ChromaDB for resource {resource_id}: {e}")
            return False

    @staticmethod
    def delete_resource(db: Session, resource_id: int, user_id: int) -> bool:
        """
        Soft delete a resource.
        Also removes from ChromaDB if applicable.
        """
        resource = db.query(Resource).filter(
            Resource.id == resource_id,
            Resource.is_active == True
        ).first()

        if not resource:
            return False

        rt = resource.resource_type
        if isinstance(rt, str):
            rt = ResourceType(rt)

        # Remove from ChromaDB if text or table
        if rt in [ResourceType.TEXT, ResourceType.TABLE]:
            ResourceService._delete_from_chromadb(resource_id, rt.value)

        # Soft delete
        resource.is_active = False
        resource.modified_by = user_id
        db.commit()

        return True

    # ==========================================================================
    # ARTICLE-RESOURCE LINKING
    # ==========================================================================

    @staticmethod
    def link_resource_to_article(
        db: Session,
        resource_id: int,
        article_id: int
    ) -> bool:
        """Link a resource to an article."""
        # Verify both exist
        resource = db.query(Resource).filter(Resource.id == resource_id).first()
        article = db.query(ContentArticle).filter(ContentArticle.id == article_id).first()

        if not resource or not article:
            return False

        # Check if link already exists
        existing = db.execute(
            article_resources.select().where(
                and_(
                    article_resources.c.article_id == article_id,
                    article_resources.c.resource_id == resource_id
                )
            )
        ).first()

        if existing:
            return True  # Already linked

        # Create link
        db.execute(
            article_resources.insert().values(
                article_id=article_id,
                resource_id=resource_id
            )
        )
        db.commit()
        return True

    @staticmethod
    def unlink_resource_from_article(
        db: Session,
        resource_id: int,
        article_id: int,
        auto_purge: bool = True
    ) -> bool:
        """
        Remove link between resource and article.
        If auto_purge is True, checks if resource is orphaned and purges it.
        """
        result = db.execute(
            article_resources.delete().where(
                and_(
                    article_resources.c.article_id == article_id,
                    article_resources.c.resource_id == resource_id
                )
            )
        )
        db.commit()

        # Check if resource is now orphaned and purge if so
        if auto_purge and result.rowcount > 0:
            ResourceService.check_and_purge_orphan(db, resource_id)

        return result.rowcount > 0

    # ==========================================================================
    # STATUS MANAGEMENT
    # ==========================================================================

    @staticmethod
    def update_resource_status(
        db: Session,
        resource_id: int,
        status: ResourceStatus,
        user_id: int
    ) -> Optional[Resource]:
        """
        Update resource status (editorial workflow).

        Status transitions: draft -> editor -> published
        """
        resource = db.query(Resource).filter(
            Resource.id == resource_id,
            Resource.is_active == True
        ).first()

        if not resource:
            return None

        resource.status = status
        resource.modified_by = user_id
        db.commit()
        db.refresh(resource)

        logger.info(f"Resource {resource_id} status updated to {status.value}")
        return resource

    # ==========================================================================
    # ORPHAN RESOURCE MANAGEMENT
    # ==========================================================================

    @staticmethod
    def is_orphan(db: Session, resource_id: int) -> bool:
        """
        Check if a resource is orphaned (has no article or group links).

        A resource is orphaned if:
        - It has no linked articles (no entries in article_resources)
        - It has no group assignment (group_id is NULL)
        """
        resource = db.query(Resource).filter(Resource.id == resource_id).first()
        if not resource:
            return False

        # Check if has group
        if resource.group_id is not None:
            return False

        # Check if has any article links
        article_count = db.execute(
            article_resources.select().where(
                article_resources.c.resource_id == resource_id
            )
        ).fetchall()

        return len(article_count) == 0

    @staticmethod
    def check_and_purge_orphan(db: Session, resource_id: int) -> bool:
        """
        Check if resource is orphaned and purge if so.

        Returns True if resource was purged, False otherwise.
        """
        if not ResourceService.is_orphan(db, resource_id):
            return False

        return ResourceService.purge_resource(db, resource_id)

    @staticmethod
    def purge_resource(db: Session, resource_id: int) -> bool:
        """
        Completely delete a resource and all its data.

        This performs a HARD DELETE (not soft delete):
        - Removes from ChromaDB if text/table
        - Deletes file from filesystem if file-based
        - Deletes all database records (cascade)
        """
        resource = db.query(Resource).filter(Resource.id == resource_id).first()
        if not resource:
            return False

        rt = resource.resource_type
        if isinstance(rt, str):
            rt = ResourceType(rt)

        logger.info(f"Purging orphan resource {resource_id} (type: {rt.value})")

        # Remove from ChromaDB if text or table
        if rt in [ResourceType.TEXT, ResourceType.TABLE]:
            ResourceService._delete_from_chromadb(resource_id, rt.value)

        # Delete file from filesystem if file-based
        if rt in [ResourceType.IMAGE, ResourceType.PDF, ResourceType.EXCEL,
                  ResourceType.ZIP, ResourceType.CSV]:
            if resource.file_resource and resource.file_resource.file_path:
                try:
                    file_path = os.path.join("/app/uploads", resource.file_resource.file_path)
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Deleted file: {file_path}")
                except Exception as e:
                    logger.error(f"Failed to delete file: {e}")

        # Hard delete from database (cascades to specialized tables)
        db.delete(resource)
        db.commit()

        logger.info(f"✓ Purged orphan resource {resource_id}")
        return True

    @staticmethod
    def purge_all_orphans(db: Session) -> int:
        """
        Find and purge all orphaned resources.

        Returns the number of resources purged.
        """
        # Find resources with no group and no article links
        # Using a subquery to find resources that have article links
        from sqlalchemy import exists, select

        resources_with_articles = select(article_resources.c.resource_id).distinct()

        orphan_query = db.query(Resource).filter(
            Resource.group_id == None,
            ~Resource.id.in_(resources_with_articles)
        )

        orphans = orphan_query.all()
        purged_count = 0

        for resource in orphans:
            if ResourceService.purge_resource(db, resource.id):
                purged_count += 1

        if purged_count > 0:
            logger.info(f"✓ Purged {purged_count} orphan resources")

        return purged_count

    @staticmethod
    def get_article_resources(db: Session, article_id: int) -> List[Dict[str, Any]]:
        """Get all resources linked to an article."""
        article = db.query(ContentArticle).filter(ContentArticle.id == article_id).first()
        if not article:
            return []

        results = []
        for r in article.resources:
            if r.is_active:
                results.append({
                    "id": r.id,
                    "hash_id": r.hash_id,
                    "resource_type": r.resource_type.value if hasattr(r.resource_type, 'value') else r.resource_type,
                    "status": r.status.value if hasattr(r.status, 'value') else r.status,
                    "name": r.name,
                    "description": r.description
                })

        return results

    @staticmethod
    def get_resource_articles(db: Session, resource_id: int) -> List[Dict[str, Any]]:
        """Get all articles linked to a resource."""
        resource = db.query(Resource).filter(Resource.id == resource_id).first()
        if not resource:
            return []

        results = []
        for a in resource.articles:
            if a.is_active:
                results.append({
                    "id": a.id,
                    "headline": a.headline,
                    "topic": a.topic,
                    "status": a.status.value if hasattr(a.status, 'value') else a.status
                })

        return results

    # ==========================================================================
    # SEMANTIC SEARCH
    # ==========================================================================

    @staticmethod
    def get_resource_ids_by_group(db: Session, group_id: int) -> List[int]:
        """
        Get all resource IDs for a specific group.

        Args:
            db: Database session
            group_id: Group ID to filter by

        Returns:
            List of resource IDs
        """
        resources = db.query(Resource.id).filter(
            Resource.group_id == group_id,
            Resource.is_active == True
        ).all()
        return [r.id for r in resources]

    @staticmethod
    def get_resource_ids_by_article(db: Session, article_id: int) -> List[int]:
        """
        Get all resource IDs attached to a specific article.

        Args:
            db: Database session
            article_id: Article ID

        Returns:
            List of resource IDs
        """
        from models import ArticleResource
        article_resources = db.query(ArticleResource.resource_id).filter(
            ArticleResource.article_id == article_id
        ).all()
        return [ar.resource_id for ar in article_resources]

    @staticmethod
    def get_resource_ids_for_topic(db: Session, topic: str) -> List[int]:
        """
        Get all resource IDs for a topic (from the topic's admin group).

        Args:
            db: Database session
            topic: Topic name (macro, equity, fixed_income, esg)

        Returns:
            List of resource IDs
        """
        from models import Group
        # Find the topic's admin group (e.g., "macro:admin")
        group = db.query(Group).filter(
            Group.groupname == f"{topic}:admin"
        ).first()

        if not group:
            return []

        return ResourceService.get_resource_ids_by_group(db, group.id)

    @staticmethod
    def semantic_search_resources(
        query: str,
        resource_type: Optional[str] = None,
        limit: int = 10,
        resource_ids: Optional[List[int]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search for text and table resources.

        Args:
            query: Search query
            resource_type: Filter to specific type (text or table)
            limit: Max results
            resource_ids: Optional list of resource IDs to filter by

        Returns:
            List of matching resources with similarity scores
        """
        collection = _get_resource_collection()
        if collection is None:
            return []

        # If filtering by resource_ids and none provided, return empty
        if resource_ids is not None and len(resource_ids) == 0:
            return []

        try:
            # Generate query embedding
            query_embedding = VectorService._generate_embedding(query)
            if not query_embedding:
                return []

            # Build where filter
            where_filter = None
            if resource_type and resource_ids:
                # Both type and resource_ids filter
                where_filter = {
                    "$and": [
                        {"type": resource_type},
                        {"resource_id": {"$in": resource_ids}}
                    ]
                }
            elif resource_type:
                where_filter = {"type": resource_type}
            elif resource_ids:
                where_filter = {"resource_id": {"$in": resource_ids}}

            # Query collection - get more results if filtering by IDs
            n_results = limit * 3 if resource_ids else limit

            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_filter
            )

            # Format results
            resources = []
            if results['ids'] and len(results['ids']) > 0:
                for i, doc_id in enumerate(results['ids'][0]):
                    resource_id = results['metadatas'][0][i].get('resource_id')

                    # Additional filter check (belt and suspenders)
                    if resource_ids and resource_id not in resource_ids:
                        continue

                    resources.append({
                        'resource_id': resource_id,
                        'name': results['metadatas'][0][i].get('name'),
                        'type': results['metadatas'][0][i].get('type'),
                        'similarity_score': 1 - results['distances'][0][i],
                        'content_preview': results['documents'][0][i][:200] if results['documents'][0][i] else None
                    })

                    if len(resources) >= limit:
                        break

            return resources

        except Exception as e:
            logger.error(f"Resource semantic search error: {e}")
            return []

    @staticmethod
    def semantic_search_for_content(
        db: Session,
        query: str,
        topic: Optional[str] = None,
        article_id: Optional[int] = None,
        resource_type: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Semantic search scoped to a topic and/or article resources.

        This method searches:
        1. Resources in the topic's group (if topic provided)
        2. Resources attached to the article (if article_id provided)
        3. Combines and deduplicates results

        Args:
            db: Database session
            query: Search query
            topic: Topic name (macro, equity, fixed_income, esg)
            article_id: Article ID for article-specific resources
            resource_type: Filter to specific type (text or table)
            limit: Max results

        Returns:
            List of matching resources with similarity scores
        """
        # Collect resource IDs from both sources
        all_resource_ids = set()

        if topic:
            topic_ids = ResourceService.get_resource_ids_for_topic(db, topic)
            all_resource_ids.update(topic_ids)
            logger.info(f"Found {len(topic_ids)} resources for topic '{topic}'")

        if article_id:
            article_ids = ResourceService.get_resource_ids_by_article(db, article_id)
            all_resource_ids.update(article_ids)
            logger.info(f"Found {len(article_ids)} resources for article {article_id}")

        if not all_resource_ids:
            logger.info("No resources found for the given topic/article")
            return []

        # Search with combined resource IDs
        return ResourceService.semantic_search_resources(
            query=query,
            resource_type=resource_type,
            limit=limit,
            resource_ids=list(all_resource_ids)
        )

    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================

    @staticmethod
    def calculate_file_checksum(file_path: str) -> Optional[str]:
        """Calculate SHA-256 checksum of a file."""
        try:
            sha256_hash = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha256_hash.update(chunk)
            return sha256_hash.hexdigest()
        except Exception as e:
            logger.error(f"Failed to calculate checksum: {e}")
            return None

    @staticmethod
    def get_mime_type_for_resource_type(resource_type: ResourceType) -> List[str]:
        """Get allowed MIME types for a resource type."""
        mime_types = {
            ResourceType.IMAGE: ["image/png", "image/jpeg", "image/gif", "image/webp", "image/svg+xml"],
            ResourceType.PDF: ["application/pdf"],
            ResourceType.EXCEL: [
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/vnd.ms-excel"
            ],
            ResourceType.ZIP: ["application/zip", "application/x-zip-compressed"],
            ResourceType.CSV: ["text/csv", "application/csv"]
        }
        return mime_types.get(resource_type, [])
