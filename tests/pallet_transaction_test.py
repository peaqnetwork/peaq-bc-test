import pytest
import unittest
from substrateinterface import SubstrateInterface, Keypair
from tools.constants import WS_URL
from peaq.utils import ExtrinsicBatch


def get_service_request_call(substrate, kp_dst, token_num):
    return substrate.compose_call(
        call_module='Transaction',
        call_function='service_requested',
        call_params={
            'provider': kp_dst.ss58_address,
            'token_deposited': token_num
        })


def service_request(substrate, kp_src, kp_dst, token_num):
    batch = ExtrinsicBatch(substrate, kp_src)
    batch.compose_call(
        'Transaction',
        'service_requested',
        {
            'provider': kp_dst.ss58_address,
            'token_deposited': token_num
        }
    )
    return batch.execute()


def service_deliver(substrate, kp_src, kp_dst, receipt, call):
    # Do the request service
    info = receipt.get_extrinsic_identifier().split('-')
    timepoint = {'height': int(info[0]), 'index': int(info[1])}

    batch = ExtrinsicBatch(substrate, kp_src)
    batch.compose_call(
        'Transaction',
        'service_delivered',
        {
            'consumer': kp_dst.ss58_address,
            'refund_info': {
                'token_num': 10,
                'tx_hash': receipt.extrinsic_hash,
                'time_point': timepoint,
                'call_hash': f'0x{call.call_hash.hex()}',
            },
            'spent_info': {
                'token_num': 20,
                'tx_hash': receipt.extrinsic_hash,
                'time_point': timepoint,
                'call_hash': f'0x{call.call_hash.hex()}',
            }
        }
    )
    return batch.execute()


@pytest.mark.substrate
class TestPalletTransaction(unittest.TestCase):
    def setUp(self):
        self.substrate = SubstrateInterface(url=WS_URL)
        self.kp_src = Keypair.create_from_uri('//Alice')
        self.kp_dst = Keypair.create_from_uri('//Bob//stash')

    def test_transaction(self):
        # fund(substrate, kp_src, 500)
        # transfer(substrate, kp_src, kp_dst.ss58_address, 50)
        receipt = service_request(self.substrate, self.kp_src, self.kp_dst, 50)
        self.assertTrue(receipt.is_success,
                        f'service_request failed: {receipt.error_message} + ' +
                        f'{self.substrate.get_events(receipt.block_hash)}')

        call = get_service_request_call(self.substrate, self.kp_dst, 50)

        receipt = service_deliver(self.substrate, self.kp_src, self.kp_dst, receipt, call)
        self.assertTrue(receipt.is_success,
                        f'service_delivered failed: {receipt.error_message} + ' +
                        f'{self.substrate.get_events(receipt.block_hash)}')
