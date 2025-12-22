"""Service for managing table resource publishing and child resource generation."""

import os
import uuid
import hashlib
import html
from datetime import datetime
from typing import Optional, Tuple
from sqlalchemy.orm import Session
import logging
from io import BytesIO

from models import (
    Resource, ResourceType, ResourceStatus, FileResource, TextResource, TableResource
)
from services.storage_service import get_storage

logger = logging.getLogger("uvicorn")


def _generate_table_image(name: str, columns: list, data: list) -> Optional[bytes]:
    """
    Generate a PNG image of a table using matplotlib.

    Args:
        name: Table name for title
        columns: List of column names
        data: List of rows, each row is a list of cell values

    Returns:
        PNG image bytes or None on error
    """
    try:
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        import matplotlib.pyplot as plt
        from matplotlib.table import Table as MplTable

        # Limit rows for image (too many rows = unreadable image)
        max_rows = 25
        display_data = data[:max_rows]
        truncated = len(data) > max_rows

        # Calculate figure size based on data
        n_cols = len(columns) if columns else 1
        n_rows = len(display_data) + 1  # +1 for header
        fig_width = max(8, min(16, n_cols * 1.5))
        fig_height = max(2, min(12, n_rows * 0.4))

        fig, ax = plt.subplots(figsize=(fig_width, fig_height))
        ax.axis('off')
        ax.set_title(name, fontsize=12, fontweight='bold', pad=10)

        # Format data for table
        cell_text = []
        for row in display_data:
            formatted_row = []
            for cell in row:
                if cell is None:
                    formatted_row.append('')
                elif isinstance(cell, float):
                    formatted_row.append(f'{cell:,.2f}')
                else:
                    formatted_row.append(str(cell)[:30])  # Truncate long text
            cell_text.append(formatted_row)

        if truncated:
            cell_text.append(['...' for _ in columns])

        # Create table
        table = ax.table(
            cellText=cell_text,
            colLabels=columns,
            cellLoc='center',
            loc='center',
            colColours=['#f8fafc'] * n_cols
        )

        # Style the table
        table.auto_set_font_size(False)
        table.set_fontsize(8)
        table.scale(1.2, 1.5)

        # Style header row
        for j in range(n_cols):
            cell = table[0, j]
            cell.set_text_props(weight='bold')
            cell.set_facecolor('#e2e8f0')

        # Alternate row colors
        for i in range(1, len(cell_text) + 1):
            for j in range(n_cols):
                if i % 2 == 0:
                    table[i, j].set_facecolor('#fafbfc')

        plt.tight_layout()

        # Save to bytes
        buf = BytesIO()
        fig.savefig(buf, format='png', dpi=150, bbox_inches='tight',
                    facecolor='white', edgecolor='none')
        plt.close(fig)
        buf.seek(0)

        return buf.getvalue()

    except Exception as e:
        logger.error(f"Failed to generate table image: {e}")
        return None


class TableResourceService:
    """
    Service for creating child resources when table resources are published.

    When a table resource is published, this service creates:
    - HTML child resource: A dynamic sortable HTML table
    - Image child resource: A static image of the table (optional, for previews)
    """

    @staticmethod
    def _generate_table_styles(table_id: str) -> str:
        """Generate CSS styles for an interactive table."""
        return f'''
        .embedded-table-{table_id} {{
            width: 100%;
            overflow-x: auto;
            margin: 1rem 0;
        }}
        .embedded-table-{table_id} table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.875rem;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            border: 1px solid #d1d5db;
        }}
        .embedded-table-{table_id} th {{
            background: #f9fafb;
            border: 1px solid #d1d5db;
            padding: 0.5rem 0.75rem;
            text-align: left;
            font-weight: 600;
            color: #374151;
            white-space: nowrap;
            cursor: pointer;
            user-select: none;
        }}
        .embedded-table-{table_id} th:hover {{
            background: #f3f4f6;
        }}
        .embedded-table-{table_id} th.dragging {{
            opacity: 0.5;
            background: #dbeafe;
        }}
        .embedded-table-{table_id} th.drag-over {{
            border-left: 2px solid #3b82f6;
        }}
        .embedded-table-{table_id} th .sort-icon {{
            display: inline-block;
            width: 14px;
            height: 12px;
            margin-left: 4px;
            vertical-align: middle;
            opacity: 0.4;
        }}
        .embedded-table-{table_id} th:hover .sort-icon {{
            opacity: 0.6;
        }}
        .embedded-table-{table_id} th .sort-icon svg {{
            width: 12px;
            height: 12px;
            fill: currentColor;
        }}
        .embedded-table-{table_id} th.sorted-asc .sort-icon,
        .embedded-table-{table_id} th.sorted-desc .sort-icon {{
            opacity: 1;
            color: #2563eb;
        }}
        .embedded-table-{table_id} td {{
            padding: 0.5rem 0.75rem;
            border: 1px solid #e5e7eb;
            color: #374151;
        }}
        .embedded-table-{table_id} tbody tr:hover {{
            background: #f9fafb;
        }}
        .embedded-table-{table_id} tr.selected {{
            background: #dbeafe !important;
        }}
        .embedded-table-{table_id} td.col-selected,
        .embedded-table-{table_id} th.col-selected {{
            background: #dbeafe !important;
        }}
        '''

    @staticmethod
    def _generate_table_script(table_id: str) -> str:
        """Generate JavaScript for interactive table features."""
        return f'''
        (function() {{
            const tableId = '{table_id}';
            const table = document.getElementById(tableId);
            if (!table) return;

            let sortColumn = -1;
            let sortDirection = 'none'; // 'none', 'asc', 'desc'
            let originalOrder = [];
            let dragSrcCol = null;
            let selectedRows = new Set();
            let selectedCols = new Set(); // Multi-column selection

            // SVG icons for sort indicators
            const icons = {{
                none: '<svg viewBox="0 0 24 24"><path d="M7 10l5-5 5 5H7zm10 4l-5 5-5-5h10z" opacity="0.4"/></svg>',
                asc: '<svg viewBox="0 0 24 24"><path d="M7 14l5-5 5 5H7z"/></svg>',
                desc: '<svg viewBox="0 0 24 24"><path d="M7 10l5 5 5-5H7z"/></svg>'
            }};

            // Save original row order on init
            function saveOriginalOrder() {{
                const tbody = table.querySelector('tbody');
                originalOrder = Array.from(tbody.querySelectorAll('tr'));
            }}
            saveOriginalOrder();

            // Update sort icons in all headers
            function updateSortIcons() {{
                const headers = table.querySelectorAll('th');
                headers.forEach((th, i) => {{
                    const iconSpan = th.querySelector('.sort-icon');
                    if (iconSpan) {{
                        th.classList.remove('sorted-asc', 'sorted-desc');
                        if (i === sortColumn && sortDirection !== 'none') {{
                            iconSpan.innerHTML = icons[sortDirection];
                            th.classList.add(sortDirection === 'asc' ? 'sorted-asc' : 'sorted-desc');
                        }} else {{
                            iconSpan.innerHTML = icons.none;
                        }}
                    }}
                }});
            }}

            // Initialize icons
            updateSortIcons();

            // Column sorting with 3-state cycle: none -> asc -> desc -> none
            function sortTable(columnIndex) {{
                const tbody = table.querySelector('tbody');
                const rows = Array.from(tbody.querySelectorAll('tr'));

                // Determine next sort state
                if (sortColumn === columnIndex) {{
                    // Cycle: asc -> desc -> none
                    if (sortDirection === 'asc') {{
                        sortDirection = 'desc';
                    }} else if (sortDirection === 'desc') {{
                        sortDirection = 'none';
                    }} else {{
                        sortDirection = 'asc';
                    }}
                }} else {{
                    sortColumn = columnIndex;
                    sortDirection = 'asc';
                }}

                updateSortIcons();

                // If returning to original order
                if (sortDirection === 'none') {{
                    originalOrder.forEach(row => tbody.appendChild(row));
                    return;
                }}

                // Sort rows
                rows.sort((a, b) => {{
                    const aVal = a.cells[columnIndex]?.textContent?.trim() || '';
                    const bVal = b.cells[columnIndex]?.textContent?.trim() || '';
                    const aNum = parseFloat(aVal.replace(/[,\\s]/g, ''));
                    const bNum = parseFloat(bVal.replace(/[,\\s]/g, ''));

                    if (!isNaN(aNum) && !isNaN(bNum)) {{
                        return sortDirection === 'asc' ? aNum - bNum : bNum - aNum;
                    }}
                    return sortDirection === 'asc' ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
                }});

                rows.forEach(row => tbody.appendChild(row));
            }}

            // Column reordering via drag and drop
            function handleDragStart(e) {{
                dragSrcCol = this.cellIndex;
                this.classList.add('dragging');
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', dragSrcCol);
            }}

            function handleDragOver(e) {{
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                this.classList.add('drag-over');
            }}

            function handleDragLeave(e) {{
                this.classList.remove('drag-over');
            }}

            function handleDrop(e) {{
                e.preventDefault();
                e.stopPropagation();
                this.classList.remove('drag-over');

                const targetCol = this.cellIndex;
                if (dragSrcCol === null || dragSrcCol === targetCol) return;

                // Reorder columns in all rows
                const allRows = table.querySelectorAll('tr');
                allRows.forEach(row => {{
                    const cells = Array.from(row.children);
                    const srcCell = cells[dragSrcCol];
                    const targetCell = cells[targetCol];
                    if (dragSrcCol < targetCol) {{
                        row.insertBefore(srcCell, targetCell.nextSibling);
                    }} else {{
                        row.insertBefore(srcCell, targetCell);
                    }}
                }});

                // Reset sort state after reorder and save new original order
                sortColumn = -1;
                sortDirection = 'none';
                saveOriginalOrder();
                updateSortIcons();
            }}

            function handleDragEnd(e) {{
                table.querySelectorAll('th').forEach(th => {{
                    th.classList.remove('dragging', 'drag-over');
                }});
                dragSrcCol = null;
            }}

            // Row selection
            function handleRowClick(e) {{
                const row = e.target.closest('tr');
                if (!row || row.parentElement.tagName === 'THEAD') return;

                if (e.ctrlKey || e.metaKey) {{
                    row.classList.toggle('selected');
                    if (row.classList.contains('selected')) {{
                        selectedRows.add(row);
                    }} else {{
                        selectedRows.delete(row);
                    }}
                }} else if (e.shiftKey && selectedRows.size > 0) {{
                    const tbody = table.querySelector('tbody');
                    const rows = Array.from(tbody.querySelectorAll('tr'));
                    const lastSelected = Array.from(selectedRows).pop();
                    const startIdx = rows.indexOf(lastSelected);
                    const endIdx = rows.indexOf(row);
                    const [from, to] = startIdx < endIdx ? [startIdx, endIdx] : [endIdx, startIdx];
                    for (let i = from; i <= to; i++) {{
                        rows[i].classList.add('selected');
                        selectedRows.add(rows[i]);
                    }}
                }} else {{
                    table.querySelectorAll('tr.selected').forEach(r => r.classList.remove('selected'));
                    selectedRows.clear();
                    row.classList.add('selected');
                    selectedRows.add(row);
                }}
                // Clear column selection when selecting rows
                selectedCols.clear();
                table.querySelectorAll('th.col-selected, td.col-selected').forEach(c => c.classList.remove('col-selected'));
            }}

            // Column selection - supports multi-column with Ctrl+click
            function handleHeaderClick(e) {{
                if (e.target.closest('th')) {{
                    const th = e.target.closest('th');
                    const colIdx = th.cellIndex;

                    if (e.ctrlKey || e.metaKey) {{
                        // Toggle column selection (multi-select)
                        if (selectedCols.has(colIdx)) {{
                            selectedCols.delete(colIdx);
                        }} else {{
                            selectedCols.add(colIdx);
                        }}
                        // Clear row selection
                        table.querySelectorAll('tr.selected').forEach(r => r.classList.remove('selected'));
                        selectedRows.clear();
                        updateColumnHighlights();
                    }} else if (e.shiftKey && selectedCols.size > 0) {{
                        // Range selection for columns
                        const lastCol = Math.max(...selectedCols);
                        const [from, to] = colIdx < lastCol ? [colIdx, lastCol] : [lastCol, colIdx];
                        for (let i = from; i <= to; i++) {{
                            selectedCols.add(i);
                        }}
                        table.querySelectorAll('tr.selected').forEach(r => r.classList.remove('selected'));
                        selectedRows.clear();
                        updateColumnHighlights();
                    }} else {{
                        // Sort on regular click (no selection change)
                        sortTable(colIdx);
                    }}
                }}
            }}

            function updateColumnHighlights() {{
                // Clear all column highlights
                table.querySelectorAll('th.col-selected, td.col-selected').forEach(c => c.classList.remove('col-selected'));
                // Highlight selected columns
                selectedCols.forEach(colIdx => {{
                    table.querySelectorAll('tr').forEach(row => {{
                        const cell = row.children[colIdx];
                        if (cell) cell.classList.add('col-selected');
                    }});
                }});
            }}

            // Get header text without the sort icon
            function getHeaderText(th) {{
                if (!th) return '';
                // Get text from first text node only (before the sort-icon span)
                for (const node of th.childNodes) {{
                    if (node.nodeType === Node.TEXT_NODE) {{
                        return node.textContent.trim();
                    }}
                }}
                return '';
            }}

            // Copy selection to clipboard (rows or columns)
            function handleKeyDown(e) {{
                if ((e.ctrlKey || e.metaKey) && e.key === 'c') {{
                    let text = '';
                    if (selectedRows.size > 0) {{
                        // Copy selected rows
                        selectedRows.forEach(row => {{
                            text += Array.from(row.cells).map(c => c.textContent).join('\\t') + '\\n';
                        }});
                    }} else if (selectedCols.size > 0) {{
                        // Copy selected columns - include header
                        const headers = table.querySelectorAll('th');
                        const sortedCols = Array.from(selectedCols).sort((a, b) => a - b);
                        // Header row - use getHeaderText to handle empty headers correctly
                        text += sortedCols.map(i => getHeaderText(headers[i])).join('\\t') + '\\n';
                        // Data rows
                        table.querySelectorAll('tbody tr').forEach(row => {{
                            text += sortedCols.map(i => row.cells[i]?.textContent ?? '').join('\\t') + '\\n';
                        }});
                    }}
                    if (text) {{
                        navigator.clipboard.writeText(text.trim()).catch(err => console.error('Copy failed:', err));
                        e.preventDefault();
                    }}
                }}
            }}

            // Setup event listeners
            const headers = table.querySelectorAll('th');
            headers.forEach(th => {{
                th.draggable = true;
                th.addEventListener('dragstart', handleDragStart);
                th.addEventListener('dragover', handleDragOver);
                th.addEventListener('dragleave', handleDragLeave);
                th.addEventListener('drop', handleDrop);
                th.addEventListener('dragend', handleDragEnd);
            }});

            table.querySelector('thead').addEventListener('click', handleHeaderClick);
            table.querySelector('tbody').addEventListener('click', handleRowClick);
            document.addEventListener('keydown', handleKeyDown);
        }})();
        '''

    @staticmethod
    def _generate_embeddable_table_html(
        table_id: str,
        name: str,
        columns: list,
        data: list
    ) -> str:
        """
        Generate an embeddable HTML fragment for a table.

        This is used for embedding tables directly into articles.
        Includes styles, table HTML, and interactive JavaScript.

        Args:
            table_id: Unique ID for this table instance
            name: Table name
            columns: List of column names
            data: List of rows

        Returns:
            HTML fragment with embedded styles and scripts
        """
        safe_name = html.escape(name)

        # Generate table header
        header_cells = ''.join(
            f'<th>{html.escape(str(col))}<span class="sort-icon"></span></th>'
            for col in columns
        )

        # Generate table rows
        rows_html = ''
        for row in data:
            cells = ''.join(
                f'<td>{html.escape(str(cell)) if cell is not None else ""}</td>'
                for cell in row
            )
            rows_html += f'<tr>{cells}</tr>\n'

        styles = TableResourceService._generate_table_styles(table_id)
        script = TableResourceService._generate_table_script(table_id)

        return f'''<style>{styles}</style>
<div class="embedded-table-{table_id}">
    <table id="{table_id}">
        <thead>
            <tr>{header_cells}</tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</div>
<script>{script}</script>'''

    @staticmethod
    def _generate_sortable_table_html(
        name: str,
        columns: list,
        data: list,
        description: str = ""
    ) -> str:
        """
        Generate a standalone HTML page with an interactive table.

        Args:
            name: Table name/title
            columns: List of column names
            data: List of rows, each row is a list of cell values
            description: Optional table description

        Returns:
            Complete HTML document with interactive table
        """
        import uuid
        table_id = f"table-{uuid.uuid4().hex[:8]}"
        safe_name = html.escape(name)

        # Generate table header
        header_cells = ''.join(
            f'<th>{html.escape(str(col))}<span class="sort-icon"></span></th>'
            for col in columns
        )

        # Generate table rows
        rows_html = ''
        for row in data:
            cells = ''.join(
                f'<td>{html.escape(str(cell)) if cell is not None else ""}</td>'
                for cell in row
            )
            rows_html += f'<tr>{cells}</tr>\n'

        styles = TableResourceService._generate_table_styles(table_id)
        script = TableResourceService._generate_table_script(table_id)

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{safe_name}</title>
    <style>
        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f5f5;
            padding: 1rem;
        }}
        {styles}
    </style>
</head>
<body>
    <div class="embedded-table-{table_id}">
        <table id="{table_id}">
            <thead>
                <tr>{header_cells}</tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </div>
    <script>{script}</script>
</body>
</html>'''

    @staticmethod
    def create_table_publication_resources(
        db: Session,
        table_resource: Resource,
        user_id: int
    ) -> Tuple[Optional[Resource], Optional[Resource]]:
        """
        Create HTML and image child resources for a published table.

        Args:
            db: Database session
            table_resource: The parent table resource being published
            user_id: User performing the publish action

        Returns:
            Tuple of (html_resource, image_resource) or (None, None) on error
        """
        storage = get_storage()

        if not table_resource.table_resource:
            logger.warning(f"Table resource {table_resource.id} has no table data")
            return None, None

        try:
            # Get table data
            columns = table_resource.table_resource.columns or []
            data = table_resource.table_resource.data or []

            # Parse description for display
            description = ""
            if table_resource.description:
                # Extract just the description part (before any metadata)
                desc_lines = table_resource.description.split('\n')
                if desc_lines:
                    description = desc_lines[0]

            # Generate sortable HTML
            html_content = TableResourceService._generate_sortable_table_html(
                name=table_resource.name,
                columns=columns,
                data=data,
                description=description
            )

            # Save HTML to storage
            date_dir = datetime.now().strftime("%Y/%m")
            html_bytes = html_content.encode('utf-8')
            html_filename = f"{uuid.uuid4().hex}.html"
            html_path = f"{date_dir}/{html_filename}"

            # Create safe filename
            safe_name = "".join(
                c for c in table_resource.name if c.isalnum() or c in (' ', '-', '_')
            ).rstrip()
            safe_name = safe_name.replace(' ', '_')[:50]

            if not storage.save_file_with_metadata(
                html_path, html_bytes, "text/html",
                {"table_id": str(table_resource.id), "type": "table_html"}
            ):
                raise Exception("Failed to save HTML to storage")

            # Create HTML child resource
            html_resource = Resource(
                resource_type=ResourceType.HTML,
                name=f"{table_resource.name} - Interactive",
                description="Interactive HTML version of table with sorting",
                group_id=table_resource.group_id,
                created_by=user_id,
                modified_by=user_id,
                status=ResourceStatus.PUBLISHED,
                is_active=True,
                parent_id=table_resource.id
            )
            db.add(html_resource)
            db.flush()

            html_file_resource = FileResource(
                resource_id=html_resource.id,
                filename=f"{safe_name}_table.html",
                file_path=html_path,
                file_size=len(html_bytes),
                mime_type="text/html",
                checksum=hashlib.sha256(html_bytes).hexdigest()
            )
            db.add(html_file_resource)

            # Generate image resource using matplotlib
            image_resource = None
            image_bytes = _generate_table_image(
                name=table_resource.name,
                columns=columns,
                data=data
            )

            if image_bytes:
                image_filename = f"{uuid.uuid4().hex}.png"
                image_path = f"{date_dir}/{image_filename}"

                if storage.save_file_with_metadata(
                    image_path, image_bytes, "image/png",
                    {"table_id": str(table_resource.id), "type": "table_image"}
                ):
                    image_resource = Resource(
                        resource_type=ResourceType.IMAGE,
                        name=f"{table_resource.name} - Image",
                        description="Static image of table for PDF embedding",
                        group_id=table_resource.group_id,
                        created_by=user_id,
                        modified_by=user_id,
                        status=ResourceStatus.PUBLISHED,
                        is_active=True,
                        parent_id=table_resource.id
                    )
                    db.add(image_resource)
                    db.flush()

                    image_file_resource = FileResource(
                        resource_id=image_resource.id,
                        filename=f"{safe_name}_table.png",
                        file_path=image_path,
                        file_size=len(image_bytes),
                        mime_type="image/png",
                        checksum=hashlib.sha256(image_bytes).hexdigest()
                    )
                    db.add(image_file_resource)

            db.commit()
            db.refresh(html_resource)
            if image_resource:
                db.refresh(image_resource)

            logger.info(
                f"Created publication resources for table {table_resource.id}: "
                f"html={html_resource.id}, image={image_resource.id if image_resource else 'None'}"
            )

            return html_resource, image_resource

        except Exception as e:
            db.rollback()
            logger.error(f"Error creating table publication resources: {e}")
            return None, None

    @staticmethod
    def delete_table_publication_resources(db: Session, table_resource_id: int) -> int:
        """
        Delete child publication resources for a table.

        Called when a table is recalled from published status.

        Args:
            db: Database session
            table_resource_id: ID of the parent table resource

        Returns:
            Number of resources deleted
        """
        storage = get_storage()
        deleted_count = 0

        # Find child resources
        children = db.query(Resource).filter(
            Resource.parent_id == table_resource_id,
            Resource.is_active == True
        ).all()

        for child in children:
            # Only delete HTML and IMAGE children created by publishing
            if child.resource_type in [ResourceType.HTML, ResourceType.IMAGE]:
                # Clean up file if exists
                if child.file_resource and child.file_resource.file_path:
                    try:
                        storage.delete_file(child.file_resource.file_path)
                    except Exception as e:
                        logger.warning(f"Failed to delete file for resource {child.id}: {e}")

                child.is_active = False
                deleted_count += 1

        if deleted_count > 0:
            db.commit()
            logger.info(f"Deleted {deleted_count} publication resources for table {table_resource_id}")

        return deleted_count
