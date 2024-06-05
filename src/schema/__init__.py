import json
from pathlib import Path

import networkx as nx
from jsonschema import validate

SCHEMA = Path(__file__).parent
GRAPH_SCHEMA_PATH = SCHEMA / "graph_schema.json"


def load_schema():
    with open(GRAPH_SCHEMA_PATH) as schema_file:
        return json.load(schema_file)


def validate_graph_schema(graph: nx.Graph):
    """
    Validate a networkx.Graph against the node schema
    """
    graph_schema = load_schema()
    validate(instance=graph.graph, schema=graph_schema["graph"])
    for n in list(graph.nodes):
        validate(instance=graph.nodes[n], schema=graph_schema["node"])
    for e in list(graph.edges):
        validate(instance=graph.edges[e], schema=graph_schema["edge"])
