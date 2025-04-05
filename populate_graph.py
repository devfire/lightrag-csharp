import json
import os
import time
import argparse
import sys
from neo4j import GraphDatabase, basic_auth
from tqdm import tqdm # Import tqdm

# Default batch size for processing nodes/edges
DEFAULT_DB_BATCH_SIZE = 1000

# --- Configuration & Argument Parsing ---

def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Populate Neo4j database from Roslyn code analysis JSON.")
    parser.add_argument(
        "input_file",
        help="Path to the input JSON file (e.g., code_structure.json)."
    )
    # ... (other arguments: --uri, --user, --password, --clear, --database remain the same) ...
    parser.add_argument(
        "--uri", "-u",
        default=os.environ.get("NEO4J_URI", "neo4j://localhost:7687"),
        help="Neo4j Bolt URI (default: 'neo4j://localhost:7687' or NEO4J_URI env var)."
    )
    parser.add_argument(
        "--user", "-usr",
        default=os.environ.get("NEO4J_USER", "neo4j"),
        help="Neo4j Username (default: 'neo4j' or NEO4J_USER env var)."
    )
    parser.add_argument(
        "--password", "-p",
        default=os.environ.get("NEO4J_PASSWORD", None),
        help="Neo4j Password (reads from NEO4J_PASSWORD env var by default)."
    )
    parser.add_argument(
        "--clear", "-c",
        action="store_true",
        help="Clear the existing graph database before importing."
    )
    parser.add_argument(
        "--database", "-db",
        default="neo4j",
        help="Name of the Neo4j database to use (default: 'neo4j')."
    )
    parser.add_argument( # <<< Add batch size argument
        "--db-batch-size",
        type=int,
        default=DEFAULT_DB_BATCH_SIZE,
        help=f"Batch size for Neo4j operations (default: {DEFAULT_DB_BATCH_SIZE})."
    )


    args = parser.parse_args()
    if not args.password:
        print("Warning: Neo4j password not provided via --password or NEO4J_PASSWORD env var.", file=sys.stderr)
    return args

# --- Neo4j Interaction Functions ---

# clear_database and create_constraints remain the same
def clear_database(driver, db_name):
    """Deletes all nodes and relationships in the specified database."""
    print(f"Clearing database '{db_name}'...", file=sys.stderr)
    try:
        with driver.session(database=db_name) as session:
            # Use execute_write for potentially longer operations
            session.execute_write(lambda tx: tx.run("MATCH (n) DETACH DELETE n"))
        print("Database cleared successfully.", file=sys.stderr)
    except Exception as e:
        print(f"Error clearing database: {e}", file=sys.stderr)
        raise

def create_constraints(driver, db_name):
     # (No changes needed here - keeping the previous version)
    print("Skipping automatic constraint creation (using MERGE on 'id' for uniqueness). "
          "Consider adding constraints manually if needed.", file=sys.stderr)

# --- MODIFIED insert_nodes ---
def insert_nodes(driver, db_name, nodes_data, batch_size):
    """Inserts or updates nodes in Neo4j using UNWIND in batches with progress."""
    if not nodes_data:
        print("No node data to insert.", file=sys.stderr)
        return

    total_nodes = len(nodes_data)
    print(f"Inserting/Updating {total_nodes} nodes in batches of {batch_size}...", file=sys.stderr)

    # Cypher query remains the same, but will be executed per batch
    query = """
    UNWIND $batch as node_data
    MERGE (n {id: node_data.id})
    SET n = node_data // Overwrite/set all properties from the map
    WITH n, node_data
    CALL apoc.create.addLabels(n, [apoc.text.capitalize(node_data.type)]) YIELD node
    RETURN count(node) as processed_nodes_count
    """
    processed_count = 0
    try:
        with driver.session(database=db_name) as session:
            # Use tqdm to iterate over batches
            num_batches = (total_nodes + batch_size - 1) // batch_size
            with tqdm(total=total_nodes, desc="Processing Nodes", unit="node", file=sys.stdout) as pbar:
                 for i in range(0, total_nodes, batch_size):
                    batch = nodes_data[i:min(i + batch_size, total_nodes)]
                    if not batch: continue # Should not happen with correct range, but safety check

                    # Use execute_write for transactional safety per batch
                    result = session.execute_write(lambda tx: tx.run(query, batch=batch).single())
                    count_in_batch = result["processed_nodes_count"] if result else 0
                    processed_count += count_in_batch
                    pbar.update(len(batch)) # Update progress bar by number of items in batch

        # Final summary check (optional)
        if processed_count != total_nodes:
             print(f"\nWarning: Processed node count ({processed_count}) doesn't match total nodes ({total_nodes}). Check results.", file=sys.stderr)
        else:
            print(f"\nProcessed {processed_count} nodes successfully.", file=sys.stderr)

    except Exception as e:
        print(f"\nError inserting nodes (around item {processed_count}): {e}", file=sys.stderr)
        print("Ensure APOC plugin is installed in Neo4j if using dynamic labels.", file=sys.stderr)
        raise

# --- MODIFIED insert_edges ---
def insert_edges(driver, db_name, edges_data, batch_size):
    """Inserts relationships in batches with progress."""
    if not edges_data:
        print("No edge data to insert.", file=sys.stderr)
        return

    total_edges = len(edges_data)
    print(f"Inserting {total_edges} relationships in batches of {batch_size}...", file=sys.stderr)

    query = """
    UNWIND $batch as edge_data
    MATCH (source {id: edge_data.sourceId})
    MATCH (target {id: edge_data.targetId})
    CALL apoc.create.relationship(source, apoc.text.toUpperCase(edge_data.type), {}, target) YIELD rel
    RETURN count(rel) as created_edge_count
    """
    processed_count = 0
    try:
        with driver.session(database=db_name) as session:

            with tqdm(total=total_edges, desc="Processing Edges", unit="edge", file=sys.stdout) as pbar:
                for i in range(0, total_edges, batch_size):
                    batch = edges_data[i:min(i + batch_size, total_edges)]
                    if not batch: 
                        continue

                    result = session.execute_write(lambda tx: tx.run(query, batch=batch).single())
                    count_in_batch = result["created_edge_count"] if result else 0
                    processed_count += count_in_batch
                    pbar.update(len(batch))

        if processed_count != total_edges:
             print(f"\nWarning: Created edge count ({processed_count}) doesn't match total edges ({total_edges}). Check results.", file=sys.stderr)
        else:
             print(f"\nCreated {processed_count} relationships successfully.", file=sys.stderr)

    except Exception as e:
        print(f"\nError inserting edges (around item {processed_count}): {e}", file=sys.stderr)
        print("Ensure APOC plugin is installed and source/target nodes exist.", file=sys.stderr)
        raise

# --- Main Execution ---

if __name__ == "__main__":
    print("--- Starting Neo4j Population ---", file=sys.stderr)
    start_time = time.time()
    args = parse_arguments()

    # 1. Load JSON data (no changes needed here)
    try:
        print(f"Loading JSON data from: {args.input_file}", file=sys.stderr)
        # ... (rest of JSON loading logic) ...
        with open(args.input_file, 'r', encoding='utf-8') as f:
            analysis_data = json.load(f)
        nodes = analysis_data.get('nodes', [])
        edges = analysis_data.get('edges', [])
        # ... (warnings for empty nodes/edges) ...

    except Exception as e:
        print(f"Error loading JSON file: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Connect to Neo4j (no changes needed here)
    driver = None
    try:
        print(f"Connecting to Neo4j at {args.uri}...", file=sys.stderr)
        # ... (rest of connection logic) ...
        auth_tuple = (args.user, args.password) if args.password else None
        driver = GraphDatabase.driver(args.uri, auth=auth_tuple)
        driver.verify_connectivity()
        print("Neo4j connection successful.", file=sys.stderr)


        # 3. Clear database if requested (no changes needed here)
        if args.clear:
            clear_database(driver, args.database)

        # 4. Create constraints (no changes needed here)
        create_constraints(driver, args.database)

        # 5. Insert Nodes and Edges (pass batch_size from args)
        insert_nodes(driver, args.database, nodes, args.db_batch_size) # Pass batch size
        insert_edges(driver, args.database, edges, args.db_batch_size) # Pass batch size

    except Exception as e:
        print(f"\nAn error occurred during Neo4j processing: {e}", file=sys.stderr)
        # ... (rest of error reporting) ...
        sys.exit(1)
    finally:
        # 6. Close connection (no changes needed here)
        if driver:
            driver.close()
            print("Neo4j connection closed.", file=sys.stderr)

    end_time = time.time()
    print(f"--- Neo4j population finished successfully in {end_time - start_time:.2f} seconds ---", file=sys.stderr)
    sys.exit(0)