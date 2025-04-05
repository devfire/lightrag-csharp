import json
import os
import time
import argparse
import sys
from neo4j import GraphDatabase, basic_auth # Correct import for auth

# --- Configuration & Argument Parsing ---

def parse_arguments():
    """Parses command-line arguments."""
    parser = argparse.ArgumentParser(description="Populate Neo4j database from Roslyn code analysis JSON.")
    parser.add_argument(
        "input_file",
        help="Path to the input JSON file (e.g., code_structure.json)."
    )
    parser.add_argument(
        "--uri", "-u",
        default=os.environ.get("NEO4J_URI", "neo4j://localhost:7687"), # Get from env var or default
        help="Neo4j Bolt URI (default: 'neo4j://localhost:7687' or NEO4J_URI env var)."
    )
    parser.add_argument(
        "--user", "-usr",
        default=os.environ.get("NEO4J_USER", "neo4j"), # Get from env var or default
        help="Neo4j Username (default: 'neo4j' or NEO4J_USER env var)."
    )
    parser.add_argument(
        "--password", "-p",
        default=os.environ.get("NEO4J_PASSWORD", None), # Get from env var, default to None
        help="Neo4j Password (reads from NEO4J_PASSWORD env var by default)."
    )
    parser.add_argument(
        "--clear", "-c",
        action="store_true", # Makes it a flag, default is False
        help="Clear the existing graph database before importing."
    )
    parser.add_argument(
        "--database", "-db",
        default="neo4j", # Default Neo4j database name
        help="Name of the Neo4j database to use (default: 'neo4j')."
    )

    args = parser.parse_args()
    if not args.password:
        print("Warning: Neo4j password not provided via --password or NEO4J_PASSWORD env var.", file=sys.stderr)
        # Depending on Neo4j setup, this might be okay or might fail authentication
    return args

# --- Neo4j Interaction Functions ---

def clear_database(driver, db_name):
    """Deletes all nodes and relationships in the specified database."""
    print(f"Clearing database '{db_name}'...", file=sys.stderr)
    try:
        with driver.session(database=db_name) as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("Database cleared successfully.", file=sys.stderr)
    except Exception as e:
        print(f"Error clearing database: {e}", file=sys.stderr)
        raise # Re-raise the exception to stop the script if clearing fails

def create_constraints(driver, db_name):
    """Creates necessary constraints (optional but recommended). Requires fixed labels."""
    # Note: Creating constraints with dynamic labels via APOC is complex.
    # This function assumes you might settle on fixed labels later.
    # For now, using MERGE on ID is the primary way to ensure uniqueness with dynamic labels.
    # You might manually add a constraint on the 'id' property if performance dictates,
    # though constraints usually require labels.
    # Example (if you used fixed labels like :CodeNode):
    # print(f"Applying constraints on database '{db_name}'...", file=sys.stderr)
    # try:
    #     with driver.session(database=db_name) as session:
    #          # Example constraint if all nodes had label :CodeNode
    #          session.run("CREATE CONSTRAINT constraint_node_id IF NOT EXISTS FOR (n:CodeNode) REQUIRE n.id IS UNIQUE")
    #     print("Constraints applied.", file=sys.stderr)
    # except Exception as e:
    #     print(f"Warning: Could not apply constraints (maybe they exist or labels differ): {e}", file=sys.stderr)
    print("Skipping automatic constraint creation (using MERGE on 'id' for uniqueness). "
          "Consider adding constraints manually if needed.", file=sys.stderr)


def insert_nodes(driver, db_name, nodes_data):
    """Inserts or updates nodes in Neo4j using UNWIND."""
    if not nodes_data:
        print("No node data to insert.", file=sys.stderr)
        return

    print(f"Inserting/Updating {len(nodes_data)} nodes...", file=sys.stderr)
    # Use parameter binding for safety and efficiency
    query = """
    UNWIND $nodes as node_data
    MERGE (n {id: node_data.id}) // Find or create node based on unique ID
    SET n = node_data // Overwrite/set all properties from the map
    // Dynamically set label based on 'type' using APOC
    // Ensure 'type' exists and is capitalized correctly in your JSON or adjust here
    WITH n, node_data
    CALL apoc.create.addLabels(n, [apoc.text.capitalize(node_data.type)]) YIELD node
    RETURN count(node) as processed_nodes_count
    """
    try:
        with driver.session(database=db_name) as session:
            # Use execute_write for transactional safety
            result = session.execute_write(lambda tx: tx.run(query, nodes=nodes_data).single())
            count = result["processed_nodes_count"] if result else 0
            print(f"Processed {count} nodes.", file=sys.stderr)
    except Exception as e:
        print(f"Error inserting nodes: {e}", file=sys.stderr)
        print("Ensure APOC plugin is installed in Neo4j if using dynamic labels.", file=sys.stderr)
        raise

def insert_edges(driver, db_name, edges_data):
    """Inserts relationships between existing nodes using UNWIND."""
    if not edges_data:
        print("No edge data to insert.", file=sys.stderr)
        return

    print(f"Inserting {len(edges_data)} relationships...", file=sys.stderr)
    # Ensure source/target nodes exist before creating edges
    query = """
    UNWIND $edges as edge_data
    MATCH (source {id: edge_data.sourceId}) // Use sourceId from JSON model
    MATCH (target {id: edge_data.targetId}) // Use targetId from JSON model
    // Dynamically create relationship type using APOC
    // Ensure 'type' exists and is uppercase correctly in your JSON or adjust here
    CALL apoc.create.relationship(source, apoc.text.toUpperCase(edge_data.type), {}, target) YIELD rel
    RETURN count(rel) as created_edge_count
    """
    try:
        with driver.session(database=db_name) as session:
            result = session.execute_write(lambda tx: tx.run(query, edges=edges_data).single())
            count = result["created_edge_count"] if result else 0
            print(f"Created {count} relationships.", file=sys.stderr)
    except Exception as e:
        print(f"Error inserting edges: {e}", file=sys.stderr)
        print("Ensure APOC plugin is installed in Neo4j if using dynamic relationship types.", file=sys.stderr)
        print("Also ensure all source/target nodes exist (were created in the previous step).", file=sys.stderr)
        raise

# --- Main Execution ---

if __name__ == "__main__":
    print("--- Starting Neo4j Population ---", file=sys.stderr)
    start_time = time.time()
    args = parse_arguments()

    # 1. Load JSON data
    try:
        print(f"Loading JSON data from: {args.input_file}", file=sys.stderr)
        if not os.path.exists(args.input_file):
             raise FileNotFoundError(f"Input file not found: {args.input_file}")
        with open(args.input_file, 'r', encoding='utf-8') as f:
            analysis_data = json.load(f)
        nodes = analysis_data.get('nodes', [])
        edges = analysis_data.get('edges', [])
        if not nodes:
             print("Warning: No nodes found in JSON file.", file=sys.stderr)
        if not edges:
             print("Warning: No edges found in JSON file.", file=sys.stderr)

    except Exception as e:
        print(f"Error loading JSON file: {e}", file=sys.stderr)
        sys.exit(1)

    # 2. Connect to Neo4j
    driver = None # Initialize driver to None
    try:
        print(f"Connecting to Neo4j at {args.uri}...", file=sys.stderr)
        auth_tuple = (args.user, args.password) if args.password else None
        # Use basic_auth helper or pass tuple directly
        driver = GraphDatabase.driver(args.uri, auth=auth_tuple)
        driver.verify_connectivity()
        print("Neo4j connection successful.", file=sys.stderr)

        # 3. Clear database if requested
        if args.clear:
            clear_database(driver, args.database)

        # 4. Create constraints (Optional - see function comments)
        create_constraints(driver, args.database)

        # 5. Insert Nodes and Edges
        insert_nodes(driver, args.database, nodes)
        insert_edges(driver, args.database, edges)

    except Exception as e:
        print(f"\nAn error occurred during Neo4j processing: {e}", file=sys.stderr)
        # Attempt to provide more specific Neo4j error info if available
        if hasattr(e, 'code') and hasattr(e, 'message'):
             print(f"Neo4j Error Code: {e.code}", file=sys.stderr)
             print(f"Neo4j Error Message: {e.message}", file=sys.stderr)
        sys.exit(1)
    finally:
        # 6. Close connection
        if driver:
            driver.close()
            print("Neo4j connection closed.", file=sys.stderr)

    end_time = time.time()
    print(f"--- Neo4j population finished successfully in {end_time - start_time:.2f} seconds ---", file=sys.stderr)
    sys.exit(0)