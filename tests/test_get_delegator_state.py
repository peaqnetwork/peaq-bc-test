import pytest
import unittest
from functools import wraps
from tests.utils_func import restart_parachain_and_runtime_upgrade
from tools.runtime_upgrade import wait_until_block_height
from substrateinterface import SubstrateInterface, Keypair
from tools.constants import WS_URL, ETH_URL, RELAYCHAIN_WS_URL
from tests.evm_utils import sign_and_submit_evm_transaction
from peaq.utils import ExtrinsicBatch
from tools.peaq_eth_utils import get_contract
from tools.peaq_eth_utils import get_eth_chain_id
from tools.peaq_eth_utils import get_eth_info
from tools.constants import KP_GLOBAL_SUDO, TOKEN_NUM_BASE_DEV
from peaq.utils import get_chain
from tools.utils import get_modified_chain_spec
from web3 import Web3


PARACHAIN_STAKING_ABI_FILE = 'ETH/parachain-staking/abi'
PARACHAIN_STAKING_ADDR = '0x0000000000000000000000000000000000000807'


def requires_collators(count=2):
    """Decorator to ensure test has required number of collators available"""
    def decorator(test_func):
        @wraps(test_func)
        def wrapper(self):
            assert len(self.collator_list) >= count, f"Test requires at least {count} collators"
            return test_func(self)
        return wrapper
    return decorator


@pytest.mark.relaunch
@pytest.mark.eth
class TestGetDelegatorState(unittest.TestCase):
    """
    Test suite for getDelegatorState precompile functionality.

    Setup: Creates 11 delegators with specific delegation patterns:
    - Delegators 0-6: Single delegation to Collator 1
    - Delegators 7-10: Single delegation to Collator 2
    - Delegators 1,2: Additional delegation to Collator 2 (multi-delegators)

    Performance: ~12 minutes for full suite, individual tests ~30-60 seconds
    """

    @classmethod
    def setUpClass(cls):
        restart_parachain_and_runtime_upgrade()
        wait_until_block_height(SubstrateInterface(url=RELAYCHAIN_WS_URL), 1)
        wait_until_block_height(SubstrateInterface(url=WS_URL), 1)

        # Test configuration constants
        cls.TOTAL_TEST_DELEGATORS = 11
        cls.COLLATOR_1_DELEGATOR_COUNT = 7  # First 7 delegators → Collator 1 (indices 0-6)
        cls.COLLATOR_2_DELEGATOR_COUNT = 4  # Next 4 delegators → Collator 2 (indices 7-10)
        cls.PRIMARY_MULTI_DELEGATOR_IDX = 1  # First delegator with multiple delegations
        cls.SECONDARY_MULTI_DELEGATOR_IDX = 2  # Second delegator with multiple delegations
        cls.MULTI_DELEGATOR_INDICES = [cls.PRIMARY_MULTI_DELEGATOR_IDX, cls.SECONDARY_MULTI_DELEGATOR_IDX]
        cls.SINGLE_DELEGATION_AMOUNT = None  # Will be set during setup
        cls.MIN_DELEGATION = None  # Will be set during setup

        # Setup cached infrastructure once for all tests
        cls._substrate = SubstrateInterface(url=WS_URL)
        cls._w3 = Web3(Web3.HTTPProvider(ETH_URL))
        cls._eth_chain_id = get_eth_chain_id(cls._substrate)
        cls._contract = get_contract(cls._w3, PARACHAIN_STAKING_ADDR, PARACHAIN_STAKING_ABI_FILE)
        cls._collator_list_cache = None  # Will be populated on first access

        # Setup delegators once for all tests
        cls._setup_class_delegators()

    @classmethod
    def _get_min_delegation(cls):
        """Get minimum delegation amount from chain constants"""
        min_delegation_obj = cls._substrate.get_constant('ParachainStaking', 'MinDelegation')
        if not min_delegation_obj:
            raise RuntimeError(
                "Failed to get MinDelegation constant from ParachainStaking pallet - check runtime configuration")
        return min_delegation_obj.value

    @classmethod
    def _get_or_create_collator_list(cls):
        """Get cached collator list or fetch from chain"""
        if cls._collator_list_cache is None:
            out = cls._contract.functions.getCollatorList().call()
            cls._collator_list_cache = sorted(out, key=lambda x: x[1], reverse=True)
        return cls._collator_list_cache

    @classmethod
    def _ensure_minimum_collators(cls, required_count=2):
        """Ensure we have at least the required number of collators"""
        collator_list = cls._get_or_create_collator_list()

        while len(collator_list) < required_count:
            # Create new collator
            kp_new_collator = Keypair.create_from_uri(f'//TestCollator{len(collator_list)}')

            # Fund new collator
            funding_amount = (max(collator_list[0][1] * 10, 60000 * TOKEN_NUM_BASE_DEV)
                              if collator_list else 60000 * TOKEN_NUM_BASE_DEV)
            batch = ExtrinsicBatch(cls._substrate, KP_GLOBAL_SUDO)
            batch.compose_sudo_call('Balances', 'force_set_balance', {
                'who': kp_new_collator.ss58_address,
                'new_free': funding_amount,
            })
            receipt = batch.execute()
            cls.assertTrue(receipt.is_success, f"Failed to fund new collator: {receipt.error_message}")

            # Join as collator
            stake_amount = collator_list[0][1] if collator_list else 10000 * TOKEN_NUM_BASE_DEV
            batch = ExtrinsicBatch(cls._substrate, kp_new_collator)
            batch.compose_call('ParachainStaking', 'join_candidates', {'stake': stake_amount})
            receipt = batch.execute()
            cls.assertTrue(receipt.is_success, f"Failed to add new collator: {receipt.error_message}")

            # Update cache
            out = cls._contract.functions.getCollatorList().call()
            collator_list = sorted(out, key=lambda x: x[1], reverse=True)
            cls._collator_list_cache = collator_list

        return collator_list

    @classmethod
    def _setup_infrastructure(cls):
        """Simple method to get all required test infrastructure"""
        # Get connections (already cached from setUpClass)
        substrate = cls._substrate
        w3 = cls._w3
        eth_chain_id = cls._eth_chain_id
        contract = cls._contract

        # Get chain constants
        min_delegation = cls._get_min_delegation()

        # Ensure we have enough collators
        collator_list = cls._ensure_minimum_collators(required_count=2)

        return substrate, w3, eth_chain_id, contract, min_delegation, collator_list

    @classmethod
    def _build_delegation_transaction(cls, w3, contract, action_type, delegator_kp, collator_addr,
                                      stake_amount, eth_chain_id):
        """Build delegation transaction based on action type"""
        nonce = w3.eth.get_transaction_count(delegator_kp['kp'].ss58_address)
        if action_type == 'join':
            return contract.functions.joinDelegators(collator_addr, stake_amount).build_transaction({
                'from': delegator_kp['kp'].ss58_address,
                'nonce': nonce,
                'chainId': eth_chain_id
            })
        else:  # 'delegate'
            return contract.functions.delegateAnotherCandidate(collator_addr, stake_amount).build_transaction({
                'from': delegator_kp['kp'].ss58_address,
                'nonce': nonce,
                'chainId': eth_chain_id
            })

    @classmethod
    def _send_delegation_transactions(cls, w3, contract, delegation_requests, eth_chain_id):
        """Send all delegation transactions asynchronously"""
        from tools.peaq_eth_utils import send_raw_tx

        pending = []
        for request in delegation_requests:
            delegator_idx, action_type, collator_addr, delegator_kp, stake_amount = request
            try:
                tx = cls._build_delegation_transaction(
                    w3, contract, action_type, delegator_kp, collator_addr, stake_amount, eth_chain_id)

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
        return pending

    @classmethod
    def _check_transaction_receipts(cls, w3, pending_transactions):
        """Check transaction receipts in two passes for optimal performance"""
        import time
        from tools.constants import BLOCK_GENERATE_TIME

        # Use shorter initial wait - just 1 block
        time.sleep(BLOCK_GENERATE_TIME)

        failed = []
        succeeded = []

        # First pass - quick check for already confirmed transactions
        remaining = []
        for delegator_info in pending_transactions:
            delegator_idx, action_type, collator_addr, delegator_kp, tx_hash = delegator_info
            try:
                receipt = w3.eth.get_transaction_receipt(tx_hash)
                if receipt['status'] == 1:
                    succeeded.append(delegator_info)
                    print(f'Delegator {delegator_idx} {action_type} succeeded (immediate)')
                else:
                    failed.append(delegator_info)
                    print(f'Delegator {delegator_idx} {action_type} failed (status=0)')
            except Exception:
                # Transaction not yet confirmed, add to remaining for retry
                remaining.append(delegator_info)

        # Second pass - wait and retry only unconfirmed transactions
        if remaining:
            print(f'Waiting for {len(remaining)} remaining transactions...')
            time.sleep(BLOCK_GENERATE_TIME)  # Wait one more block

            for delegator_info in remaining:
                delegator_idx, action_type, collator_addr, delegator_kp, tx_hash = delegator_info
                try:
                    receipt = w3.eth.get_transaction_receipt(tx_hash)
                    if receipt['status'] == 1:
                        succeeded.append(delegator_info)
                        print(f'Delegator {delegator_idx} {action_type} succeeded (retry)')
                    else:
                        failed.append(delegator_info)
                        print(f'Delegator {delegator_idx} {action_type} failed (status=0)')
                except Exception as e:
                    failed.append(delegator_info)
                    print(f'Delegator {delegator_idx} {action_type} receipt not found: {e}')

        return succeeded, failed

    @classmethod
    def _verify_failed_transactions(cls, w3, failed_transactions):
        """Double-check failed transactions to avoid false negatives"""
        actually_failed = []
        succeeded = []

        for delegator_info in failed_transactions:
            delegator_idx, action_type, collator_addr, delegator_kp, tx_hash = delegator_info

            # Double-check if this transaction actually exists and succeeded
            try:
                final_receipt = w3.eth.get_transaction_receipt(tx_hash)
                if final_receipt and final_receipt['status'] == 1:
                    print(f'Delegator {delegator_idx} {action_type} actually succeeded (found on final check)')
                    succeeded.append(delegator_info)
                else:
                    actually_failed.append(delegator_info)
            except Exception:
                actually_failed.append(delegator_info)

        return succeeded, actually_failed

    @classmethod
    def _retry_failed_delegations(cls, w3, contract, delegation_requests, actually_failed, eth_chain_id):
        """Retry transactions that actually failed"""
        from tests.evm_utils import sign_and_submit_evm_transaction

        for delegator_info in actually_failed:
            delegator_idx, action_type, collator_addr, delegator_kp, _ = delegator_info

            # Find the correct stake amount for this specific request
            stake_amount = None
            for req in delegation_requests:
                if req[0] == delegator_idx and req[1] == action_type:
                    stake_amount = req[4]
                    break

            if stake_amount is None:
                raise ValueError(
                    f'Could not find stake amount for delegator {delegator_idx} - internal test setup error')

            print(f'Retrying {action_type} for delegator {delegator_idx} with amount {stake_amount}')

            tx = cls._build_delegation_transaction(
                w3, contract, action_type, delegator_kp, collator_addr, stake_amount, eth_chain_id)

            try:
                evm_receipt = sign_and_submit_evm_transaction(tx, w3, delegator_kp['kp'])
                assert evm_receipt['status'] == 1, (
                    f'Delegator {delegator_idx} {action_type} retry failed '
                    f'with status {evm_receipt["status"]}')
                print(f'Delegator {delegator_idx} {action_type} retry succeeded')
            except Exception as e:
                if "already known" in str(e).lower():
                    print(f'Delegator {delegator_idx} {action_type} retry skipped '
                          '(transaction already known - likely succeeded)')
                else:
                    raise Exception(f'Delegator {delegator_idx} {action_type} retry failed: {e}')

    @classmethod
    def _process_delegations_async(cls, w3, contract, delegation_requests, eth_chain_id, wait_blocks=3):
        """Common pattern: send delegations async, wait, check results, retry failures"""
        # Send all transactions async
        pending = cls._send_delegation_transactions(w3, contract, delegation_requests, eth_chain_id)

        # Check results with optimized parallel receipt checking
        succeeded, failed = cls._check_transaction_receipts(w3, pending)

        # Verify failed transactions to avoid false negatives
        additional_succeeded, actually_failed = cls._verify_failed_transactions(w3, failed)
        succeeded.extend(additional_succeeded)

        # Retry only the actually failed transactions
        cls._retry_failed_delegations(w3, contract, delegation_requests, actually_failed, eth_chain_id)

        total_sent = len(pending)
        total_succeeded = len(succeeded)
        total_retried = len(actually_failed)
        action = pending[0][1].capitalize() if pending else "Unknown"
        print(f'{action} delegation setup complete: {total_sent} sent, '
              f'{total_succeeded} succeeded immediately, {total_retried} retried')

        return total_sent, total_retried

    @classmethod
    def _create_delegator_keypairs(cls):
        """Create 11 unique delegator keypairs"""
        cls.delegator_keypairs = []
        for i in range(11):
            kp = get_eth_info()
            cls.delegator_keypairs.append(kp)
        return cls.delegator_keypairs

    @classmethod
    def _fund_all_delegators(cls, substrate, min_delegation):
        """Fund all delegator accounts with sufficient balance"""
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
        cls.assertTrue(receipt.is_success, f"Failed to fund delegators: {receipt.error_message}")

    @classmethod
    def _prepare_join_delegation_requests(cls, collator_list, stake_amount):
        """Prepare initial join delegation requests for all delegators"""
        collator1_addr = collator_list[0][0]
        collator2_addr = collator_list[1][0]

        join_requests = []
        # First group of delegators → Collator 1
        for i in range(cls.COLLATOR_1_DELEGATOR_COUNT):
            join_requests.append((i, 'join', collator1_addr, cls.delegator_keypairs[i], stake_amount))

        # Second group of delegators → Collator 2
        for i in range(cls.COLLATOR_1_DELEGATOR_COUNT, cls.COLLATOR_1_DELEGATOR_COUNT + cls.COLLATOR_2_DELEGATOR_COUNT):
            join_requests.append((i, 'join', collator2_addr, cls.delegator_keypairs[i], stake_amount))

        return join_requests

    @classmethod
    def _force_new_round_for_multi_delegations(cls, substrate):
        """Force a new round to avoid DelegationsPerRoundExceeded error"""
        batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
        batch.compose_sudo_call('ParachainStaking', 'force_new_round', {})
        receipt = batch.execute()
        cls.assertTrue(receipt.is_success, "Failed to force new round before multi-delegations")
        print('Forced new round for multi-delegations')

    @classmethod
    def _prepare_multi_delegation_requests(cls, collator_list, stake_amount):
        """Prepare multi-delegation requests for designated multi-delegators"""
        collator2_addr = collator_list[1][0]

        print('Starting multi-delegation phase...')
        multi_requests = []
        for delegator_idx in cls.MULTI_DELEGATOR_INDICES:
            print(f'Delegator {delegator_idx}: preparing multi-delegation')
            multi_requests.append((delegator_idx, 'delegate', collator2_addr,
                                  cls.delegator_keypairs[delegator_idx], stake_amount))

        return multi_requests

    @classmethod
    def _setup_main_delegators(cls, substrate, w3, contract, collator_list, min_delegation, eth_chain_id):
        """Create 11 delegators and setup their delegations"""
        # Store test configuration for assertions
        cls.MIN_DELEGATION = min_delegation
        cls.SINGLE_DELEGATION_AMOUNT = min_delegation * 3
        stake_amount = cls.SINGLE_DELEGATION_AMOUNT

        # Create and fund delegators
        cls._create_delegator_keypairs()
        cls._fund_all_delegators(substrate, min_delegation)

        # Setup initial join delegations
        join_requests = cls._prepare_join_delegation_requests(collator_list, stake_amount)
        cls._process_delegations_async(w3, contract, join_requests, eth_chain_id, wait_blocks=1)

        # Setup multi-delegations
        cls._force_new_round_for_multi_delegations(substrate)
        multi_requests = cls._prepare_multi_delegation_requests(collator_list, stake_amount)
        cls._process_delegations_async(w3, contract, multi_requests, eth_chain_id, wait_blocks=1)

        print('Main delegation setup complete')
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
        cls.assertTrue(receipt.is_success, f"Failed to fund test delegator: {receipt.error_message}")

        # Delegate to first collator (join) - use same minimum delegation as other delegators
        stake_amount = min_delegation * 3
        nonce = w3.eth.get_transaction_count(cls.test_delegator['kp'].ss58_address)
        tx = contract.functions.joinDelegators(collator_list[0][0], stake_amount).build_transaction({
            'from': cls.test_delegator['kp'].ss58_address,
            'nonce': nonce,
            'chainId': eth_chain_id
        })
        evm_receipt = sign_and_submit_evm_transaction(tx, w3, cls.test_delegator['kp'])
        assert evm_receipt['status'] == 1, 'Test delegator failed to join first collator'

        # Delegate to second collator (2 total delegations) with force new round
        for i in range(1, 2):
            # Force a new round to avoid DelegationsPerRoundExceeded error
            batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
            batch.compose_sudo_call('ParachainStaking', 'force_new_round', {})
            receipt = batch.execute()
            cls.assertTrue(receipt.is_success, "Failed to force new round for test delegator setup")

            # Use minimum delegation amount for all delegations to ensure they're valid
            stake_amount = min_delegation * 3
            nonce = w3.eth.get_transaction_count(cls.test_delegator['kp'].ss58_address)
            tx = contract.functions.delegateAnotherCandidate(collator_list[i][0], stake_amount).build_transaction({
                'from': cls.test_delegator['kp'].ss58_address,
                'nonce': nonce,
                'chainId': eth_chain_id
            })
            evm_receipt = sign_and_submit_evm_transaction(tx, w3, cls.test_delegator['kp'])
            assert evm_receipt['status'] == 1, f'Test delegator failed to delegate to collator {i}'

        return cls.test_delegator

    @classmethod
    def _setup_class_delegators(cls):
        """Setup 11 delegators with 2 collators once for all tests"""
        # Setup infrastructure
        substrate, w3, eth_chain_id, contract, min_delegation, collator_list = cls._setup_infrastructure()

        # Setup main delegators
        cls.delegator_keypairs = cls._setup_main_delegators(
            substrate, w3, contract, collator_list, min_delegation, eth_chain_id)

        # Setup test delegator
        cls.test_delegator = cls._setup_pagination_delegator(
            substrate, w3, contract, collator_list, min_delegation, eth_chain_id)

        # Store collator list
        cls.collator_list = collator_list

    @property
    def contract(self):
        """Get parachain staking contract instance (cached at class level)"""
        return self.__class__._contract

    def _get_delegator_address(self, kp_info):
        """Get ETH address for getDelegatorState calls (now accepts address type directly)"""
        if isinstance(kp_info, dict) and 'kp' in kp_info:
            # Return ETH address directly since getDelegatorState now accepts address type
            return kp_info['kp'].ss58_address  # ETH address (0x...)
        else:
            # Fallback for backward compatibility
            if hasattr(kp_info, 'ss58_address'):
                return kp_info.ss58_address
            else:
                raise ValueError(f"Unsupported kp_info format: {type(kp_info)}")

    def _initialize_connections_and_keypairs(self):
        """Initialize keypairs using cached connections"""
        # Use cached connections from class setup
        self._substrate = self.__class__._substrate
        self._w3 = self.__class__._w3
        self._eth_chain_id = self.__class__._eth_chain_id

        # Initialize keypairs (still needed per test instance)
        self._kp_moon = get_eth_info()
        self._kp_mars = get_eth_info()
        self._kp_venus = get_eth_info()
        self._kp_src = Keypair.create_from_uri('//Moon')
        self._kp_new_collator = Keypair.create_from_uri('//NewMoon01')
        self._chain_spec = get_modified_chain_spec(get_chain(self._substrate))

    def setUp(self):
        wait_until_block_height(self.__class__._substrate, 1)
        self._initialize_connections_and_keypairs()

    def _fund_users(self, num=100 * 10 ** 18):
        """Fund test users with PEAQ tokens"""
        # Always use the keypairs from setUp for consistency
        # These are already initialized in _initialize_connections_and_keypairs

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
        """Get sorted collator list from class setup"""
        # Always use the collator list from class setup for consistency
        return self.__class__.collator_list

    def _join_delegators(self, contract, eth_kp, collator_addr, stake):
        """Helper function to join as delegator"""
        nonce = self._w3.eth.get_transaction_count(eth_kp.ss58_address)
        tx = contract.functions.joinDelegators(collator_addr, stake).build_transaction({
            'from': eth_kp.ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id
        })
        return sign_and_submit_evm_transaction(tx, self._w3, eth_kp)

    def _get_substrate_delegator_state(self, delegator_addr):
        """Get delegator state from Substrate for comparison"""
        return self._substrate.query('ParachainStaking', 'DelegatorState', [delegator_addr])

    def _validate_known_delegator(self, delegator_state, expected_substrate_bytes):
        """Validate that a known test delegator has the exact expected state"""
        # Find which test delegator this is by comparing substrate bytes
        delegator_index = None
        for i, kp in enumerate(self.delegator_keypairs):
            # Convert the substrate address to bytes32 for comparison
            kp_substrate_bytes = bytes.fromhex(self._substrate.ss58_decode(kp['substrate']))
            if kp_substrate_bytes == expected_substrate_bytes:
                delegator_index = i
                break

        if delegator_index is not None:
            # We know EXACTLY what this delegator should have - validate based on delegator type
            self._validate_exact_delegator_state(delegator_state, delegator_index)

    def _validate_exact_delegator_state(self, delegator_state, delegator_index):
        """Validate exact delegator state based on whether it's a multi-delegator or single delegator"""
        is_multi = delegator_index in self.MULTI_DELEGATOR_INDICES

        # Multi-delegators have exactly 2 delegations, single delegators have exactly 1
        expected_delegation_count = 2 if is_multi else 1
        expected_total = self.SINGLE_DELEGATION_AMOUNT * expected_delegation_count

        self.assertEqual(len(delegator_state[1]), expected_delegation_count,
                         f"Delegator {delegator_index} should have exactly {expected_delegation_count} delegations")

        # Each delegation amount should be exactly SINGLE_DELEGATION_AMOUNT
        for j, delegation in enumerate(delegator_state[1]):
            self.assertEqual(delegation[1], self.SINGLE_DELEGATION_AMOUNT,
                             f"Delegation {j} should be exactly {self.SINGLE_DELEGATION_AMOUNT}")

        # Total should equal sum of delegations
        self.assertEqual(delegator_state[2], expected_total,
                         f"Delegator {delegator_index} total should be {expected_total}")

    def _assert_delegator_state_structure(self, delegator_state, expected_delegations, context=""):
        """Validate basic delegator state structure and totals"""
        self.assertEqual(len(delegator_state), 3,
                         f"{context}: Delegator state must have [address, delegations[], total]")
        self.assertEqual(len(delegator_state[1]), expected_delegations,
                         f"{context}: Expected {expected_delegations} delegations")
        delegation_sum = sum(delegation[1] for delegation in delegator_state[1])
        self.assertEqual(delegator_state[2], delegation_sum, f"{context}: Total must exactly equal sum of delegations")

    def _assert_substrate_consistency(self, evm_state, substrate_state, delegator_id):
        """Validate EVM and Substrate results match exactly"""
        self.assertEqual(
            evm_state[2], substrate_state.value['total'],
            f"Total delegation mismatch for {delegator_id}: "
            f"EVM={evm_state[2]}, Substrate={substrate_state.value['total']}")
        self.assertEqual(
            len(evm_state[1]), len(substrate_state.value['delegations']),
            f"Delegation count mismatch for {delegator_id}: "
            f"EVM={len(evm_state[1])}, Substrate={len(substrate_state.value['delegations'])}")

    def _assert_delegator_conversion(self, eth_address, expected_substrate_bytes, delegator_state):
        """Validate delegator address conversion is correct"""
        converted_substrate = self.contract.functions.convertEthToSubstrateAccount(eth_address).call()
        self.assertEqual(converted_substrate, expected_substrate_bytes,
                         f"ETH address {eth_address} should convert to expected substrate bytes")
        self.assertEqual(delegator_state[0], expected_substrate_bytes,
                         "Delegator state should contain correct substrate bytes")

    def _assert_pagination_results(self, page_results, expected_max_count, page_description):
        """Validate pagination results structure and limits"""
        self.assertLessEqual(len(page_results), expected_max_count,
                             f"{page_description} should return at most {expected_max_count} results")
        for delegator_state in page_results:
            self._assert_delegator_state_structure(delegator_state,
                                                   len(delegator_state[1]), f"{page_description} result")

    def _handle_transaction_exception(self, exception, operation_context):
        """Standardized exception handling for transaction operations"""
        error_msg = str(exception).lower()
        if "already known" in error_msg:
            print(f'{operation_context}: Transaction already known (likely succeeded)')
            return True  # Consider as success
        elif "timeout" in error_msg or "receipt not found" in error_msg:
            print(f'{operation_context}: Transaction timeout or not found: {exception}')
            return False  # Needs retry
        else:
            print(f'{operation_context}: Unexpected error: {exception}')
            raise exception  # Re-raise for investigation

    # ========== Basic Functionality Tests ==========

    def test_convert_eth_to_substrate_account(self):
        """Test convertEthToSubstrateAccount precompile function"""
        # Test conversion for our test delegators
        for i, kp in enumerate(self.delegator_keypairs[:3]):  # Test first 3 delegators
            eth_address = kp['kp'].ss58_address  # ETH address (0x...)
            expected_substrate = kp['substrate']  # Known substrate address from setup

            # Call precompile conversion
            converted_substrate = self.contract.functions.convertEthToSubstrateAccount(eth_address).call()

            # Convert expected substrate address to bytes32 for comparison
            expected_bytes = bytes.fromhex(self._substrate.ss58_decode(expected_substrate))

            # Verify conversion is correct
            self.assertEqual(
                converted_substrate, expected_bytes,
                f"Delegator {i}: ETH address {eth_address} should convert to "
                f"substrate {expected_substrate}")

            print(f"✓ Delegator {i}: {eth_address} → {converted_substrate.hex()}")

    @requires_collators(2)
    def test_get_delegator_state_with_direct_eth_address(self):
        """Test getDelegatorState can now accept ETH addresses directly"""

        # Test with our primary multi-delegator
        kp = self.delegator_keypairs[self.PRIMARY_MULTI_DELEGATOR_IDX]
        eth_address = kp['kp'].ss58_address  # ETH address directly

        # Call getDelegatorState with ETH address (no conversion needed!)
        delegator_states = self.contract.functions.getDelegatorState(eth_address, 0, 10).call()

        # Should return exactly one delegator state
        self.assertEqual(len(delegator_states), 1, "Should return exactly one delegator state")

        # Validate the multi-delegator has exactly 2 delegations
        delegator_state = delegator_states[0]
        self.assertEqual(len(delegator_state[1]), 2, "Multi-delegator should have exactly 2 delegations")
        self.assertEqual(delegator_state[2], self.SINGLE_DELEGATION_AMOUNT * 2,
                         "Multi-delegator total should be 2 * SINGLE_DELEGATION_AMOUNT")

        print(f"✓ Direct ETH address query: {eth_address} → {len(delegator_state[1])} delegations")

    def test_get_delegator_state_single_delegator_basic(self):
        """Test getDelegatorState for a single delegator with one delegation"""
        collator_list = self._get_collator_list()
        receipt = self._fund_users(collator_list[0][1] * 2)
        self.assertEqual(receipt.is_success, True,
                         "Failed to fund test users for single delegator test")

        # Join as delegator
        evm_receipt = self._join_delegators(self.contract, self._kp_moon['kp'],
                                            collator_list[0][0], collator_list[0][1])
        self.assertEqual(evm_receipt['status'], 1,
                         f"Moon delegator failed to join collator {collator_list[0][0]}")

        # Test getDelegatorState
        moon_delegator_address = self._get_delegator_address(self._kp_moon)

        # Get delegator state via EVM (use pagination parameters since 1-param version was removed)
        delegator_states = self.contract.functions.getDelegatorState(moon_delegator_address, 0, 10).call()

        # Verify results
        self.assertEqual(len(delegator_states), 1, "Should return exactly one delegator state")

        delegator_state = delegator_states[0]
        # delegator_state[0] is substrate bytes32, convert moon_delegator_address for comparison
        expected_substrate_bytes = self.contract.functions.convertEthToSubstrateAccount(moon_delegator_address).call()
        self.assertEqual(delegator_state[0], expected_substrate_bytes)  # delegator address
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
        # Use a random ETH address that has never delegated
        from web3 import Web3
        fake_delegator = Web3.to_checksum_address('0x' + '1234567890abcdef' * 2 + '12345678')  # Random ETH address

        # Get delegator state via EVM with pagination parameters
        delegator_states = self.contract.functions.getDelegatorState(fake_delegator, 0, 10).call()

        # Should return empty array
        self.assertEqual(len(delegator_states), 0, "Should return empty array for non-existent delegator")

    @requires_collators(2)
    def test_get_delegator_state_multiple_delegations(self):
        """Test getDelegatorState for delegator with multiple delegations"""

        mars_delegator_address = self._get_delegator_address(self.delegator_keypairs[self.PRIMARY_MULTI_DELEGATOR_IDX])

        # Get delegator state via EVM
        delegator_states = self.contract.functions.getDelegatorState(mars_delegator_address, 0, 10).call()

        # Verify results
        self.assertEqual(len(delegator_states), 1, "Should return exactly one delegator state")

        delegator_state = delegator_states[0]
        # delegator_state[0] is substrate bytes32, convert mars_delegator_address for comparison
        expected_substrate_bytes = self.contract.functions.convertEthToSubstrateAccount(mars_delegator_address).call()
        self.assertEqual(delegator_state[0], expected_substrate_bytes)
        self.assertEqual(len(delegator_state[1]), 2)  # Should have 2 delegations

        # Verify total matches sum of individual delegations
        delegation_sum = sum(delegation[1] for delegation in delegator_state[1])
        self.assertEqual(delegator_state[2], delegation_sum)

        # Compare with Substrate
        substrate_state = self._get_substrate_delegator_state(self.delegator_keypairs[1]['substrate'])
        self.assertEqual(delegator_state[2], substrate_state.value['total'])

    # ========== Comprehensive Query Tests ==========

    @requires_collators(2)
    def test_get_delegator_state_all_delegators(self):
        """Test getDelegatorState with zero address to get all delegators"""

        zero_address = '0x0000000000000000000000000000000000000000'  # All zeros ETH address for getting all delegators
        delegator_states = self.contract.functions.getDelegatorState(zero_address, 0, 20).call()

        # Should return at least our test delegators
        self.assertGreaterEqual(len(delegator_states), self.TOTAL_TEST_DELEGATORS,
                                f"Should return at least {self.TOTAL_TEST_DELEGATORS} delegators from our setup")

        # Track our specific delegators (convert to substrate bytes for comparison)
        our_delegator_substrate_bytes = {bytes.fromhex(
            self._substrate.ss58_decode(kp['substrate'])) for kp in self.delegator_keypairs}
        found_delegators = {}
        multi_delegator_count = 0

        for delegator_state in delegator_states:
            # Basic structure validation
            self.assertEqual(len(delegator_state), 3, "Delegator state should have [address, delegations[], total]")

            # Verify total EXACTLY equals sum (no rounding errors)
            delegation_sum = sum(delegation[1] for delegation in delegator_state[1])
            self.assertEqual(delegator_state[2], delegation_sum, "Total must exactly equal sum of delegations")

            # delegator_state[0] is now substrate bytes32 from the response
            substrate_bytes = delegator_state[0]

            # If this is one of our test delegators, validate EXACT expectations
            if substrate_bytes in our_delegator_substrate_bytes:
                self._validate_known_delegator(delegator_state, substrate_bytes)

                # Track what we found
                delegation_count = len(delegator_state[1])
                found_delegators[substrate_bytes] = delegation_count
                multi_delegator_count += (1 if delegation_count == 2 else 0)

        # Verify we found ALL our test delegators
        self.assertEqual(len(found_delegators), self.TOTAL_TEST_DELEGATORS,
                         f"Should find all {self.TOTAL_TEST_DELEGATORS} test delegators")

        # Verify EXACT multi-delegator count
        self.assertEqual(multi_delegator_count, len(self.MULTI_DELEGATOR_INDICES),
                         f"Should have exactly {len(self.MULTI_DELEGATOR_INDICES)} multi-delegators")

    # ========== Pagination Tests ==========

    @requires_collators(2)
    def test_get_delegator_state_with_pagination_basic(self):
        """Test getDelegatorState with pagination parameters - basic functionality"""

        zero_address = '0x0000000000000000000000000000000000000000'  # Get all delegators
        our_delegator_substrate_bytes = {bytes.fromhex(
            self._substrate.ss58_decode(kp['substrate'])) for kp in self.delegator_keypairs}

        # Get first delegator
        first_page = self.contract.functions.getDelegatorState(zero_address, 0, 1).call()
        self.assertEqual(len(first_page), 1, "First page with limit=1 should return exactly 1 delegator")

        # Validate first delegator structure
        first_delegator = first_page[0]
        self._assert_delegator_state_structure(first_delegator, len(first_delegator[1]), "First page delegator")

        # If it's one of our test delegators, validate exact expectations
        first_substrate_bytes = first_delegator[0]
        if first_substrate_bytes in our_delegator_substrate_bytes:
            self._validate_known_delegator(first_delegator, first_substrate_bytes)

        # Get next 2 delegators and validate pagination
        second_page = self.contract.functions.getDelegatorState(zero_address, 1, 2).call()
        self._assert_pagination_results(second_page, 2, "Second page")

        # Validate known delegators in second page
        for delegator_state in second_page:
            substrate_bytes = delegator_state[0]
            if substrate_bytes in our_delegator_substrate_bytes:
                self._validate_known_delegator(delegator_state, substrate_bytes)

        # Verify no duplicates between pages
        first_substrate_addr = first_page[0][0]
        second_substrate_addrs = [d[0] for d in second_page]
        self.assertNotIn(first_substrate_addr, second_substrate_addrs, "Pages should not have duplicate delegators")

    @requires_collators(2)
    def test_get_delegator_state_single_delegator_pagination(self):
        """Test getDelegatorState pagination for single delegator with multiple collators"""

        mars_delegator_address = self._get_delegator_address(self.delegator_keypairs[1])

        # Get first collator delegation only
        delegator_states = self.contract.functions.getDelegatorState(
            mars_delegator_address, 0, 1
        ).call()

        self.assertEqual(len(delegator_states), 1)
        self.assertEqual(len(delegator_states[0][1]), 1, "Should return only 1 delegation")

        # Get second collator delegation
        delegator_states_page2 = self.contract.functions.getDelegatorState(
            mars_delegator_address, 1, 1
        ).call()

        if len(delegator_states_page2) > 0:
            self.assertEqual(len(delegator_states_page2[0][1]), 1, "Should return only 1 delegation")

    def test_get_delegator_state_pagination_edge_cases(self):
        """Test getDelegatorState pagination edge cases and error conditions"""
        zero_address = '0x0000000000000000000000000000000000000000'

        # Test with limit = 0 (should fail)
        with self.assertRaises(Exception) as context:
            self.contract.functions.getDelegatorState(zero_address, 0, 0).call()
        self.assertIn("must be greater than 0", str(context.exception).lower())

        # Test with very large offset (should return empty)
        delegator_states = self.contract.functions.getDelegatorState(
            zero_address, 1000, 10
        ).call()
        self.assertEqual(len(delegator_states), 0, "Large offset should return empty results")

        # Test maximum limit (512)
        try:
            delegator_states = self.contract.functions.getDelegatorState(
                zero_address, 0, 512
            ).call()
            # Should not throw exception
            self.assertIsInstance(delegator_states, list)
        except Exception as e:
            self.fail(f"Maximum limit (512) should not fail: {e}")

        # Test exceeding maximum limit (should fail)
        with self.assertRaises(Exception) as context:
            self.contract.functions.getDelegatorState(zero_address, 0, 513).call()
        self.assertIn("maximum allowed is 512", str(context.exception).lower())

    # ========== Performance and Gas Tests ==========

    @requires_collators(2)
    def test_get_delegator_state_gas_consumption(self):
        """Test gas consumption for getDelegatorState calls"""

        # Test single delegator query gas
        mars_delegator_address = self._get_delegator_address(self.delegator_keypairs[1])

        gas_estimate_single = self.contract.functions.getDelegatorState(
            mars_delegator_address, 0, 10
        ).estimate_gas()

        print(f"Gas estimate for single delegator query: {gas_estimate_single}")
        self.assertLess(gas_estimate_single, 100000, "Single delegator query should be efficient")

        # Test all delegators query gas
        zero_address = '0x0000000000000000000000000000000000000000'
        gas_estimate_all = self.contract.functions.getDelegatorState(
            zero_address, 0, 10
        ).estimate_gas()

        print(f"Gas estimate for all delegators query (limit 10): {gas_estimate_all}")
        self.assertLess(gas_estimate_all, 500000, "All delegators query should be reasonable")

    # ========== Consistency and Integration Tests ==========

    @requires_collators(2)
    def test_get_delegator_state_consistency_with_substrate(self):
        """Test that EVM getDelegatorState results match Substrate queries"""

        # Test first 3 delegators
        for kp in self.delegator_keypairs[:3]:
            delegator_address = self._get_delegator_address(kp)

            # Get EVM result
            evm_states = self.contract.functions.getDelegatorState(delegator_address, 0, 10).call()

            # Get Substrate result
            substrate_state = self._get_substrate_delegator_state(kp['substrate'])

            # All our test delegators MUST exist in substrate storage (they were just set up)
            self.assertIsNotNone(substrate_state.value,
                                 f"Test delegator {kp['substrate']} not found in substrate storage - setup failed!")

            # Both EVM and Substrate should return the same delegator data
            self.assertEqual(len(evm_states), 1,
                             f"EVM should return exactly 1 delegator state for {kp['substrate']}")
            evm_state = evm_states[0]

            # Use helper to validate consistency
            self._assert_substrate_consistency(evm_state, substrate_state, kp['substrate'])

            # Compare individual delegation amounts - sort both for consistent comparison
            evm_delegations = sorted(evm_state[1], key=lambda x: x[1], reverse=True)
            substrate_delegations = sorted(substrate_state.value['delegations'],
                                           key=lambda x: x['amount'], reverse=True)

            for i, (evm_del, sub_del) in enumerate(zip(evm_delegations, substrate_delegations)):
                self.assertEqual(
                    evm_del[1], sub_del['amount'],
                    f"Delegation amount mismatch at index {i} for {kp['substrate']}: "
                    f"EVM={evm_del[1]}, Substrate={sub_del['amount']}")

    def test_get_delegator_state_after_operations(self):
        """Test getDelegatorState results after various staking operations"""
        collator_list = self._get_collator_list()
        receipt = self._fund_users(collator_list[0][1] * 4)
        self.assertTrue(receipt.is_success,
                        "Failed to fund test users for delegation operations test")

        # Initial delegation
        evm_receipt = self._join_delegators(self.contract, self._kp_moon['kp'],
                                            collator_list[0][0], collator_list[0][1])
        self.assertEqual(evm_receipt['status'], 1,
                         "Failed to create initial delegation for operations test")

        # Check initial state
        moon_address = self._get_delegator_address(self._kp_moon)
        states = self.contract.functions.getDelegatorState(moon_address, 0, 10).call()
        self.assertEqual(len(states), 1)
        self.assertEqual(states[0][2], collator_list[0][1])  # Initial amount

        # Increase stake
        nonce = self._w3.eth.get_transaction_count(self._kp_moon['kp'].ss58_address)
        tx = self.contract.functions.delegatorStakeMore(
            collator_list[0][0], collator_list[0][1] // 2
        ).build_transaction({
            'from': self._kp_moon['kp'].ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id
        })
        evm_receipt = sign_and_submit_evm_transaction(tx, self._w3, self._kp_moon['kp'])
        self.assertEqual(evm_receipt['status'], 1)

        # Check state after increase
        states = self.contract.functions.getDelegatorState(moon_address, 0, 10).call()
        expected_total = collator_list[0][1] + collator_list[0][1] // 2
        self.assertEqual(states[0][2], expected_total)

        # Decrease stake
        nonce = self._w3.eth.get_transaction_count(self._kp_moon['kp'].ss58_address)
        tx = self.contract.functions.delegatorStakeLess(
            collator_list[0][0], collator_list[0][1] // 4
        ).build_transaction({
            'from': self._kp_moon['kp'].ss58_address,
            'nonce': nonce,
            'chainId': self._eth_chain_id
        })
        evm_receipt = sign_and_submit_evm_transaction(tx, self._w3, self._kp_moon['kp'])
        self.assertEqual(evm_receipt['status'], 1)

        # Check state after decrease
        states = self.contract.functions.getDelegatorState(moon_address, 0, 10).call()
        expected_total = expected_total - collator_list[0][1] // 4
        self.assertEqual(states[0][2], expected_total)

    def test_get_delegator_state_large_delegation_set(self):
        """Test getDelegatorState with a delegator having multiple delegations"""
        # Use class-level test delegator (has 2 delegations to different collators)
        delegator_address = self._get_delegator_address(self.test_delegator)
        states = self.contract.functions.getDelegatorState(delegator_address, 0, 10).call()

        self.assertEqual(len(states), 1)
        delegator_state = states[0]
        # delegator_state[0] is substrate bytes32, convert delegator_address for comparison
        expected_substrate_bytes = self.contract.functions.convertEthToSubstrateAccount(delegator_address).call()
        self.assertEqual(delegator_state[0], expected_substrate_bytes)

        # Should have exactly 2 delegations (to 2 different collators)
        self.assertEqual(len(delegator_state[1]), 2)

        # Verify total equals sum of individual delegations
        delegation_sum = sum(delegation[1] for delegation in delegator_state[1])
        self.assertEqual(delegator_state[2], delegation_sum)

        # Test pagination within this delegator's delegations
        # We know this delegator has exactly 2 delegations from class setup
        self.assertEqual(len(delegator_state[1]), 2, "Expected exactly 2 delegations from class setup")

        # Get first delegation only (limit=1)
        states_paged = self.contract.functions.getDelegatorState(delegator_address, 0, 1).call()
        self.assertEqual(len(states_paged), 1)
        print(f"Requested limit=1, got {len(states_paged[0][1])} delegations")
        print(f"Full delegations: {len(delegator_state[1])}")
        self.assertEqual(len(states_paged[0][1]), 1)  # Should return only 1 delegation
        self.assertEqual(states_paged[0][2], delegator_state[2])  # Total should remain the same

        # Get second delegation (offset=1, limit=1)
        states_remaining = self.contract.functions.getDelegatorState(delegator_address, 1, 1).call()
        self.assertEqual(len(states_remaining), 1)
        self.assertEqual(len(states_remaining[0][1]), 1)  # Should return exactly 1 remaining delegation

        # Compare with Substrate state for consistency
        substrate_state = self._get_substrate_delegator_state(self.test_delegator['substrate'])
        self.assertEqual(delegator_state[2], substrate_state.value['total'])
        self.assertEqual(len(delegator_state[1]), len(substrate_state.value['delegations']))
