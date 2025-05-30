from tools.peaq_eth_utils import deploy_contract, deploy_contract_with_args
from tools.peaq_eth_utils import get_contract
from tests.evm_utils import sign_and_submit_evm_transaction
from tools.peaq_eth_utils import TX_SUCCESS_STATUS


from functools import wraps


def log_func(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        class_name = self.__class__.__name__
        print(f"▶️ Calling: {class_name}.{func.__name__}")
        return func(self, *args, **kwargs)

    return wrapper


ABI_FILE = "ETH/batch/abi"
BATCH_ADDRESS = "0x0000000000000000000000000000000000000805"


class SmartContractBehavior:
    def __init__(self, unittest, folder, w3, kp_deployer):
        """This class is used to deploy the smart contract and test its behavior
        folder: the folder where the smart contract is located
        w3: the web3 instance
        """
        self._folder = folder
        self._w3 = w3
        self._eth_chain_id = w3.eth.chain_id
        self._kp_deployer = kp_deployer
        self._unittest = unittest

        self._abi = f"{self._folder}/abi"

        self._batch_contract = get_contract(self._w3, BATCH_ADDRESS, ABI_FILE)

    def _load_bytecode(self):
        bytecode_file = f"{self._folder}/bytecode"
        with open(bytecode_file, "r") as f:
            bytecode = f.read().strip()
        return bytecode

    def send_and_check_tx(self, tx, kp):
        tx_receipt = sign_and_submit_evm_transaction(tx, self._w3, kp["kp"])
        self._unittest.assertEqual(
            tx_receipt["status"],
            TX_SUCCESS_STATUS,
            "The transaction was not successful",
        )
        return tx_receipt

    def deploy(self, deploy_args=None):
        bytecode = self._load_bytecode()

        if not deploy_args:
            self._address = deploy_contract(
                self._w3,
                self._kp_deployer["kp"],
                self._eth_chain_id,
                self._abi,
                bytecode,
            )
        else:
            self._address = deploy_contract_with_args(
                self._w3,
                self._kp_deployer["kp"],
                self._eth_chain_id,
                self._abi,
                bytecode,
                deploy_args,
            )

    def compose_build_transaction_args(self, kp):
        return {
            "from": kp["kp"].ss58_address,
            "nonce": self._w3.eth.get_transaction_count(kp["kp"].ss58_address),
            "chainId": self._eth_chain_id,
        }

    def compose_all_args(self):
        """
        This method is used to compose all the arguments for the smart contract
        Please overwrite this method in the child class
        """
        raise IOError("Not implemented yet!")

    def _get_contract(self):
        if not self._address:
            raise IOError("The contract is not deployed yet!")

        return get_contract(self._w3, self._address, self._abi)

    def before_migration_sc_behavior(self):
        if self._args is None:
            raise IOError("You should call compose_all_args() before this method!")
        self._before_act_result = self.migration_same_behavior(self._args["pre"])

    def after_migration_sc_behavior(self):
        if self._args is None:
            raise IOError("You should call compose_all_args() before this method!")
        self._after_act_result = self.migration_same_behavior(self._args["after"])

    def check_migration_difference(self):
        self._unittest.assertEqual(
            self._before_act_result.keys(),
            self._after_act_result.keys(),
            "The keys of the before and after migration are not the same: "
            f"{self._before_act_result.keys()} != {self._after_act_result.keys()}",
        )
        for key in self._before_act_result.keys():
            self._unittest.assertEqual(
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


class SmartMultipleContractBehavior:
    def __init__(self, unittest, folders, w3, kp_deployer):
        """This class is used to deploy the smart contract and test its behavior
        folder: the folder where the smart contract is located
        w3: the web3 instance
        """
        self._folders = folders
        self._w3 = w3
        self._eth_chain_id = w3.eth.chain_id
        self._kp_deployer = kp_deployer
        self._unittest = unittest

        self._abis = {k: f"{v}/abi" for k, v in folders.items()}

        self._batch_contract = get_contract(self._w3, BATCH_ADDRESS, ABI_FILE)

    def _load_bytecode_by_key(self, key):
        bytecode_file = f"{self._folders[key]}/bytecode"
        with open(bytecode_file, "r") as f:
            bytecode = f.read().strip()
        return bytecode

    def _get_contract_by_key(self, key):
        if not self._addresses[key]:
            raise IOError("The contract is not deployed yet!")

        return get_contract(self._w3, self._addresses[key], self._abis[key])

    def deploy(self, deploy_args=None):
        """
        Deploy the multiple smart contract
        Please remember to setup the address
        """
        raise IOError("Not implemented yet!")

    def compose_build_transaction_args(self, kp):
        return {
            "from": kp["kp"].ss58_address,
            "nonce": self._w3.eth.get_transaction_count(kp["kp"].ss58_address),
            "chainId": self._eth_chain_id,
        }

    def compose_all_args(self):
        """
        This method is used to compose all the arguments for the smart contract
        Please overwrite this method in the child class
        """
        raise IOError("Not implemented yet!")

    def send_and_check_tx(self, tx, kp):
        tx_receipt = sign_and_submit_evm_transaction(tx, self._w3, kp["kp"])
        self._unittest.assertEqual(
            tx_receipt["status"],
            TX_SUCCESS_STATUS,
            "The transaction was not successful",
        )
        return tx_receipt

    def before_migration_sc_behavior(self):
        if self._args is None:
            raise IOError("You should call compose_all_args() before this method!")
        self._before_act_result = self.migration_same_behavior(self._args["pre"])

    def after_migration_sc_behavior(self):
        if self._args is None:
            raise IOError("You should call compose_all_args() before this method!")
        self._after_act_result = self.migration_same_behavior(self._args["after"])

    def check_migration_difference(self):
        self._unittest.assertEqual(
            self._before_act_result.keys(),
            self._after_act_result.keys(),
            "The keys of the before and after migration are not the same: "
            f"{self._before_act_result.keys()} != {self._after_act_result.keys()}",
        )
        for key in self._before_act_result.keys():
            self._unittest.assertEqual(
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
