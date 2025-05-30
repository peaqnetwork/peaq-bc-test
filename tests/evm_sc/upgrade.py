from tests.evm_sc.base import SmartMultipleContractBehavior, log_func
from tools.peaq_eth_utils import deploy_contract, deploy_contract_with_args
from tools.peaq_eth_utils import get_contract
from web3 import Web3


class UpgradeSCBehavior(SmartMultipleContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        self._upgrade_version = 100
        super().__init__(
            unittest,
            {
                "proxy": "ETH/upgradable/erc1967",
                "logic": "ETH/upgradable/UUPSContract",
            },
            w3,
            kp_deployer,
        )

    @log_func
    def deploy(self, deploy_args=None):
        logic_address = deploy_contract(
            self._w3,
            self._kp_deployer["kp"],
            self._eth_chain_id,
            self._abis["logic"],
            self._load_bytecode_by_key("logic"),
        )
        logic_contract = get_contract(self._w3, logic_address, self._abis["logic"])
        init_data = logic_contract.encodeABI(
            fn_name="initialize",
            args=[f"v{self._upgrade_version}"],
        )

        proxy_address = deploy_contract_with_args(
            self._w3,
            self._kp_deployer["kp"],
            self._eth_chain_id,
            self._abis["proxy"],
            self._load_bytecode_by_key("proxy"),
            [logic_address, init_data],
        )

        self._addresses = {
            "logic": logic_address,
            "proxy": proxy_address,
        }
        self._contracts = {
            "logic": logic_contract,
            "proxy": self._get_contract_by_key("proxy"),
        }

        # Check if the logic contract is initialized
        self._unittest.assertEqual(
            get_contract(self._w3, proxy_address, self._abis["logic"])
            .functions.version()
            .call(),
            f"v{self._upgrade_version}",
            "The logic contract is not initialized",
        )
        self._unittest.assertEqual(
            self.calculate_logic_addr(self._addresses["proxy"]),
            self._addresses["logic"],
            "The logic contract address is not the same as expected",
        )

    def compose_all_args(self):
        self._args = {
            "pre": {
                "upgrade_to": [],
            },
            "after": {
                "upgrade_to": [],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return [self._kp_deployer["substrate"]] + [
            kp["substrate"]
            for action_type in ["pre", "after"]
            for kp in self._args[action_type]["upgrade_to"][:1]
        ]

    def calculate_logic_addr(self, proxy_address):
        slot_hash = Web3.keccak(text="eip1967.proxy.implementation")
        slot = int.from_bytes(slot_hash, "big") - 1

        implementation_raw = self._w3.eth.get_storage_at(proxy_address, slot)
        return Web3.to_checksum_address(implementation_raw[-20:].hex())

    @log_func
    def upgrade_to(self):
        self._upgrade_version += 1

        new_logic_address = deploy_contract(
            self._w3,
            self._kp_deployer["kp"],
            self._eth_chain_id,
            self._abis["logic"],
            self._load_bytecode_by_key("logic"),
        )
        new_logic_contract = get_contract(
            self._w3, new_logic_address, self._abis["logic"]
        )
        init_data = new_logic_contract.encodeABI(
            fn_name="setVersion",
            args=[f"v{self._upgrade_version}"],
        )

        proxy_contract = get_contract(
            self._w3, self._addresses["proxy"], self._abis["logic"]
        )
        tx = proxy_contract.functions.upgradeToAndCall(
            new_logic_address, init_data
        ).build_transaction(self.compose_build_transaction_args(self._kp_deployer))
        self.send_and_check_tx(tx, self._kp_deployer)

        self._unittest.assertEqual(
            self.calculate_logic_addr(self._addresses["proxy"]),
            new_logic_address,
            "The logic contract address is not the same as expected",
        )

        self._unittest.assertEqual(
            proxy_contract.functions.version().call(),
            f"v{self._upgrade_version}",
            "The new version is not the same as expected",
        )

        tx = proxy_contract.functions.setValue(self._upgrade_version).build_transaction(
            self.compose_build_transaction_args(self._kp_deployer)
        )
        self.send_and_check_tx(tx, self._kp_deployer)
        self._unittest.assertEqual(
            proxy_contract.functions.value().call(),
            self._upgrade_version,
            "The value is not the same as expected",
        )

        return None

    def migration_same_behavior(self, args):
        return {
            "upgrade_to": self.upgrade_to(*args["upgrade_to"]),
        }
