import pytest
import unittest
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.runtime_upgrade import wait_until_block_height
from substrateinterface import SubstrateInterface, Keypair
from tools.constants import WS_URL, ETH_URL, RELAYCHAIN_WS_URL
from tests.evm_utils import sign_and_submit_evm_transaction
from peaq.utils import ExtrinsicBatch
from tests import utils_func as TestUtils
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import get_eth_chain_id
from tools.peaq_eth_utils import get_eth_info
from tools.constants import KP_GLOBAL_SUDO, KP_COLLATOR, BLOCK_GENERATE_TIME
from peaq.utils import get_block_hash, get_chain
from tools.utils import get_modified_chain_spec
from web3 import Web3


PARACHAIN_STAKING_ABI_FILE = 'ETH/parachain-staking/abi'
PARACHAIN_STAKING_ADDR = '0x0000000000000000000000000000000000000807'

# Extended ABI to include getDelegatorState functions
EXTENDED_ABI = [
    {
        "inputs": [
            {
                "internalType": "bytes32",
                "name": "delegator",
                "type": "bytes32"
            }
        ],
        "name": "getDelegatorState",
        "outputs": [
            {
                "components": [
                    {
                        "internalType": "bytes32",
                        "name": "delegator",
                        "type": "bytes32"
                    },
                    {
                        "components": [
                            {
                                "internalType": "bytes32",
                                "name": "collator",
                                "type": "bytes32"
                            },
                            {
                                "internalType": "uint256",
                                "name": "amount",
                                "type": "uint256"
                            }
                        ],
                        "internalType": "struct ParachainStaking.DelegationInfo[]",
                        "name": "collators",
                        "type": "tuple[]"
                    },
                    {
                        "internalType": "uint256",
                        "name": "total",
                        "type": "uint256"
                    }
                ],
                "internalType": "struct ParachainStaking.CollatorDelegatorState[]",
                "name": "",
                "type": "tuple[]"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    },
    {
        "inputs": [
            {
                "internalType": "bytes32",
                "name": "delegator",
                "type": "bytes32"
            },
            {
                "internalType": "uint256",
                "name": "offset",
                "type": "uint256"
            },
            {
                "internalType": "uint256",
                "name": "limit",
                "type": "uint256"
            }
        ],
        "name": "getDelegatorState",
        "outputs": [
            {
                "components": [
                    {
                        "internalType": "bytes32",
                        "name": "delegator",
                        "type": "bytes32"
                    },
                    {
                        "components": [
                            {
                                "internalType": "bytes32",
                                "name": "collator",
                                "type": "bytes32"
                            },
                            {
                                "internalType": "uint256",
                                "name": "amount",
                                "type": "uint256"
                            }
                        ],
                        "internalType": "struct ParachainStaking.DelegationInfo[]",
                        "name": "collators",
                        "type": "tuple[]"
                    },
                    {
                        "internalType": "uint256",
                        "name": "total",
                        "type": "uint256"
                    }
                ],
                "internalType": "struct ParachainStaking.CollatorDelegatorState[]",
                "name": "",
                "type": "tuple[]"
            }
        ],
        "stateMutability": "view",
        "type": "function"
    }
]


@pytest.mark.relaunch
@pytest.mark.eth
class TestGetDelegatorState(unittest.TestCase):
    """Test suite for getDelegatorState functionality in parachain staking precompile"""

    @classmethod
    def setUpClass(cls):
        restart_parachain_and_runtime_upgrade()
        wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 1)
        wait_until_block_height(SubstrateInterface(url=WS_URL), 1)

    def _initialize_connections_and_keypairs(self):
        """Initialize connections and keypairs"""
        self._substrate = SubstrateInterface(url=WS_URL)
        self._w3 = Web3(Web3.HTTPProvider(ETH_URL))
        self._kp_moon = get_eth_info()
        self._kp_mars = get_eth_info()
        self._kp_venus = get_eth_info()
        self._eth_chain_id = get_eth_chain_id(self._substrate)
        self._kp_src = Keypair.create_from_uri('//Moon')
        self._kp_new_collator = Keypair.create_from_uri('//NewMoon01')
        self._chain_spec = get_modified_chain_spec(get_chain(self._substrate))

    def setUp(self):
        wait_until_block_height(SubstrateInterface(url=WS_URL), 1)
        self._initialize_connections_and_keypairs()

    def _fund_users(self, num=100 * 10 ** 18):
        """Fund test users with PEAQ tokens"""
        self._kp_moon = get_eth_info()
        self._kp_mars = get_eth_info()
        self._kp_venus = get_eth_info()
        
        if num < 100 * 10 ** 18:
            num = 100 * 10 ** 18
            
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        for kp in [self._kp_moon, self._kp_mars, self._kp_venus]:
            batch.compose_sudo_call(
                'Balances',
                'force_set_balance',
                {
                    'who': kp['substrate'],
                    'new_free': num,
                }
            )
        
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': self._kp_src.ss58_address,
                'new_free': num,
            }
        )
        batch.compose_sudo_call(
            'Balances',
            'force_set_balance',
            {
                'who': self._kp_new_collator.ss58_address,
                'new_free': num,
            }
        )
        return batch.execute()

    def _create_extended_contract(self):
        """Create contract instance with extended ABI including getDelegatorState"""
        # Now using the actual ABI file which has been updated with getDelegatorState
        return get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)

    def _get_collator_list(self):
        """Get sorted collator list"""
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        out = contract.functions.getCollatorList().call()
        return sorted(out, key=lambda x: x[1], reverse=True)

    def _join_delegators(self, contract, eth_kp, collator_addr, stake):
        """Helper function to join as delegator"""
        nonce = self._w3.eth.get_transaction_count(eth_kp.ss58_address)
        tx = contract.functions.joinDelegators(collator_addr, stake).build_transaction({
            'from': eth_kp.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id
        })
        return sign_and_submit_evm_transaction(tx, self._w3, eth_kp)

    def _delegate_another_candidate(self, contract, eth_kp, collator_addr, stake):
        """Helper function to delegate to another candidate"""
        nonce = self._w3.eth.get_transaction_count(eth_kp.ss58_address)
        tx = contract.functions.delegateAnotherCandidate(collator_addr, stake).build_transaction({
            'from': eth_kp.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id
        })
        return sign_and_submit_evm_transaction(tx, self._w3, eth_kp)

    def _get_substrate_delegator_state(self, delegator_addr):
        """Get delegator state from Substrate for comparison"""
        return self._substrate.query('ParachainStaking', 'DelegatorState', [delegator_addr])

    def _setup_multiple_delegators_and_collators(self):
        """Setup 11 delegators with 2 collators (7+5 distribution) and 2 multi-delegators"""
        # Ensure we have 2 collators
        collator_list = self._get_collator_list()
        if len(collator_list) < 2:
            # Add a new collator if needed
            receipt = self._fund_users(collator_list[0][1] * 2)
            self.assertEqual(receipt.is_success, True)
            
            batch = ExtrinsicBatch(self._substrate, self._kp_new_collator)
            batch.compose_call(
                'ParachainStaking',
                'join_candidates',
                {'stake': collator_list[0][1]}
            )
            receipt = batch.execute()
            self.assertEqual(receipt.is_success, True)
            
            collator_list = self._get_collator_list()

        # Create 11 unique delegators (including the original 3)
        self.delegator_keypairs = [self._kp_moon, self._kp_mars, self._kp_venus]
        for i in range(8):  # Create 8 more delegators
            kp = get_eth_info()
            self.delegator_keypairs.append(kp)

        # Fund all 11 delegators with more tokens
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        for kp in self.delegator_keypairs:
            batch.compose_sudo_call(
                'Balances',
                'force_set_balance',
                {
                    'who': kp['substrate'],
                    'new_free': collator_list[0][1] * 10,  # Increased funding
                }
            )
        receipt = batch.execute()
        self.assertEqual(receipt.is_success, True)

        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        collator1_addr = collator_list[0][0]  # First collator (will get 7 delegators)
        collator2_addr = collator_list[1][0]  # Second collator (will get 5 delegators)
        
        # Setup delegations:
        # First 7 delegators → Collator 1 (indices 0-6)
        for i in range(7):
            kp = self.delegator_keypairs[i]
            # Ensure stake is above minimum (typically 5 * 10^18 for PEAQ)
            stake_amount = max(collator_list[0][1] // (10 + i), 10 * 10**18)  # Varying amounts with minimum
            
            evm_receipt = self._join_delegators(contract, kp['kp'], collator1_addr, stake_amount)
            self.assertEqual(evm_receipt['status'], 1, f'Delegator {i} failed to join collator1')

        # Next 4 delegators → Collator 2 (indices 7-10)  
        for i in range(7, 11):
            kp = self.delegator_keypairs[i]
            # Ensure stake is above minimum
            stake_amount = max(collator_list[1][1] // (15 + i), 10 * 10**18)  # Different varying amounts with minimum
            
            evm_receipt = self._join_delegators(contract, kp['kp'], collator2_addr, stake_amount)
            self.assertEqual(evm_receipt['status'], 1, f'Delegator {i} failed to join collator2')

        # Make 2 delegators have multiple delegations:
        # Multi-delegator 1: Delegator 1 (Mars) - already delegated to collator1, now add collator2
        stake_amount = max(collator_list[1][1] // 20, 10 * 10**18)
        evm_receipt = self._delegate_another_candidate(contract, self.delegator_keypairs[1]['kp'], 
                                                     collator2_addr, stake_amount)
        self.assertEqual(evm_receipt['status'], 1, 'Multi-delegator 1 failed to delegate to collator2')

        # Multi-delegator 2: Delegator 8 - already delegated to collator2, now add collator1  
        stake_amount = max(collator_list[0][1] // 25, 10 * 10**18)
        evm_receipt = self._delegate_another_candidate(contract, self.delegator_keypairs[8]['kp'], 
                                                     collator1_addr, stake_amount)
        self.assertEqual(evm_receipt['status'], 1, 'Multi-delegator 2 failed to delegate to collator1')

        return collator_list

    def test_get_delegator_state_single_delegator_basic(self):
        """Test getDelegatorState for a single delegator with one delegation"""
        collator_list = self._get_collator_list()
        receipt = self._fund_users(collator_list[0][1] * 2)
        self.assertEqual(receipt.is_success, True)

        # Join as delegator
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        evm_receipt = self._join_delegators(contract, self._kp_moon['kp'], 
                                          collator_list[0][0], collator_list[0][1])
        self.assertEqual(evm_receipt['status'], 1)

        # Test getDelegatorState with extended contract
        extended_contract = self._create_extended_contract()
        moon_delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(self._kp_moon['substrate']))
        
        # Get delegator state via EVM
        delegator_states = extended_contract.functions.getDelegatorState(moon_delegator_bytes).call()
        
        # Verify results
        self.assertEqual(len(delegator_states), 1, "Should return exactly one delegator state")
        
        delegator_state = delegator_states[0]
        self.assertEqual(delegator_state[0], moon_delegator_bytes)  # delegator address
        self.assertEqual(len(delegator_state[1]), 1)  # collators array length
        self.assertEqual(delegator_state[2], collator_list[0][1])  # total stake
        
        # Verify delegation info
        delegation_info = delegator_state[1][0]
        self.assertEqual(delegation_info[0], collator_list[0][0])  # collator address
        self.assertEqual(delegation_info[1], collator_list[0][1])  # delegation amount

        # Compare with Substrate query
        substrate_state = self._get_substrate_delegator_state(self._kp_moon['substrate'])
        self.assertEqual(delegator_state[2], substrate_state.value['total'])

    def test_get_delegator_state_nonexistent_delegator(self):
        """Test getDelegatorState for a non-existent delegator"""
        extended_contract = self._create_extended_contract()
        
        # Use a random address that has never delegated
        fake_delegator = bytes(32)  # All zeros
        
        # Get delegator state via EVM with pagination parameters
        delegator_states = extended_contract.functions.getDelegatorState(fake_delegator, 0, 10).call()
        
        # Should return empty array
        self.assertEqual(len(delegator_states), 0, "Should return empty array for non-existent delegator")

    def test_get_delegator_state_multiple_delegations(self):
        """Test getDelegatorState for delegator with multiple delegations"""
        collator_list = self._setup_multiple_delegators_and_collators()
        
        if len(collator_list) < 2:
            self.skipTest("Need at least 2 collators for this test")
        
        extended_contract = self._create_extended_contract()
        mars_delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(self.delegator_keypairs[1]['substrate']))
        
        # Get delegator state via EVM
        delegator_states = extended_contract.functions.getDelegatorState(mars_delegator_bytes, 0, 10).call()
        
        # Verify results
        self.assertEqual(len(delegator_states), 1, "Should return exactly one delegator state")
        
        delegator_state = delegator_states[0]
        self.assertEqual(delegator_state[0], mars_delegator_bytes)
        self.assertEqual(len(delegator_state[1]), 2)  # Should have 2 delegations
        
        # Verify total matches sum of individual delegations
        delegation_sum = sum(delegation[1] for delegation in delegator_state[1])
        self.assertEqual(delegator_state[2], delegation_sum)
        
        # Compare with Substrate
        substrate_state = self._get_substrate_delegator_state(self.delegator_keypairs[1]['substrate'])
        self.assertEqual(delegator_state[2], substrate_state.value['total'])

    def test_get_delegator_state_all_delegators(self):
        """Test getDelegatorState with zero address to get all delegators"""
        collator_list = self._setup_multiple_delegators_and_collators()
        
        extended_contract = self._create_extended_contract()
        zero_address = bytes(32)  # All zeros for getting all delegators
        
        # Get all delegator states via EVM
        delegator_states = extended_contract.functions.getDelegatorState(zero_address, 0, 20).call()
        
        # Should return 11 delegators
        self.assertEqual(len(delegator_states), 11, "Should return exactly 11 delegators")
        
        # Count delegators by collator and multi-delegators
        single_delegation_count = 0
        multi_delegation_count = 0
        collator1_delegator_count = 0
        collator2_delegator_count = 0
        
        for delegator_state in delegator_states:
            self.assertEqual(len(delegator_state), 3)  # [delegator, collators[], total]
            self.assertGreater(len(delegator_state[1]), 0)  # Should have at least one delegation
            self.assertGreater(delegator_state[2], 0)  # Total should be positive
            
            # Verify total equals sum of individual delegations
            delegation_sum = sum(delegation[1] for delegation in delegator_state[1])
            self.assertEqual(delegator_state[2], delegation_sum)
            
            # Count delegation patterns
            if len(delegator_state[1]) == 1:
                single_delegation_count += 1
            elif len(delegator_state[1]) == 2:
                multi_delegation_count += 1
                
            # Count delegators per collator (some may delegate to both)
            delegations = delegator_state[1]
            for delegation in delegations:
                if delegation[0] == collator_list[0][0]:  # Collator 1
                    collator1_delegator_count += 1
                elif delegation[0] == collator_list[1][0]:  # Collator 2  
                    collator2_delegator_count += 1
        
        # Verify distribution: 9 single delegators + 2 multi delegators = 11 total
        self.assertEqual(single_delegation_count, 9, "Should have 9 single delegators")
        self.assertEqual(multi_delegation_count, 2, "Should have 2 multi delegators")
        
        # Verify collator distribution: 8 to collator1 (7 direct + 1 multi), 6 to collator2 (4 direct + 2 multi)
        self.assertEqual(collator1_delegator_count, 8, "Collator1 should have 8 delegations")
        self.assertEqual(collator2_delegator_count, 6, "Collator2 should have 6 delegations")

    def test_get_delegator_state_with_pagination_basic(self):
        """Test getDelegatorState with pagination parameters - basic functionality"""
        collator_list = self._setup_multiple_delegators_and_collators()
        
        extended_contract = self._create_extended_contract()
        zero_address = bytes(32)  # Get all delegators
        
        # Test with limit = 1 (get first delegator only)
        delegator_states_page1 = extended_contract.functions.getDelegatorState(
            zero_address, 0, 1
        ).call()
        
        # Test with limit = 2, offset = 1 (get second and third delegators)
        delegator_states_page2 = extended_contract.functions.getDelegatorState(
            zero_address, 1, 2
        ).call()
        
        # Verify pagination works
        self.assertEqual(len(delegator_states_page1), 1, "First page should have 1 delegator")
        self.assertLessEqual(len(delegator_states_page2), 2, "Second page should have at most 2 delegators")
        
        # Verify structure of paginated results
        for delegator_state in delegator_states_page1 + delegator_states_page2:
            self.assertEqual(len(delegator_state), 3)
            self.assertGreater(len(delegator_state[1]), 0)
            self.assertGreater(delegator_state[2], 0)

    def test_get_delegator_state_single_delegator_pagination(self):
        """Test getDelegatorState pagination for single delegator with multiple collators"""
        collator_list = self._setup_multiple_delegators_and_collators()
        
        if len(collator_list) < 2:
            self.skipTest("Need at least 2 collators for this test")
        
        extended_contract = self._create_extended_contract()
        mars_delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(self._kp_mars['substrate']))
        
        # Get first collator delegation only
        delegator_states = extended_contract.functions.getDelegatorState(
            mars_delegator_bytes, 0, 1
        ).call()
        
        self.assertEqual(len(delegator_states), 1)
        self.assertEqual(len(delegator_states[0][1]), 1, "Should return only 1 delegation")
        
        # Get second collator delegation
        delegator_states_page2 = extended_contract.functions.getDelegatorState(
            mars_delegator_bytes, 1, 1
        ).call()
        
        if len(delegator_states_page2) > 0:
            self.assertEqual(len(delegator_states_page2[0][1]), 1, "Should return only 1 delegation")

    def test_get_delegator_state_pagination_edge_cases(self):
        """Test getDelegatorState pagination edge cases and error conditions"""
        extended_contract = self._create_extended_contract()
        zero_address = bytes(32)
        
        # Test with limit = 0 (should fail)
        with self.assertRaises(Exception) as context:
            extended_contract.functions.getDelegatorState(zero_address, 0, 0).call()
        self.assertIn("must be greater than 0", str(context.exception).lower())
        
        # Test with very large offset (should return empty)
        delegator_states = extended_contract.functions.getDelegatorState(
            zero_address, 1000, 10
        ).call()
        self.assertEqual(len(delegator_states), 0, "Large offset should return empty results")
        
        # Test maximum limit (512)
        try:
            delegator_states = extended_contract.functions.getDelegatorState(
                zero_address, 0, 512
            ).call()
            # Should not throw exception
            self.assertIsInstance(delegator_states, list)
        except Exception as e:
            self.fail(f"Maximum limit (512) should not fail: {e}")
        
        # Test exceeding maximum limit (should fail)
        with self.assertRaises(Exception) as context:
            extended_contract.functions.getDelegatorState(zero_address, 0, 513).call()
        self.assertIn("maximum allowed is 512", str(context.exception).lower())

    def test_get_delegator_state_gas_consumption(self):
        """Test gas consumption for getDelegatorState calls"""
        collator_list = self._setup_multiple_delegators_and_collators()
        extended_contract = self._create_extended_contract()
        
        # Test single delegator query gas
        mars_delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(self.delegator_keypairs[1]['substrate']))
        
        gas_estimate_single = extended_contract.functions.getDelegatorState(
            mars_delegator_bytes, 0, 10
        ).estimate_gas()
        
        print(f"Gas estimate for single delegator query: {gas_estimate_single}")
        self.assertLess(gas_estimate_single, 100000, "Single delegator query should be efficient")
        
        # Test all delegators query gas
        zero_address = bytes(32)
        gas_estimate_all = extended_contract.functions.getDelegatorState(
            zero_address, 0, 10
        ).estimate_gas()
        
        print(f"Gas estimate for all delegators query (limit 10): {gas_estimate_all}")
        self.assertLess(gas_estimate_all, 500000, "All delegators query should be reasonable")

    def test_get_delegator_state_consistency_with_substrate(self):
        """Test that EVM getDelegatorState results match Substrate queries"""
        collator_list = self._setup_multiple_delegators_and_collators()
        extended_contract = self._create_extended_contract()
        
        # Test first 3 delegators
        for kp in self.delegator_keypairs[:3]:
            delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(kp['substrate']))
            
            # Get EVM result
            evm_states = extended_contract.functions.getDelegatorState(delegator_bytes, 0, 10).call()
            
            # Get Substrate result
            substrate_state = self._get_substrate_delegator_state(kp['substrate'])
            
            if substrate_state.value:  # If delegator exists
                self.assertEqual(len(evm_states), 1)
                evm_state = evm_states[0]
                
                # Compare totals
                self.assertEqual(evm_state[2], substrate_state.value['total'])
                
                # Compare number of delegations
                self.assertEqual(len(evm_state[1]), len(substrate_state.value['delegations']))
                
                # Compare individual delegation amounts
                evm_delegations = sorted(evm_state[1], key=lambda x: x[1], reverse=True)
                substrate_delegations = sorted(substrate_state.value['delegations'], 
                                             key=lambda x: x['amount'], reverse=True)
                
                for i, (evm_del, sub_del) in enumerate(zip(evm_delegations, substrate_delegations)):
                    self.assertEqual(evm_del[1], sub_del['amount'], 
                                   f"Delegation amount mismatch at index {i}")
            else:
                self.assertEqual(len(evm_states), 0, "EVM should return empty for non-delegator")

    def test_get_delegator_state_after_operations(self):
        """Test getDelegatorState results after various staking operations"""
        collator_list = self._get_collator_list()
        receipt = self._fund_users(collator_list[0][1] * 4)
        self.assertEqual(receipt.is_success, True)

        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        extended_contract = self._create_extended_contract()
        
        # Initial delegation
        evm_receipt = self._join_delegators(contract, self._kp_moon['kp'], 
                                          collator_list[0][0], collator_list[0][1])
        self.assertEqual(evm_receipt['status'], 1)
        
        # Check initial state
        moon_bytes = bytes.fromhex(self._substrate.ss58_decode(self._kp_moon['substrate']))
        states = extended_contract.functions.getDelegatorState(moon_bytes, 0, 10).call()
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0][2], collator_list[0][1])  # Initial amount
        
        # Increase stake
        nonce = self._w3.eth.get_transaction_count(self._kp_moon['kp'].ss58_address)
        tx = contract.functions.delegatorStakeMore(
            collator_list[0][0], collator_list[0][1] // 2
        ).build_transaction({
            'from': self._kp_moon['kp'].ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id
        })
        evm_receipt = sign_and_submit_evm_transaction(tx, self._w3, self._kp_moon['kp'])
        self.assertEqual(evm_receipt['status'], 1)
        
        # Check state after increase
        states = extended_contract.functions.getDelegatorState(moon_bytes, 0, 10).call()
        expected_total = collator_list[0][1] + collator_list[0][1] // 2
        self.assertEqual(states[0][2], expected_total)
        
        # Decrease stake
        nonce = self._w3.eth.get_transaction_count(self._kp_moon['kp'].ss58_address)
        tx = contract.functions.delegatorStakeLess(
            collator_list[0][0], collator_list[0][1] // 4
        ).build_transaction({
            'from': self._kp_moon['kp'].ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id
        })
        evm_receipt = sign_and_submit_evm_transaction(tx, self._w3, self._kp_moon['kp'])
        self.assertEqual(evm_receipt['status'], 1)
        
        # Check state after decrease
        states = extended_contract.functions.getDelegatorState(moon_bytes, 0, 10).call()
        expected_total = expected_total - collator_list[0][1] // 4
        self.assertEqual(states[0][2], expected_total)

    def test_get_delegator_state_large_delegation_set(self):
        """Test getDelegatorState with a delegator having maximum allowed delegations"""
        collator_list = self._get_collator_list()
        
        # Ensure we have enough collators (need at least 4 for max delegations per delegator)
        while len(collator_list) < 4:
            receipt = self._fund_users(collator_list[0][1] * 2)
            self.assertEqual(receipt.is_success, True)
            
            # Create a new collator
            new_collator_kp = Keypair.create_from_uri(f'//TestCollator{len(collator_list)}')
            batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
            batch.compose_sudo_call(
                'Balances',
                'force_set_balance',
                {
                    'who': new_collator_kp.ss58_address,
                    'new_free': collator_list[0][1] * 2,
                }
            )
            receipt = batch.execute()
            self.assertEqual(receipt.is_success, True)
            
            batch = ExtrinsicBatch(self._substrate, new_collator_kp)
            batch.compose_call(
                'ParachainStaking',
                'join_candidates',
                {'stake': collator_list[0][1]}
            )
            receipt = batch.execute()
            self.assertEqual(receipt.is_success, True)
            
            collator_list = self._get_collator_list()

        # Fund the test delegator
        receipt = self._fund_users(sum(c[1] for c in collator_list) + (10 * 10 ** 18))
        self.assertEqual(receipt.is_success, True)

        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        extended_contract = self._create_extended_contract()
        
        # Delegate to first collator (join)
        stake_amount = collator_list[0][1] // 4
        evm_receipt = self._join_delegators(contract, self._kp_moon['kp'], 
                                          collator_list[0][0], stake_amount)
        self.assertEqual(evm_receipt['status'], 1)
        
        # Delegate to additional collators (up to 3 more = 4 total, which is typical max)
        for i in range(1, min(4, len(collator_list))):
            stake_amount = collator_list[i][1] // (4 + i)  # Varying amounts
            evm_receipt = self._delegate_another_candidate(contract, self._kp_moon['kp'], 
                                                         collator_list[i][0], stake_amount)
            self.assertEqual(evm_receipt['status'], 1)
        
        # Test getDelegatorState with all delegations
        moon_bytes = bytes.fromhex(self._substrate.ss58_decode(self._kp_moon['substrate']))
        states = extended_contract.functions.getDelegatorState(moon_bytes, 0, 10).call()
        
        self.assertEqual(len(states), 1)
        delegator_state = states[0]
        self.assertEqual(delegator_state[0], moon_bytes)
        
        # Should have 4 delegations (or less if fewer collators available)
        expected_delegations = min(4, len(collator_list))
        self.assertEqual(len(delegator_state[1]), expected_delegations)
        
        # Verify total equals sum of individual delegations
        delegation_sum = sum(delegation[1] for delegation in delegator_state[1])
        self.assertEqual(delegator_state[2], delegation_sum)
        
        # Test pagination within this delegator's delegations
        if len(delegator_state[1]) > 2:
            # Get first 2 delegations only
            states_paged = extended_contract.functions.getDelegatorState(moon_bytes, 0, 2).call()
            self.assertEqual(len(states_paged), 1)
            self.assertEqual(len(states_paged[0][1]), 2)  # Should return only 2 delegations
            self.assertEqual(states_paged[0][2], delegator_state[2])  # Total should remain the same
            
            # Get remaining delegations
            remaining_delegations = len(delegator_state[1]) - 2
            states_remaining = extended_contract.functions.getDelegatorState(moon_bytes, 2, remaining_delegations).call()
            self.assertEqual(len(states_remaining), 1)
            self.assertEqual(len(states_remaining[0][1]), remaining_delegations)
        
        # Compare with Substrate state for consistency
        substrate_state = self._get_substrate_delegator_state(self._kp_moon['substrate'])
        self.assertEqual(delegator_state[2], substrate_state.value['total'])
        self.assertEqual(len(delegator_state[1]), len(substrate_state.value['delegations']))

    def test_get_delegator_state_nine_delegators_two_collators(self):
        """Test getDelegatorState with 9 delegators split between 2 collators (5+4)"""
        collator_list = self._get_collator_list()
        
        # Ensure we have at least 2 collators
        while len(collator_list) < 2:
            receipt = self._fund_users(collator_list[0][1] * 2)
            self.assertEqual(receipt.is_success, True)
            
            # Create a new collator
            new_collator_kp = Keypair.create_from_uri(f'//TestCollator{len(collator_list)}')
            batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
            batch.compose_sudo_call(
                'Balances',
                'force_set_balance',
                {
                    'who': new_collator_kp.ss58_address,
                    'new_free': collator_list[0][1] * 2,
                }
            )
            receipt = batch.execute()
            self.assertEqual(receipt.is_success, True)
            
            batch = ExtrinsicBatch(self._substrate, new_collator_kp)
            batch.compose_call(
                'ParachainStaking',
                'join_candidates',
                {'stake': collator_list[0][1]}
            )
            receipt = batch.execute()
            self.assertEqual(receipt.is_success, True)
            
            collator_list = self._get_collator_list()

        # Create 9 unique delegators
        delegator_keypairs = []
        for i in range(9):
            kp = get_eth_info()
            delegator_keypairs.append(kp)

        # Fund all 9 delegators
        batch = ExtrinsicBatch(self._substrate, KP_GLOBAL_SUDO)
        for kp in delegator_keypairs:
            batch.compose_sudo_call(
                'Balances',
                'force_set_balance',
                {
                    'who': kp['substrate'],
                    'new_free': collator_list[0][1] * 3,  # Give enough tokens for delegation
                }
            )
        receipt = batch.execute()
        self.assertEqual(receipt.is_success, True, f'Failed to fund delegators: {receipt}')

        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        extended_contract = self._create_extended_contract()
        
        collator1_addr = collator_list[0][0]  # First collator (will get 5 delegators)
        collator2_addr = collator_list[1][0]  # Second collator (will get 4 delegators)
        
        # Delegate first 5 delegators to collator1
        collator1_delegators = []
        for i in range(5):
            kp = delegator_keypairs[i]
            stake_amount = collator_list[0][1] // (10 + i)  # Varying amounts: 1/10, 1/11, 1/12, etc.
            
            evm_receipt = self._join_delegators(contract, kp['kp'], collator1_addr, stake_amount)
            self.assertEqual(evm_receipt['status'], 1, f'Delegator {i} failed to join collator1')
            collator1_delegators.append(kp)

        # Delegate remaining 4 delegators to collator2  
        collator2_delegators = []
        for i in range(5, 9):
            kp = delegator_keypairs[i]
            stake_amount = collator_list[1][1] // (15 + i)  # Different varying amounts
            
            evm_receipt = self._join_delegators(contract, kp['kp'], collator2_addr, stake_amount)
            self.assertEqual(evm_receipt['status'], 1, f'Delegator {i} failed to join collator2')
            collator2_delegators.append(kp)

        # Test 1: Get all delegators (should return 9)
        zero_address = bytes(32)
        all_states = extended_contract.functions.getDelegatorState(zero_address, 0, 20).call()
        
        self.assertEqual(len(all_states), 9, "Should return exactly 9 delegator states")
        
        # Verify each delegator state structure
        for delegator_state in all_states:
            self.assertEqual(len(delegator_state), 3)  # [delegator, collators[], total]
            self.assertEqual(len(delegator_state[1]), 1)  # Each delegator has exactly 1 delegation
            self.assertGreater(delegator_state[2], 0)  # Total should be positive
            
            # Verify total equals the single delegation amount
            self.assertEqual(delegator_state[2], delegator_state[1][0][1])

        # Test 2: Verify collator distribution (5+4)
        collator1_count = 0
        collator2_count = 0
        
        for delegator_state in all_states:
            delegation_info = delegator_state[1][0]  # First (and only) delegation
            if delegation_info[0] == collator1_addr:
                collator1_count += 1
            elif delegation_info[0] == collator2_addr:
                collator2_count += 1
        
        self.assertEqual(collator1_count, 5, "Collator1 should have exactly 5 delegators")
        self.assertEqual(collator2_count, 4, "Collator2 should have exactly 4 delegators")

        # Test 3: Pagination - get first 5 delegators (should include all collator1 delegators)
        first_batch = extended_contract.functions.getDelegatorState(zero_address, 0, 5).call()
        self.assertEqual(len(first_batch), 5, "First batch should return 5 delegators")

        # Test 4: Pagination - get remaining 4 delegators
        second_batch = extended_contract.functions.getDelegatorState(zero_address, 5, 4).call()
        self.assertEqual(len(second_batch), 4, "Second batch should return 4 delegators")

        # Test 5: Verify no duplicates between batches
        first_batch_addresses = {state[0] for state in first_batch}
        second_batch_addresses = {state[0] for state in second_batch}
        self.assertEqual(len(first_batch_addresses.intersection(second_batch_addresses)), 0, 
                        "No delegator should appear in both batches")

        # Test 6: Test individual delegator queries
        for i, kp in enumerate(delegator_keypairs):
            delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(kp['substrate']))
            individual_state = extended_contract.functions.getDelegatorState(delegator_bytes, 0, 10).call()
            
            self.assertEqual(len(individual_state), 1, f"Delegator {i} should return exactly 1 state")
            self.assertEqual(individual_state[0][0], delegator_bytes, f"Delegator {i} address mismatch")
            self.assertEqual(len(individual_state[0][1]), 1, f"Delegator {i} should have 1 delegation")

        # Test 7: Verify consistency with Substrate state for random delegator
        random_delegator = delegator_keypairs[3]  # Pick delegator index 3
        delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(random_delegator['substrate']))
        
        evm_state = extended_contract.functions.getDelegatorState(delegator_bytes, 0, 10).call()
        substrate_state = self._get_substrate_delegator_state(random_delegator['substrate'])
        
        self.assertEqual(evm_state[0][2], substrate_state.value['total'], 
                        "EVM and Substrate total should match")
        self.assertEqual(len(evm_state[0][1]), len(substrate_state.value['delegations']),
                        "EVM and Substrate delegation count should match")

        # Test 8: Test gas efficiency for large query
        gas_estimate = extended_contract.functions.getDelegatorState(zero_address, 0, 9).estimate_gas()
        print(f"Gas estimate for 9 delegators query: {gas_estimate}")
        self.assertLess(gas_estimate, 1000000, "Gas usage should be reasonable for 9 delegators")

        print(f"✅ Successfully tested 9 delegators: {collator1_count} → Collator1, {collator2_count} → Collator2")