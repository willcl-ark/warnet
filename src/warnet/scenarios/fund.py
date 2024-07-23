#!/usr/bin/env python3

from time import sleep

from warnet.scenarios.utils import ensure_miner
from warnet.test_framework_bridge import WarnetTestFramework


def cli_help():
    return "Fund all nodes with a load of coins"


class Miner:
    def __init__(self, node):
        self.node = node
        self.wallet = ensure_miner(self.node)
        self.addr = self.wallet.getnewaddress()


class Funder(WarnetTestFramework):
    def set_test_params(self):
        self.num_nodes = 0
        self.miners = []

    def run_test(self):
        self.log.info("Waiting for complete network connection...")
        while not self.warnet.network_connected():
            sleep(0.25)
        self.log.info("Network connected. Starting funding...")

        for index in range(len(self.nodes)):
            self.miners.append(Miner(self.nodes[index]))

        for miner in self.miners:
            num = 10
            try:
                self.generatetoaddress(miner.node, num, miner.addr, sync_fun=self.no_op)
                height = miner.node.getblockcount()
                self.log.info(
                    f"generated {num} block(s) from node {miner.node.index}. New chain height: {height}"
                )
            except Exception as e:
                self.log.error(f"node {miner.node.index} error: {e}")
            sleep(5)
        self.generatetoaddress(miner.node, 101, miner.addr, sync_fun=self.no_op)


if __name__ == "__main__":
    Funder().main()
