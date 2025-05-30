from tests.evm_sc.base import SmartContractBehavior, log_func
from tools.peaq_eth_utils import get_eth_info
from web3 import Web3
import pytest


class ERC721SmartContractBehavior(SmartContractBehavior):
    def __init__(self, unittest, w3, kp_deployer):
        super().__init__(unittest, "ETH/erc721.openzeppelin", w3, kp_deployer)

    @log_func
    def deploy(self, deploy_args=None):
        super().deploy(deploy_args)

    def compose_all_args(self):
        self._args = {
            "pre": {
                "mint_and_burn_nft": [get_eth_info()],
                "mint_and_safe_transfer_nft": [
                    get_eth_info(),
                    get_eth_info(),
                    get_eth_info(),
                ],
                "mint_and_approval_for_all_nft": [
                    get_eth_info(),
                    get_eth_info(),
                    get_eth_info(),
                ],
            },
            "after": {
                "mint_and_burn_nft": [get_eth_info()],
                "mint_and_safe_transfer_nft": [
                    get_eth_info(),
                    get_eth_info(),
                    get_eth_info(),
                ],
                "mint_and_approval_for_all_nft": [
                    get_eth_info(),
                    get_eth_info(),
                    get_eth_info(),
                ],
            },
        }

    def get_fund_ss58_keys(self):
        """Get the ss58 keys for funding"""
        return (
            [self._kp_deployer["substrate"]]
            + [
                kp["substrate"]
                for action_type in ["pre", "after"]
                for kp in self._args[action_type]["mint_and_burn_nft"][:1]
            ]
            + [
                kp["substrate"]
                for action_type in ["pre", "after"]
                for kp in self._args[action_type]["mint_and_safe_transfer_nft"][:3]
            ]
            + [
                kp["substrate"]
                for action_type in ["pre", "after"]
                for kp in self._args[action_type]["mint_and_approval_for_all_nft"][:3]
            ]
        )

    @log_func
    def mint_and_approval_for_all_nft(self, kp_from, kp_operator, kp_to):
        address_dict = {
            kp_from["kp"].ss58_address: "from",
            kp_operator["kp"].ss58_address: "operator",
            kp_to["kp"].ss58_address: "to",
        }

        contract = self._get_contract()
        token_uri = f"{kp_from['kp'].ss58_address}"
        # Get new_tokne_id by mint
        new_token_id = contract.functions.mint(
            kp_from["kp"].ss58_address, token_uri
        ).call(self.compose_build_transaction_args(self._kp_deployer))

        tx = contract.functions.mint(
            kp_from["kp"].ss58_address, token_uri
        ).build_transaction(self.compose_build_transaction_args(self._kp_deployer))
        self.send_and_check_tx(tx, self._kp_deployer)

        tx = contract.functions.setApprovalForAll(
            kp_operator["kp"].ss58_address, True
        ).build_transaction(self.compose_build_transaction_args(kp_from))
        self.send_and_check_tx(tx, kp_from)

        self._unittest.assertEqual(
            contract.functions.isApprovedForAll(
                kp_from["kp"].ss58_address, kp_operator["kp"].ss58_address
            ).call(),
            True,
            "The operator is not approved for all",
        )

        tx = contract.functions.safeTransferFrom(
            kp_from["kp"].ss58_address, kp_to["kp"].ss58_address, new_token_id
        ).build_transaction(self.compose_build_transaction_args(kp_operator))
        self.send_and_check_tx(tx, kp_operator)

        owner = contract.functions.ownerOf(new_token_id).call()
        uri_detail = contract.functions.tokenURI(new_token_id).call()
        return {
            "mint_and_approval_for_all_nft": {
                "sender_nft": contract.functions.balanceOf(
                    kp_from["kp"].ss58_address
                ).call(),
                "operator_nft": contract.functions.balanceOf(
                    kp_operator["kp"].ss58_address
                ).call(),
                "receiver_nft": contract.functions.balanceOf(
                    kp_to["kp"].ss58_address
                ).call(),
                "owner": address_dict[owner],
                "uri": address_dict[uri_detail],
            }
        }

    @log_func
    def mint_and_safe_transfer_nft(self, kp_from, kp_approval, kp_to):
        address_dict = {
            kp_from["kp"].ss58_address: "from",
            kp_approval["kp"].ss58_address: "approval",
            kp_to["kp"].ss58_address: "to",
        }

        contract = self._get_contract()
        token_uri = f"{kp_from['kp'].ss58_address}"
        # Get new_tokne_id by mint
        new_token_id = contract.functions.mint(
            kp_from["kp"].ss58_address, token_uri
        ).call(
            {
                "from": self._kp_deployer["kp"].ss58_address,
                "nonce": self._w3.eth.get_transaction_count(
                    self._kp_deployer["kp"].ss58_address
                ),
                "chainId": self._eth_chain_id,
            }
        )

        tx = contract.functions.mint(
            kp_from["kp"].ss58_address, token_uri
        ).build_transaction(self.compose_build_transaction_args(self._kp_deployer))
        self.send_and_check_tx(tx, self._kp_deployer)

        tx = contract.functions.approve(
            kp_approval["kp"].ss58_address, new_token_id
        ).build_transaction(self.compose_build_transaction_args(kp_from))
        self.send_and_check_tx(tx, kp_from)

        tx = contract.functions.safeTransferFrom(
            kp_from["kp"].ss58_address, kp_to["kp"].ss58_address, new_token_id
        ).build_transaction(self.compose_build_transaction_args(kp_approval))
        self.send_and_check_tx(tx, kp_approval)

        owner = contract.functions.ownerOf(new_token_id).call()
        uri_detail = contract.functions.tokenURI(new_token_id).call()
        return {
            "mint_and_safe_transfer_nft": {
                "sender_nft": contract.functions.balanceOf(
                    kp_from["kp"].ss58_address
                ).call(),
                "approval_nft": contract.functions.balanceOf(
                    kp_approval["kp"].ss58_address
                ).call(),
                "receiver_nft": contract.functions.balanceOf(
                    kp_to["kp"].ss58_address
                ).call(),
                "owner": address_dict[owner],
                "uri": address_dict[uri_detail],
            }
        }

    @log_func
    def mint_and_burn_nft(self, kp_nft):
        contract = self._get_contract()
        token_uri = f"{kp_nft['kp'].ss58_address}/token_uri"
        # Get new_tokne_id by mint
        new_token_id = contract.functions.mint(
            kp_nft["kp"].ss58_address, token_uri
        ).call(
            {
                "from": self._kp_deployer["kp"].ss58_address,
                "nonce": self._w3.eth.get_transaction_count(
                    self._kp_deployer["kp"].ss58_address
                ),
                "chainId": self._eth_chain_id,
            }
        )

        # Batch call with mint + burn
        tx = self._batch_contract.functions.batchAll(
            [
                Web3.to_checksum_address(self._address),
                Web3.to_checksum_address(self._address),
            ],
            [0, 0],
            [
                contract.encodeABI(
                    fn_name="mint", args=[kp_nft["kp"].ss58_address, token_uri]
                ),
                contract.encodeABI(fn_name="burn", args=[new_token_id]),
            ],
            [0, 0],
        ).build_transaction(self.compose_build_transaction_args(self._kp_deployer))
        self.send_and_check_tx(tx, self._kp_deployer)

        with pytest.raises(Exception):
            contract.functions.ownerOf(new_token_id).call()

        return {
            "mint_and_burn_nft": True,
        }

    def migration_same_behavior(self, args):
        return {
            "mint_and_burn_nft": self.mint_and_burn_nft(*args["mint_and_burn_nft"]),
            "mint_and_safe_transfer_nft": self.mint_and_safe_transfer_nft(
                *args["mint_and_safe_transfer_nft"]
            ),
            "mint_and_approval_for_all_nft": self.mint_and_approval_for_all_nft(
                *args["mint_and_approval_for_all_nft"]
            ),
        }
