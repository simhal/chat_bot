# Architecture Diagrams

This directory contains Mermaid diagrams that visualize the system architecture. These diagrams can be rendered in any Markdown viewer that supports Mermaid, or converted to images using the Mermaid CLI.

## Diagram Index

| Diagram | Description |
|---------|-------------|
| [system-architecture.mmd](./system-architecture.mmd) | High-level overview of all system components |
| [api-routes.mmd](./api-routes.mmd) | API endpoint structure organized by role |
| [permission-model.mmd](./permission-model.mmd) | Role hierarchy and permission scopes |
| [article-lifecycle.mmd](./article-lifecycle.mmd) | Article status transitions (Draft → Editor → Published) |
| [multi-agent-workflow.mmd](./multi-agent-workflow.mmd) | LangGraph agent routing and sub-graphs |
| [authentication-flow.mmd](./authentication-flow.mmd) | LinkedIn OAuth sequence |
| [hitl-workflow.mmd](./hitl-workflow.mmd) | Human-in-the-loop approval process |
| [frontend-architecture.mmd](./frontend-architecture.mmd) | SvelteKit pages, components, and stores |
| [data-flow.mmd](./data-flow.mmd) | Request/response data flow through the system |

## Viewing Diagrams

### In GitHub/GitLab
Most Git hosting platforms render Mermaid diagrams automatically in Markdown files.

### In VS Code
Install the "Markdown Preview Mermaid Support" extension.

### In Browser
Use the [Mermaid Live Editor](https://mermaid.live/) - paste the diagram code to view and export.

### Command Line
Use the Mermaid CLI to generate PNG/SVG:

```bash
npm install -g @mermaid-js/mermaid-cli
mmdc -i diagram.mmd -o diagram.png
```

## Diagram Theme

All diagrams use the `base` theme for clean, professional rendering:

```mermaid
%%{init: {'theme': 'base'}}%%
```
