import unittest
from tools.peaq_eth_utils import get_eth_chain_id
from tools.peaq_eth_utils import deploy_contract, deploy_contract_with_args
from tools.peaq_eth_utils import get_contract


class SmartContractBehavior(unittest.TestCase):
    def __init__(self, folder, w3, kp_deployer):
        """This class is used to deploy the smart contract and test its behavior
        folder: the folder where the smart contract is located
        w3: the web3 instance
        """
        self._folder = folder
        self._w3 = w3
        self._eth_chain_id = get_eth_chain_id(w3)
        self._kp_deployer = kp_deployer

    def _load_bytecode(self):
        bytecode_file = f"{self._folder}/bytecode"
        with open(bytecode_file, "r") as file:
            bytecode = file.read()
        return bytecode

    def deploy(self, deploy_args=None):
        bytecode = self._load_bytecode()

        abi_folder = f"{self._folder}/abi"
        if not deploy_args:
            self._address = deploy_contract(
                self._w3, self._kp_deployer, self._eth_chain_id, abi_folder, bytecode
            )
        else:
            self._address = deploy_contract_with_args(
                self._w3,
                self._kp_deployer,
                self._eth_chain_id,
                abi_folder,
                bytecode,
                deploy_args,
            )

    def get_contract(self):
        if not self._address:
            raise IOError("The contract is not deployed yet!")

        return get_contract(self._w3, self._address, f"{self._folder}/abi")

    def before_migration_sc_behavior(self):
        if self._args is None:
            raise IOError("You should call compose_all_arg() before this method!")
        self._before_act_result = self.migration_same_behavior(self._args["pre"])

    def after_migration_sc_behavior(self):
        if self._args is None:
            raise IOError("You should call compose_all_arg() before this method!")
        self._after_act_result = self.migration_same_behavior(self._args["after"])

    def compose_all_arg(self):
        """
            This method is used to compose all the arguments for the smart contract
            Please overwrite this method in the child class
        """
        raise IOError("Not implemented yet!")

    def check_migration_difference(self):
        self.assertEqual(
            self._before_act_result.keys(),
            self._after_act_result.keys(),
            "The keys of the before and after migration are not the same: "
            f"{self._before_act_result.keys()} != {self._after_act_result.keys()}",
        )
        for key in self._before_act_result.keys():
            self.assertEqual(
                self._before_act_result[key],
                self._after_act_result[key],
                f"The value of {key} is not the same before and after migration: "
                f"{self._before_act_result[key]} != {self._after_act_result[key]}",
            )

    def migration_same_behavior(self, args):
        """
            Please overwrite this method in the child class for all the testing behavior
            just remeber to return a dictionary with the keys that you want to check.
            For example:
                {
                    'test_01': '0x1234567890abcdef',
                    'test_02': {'account': '0x1234567890abcdef', 'balance': 100},
                    'test_03': 100,
                }
            Note: we'll make sure the behavior before and after migration should be the same
        """
        raise IOError("Not implemented yet!")

    def migration_new_behavior(self, args):
        """
            Please overwrite this method in the child class for all the testing behavior
            We'll check whether behavior is correct after the migration.
            This is mainly for checking the storage/state, or some continue behaviors after the migration.
        """
        raise IOError("Not implemented yet!")
