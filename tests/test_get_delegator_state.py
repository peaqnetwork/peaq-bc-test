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
from tools.constants import KP_GLOBAL_SUDO, KP_COLLATOR, BLOCK_GENERATE_TIME, TOKEN_NUM_BASE_DEV
from peaq.utils import get_block_hash, get_chain
from tools.utils import get_modified_chain_spec
from web3 import Web3


PARACHAIN_STAKING_ABI_FILE = 'ETH/parachain-staking/abi'
PARACHAIN_STAKING_ADDR = '0x0000000000000000000000000000000000000807'


@pytest.mark.relaunch
@pytest.mark.eth
class TestGetDelegatorState(unittest.TestCase):
    """Test suite for getDelegatorState functionality in parachain staking precompile"""

    @classmethod
    def setUpClass(cls):
        restart_parachain_and_runtime_upgrade()
        wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 1)
        wait_until_block_height(SubstrateInterface(url=WS_URL), 1)
        
        # Setup delegators once for all tests
        cls._setup_class_delegators()

    @classmethod
    def _setup_infrastructure(cls):
        """Get connections, constants, and ensure 4 collators exist"""
        # Initialize connections for class setup
        substrate = SubstrateInterface(url=WS_URL)
        w3 = Web3(Web3.HTTPProvider(ETH_URL))
        eth_chain_id = get_eth_chain_id(substrate)
        kp_new_collator = Keypair.create_from_uri('//NewMoon01')
        
        # Get minimum delegation amount
        min_delegation_obj = substrate.get_constant('ParachainStaking', 'MinDelegation')
        if not min_delegation_obj:
            raise Exception("MinDelegation constant returned None")
        min_delegation = min_delegation_obj.value
        
        # Get collator list and ensure we have 2 collators
        contract = get_contract(w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        out = contract.functions.getCollatorList().call()
        collator_list = sorted(out, key=lambda x: x[1], reverse=True)
        
        # Ensure we have at least 4 collators (needed for maximum delegation tests)
        while len(collator_list) < 4:
            kp_new_collator = Keypair.create_from_uri(f'//TestCollator{len(collator_list)}')
            
            # Fund new collator with generous amount
            funding_amount = max(collator_list[0][1] * 10, 60000 * TOKEN_NUM_BASE_DEV)
            batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
            batch.compose_sudo_call('Balances', 'force_set_balance', {
                'who': kp_new_collator.ss58_address,
                'new_free': funding_amount,
            })
            receipt = batch.execute()
            if not receipt.is_success:
                raise Exception(f"Failed to fund new collator: {receipt.error_message}")
            
            # Join as collator
            batch = ExtrinsicBatch(substrate, kp_new_collator)
            batch.compose_call('ParachainStaking', 'join_candidates', {'stake': collator_list[0][1]})
            receipt = batch.execute()
            if not receipt.is_success:
                raise Exception(f"Failed to add new collator: {receipt.error_message}")
            
            # Update collator list
            out = contract.functions.getCollatorList().call()
            collator_list = sorted(out, key=lambda x: x[1], reverse=True)
        
        return substrate, w3, eth_chain_id, contract, min_delegation, collator_list

    @classmethod
    def _process_delegations_async(cls, w3, contract, delegation_requests, eth_chain_id, wait_blocks=3):
        """Common pattern: send delegations async, wait, check results, retry failures"""
        from tools.peaq_eth_utils import send_raw_tx
        from tools.constants import BLOCK_GENERATE_TIME
        from tests.evm_utils import sign_and_submit_evm_transaction
        import time
        
        # Send all transactions async
        pending = []
        for request in delegation_requests:
            delegator_idx, action_type, collator_addr, delegator_kp, stake_amount = request
            try:
                # Build transaction based on action type
                nonce = w3.eth.get_transaction_count(delegator_kp['kp'].ss58_address)
                if action_type == 'join':
                    tx = contract.functions.joinDelegators(collator_addr, stake_amount).build_transaction({
                        'from': delegator_kp['kp'].ss58_address,
                        'nonce': nonce,
                        'chainId': eth_chain_id
                    })
                else:  # 'delegate'
                    tx = contract.functions.delegateAnotherCandidate(collator_addr, stake_amount).build_transaction({
                        'from': delegator_kp['kp'].ss58_address,
                        'nonce': nonce,
                        'chainId': eth_chain_id
                    })
                
                # Send transaction async
                signed_txn = w3.eth.account.sign_transaction(tx, private_key=delegator_kp['kp'].private_key)
                tx_hash = send_raw_tx(w3, signed_txn)
                pending.append((delegator_idx, action_type, collator_addr, delegator_kp, tx_hash))
                
                if action_type == 'delegate':  # Extra logging for multi-delegations
                    print(f'Delegator {delegator_idx} multi-delegation sent: {tx_hash.hex()}')
                    
            except Exception as e:
                print(f'Error preparing {action_type} for delegator {delegator_idx}: {e}')
                raise
        
        print(f'Sent {len(pending)} {pending[0][1] if pending else "unknown"} delegations, waiting for confirmation...')
        
        # Wait for transactions to be included
        time.sleep(BLOCK_GENERATE_TIME * wait_blocks)
        
        # Check results
        failed = []
        for delegator_info in pending:
            delegator_idx, action_type, collator_addr, delegator_kp, tx_hash = delegator_info
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                if receipt['status'] != 1:
                    failed.append(delegator_info)
                    print(f'Delegator {delegator_idx} {action_type} failed (status=0)')
            except Exception as e:
                failed.append(delegator_info)
                print(f'Delegator {delegator_idx} {action_type} failed: {e}')
        
        # Retry failed transactions synchronously
        for delegator_info in failed:
            delegator_idx, action_type, collator_addr, delegator_kp, _ = delegator_info
            stake_amount = delegation_requests[0][4]  # Get stake amount from original request
            nonce = w3.eth.get_transaction_count(delegator_kp['kp'].ss58_address)
            
            if action_type == 'join':
                tx = contract.functions.joinDelegators(collator_addr, stake_amount).build_transaction({
                    'from': delegator_kp['kp'].ss58_address,
                    'nonce': nonce,
                    'chainId': eth_chain_id
                })
            else:  # 'delegate'
                tx = contract.functions.delegateAnotherCandidate(collator_addr, stake_amount).build_transaction({
                    'from': delegator_kp['kp'].ss58_address,
                    'nonce': nonce,
                    'chainId': eth_chain_id
                })
            
            evm_receipt = sign_and_submit_evm_transaction(tx, w3, delegator_kp['kp'])
            if evm_receipt['status'] != 1:
                raise Exception(f'Delegator {delegator_idx} {action_type} retry failed')
            print(f'Delegator {delegator_idx} {action_type} retry succeeded')
        
        success_count = len(pending)
        retry_count = len(failed)
        print(f'{pending[0][1].capitalize() if pending else "Unknown"} delegation setup complete: {success_count} sent, {retry_count} retried')
        
        return success_count, retry_count

    @classmethod
    def _setup_main_delegators(cls, substrate, w3, contract, collator_list, min_delegation, eth_chain_id):
        """Create 11 delegators and setup their delegations"""
        
        # Create 11 unique delegators
        cls.delegator_keypairs = []
        for i in range(11):
            kp = get_eth_info()
            cls.delegator_keypairs.append(kp)
        
        # Fund all delegators
        funding_amount = 1000 * TOKEN_NUM_BASE_DEV
        min_required = min_delegation + (1 * TOKEN_NUM_BASE_DEV)
        if funding_amount <= min_required:
            raise Exception(f"Funding amount {funding_amount / TOKEN_NUM_BASE_DEV:.2f} PEAQ is not sufficient. "
                          f"Need more than {min_required / TOKEN_NUM_BASE_DEV:.2f} PEAQ (min_delegation + gas)")
        
        batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
        for i, kp in enumerate(cls.delegator_keypairs):
            batch.compose_sudo_call('Balances', 'force_set_balance', {
                'who': kp['substrate'],
                'new_free': funding_amount,
            })
        receipt = batch.execute()
        if not receipt.is_success:
            raise Exception(f"Failed to fund delegators: {receipt.error_message}")
        
        # Setup delegations
        collator1_addr = collator_list[0][0]
        collator2_addr = collator_list[1][0]
        stake_amount = min_delegation * 3
        
        # Prepare join delegation requests
        join_requests = []
        # First 7 delegators → Collator 1 (indices 0-6)
        for i in range(7):
            join_requests.append((i, 'join', collator1_addr, cls.delegator_keypairs[i], stake_amount))
        
        # Next 4 delegators → Collator 2 (indices 7-10)
        for i in range(7, 11):
            join_requests.append((i, 'join', collator2_addr, cls.delegator_keypairs[i], stake_amount))
        
        # Process join delegations using async pattern
        cls._process_delegations_async(w3, contract, join_requests, eth_chain_id, wait_blocks=3)
        
        # Force a new round to avoid DelegationsPerRoundExceeded error for multi-delegations
        batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call('ParachainStaking', 'force_new_round', {})
        receipt = batch.execute()
        if not receipt.is_success:
            raise Exception("Failed to force new round before multi-delegations")
        print('Forced new round for multi-delegations')
        
        # Wait a bit more to ensure all join transactions are fully confirmed
        from tools.constants import BLOCK_GENERATE_TIME
        import time
        time.sleep(BLOCK_GENERATE_TIME)
        
        # Prepare multi-delegation requests (delegators 1 and 2 delegate to collator2)
        print('Starting multi-delegation phase...')
        multi_requests = []
        for delegator_idx in [1, 2]:
            print(f'Delegator {delegator_idx}: preparing multi-delegation')
            multi_requests.append((delegator_idx, 'delegate', collator2_addr, cls.delegator_keypairs[delegator_idx], stake_amount))
        
        # Process multi-delegations using async pattern
        cls._process_delegations_async(w3, contract, multi_requests, eth_chain_id, wait_blocks=2)
        
        print(f'Main delegation setup complete')
        
        return cls.delegator_keypairs

    @classmethod
    def _setup_pagination_delegator(cls, substrate, w3, contract, collator_list, min_delegation, eth_chain_id):
        """Create test delegator with 4 delegations"""
        # Create a dedicated test delegator with 4 delegations for pagination tests
        cls.test_delegator = get_eth_info()
        
        # Fund the test delegator
        collator_sum = sum(c[1] for c in collator_list)
        funding_amount = collator_sum + (10 * TOKEN_NUM_BASE_DEV)
        batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call('Balances', 'force_set_balance', {
            'who': cls.test_delegator['substrate'],
            'new_free': funding_amount,
        })
        receipt = batch.execute()
        if not receipt.is_success:
            raise Exception(f"Failed to fund test delegator: {receipt.error_message}")
        
        # Delegate to first collator (join) - use same minimum delegation as other delegators
        stake_amount = min_delegation * 3
        nonce = w3.eth.get_transaction_count(cls.test_delegator['kp'].ss58_address)
        tx = contract.functions.joinDelegators(collator_list[0][0], stake_amount).build_transaction({
            'from': cls.test_delegator['kp'].ss58_address,
            'nonce': nonce,
            'chainId': eth_chain_id
        })
        evm_receipt = sign_and_submit_evm_transaction(tx, w3, cls.test_delegator['kp'])
        if evm_receipt['status'] != 1:
            raise Exception('Test delegator failed to join first collator')
        
        # Delegate to additional collators (3 more = 4 total) with force new round between each
        for i in range(1, 4):
            # Force a new round to avoid DelegationsPerRoundExceeded error
            batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
            batch.compose_sudo_call('ParachainStaking', 'force_new_round', {})
            receipt = batch.execute()
            if not receipt.is_success:
                raise Exception("Failed to force new round for test delegator setup")
            
            # Use minimum delegation amount for all delegations to ensure they're valid
            stake_amount = min_delegation * 3
            nonce = w3.eth.get_transaction_count(cls.test_delegator['kp'].ss58_address)
            tx = contract.functions.delegateAnotherCandidate(collator_list[i][0], stake_amount).build_transaction({
                'from': cls.test_delegator['kp'].ss58_address,
                'nonce': nonce,
                'chainId': eth_chain_id
            })
            evm_receipt = sign_and_submit_evm_transaction(tx, w3, cls.test_delegator['kp'])
            if evm_receipt['status'] != 1:
                raise Exception(f'Test delegator failed to delegate to collator {i}')
        
        return cls.test_delegator

    @classmethod
    def _setup_class_delegators(cls):
        """Setup 11 delegators with 2 collators once for all tests"""
        # Setup infrastructure
        substrate, w3, eth_chain_id, contract, min_delegation, collator_list = cls._setup_infrastructure()
        
        # Setup main delegators  
        cls.delegator_keypairs = cls._setup_main_delegators(substrate, w3, contract, collator_list, min_delegation, eth_chain_id)
        
        # Setup test delegator
        cls.test_delegator = cls._setup_pagination_delegator(substrate, w3, contract, collator_list, min_delegation, eth_chain_id)
        
        # Store collator list
        cls.collator_list = collator_list

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

    def _get_min_delegation_amount(self):
        """Get minimum delegation amount from chain constants"""
        try:
            min_delegation = self._substrate.get_constant(
                'ParachainStaking',
                'MinDelegation'
            )
            if min_delegation:
                return min_delegation.value
            else:
                raise Exception("MinDelegation constant returned None")
        except Exception as e:
            self.fail(f"Failed to get MinDelegation constant from chain: {e}")


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

        # Test getDelegatorState
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        moon_delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(self._kp_moon['substrate']))

        # Get delegator state via EVM (use pagination parameters since 1-param version was removed)
        delegator_states = contract.functions.getDelegatorState(moon_delegator_bytes, 0, 10).call()

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
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)

        # Use a random address that has never delegated
        fake_delegator = bytes.fromhex('1234567890abcdef' * 4)  # Random non-zero address

        # Get delegator state via EVM with pagination parameters
        delegator_states = contract.functions.getDelegatorState(fake_delegator, 0, 10).call()

        # Should return empty array
        self.assertEqual(len(delegator_states), 0, "Should return empty array for non-existent delegator")

    def test_get_delegator_state_multiple_delegations(self):
        """Test getDelegatorState for delegator with multiple delegations"""
        if len(self.collator_list) < 2:
            self.fail("Insufficient collators: test requires at least 2 collators")

        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        mars_delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(self.delegator_keypairs[1]['substrate']))

        # Get delegator state via EVM
        delegator_states = contract.functions.getDelegatorState(mars_delegator_bytes, 0, 10).call()

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
        if len(self.collator_list) < 2:
            self.fail("Insufficient collators: test requires at least 2 collators")

        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        zero_address = bytes(32)  # All zeros for getting all delegators

        # Get all delegator states via EVM
        delegator_states = contract.functions.getDelegatorState(zero_address, 0, 20).call()

        # Should return at least 11 delegators (our setup + potentially others from previous tests)
        self.assertGreaterEqual(len(delegator_states), 11, "Should return at least 11 delegators from our setup")

        # Verify our specific delegators exist and have correct structure
        our_delegator_addresses = {bytes.fromhex(self._substrate.ss58_decode(kp['substrate'])) for kp in self.delegator_keypairs}
        found_our_delegators = 0
        our_multi_delegators = 0
        
        for delegator_state in delegator_states:
            self.assertEqual(len(delegator_state), 3)  # [delegator, collators[], total]
            self.assertGreater(len(delegator_state[1]), 0)  # Should have at least one delegation
            self.assertGreater(delegator_state[2], 0)  # Total should be positive

            # Verify total equals sum of individual delegations
            delegation_sum = sum(delegation[1] for delegation in delegator_state[1])
            self.assertEqual(delegator_state[2], delegation_sum)

            # Check if this is one of our delegators
            if delegator_state[0] in our_delegator_addresses:
                found_our_delegators += 1
                if len(delegator_state[1]) == 2:  # Multi-delegator
                    our_multi_delegators += 1

        # Verify we found all our delegators
        self.assertEqual(found_our_delegators, 11, "Should find all 11 of our delegators")
        self.assertEqual(our_multi_delegators, 2, "Should have exactly 2 multi-delegators from our setup")

    def test_get_delegator_state_with_pagination_basic(self):
        """Test getDelegatorState with pagination parameters - basic functionality"""
        if len(self.collator_list) < 2:
            self.fail("Insufficient collators: test requires at least 2 collators")

        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        zero_address = bytes(32)  # Get all delegators

        # Test with limit = 1 (get first delegator only)
        delegator_states_page1 = contract.functions.getDelegatorState(
            zero_address, 0, 1
        ).call()

        # Test with limit = 2, offset = 1 (get second and third delegators)
        delegator_states_page2 = contract.functions.getDelegatorState(
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
        if len(self.collator_list) < 2:
            self.fail("Insufficient collators: test requires at least 2 collators")

        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        mars_delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(self.delegator_keypairs[1]['substrate']))

        # Get first collator delegation only
        delegator_states = contract.functions.getDelegatorState(
            mars_delegator_bytes, 0, 1
        ).call()

        self.assertEqual(len(delegator_states), 1)
        self.assertEqual(len(delegator_states[0][1]), 1, "Should return only 1 delegation")

        # Get second collator delegation
        delegator_states_page2 = contract.functions.getDelegatorState(
            mars_delegator_bytes, 1, 1
        ).call()

        if len(delegator_states_page2) > 0:
            self.assertEqual(len(delegator_states_page2[0][1]), 1, "Should return only 1 delegation")

    def test_get_delegator_state_pagination_edge_cases(self):
        """Test getDelegatorState pagination edge cases and error conditions"""
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        zero_address = bytes(32)

        # Test with limit = 0 (should fail)
        with self.assertRaises(Exception) as context:
            contract.functions.getDelegatorState(zero_address, 0, 0).call()
        self.assertIn("must be greater than 0", str(context.exception).lower())

        # Test with very large offset (should return empty)
        delegator_states = contract.functions.getDelegatorState(
            zero_address, 1000, 10
        ).call()
        self.assertEqual(len(delegator_states), 0, "Large offset should return empty results")

        # Test maximum limit (512)
        try:
            delegator_states = contract.functions.getDelegatorState(
                zero_address, 0, 512
            ).call()
            # Should not throw exception
            self.assertIsInstance(delegator_states, list)
        except Exception as e:
            self.fail(f"Maximum limit (512) should not fail: {e}")

        # Test exceeding maximum limit (should fail)
        with self.assertRaises(Exception) as context:
            contract.functions.getDelegatorState(zero_address, 0, 513).call()
        self.assertIn("maximum allowed is 512", str(context.exception).lower())

    def test_get_delegator_state_gas_consumption(self):
        """Test gas consumption for getDelegatorState calls"""
        if len(self.collator_list) < 2:
            self.fail("Insufficient collators: test requires at least 2 collators")
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)

        # Test single delegator query gas
        mars_delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(self.delegator_keypairs[1]['substrate']))

        gas_estimate_single = contract.functions.getDelegatorState(
            mars_delegator_bytes, 0, 10
        ).estimate_gas()

        print(f"Gas estimate for single delegator query: {gas_estimate_single}")
        self.assertLess(gas_estimate_single, 100000, "Single delegator query should be efficient")

        # Test all delegators query gas
        zero_address = bytes(32)
        gas_estimate_all = contract.functions.getDelegatorState(
            zero_address, 0, 10
        ).estimate_gas()

        print(f"Gas estimate for all delegators query (limit 10): {gas_estimate_all}")
        self.assertLess(gas_estimate_all, 500000, "All delegators query should be reasonable")

    def test_get_delegator_state_consistency_with_substrate(self):
        """Test that EVM getDelegatorState results match Substrate queries"""
        if len(self.collator_list) < 2:
            self.fail("Insufficient collators: test requires at least 2 collators")
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)

        # Test first 3 delegators
        for kp in self.delegator_keypairs[:3]:
            delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(kp['substrate']))

            # Get EVM result
            evm_states = contract.functions.getDelegatorState(delegator_bytes, 0, 10).call()

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

        # Initial delegation
        evm_receipt = self._join_delegators(contract, self._kp_moon['kp'],
                                          collator_list[0][0], collator_list[0][1])
        self.assertEqual(evm_receipt['status'], 1)

        # Check initial state
        moon_bytes = bytes.fromhex(self._substrate.ss58_decode(self._kp_moon['substrate']))
        states = contract.functions.getDelegatorState(moon_bytes, 0, 10).call()
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
        states = contract.functions.getDelegatorState(moon_bytes, 0, 10).call()
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
        states = contract.functions.getDelegatorState(moon_bytes, 0, 10).call()
        expected_total = expected_total - collator_list[0][1] // 4
        self.assertEqual(states[0][2], expected_total)

    def test_get_delegator_state_large_delegation_set(self):
        """Test getDelegatorState with a delegator having maximum allowed delegations"""
        # Use class-level test delegator (already has 4 delegations)
        contract = get_contract(self._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        delegator_bytes = bytes.fromhex(self._substrate.ss58_decode(self.test_delegator['substrate']))
        states = contract.functions.getDelegatorState(delegator_bytes, 0, 10).call()

        self.assertEqual(len(states), 1)
        delegator_state = states[0]
        self.assertEqual(delegator_state[0], delegator_bytes)

        # Should have exactly 4 delegations
        self.assertEqual(len(delegator_state[1]), 4)

        # Verify total equals sum of individual delegations
        delegation_sum = sum(delegation[1] for delegation in delegator_state[1])
        self.assertEqual(delegator_state[2], delegation_sum)

        # Test pagination within this delegator's delegations
        # We know this delegator has exactly 4 delegations from class setup
        if len(delegator_state[1]) != 4:
            self.fail(f"Expected exactly 4 delegations from class setup, got {len(delegator_state[1])}")
        
        # Get first 2 delegations only
        states_paged = contract.functions.getDelegatorState(delegator_bytes, 0, 2).call()
        self.assertEqual(len(states_paged), 1)
        print(f"Requested limit=2, got {len(states_paged[0][1])} delegations")
        print(f"Full delegations: {len(delegator_state[1])}")
        self.assertEqual(len(states_paged[0][1]), 2)  # Should return only 2 delegations
        self.assertEqual(states_paged[0][2], delegator_state[2])  # Total should remain the same

        # Get remaining 2 delegations (offset=2, limit=2)
        states_remaining = contract.functions.getDelegatorState(delegator_bytes, 2, 2).call()
        self.assertEqual(len(states_remaining), 1)
        self.assertEqual(len(states_remaining[0][1]), 2)  # Should return exactly 2 remaining delegations

        # Compare with Substrate state for consistency
        substrate_state = self._get_substrate_delegator_state(self.test_delegator['substrate'])
        self.assertEqual(delegator_state[2], substrate_state.value['total'])
        self.assertEqual(len(delegator_state[1]), len(substrate_state.value['delegations']))

