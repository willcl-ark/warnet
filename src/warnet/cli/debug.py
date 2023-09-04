from pathlib import Path

import click
from rich import print

from templates import TEMPLATES
from warnet.cli.rpc import rpc_call

EXAMPLE_GRAPH_FILE = TEMPLATES / "example.graphml"


@click.group(name="debug")
def debug():
    """Debug commands"""


@debug.command()
@click.argument("graph_file", type=str)
@click.option("--network", default="warnet", show_default=True)
def generate_compose(graph_file: str, network: str = "warnet"):
    """
    Generate the docker-compose file for a given <graph_file> and <--network> (default: "warnet") name and return it.
    """
    try:
        result = rpc_call(
            "generate_compose", {"graph_file": graph_file, "network": network}
        )
        print(result)
    except Exception as e:
        print(f"Error generating compose: {e}")


@debug.command()
@click.argument("graph_file", type=str)
@click.option("--network", default="warnet", show_default=True)
def update_dns_seed(graph_file: Path = EXAMPLE_GRAPH_FILE, network: str = "warnet"):
    """
    Update the dns seed database using a <graph_file> on <--network> (default: "warnet")
    """
    try:
        result = rpc_call(
            "update_dns_seeder", {"graph_file": str(graph_file), "network": network}
        )
        print(result)
    except Exception as e:
        print(f"Error updating dns seed addresses: {e}")
