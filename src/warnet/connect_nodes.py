import yaml
import subprocess
import logging
import networkx as nx
import docker
from warnet.generate_docker_compose import generate_docker_compose
from warnet.ip_addr import generate_ip_addresses
import warnet.rpc_utils as bitcoin_cli

BITCOIN_GRAPH_FILE = './graphs/basic3.graphml'
CONFIG_FILE = 'config.yaml'

logging.basicConfig(level=logging.INFO)


def parse_config(config_file: str = CONFIG_FILE):
    """
    Parse the configuration file.

    :param config_file: The path to the configuration file
    :return: The parsed configuration
    """
    try:
        with open(config_file, "r") as file:
            return yaml.safe_load(file)
    except Exception as e:
        logging.error(f"An error occurred while reading the config file: {e}")


def delete_containers(client: docker.DockerClient,
                      container_name_prefix: str = "warnet"):
    """
    Delete all containers with the specified name prefix.

    :param container_name_prefix: The prefix of the container names to filter.
    """
    try:
        containers = client.containers.list(
            all=True, filters={"name": container_name_prefix})
        for container in containers:
            container.remove(force=True)
        logging.info("  Removed all containers")
    except Exception as e:
        logging.error(f"An error occurred while deleting containers: {e}")


def generate_compose(graph_file: str):
    """
    Read a graph file and build a docker compose.

    :param graph_file: The path to the graph file
    """
    try:
        graph = nx.read_graphml(graph_file, node_type=int)
        version = [graph.nodes[node]["version"] for node in graph.nodes()]
        generate_docker_compose(node_count=len(graph.nodes()), version=version)
        logging.info(
            f"  Graph file contains {len(graph.nodes())} nodes and {len(graph.edges())} connections"
        )
        logging.info("  Generated docker-compose.yml file")
    except Exception as e:
        logging.error(f"An error occurred while running new node: {e}")


def get_container_ip(ip_addresses: dict, container_name: str):
    """
    Get the fake IP address of a container from the ip_addresses dictionary.

    :param ip_addresses: The dictionary containing the fake IP addresses
    :param container_name: The name of the container
    :return: The fake IP address of the container
    """
    try:
        return ip_addresses[container_name][0]
    except Exception as e:
        logging.error(f"An error occurred while getting container IP: {e}")


def get_containers(client: docker.DockerClient,
                   container_name_prefix: str = "warnet"):
    """
    Get the names and instances of all containers with the specified name prefix.

    :param container_name_prefix: The prefix of the container names to filter.
    :return: A list of tuples containing the names and instances of the containers
    """
    containers = client.containers.list(
        all=True, filters={"name": container_name_prefix})
    return [(container.name, container) for container in containers]


def setup_network(client: docker.DockerClient, graph_file: str,
                  ip_addresses: dict):
    """
    Setup and add nodes to the network.

    :param graph_file: The path to the graph file
    :param ip_addresses: The dictionary containing the fake IP addresses
    """
    try:
        graph = nx.read_graphml(graph_file, node_type=int)
        logging.info(get_containers(client))
        for edge in graph.edges():
            source = f"warnet_{str(edge[0])}"
            dest = f"warnet_{str(edge[1])}"
            source_container = client.containers.get(source)
            logging.info(f"Connecting node {source} to {dest}")
            bitcoin_cli.addnode(source_container,
                                get_container_ip(ip_addresses, dest))
    except Exception as e:
        logging.error(f"An error occurred while setting up the network: {e}")


def docker_setup_network(client, ip_addresses):
    containers = get_containers(client)
    print(ip_addresses)

    for container_name, container in containers:
        fake_ip = ip_addresses[container_name][0]

        # Add DNAT and SNAT rules for bi-directional communication with other containers
        for other_container_name, other_container in containers:
            if other_container_name != container_name:
                other_container_docker_ip = other_container.attrs[
                    'NetworkSettings']['Networks']['warnet_default'][
                        'IPAddress']
                other_fake_ip = ip_addresses[other_container_name][0]
                print(
                    f"Other Container Docker IP: {other_container_docker_ip}")

                # DNAT Rule: Redirect traffic destined for other's fake IP to other's actual Docker IP
                dnat_rule = f"iptables -t nat -A OUTPUT -d {other_fake_ip} -j DNAT --to-destination {other_container_docker_ip}"
                print(f"DNAT Rule: {dnat_rule}")
                result = container.exec_run(dnat_rule)
                if result.exit_code != 0:
                    logging.error(
                        f"Failed to set DNAT rule in {container_name}. Error: {result.output.decode('utf-8')}"
                    )

                # SNAT Rule: Rewrite the source IP of outgoing packets to this container's fake IP when sending to other's fake IP
                snat_rule = f"iptables -t nat -A POSTROUTING -d {other_fake_ip} -j SNAT --to-source {fake_ip}"
                print(f"SNAT Rule: {snat_rule}")
                result = container.exec_run(snat_rule)
                if result.exit_code != 0:
                    logging.error(
                        f"Failed to set SNAT rule in {container_name}. Error: {result.output.decode('utf-8')}"
                    )


def docker_compose():
    """
    Run docker compose
    """
    try:
        subprocess.run(["docker-compose", "up", "-d"])
    except Exception as e:
        logging.error(f"An error occurred while running docker compose: {e}")


def main():
    client = docker.from_env()
    delete_containers(client)
    generate_compose(BITCOIN_GRAPH_FILE)
    docker_compose()
    containers = get_containers(client)
    ip_addresses = generate_ip_addresses(containers, 1)
    docker_setup_network(client, ip_addresses)
    setup_network(client, BITCOIN_GRAPH_FILE, ip_addresses)


if __name__ == "__main__":
    main()
