docker run \
    -p 7474:7474 -p 7687:7687 \
    --volume=./data:/data \
    --name neo4j-apoc \
    -e NEO4J_AUTH=none \
    -e NEO4J_apoc_export_file_enabled=true \
    -e NEO4J_apoc_import_file_enabled=true \
    -e NEO4J_apoc_import_file_use__neo4j__config=true \
    -e NEO4J_PLUGINS=\[\"apoc\"\] \
    neo4j
