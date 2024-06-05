import logging
import random
from pathlib import Path

import networkx as nx
from warnet.config_utils import dump_bitcoin_conf, parse_bitcoin_conf
from warnet.tags import WEIGHTED_TAGS

logger = logging.getLogger("cycle_graph")


def create_cycle_graph(n: int, version: str, bitcoin_conf: str | None, random_version: bool):
    try:
        # Use nx.MultiDiGraph() so we get directed edges (source->target)
        # and still allow parallel edges (L1 p2p connections + LN channels)
        graph = nx.generators.cycle_graph(n, nx.MultiDiGraph())
    except TypeError as e:
        msg = f"Failed to create graph: {e}"
        logger.error(msg)
        return msg

    # Graph is a simply cycle graph with all nodes connected in a loop, including both ends.
    # Ensure each node has at least 8 outbound connections by making 7 more outbound connections
    for src_node in graph.nodes():
        logger.debug(f"Creating additional connections for node {src_node}")
        for _ in range(8):
            # Choose a random node to connect to
            # Make sure it's not the same node and they aren't already connected in either direction
            potential_nodes = [
                dst_node
                for dst_node in range(n)
                if dst_node != src_node
                and not graph.has_edge(dst_node, src_node)
                and not graph.has_edge(src_node, dst_node)
            ]
            if potential_nodes:
                chosen_node = random.choice(potential_nodes)
                graph.add_edge(src_node, chosen_node)
                logger.debug(f"Added edge: {src_node}:{chosen_node}")
        logger.debug(f"Node {src_node} edges: {graph.edges(src_node)}")

    # parse and process conf file
    conf_contents = ""
    if bitcoin_conf is not None:
        conf = Path(bitcoin_conf)
        if conf.is_file():
            with open(conf) as f:
                # parse INI style conf then dump using for_graph
                conf_dict = parse_bitcoin_conf(f.read())
                conf_contents = dump_bitcoin_conf(conf_dict, for_graph=True)

    # populate our custom fields
    for i, node in enumerate(graph.nodes()):
        if random_version:
            graph.nodes[node]["version"] = random.choice(WEIGHTED_TAGS)
        else:
            # One node demoing the image tag
            if i == 1:
                graph.nodes[node]["image"] = f"bitcoindevproject/bitcoin:{version}"
            else:
                graph.nodes[node]["version"] = version
        graph.nodes[node]["bitcoin_config"] = conf_contents
        graph.nodes[node]["tc_netem"] = ""
        graph.nodes[node]["build_args"] = ""
        graph.nodes[node]["exporter"] = False
        graph.nodes[node]["collect_logs"] = False

    convert_unsupported_attributes(graph)
    return graph


def convert_unsupported_attributes(graph: nx.Graph):
    # Sometimes networkx complains about invalid types when writing the graph
    # (it just generated itself!). Try to convert them here just in case.
    for _, node_data in graph.nodes(data=True):
        for key, value in node_data.items():
            if isinstance(value, set):
                node_data[key] = list(value)
            elif isinstance(value, int | float | str):
                continue
            else:
                node_data[key] = str(value)

    for _, _, edge_data in graph.edges(data=True):
        for key, value in edge_data.items():
            if isinstance(value, set):
                edge_data[key] = list(value)
            elif isinstance(value, int | float | str):
                continue
            else:
                edge_data[key] = str(value)
