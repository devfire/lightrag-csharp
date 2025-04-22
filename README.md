# LightRAG C# Code Analysis Graph Importer

## Description

This project provides a Python script (`populate_graph.py`) to parse code analysis data,  generated from C# projects using https://github.com/devfire/RoslynCodeAnalyzer, and import it into a Neo4j graph database. 

It leverages the Neo4j Python driver and the APOC library for efficient batch processing and dynamic graph element creation.

The goal is to represent the structure and relationships within a C# codebase as a graph, enabling complex queries and analysis, specifically by Neo4j MCP server. 

See https://neo4j.com/blog/developer/claude-converses-neo4j-via-mcp/ for more details.

## Features

*   **Neo4j Integration:** Connects to a Neo4j database to store code analysis results.
*   **JSON Input:** Parses a specific JSON format containing nodes (code elements like classes, methods, etc.) and edges (relationships like calls, inheritance, etc.).
*   **Batch Processing:** Inserts nodes and relationships in configurable batches for better performance, especially with large datasets. Includes progress bars using `tqdm`.
*   **APOC Dependency:** Utilizes the Neo4j APOC library for dynamic label creation (`apoc.create.addLabels`) and relationship creation (`apoc.create.relationship`).
*   **Flexible Configuration:** Neo4j connection details (URI, user, password, database name) can be configured via command-line arguments or environment variables.
*   **Database Management:** Option to clear the target Neo4j database before importing new data.
*   **Dockerized Neo4j Setup:** Includes a helper script (`neo4j.sh`) to easily run a Neo4j instance using Docker, pre-configured with the required APOC plugin.

## Prerequisites

*   **Python:** Version 3.11 or higher.
*   **Docker:** Required if using the `neo4j.sh` script to run the Neo4j database.
*   **Neo4j Instance:** A running Neo4j database (version compatible with `neo4j` driver v5.28.1+).
*   **APOC Plugin:** The APOC plugin must be installed in your Neo4j instance. The `neo4j.sh` script handles this automatically if used.
*   **Input JSON File:** A JSON file containing the code analysis data (nodes and edges). The exact structure expected by `populate_graph.py` needs to be adhered to (see Usage section).

## Setup

1.  **Clone the Repository:**
    ```bash
    git clone <repository-url>
    cd lightrag-csharp
    ```

2.  **Set up Neo4j:**
    *   **Option A (Recommended - Using Docker):** Run the provided script. This starts a Neo4j container named `neo4j-apoc` with the APOC plugin enabled and no authentication (adjust `neo4j.sh` if needed).
        ```bash
        ./neo4j.sh
        ```
        The database will be accessible at `neo4j://localhost:7687` (Bolt port) and `http://localhost:7474` (HTTP browser).
    *   **Option B (Manual):** Ensure you have a Neo4j instance running with the APOC plugin installed. Note the Bolt URI, username, and password.

3.  **Set up Python Environment:**
    It's recommended to use a virtual environment. This project uses `uv` (specified in `uv.lock`), but you can use `venv` as well.
    *   **Using `uv` (if installed):**
        ```bash
        uv venv # Create virtual environment .venv
        uv sync # Install dependencies from pyproject.toml/uv.lock
        source .venv/bin/activate # Activate environment (Linux/macOS)
        # or .venv\Scripts\activate (Windows)
        ```
    *   **Using `venv`:**
        ```bash
        python -m venv .venv
        source .venv/bin/activate # Activate environment (Linux/macOS)
        # or .venv\Scripts\activate (Windows)
        pip install -r requirements.txt # (You might need to generate this from pyproject.toml first if it doesn't exist: pip install pip-tools; pip-compile pyproject.toml)
        # Or directly:
        pip install "neo4j>=5.28.1" "tqdm>=4.67.1"
        ```

## Usage

The core of the project is the `populate_graph.py` script.

```bash
python populate_graph.py <input_file.json> [options]
```

**Required Argument:**

*   `<input_file.json>`: Path to the JSON file containing the code analysis data.

**JSON Input Format:**

The script expects a JSON file with the following top-level structure:

```json
{
  "nodes": [
    {
      "id": "unique_node_identifier_1",
      "type": "NodeTypeAsString", // e.g., "Class", "Method", "Namespace"
      "property1": "value1",
      "property2": "value2",
      // ... other node properties
    },
    // ... more nodes
  ],
  "edges": [
    {
      "sourceId": "unique_node_identifier_1", // ID of the source node
      "targetId": "unique_node_identifier_2", // ID of the target node
      "type": "RelationshipTypeAsString" // e.g., "CALLS", "INHERITS_FROM"
      // Properties on relationships are not explicitly handled by default in the script's MERGE,
      // but could be added by modifying the Cypher query.
    },
    // ... more edges
  ]
}
```

*   **Nodes:** Each node object *must* have an `id` (unique identifier used for `MERGE`) and a `type` (used for dynamic labeling via APOC). All other key-value pairs in the node object will be set as properties on the Neo4j node.
*   **Edges:** Each edge object *must* have `sourceId`, `targetId`, and `type`. The `type` is used for the relationship type (converted to uppercase via APOC).

**Options:**

*   `--uri` / `-u`: Neo4j Bolt URI (Default: `neo4j://localhost:7687` or `NEO4J_URI` env var).
*   `--user` / `-usr`: Neo4j Username (Default: `neo4j` or `NEO4J_USER` env var).
*   `--password` / `-p`: Neo4j Password (Default: `NEO4J_PASSWORD` env var). *Note: If using the default `neo4j.sh`, authentication is disabled, so no password is needed.*
*   `--clear` / `-c`: Clear the existing graph database before importing (Deletes all nodes and relationships).
*   `--database` / `-db`: Name of the Neo4j database to use (Default: `neo4j`).
*   `--db-batch-size`: Batch size for Neo4j node/edge insertion operations (Default: 1000).

**Example:**

```bash
# Assuming Neo4j is running via ./neo4j.sh and code_analysis.json exists
python populate_graph.py code_analysis.json --clear
```

## Configuration via Environment Variables

Instead of command-line arguments, you can configure the Neo4j connection using these environment variables:

*   `NEO4J_URI`
*   `NEO4J_USER`
*   `NEO4J_PASSWORD`

## License

MIT: do you whatever you want.