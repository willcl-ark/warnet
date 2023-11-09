import logging
import os
import pkgutil
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from functools import wraps
from io import BytesIO
from logging.handlers import RotatingFileHandler
from logging import StreamHandler
from pathlib import Path
from typing import List, Dict, Optional, Callable, Any
from flask import Flask, request
from flask_jsonrpc.app import JSONRPC

import networkx as nx

import scenarios
from warnet.warnet import Warnet
from warnet.utils import (
    create_graph_with_probability,
    gen_config_dir,
)

WARNET_SERVER_PORT = 9276


def rpc_error_handler(f: Callable) -> Callable:
    """
    Decorator to add error handling to RPC calls.
    """

    @wraps(f)
    def wrapper(self, *args, **kwargs) -> Any:
        try:
            result = f(self, *args, **kwargs)
            return result
        except Exception as e:
            args_str = ", ".join(repr(arg) for arg in args)
            kwargs_str = ", ".join(f"{k}={v!r}" for k, v in kwargs.items())
            self.logger.error(f"Error processing request with args: ({args_str}), kwargs: ({kwargs_str}):\n{e}")
            return "Server error processing request"
    return wrapper


class Server():
    def __init__(self):
        self.basedir = os.environ.get("XDG_STATE_HOME")
        if self.basedir is None:
            # ~/.warnet/warnet.log
            self.basedir = os.path.join(os.environ["HOME"], ".warnet")
        else:
            # XDG_STATE_HOME / warnet / warnet.log
            self.basedir = os.path.join(self.basedir, "warnet")

        self.running_scenarios = []

        self.app = Flask(__name__)
        self.jsonrpc = JSONRPC(self.app, "/api")

        self.log_file_path = os.path.join(self.basedir, "warnet.log")
        self.logger: logging.Logger
        self.setup_logging()
        self.setup_rpc()

    def setup_logging(self):
        # Ensure the directory exists
        os.makedirs(os.path.dirname(self.log_file_path), exist_ok=True)

        # Configure root logger
        logging.basicConfig(
            level=logging.DEBUG,
            handlers=[
                RotatingFileHandler(
                    self.log_file_path, maxBytes=16_000_000, backupCount=3, delay=True
                ),
                StreamHandler(sys.stdout)
            ],
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        # Disable urllib3.connectionpool logging
        logging.getLogger("urllib3.connectionpool").setLevel(logging.CRITICAL)
        self.logger = logging.getLogger("warnet")
        self.logger.info("Logging started")

        def log_request():
            self.logger.debug(request.json)

        self.app.before_request(log_request)

    def setup_rpc(self):
        # Tanks
        self.jsonrpc.register(self.tank_bcli)
        self.jsonrpc.register(self.tank_debug_log)
        self.jsonrpc.register(self.tank_messages)
        # Scenarios
        self.jsonrpc.register(self.scenarios_list)
        self.jsonrpc.register(self.scenarios_run)
        self.jsonrpc.register(self.scenarios_stop)
        self.jsonrpc.register(self.scenarios_list_running)
        # Networks
        self.jsonrpc.register(self.network_up)
        self.jsonrpc.register(self.network_from_file)
        self.jsonrpc.register(self.network_down)
        self.jsonrpc.register(self.network_info)
        self.jsonrpc.register(self.network_status)
        # Graph
        self.jsonrpc.register(self.graph_generate)
        # Debug
        self.jsonrpc.register(self.generate_deployment)
        # Server
        self.jsonrpc.register(self.server_stop)
        # Logs
        self.jsonrpc.register(self.logs_grep)

    @rpc_error_handler
    def tank_bcli(self, node: int, method: str, params: List[str] = [], network: str = "warnet") -> str:
        """
        Call bitcoin-cli on <node> <method> <params> in [network]
        """
        wn = Warnet.from_network(network)
        return wn.container_interface.get_bitcoin_cli(wn.tanks[node], method, params)

    @rpc_error_handler
    def tank_debug_log(self, network: str, node: int) -> str:
        """
        Fetch the Bitcoin Core debug log from <noe>
        """
        wn = Warnet.from_network(network)
        return wn.container_interface.get_bitcoin_debug_log(wn.tanks[node].container_name)

    @rpc_error_handler
    def tank_messages(self, network: str, node_a: int, node_b: int) -> str:
        """
        Fetch messages sent between <node_a> and <node_b>.
        """
        wn = Warnet.from_network(network)
        messages = [
            msg for msg in wn.container_interface.get_messages(wn.tanks[node_a].container_name, wn.tanks[node_b].ipv4, wn.bitcoin_network) if msg is not None
        ]
        if not messages:
            return f"No messages found between {node_a} and {node_b}"

        messages_str_list = []

        for message in messages:
            # Check if 'time' key exists and its value is a number
            if not (message.get("time") and isinstance(message["time"], (int, float))):
                continue

            timestamp = datetime.utcfromtimestamp(message["time"] / 1e6).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            direction = ">>>" if message.get("outbound", False) else "<<<"
            msgtype = message.get("msgtype", "")
            body_dict = message.get("body", {})

            if not isinstance(body_dict, dict):  # messages will be in dict form
                continue

            body_str = ", ".join(f"{key}: {value}" for key, value in body_dict.items())
            messages_str_list.append(f"{timestamp} {direction} {msgtype} {body_str}")

        return "\n".join(messages_str_list)

    @rpc_error_handler
    def scenarios_list(self) -> List[tuple]:
        """
        List available scenarios in the Warnet Test Framework
        """
        scenario_list = []
        for s in pkgutil.iter_modules(scenarios.__path__):
            m = pkgutil.resolve_name(f"scenarios.{s.name}")
            if hasattr(m, "cli_help"):
                scenario_list.append((s.name, m.cli_help()))
        return scenario_list

    @rpc_error_handler
    def scenarios_run(self, scenario: str, additional_args: List[str], network: str = "warnet") -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        scenario_path = os.path.join(base_dir, "scenarios", f"{scenario}.py")

        if not os.path.exists(scenario_path):
            return f"Scenario {scenario} not found at {scenario_path}."

        run_cmd = [sys.executable, scenario_path] + additional_args + [f"--network={network}"]
        self.logger.debug(f"Running {run_cmd}")

        proc = subprocess.Popen(
            run_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        def proc_logger():
            for line in proc.stdout:
                self.logger.info(line.decode().rstrip())

        t = threading.Thread(target=lambda: proc_logger())
        t.daemon = True
        t.start()

        self.running_scenarios.append({
            "pid": proc.pid,
            "cmd": f"{scenario} {' '.join(additional_args)}",
            "proc": proc,
            "network": network,
        })

        return f"Running scenario {scenario} with PID {proc.pid} in the background..."

    @rpc_error_handler
    def scenarios_stop(self, pid: int) -> str:
        matching_scenarios = [sc for sc in self.running_scenarios if sc["pid"] == pid]
        if matching_scenarios:
            matching_scenarios[0]["proc"].terminate() # sends SIGTERM
            # Remove from running list
            self.running_scenarios = [sc for sc in self.running_scenarios if sc["pid"] != pid]
            return f"Stopped scenario with PID {pid}."
        else:
            return f"Could not find scenario with PID {pid}."

    @rpc_error_handler
    def scenarios_list_running(self) -> List[Dict]:
        return [{
            "pid": sc["pid"],
            "cmd": sc["cmd"],
            "active": sc["proc"].poll() is None,
            "network": sc["network"],
        } for sc in self.running_scenarios]

    @rpc_error_handler
    def network_up(self, network: str = "warnet") -> str:
        wn = Warnet.from_network(network)

        def thread_start(wn):
            wn.container_interface.up()
            # Update warnet from docker here to get ip addresses
            wn = Warnet.from_network(network)
            wn.apply_network_conditions()
            wn.connect_edges()
            self.logger.info(
                f"Resumed warnet named '{network}' from config dir {wn.config_dir}"
            )

        t = threading.Thread(target=lambda: thread_start(wn))
        t.daemon
        t.start()
        return f"Resuming warnet..."

    @rpc_error_handler
    def network_from_file(self, graph_file: str, force: bool = False, network: str = "warnet") -> str:
        """
        Run a warnet with topology loaded from a <graph_file>
        """
        config_dir = gen_config_dir(network)
        if config_dir.exists():
            if force:
                shutil.rmtree(config_dir)
            else:
                return f"Config dir {config_dir} already exists, not overwriting existing warnet without --force"
        wn = Warnet.from_graph_file(graph_file, config_dir, network)

        def thread_start(wn):
            wn.generate_deployment()
            # grep: disable-exporters
            # wn.write_prometheus_config()
            wn.write_fork_observer_config()
            wn.warnet_build()
            wn.warnet_up()
            wn.apply_network_conditions()
            wn.connect_edges()
            self.logger.info(
                f"Created warnet named '{network}' from graph file {graph_file}"
            )

        t = threading.Thread(target=lambda: thread_start(wn))
        t.daemon
        t.start()
        return f"Starting warnet network named '{network}' with the following parameters:\n{wn}"

    @rpc_error_handler
    def graph_generate(self, params: List[str], outfile: str, version: str, bitcoin_conf: Optional[str] = None, random: bool = False) -> str:
        graph_func = nx.generators.random_internet_as_graph

        graph = create_graph_with_probability(graph_func, params, version, bitcoin_conf, random)

        if outfile:
            file_path = Path(outfile)
            nx.write_graphml(graph, file_path)
            return f"Generated graph written to file: {outfile}"
        bio = BytesIO()
        nx.write_graphml(graph, bio)
        xml_data = bio.getvalue()
        return f"Generated graph:\n\n{xml_data.decode('utf-8')}"

    @rpc_error_handler
    def network_down(self, network: str = "warnet") -> str:
        """
        Stop all containers in <network>.
        """
        wn = Warnet.from_network(network)
        wn.warnet_down()
        return "Stopping warnet"

    @rpc_error_handler
    def network_info(self, network: str = "warnet") -> str:
        """
        Get info about a warnet network named <network>
        """
        wn = Warnet.from_network(network)
        return f"{wn}"

    @rpc_error_handler
    def network_status(self, network: str = "warnet") -> List[dict]:
        """
        Get running status of a warnet network named <network>
        """
        wn = Warnet.from_network(network)
        stats = []
        for tank in wn.tanks:
            status = tank.container.status if tank.container is not None else None
            stats.append({
            "container_name": tank.container_name,
            "status": status})
        return stats

    @rpc_error_handler
    def generate_deployment(self, graph_file: str, network: str = "warnet") -> str:
        """
        Generate the deployment file for a graph file
        """
        config_dir = gen_config_dir(network)
        if config_dir.exists():
            return (
                f"Config dir {config_dir} already exists, not overwriting existing warnet"
            )
        wn = Warnet.from_graph_file(graph_file, config_dir, network)
        wn.generate_deployment()
        if not wn.deployment_file.is_file():
            return f"No deployment file found at {wn.deployment_file}"
        with open(wn.deployment_file, "r") as f:
            return f.read()

    @rpc_error_handler
    def server_stop(self) -> str:
        """
        Stop warnet.
        """
        sys.exit(0)
        return "Stopping warnet server..."

    @rpc_error_handler
    def logs_grep(self, pattern: str, network: str = "warnet") -> str:
        """
        Grep the logs from the fluentd container for a regex pattern
        """
        wn = Warnet.from_network(network)
        return wn.container_interface.logs_grep(pattern, network)


def run_server():
    # https://flask.palletsprojects.com/en/2.3.x/api/#flask.Flask.run
    # "If the debug flag is set the server will automatically reload
    # for code changes and show a debugger in case an exception happened."
    Server().app.run(host="0.0.0.0", port=WARNET_SERVER_PORT, debug=False)


if __name__ == "__main__":
    run_server()
