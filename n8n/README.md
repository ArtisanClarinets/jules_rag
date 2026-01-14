# Code RAG n8n Workflow

This directory contains an n8n workflow (`rag_workflow.json`) that integrates the Code RAG system as an AI Agent.

## Prerequisites

1.  **n8n**: You must have [n8n](https://n8n.io/) installed (self-hosted or cloud).
2.  **RAG Backend**: The Python backend from this repository must be running.
    ```bash
    # From the root of the repo
    python -m api.server
    ```
    This starts the API at `http://localhost:8000`.

## Installation

1.  Open your n8n dashboard.
2.  Go to **Workflows** > **Import from File**.
3.  Select `n8n/rag_workflow.json`.

## Configuration

### 1. Credentials
The workflow uses an OpenAI Chat Model. You need to configure your OpenAI credentials in n8n:
-   Double click the **OpenAI Chat Model** node.
-   Select or create a new **Credential** for OpenAI API.

### 2. Connection to Backend
The workflow assumes the RAG backend is running on `http://localhost:8000`.
If you are running n8n in Docker and the backend on the host, you might need to change `localhost` to `host.docker.internal` or the IP address of your host machine.

-   Update the **URL** field in the **Search Code**, **Index Code**, and **Explain Symbol** nodes if necessary.

## Usage

1.  Click **Chat** in the n8n workflow editor (or use the test chat).
2.  Ask questions like:
    -   "Index the current folder."
    -   "How does the authentication middleware work?"
    -   "Explain the FileIndexer class."

The AI Agent will use the defined tools to query your local RAG system and provide answers.
