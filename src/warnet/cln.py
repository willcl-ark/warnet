from backend.kubernetes_backend import KubernetesBackend
from warnet.services import ServiceType
from warnet.utils import exponential_backoff, generate_ipv4_addr, handle_json

from .lnchannel import LNChannel
from .lnnode import LNNode
from .status import RunningStatus

CLN_CONFIG_BASE = " ".join(
    [
        "--network=regtest",
        "--database-upgrade=true",
        "--bitcoin-retry-timeout=600",
        "--bind-addr=0.0.0.0:9735",
    ]
)


class CLNNode(LNNode):
    def __init__(self, warnet, tank, backend: KubernetesBackend, options):
        self.warnet = warnet
        self.tank = tank
        self.backend = backend
        self.image = options["ln_image"]
        self.cb = options["cb_image"]
        self.ln_config = options["ln_config"]
        self.ipv4 = generate_ipv4_addr(self.warnet.subnet)
        self.rpc_port = 10009
        self.impl = "cln"

    @property
    def status(self) -> RunningStatus:
        return super().status

    @property
    def cb_status(self) -> RunningStatus:
        return super().cb_status

    def get_conf(self, ln_container_name, tank_container_name) -> str:
        conf = CLN_CONFIG_BASE
        conf += f" --alias={self.tank.index}"
        conf += f" --grpc-port={self.rpc_port}"
        conf += f" --bitcoin-rpcuser={self.tank.rpc_user}"
        conf += f" --bitcoin-rpcpassword={self.tank.rpc_password}"
        conf += f" --bitcoin-rpcconnect={tank_container_name}"
        conf += f" --bitcoin-rpcport={self.tank.rpc_port}"
        conf += f" --announce-addr=dns:{ln_container_name}:9735"
        return conf

    @exponential_backoff(max_retries=20, max_delay=300)
    @handle_json
    def lncli(self, cmd) -> dict:
        cli = "lightning-cli"
        cmd = f"{cli} --network=regtest {cmd}"
        return self.backend.exec_run(self.tank.index, ServiceType.LIGHTNING, cmd)

    def getnewaddress(self):
        return self.lncli("newaddr")["bech32"]

    def get_pub_key(self):
        res = self.lncli("getinfo")
        return res["id"]

    def getURI(self):
        res = self.lncli("getinfo")
        if len(res["address"]) < 1:
            return None
        return f'{res["id"]}@{res["address"][0]["address"]}:{res["address"][0]["port"]}'

    def get_wallet_balance(self) -> int:
        res = self.lncli("listfunds")
        return int(sum(o["amount_msat"] for o in res["outputs"]) / 1000)

    # returns the channel point in the form txid:output_index
    def open_channel_to_tank(self, index: int, channel_open_data: str) -> str:
        tank = self.warnet.tanks[index]
        [pubkey, host] = tank.lnnode.getURI().split("@")
        res = self.lncli(f"fundchannel id={pubkey} {channel_open_data}")
        return f"{res['txid']}:{res['outnum']}"

    def update_channel_policy(self, chan_point: str, policy: str) -> str:
        return self.lncli(f"setchannel {chan_point} {policy}")

    def get_graph_nodes(self) -> list[str]:
        return list(n["nodeid"] for n in self.lncli("listnodes")["nodes"])

    def get_graph_channels(self) -> list[dict]:
        cln_channels = self.lncli("listchannels")["channels"]
        # CLN lists channels twice, once for each direction. This finds the unique channel ids.
        short_channel_ids = {chan["short_channel_id"]: chan for chan in cln_channels}.keys()
        channels: list[LNChannel] = []
        for short_channel_id in short_channel_ids:
            channel_1 = [
                chans for chans in cln_channels if chans["short_channel_id"] == short_channel_id
            ][0]
            channel_2 = [
                chans for chans in cln_channels if chans["short_channel_id"] == short_channel_id
            ][1]

            channels.append(
                LNChannel(
                    node1_pub=channel_1["source"],
                    node2_pub=channel_2["source"],
                    capacity_msat=channel_1["amount_msat"],
                    short_chan_id=channel_1["short_channel_id"],
                    node1_min_htlc=channel_1["htlc_minimum_msat"],
                    node2_min_htlc=channel_2["htlc_minimum_msat"],
                    node1_max_htlc=channel_1["htlc_maximum_msat"],
                    node2_max_htlc=channel_2["htlc_maximum_msat"],
                    node1_base_fee_msat=channel_1["base_fee_millisatoshi"],
                    node2_base_fee_msat=channel_2["base_fee_millisatoshi"],
                    node1_fee_rate_milli_msat=channel_1["fee_per_millionth"],
                    node2_fee_rate_milli_msat=channel_2["fee_per_millionth"],
                )
            )

        return channels

    def get_peers(self) -> list[str]:
        return list(p["id"] for p in self.lncli("listpeers")["peers"])

    def connect_to_tank(self, index):
        return super().connect_to_tank(index)

    def generate_cli_command(self, command: list[str]):
        network = f"--network={self.tank.warnet.bitcoin_network}"
        cmd = f"{network} {' '.join(command)}"
        cmd = f"lightning-cli {cmd}"

    def export(self, config: object, tar_file):
        pass
