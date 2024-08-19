from substrateinterface.exceptions import SubstrateRequestException, ExtrinsicNotFound
from scalecodec.types import GenericExtrinsic
from substrateinterface.base import ExtrinsicReceipt
import time


def _wait_finalization(substrate, included_block):
    while True:
        finalized_block = substrate.get_block_number(substrate.get_chain_finalised_head())
        print(f'Checking finalized block {finalized_block} and included block {included_block}')
        if finalized_block >= included_block:
            break
        time.sleep(6)


def monkey_submit_extrinsic(self, extrinsic: GenericExtrinsic, wait_for_inclusion: bool = False,
                            wait_for_finalization: bool = False) -> "ExtrinsicReceipt":
    response = self.rpc_request("author_submitExtrinsic", [str(extrinsic.data)])

    if 'result' not in response:
        raise SubstrateRequestException(response.get('error'))

    result = ExtrinsicReceipt(
        substrate=self,
        extrinsic_hash=response['result']
    )
    if not wait_for_inclusion and not wait_for_finalization:
        return result

    time.sleep(18)
    now_block_num = self.get_block_number(None)
    included_block = None
    tx_identifier = None
    for i in range(5):
        print(f'Checking block {now_block_num - i}')
        block_hash = self.get_block_hash(now_block_num - i)
        block = self.get_block(block_hash)
        for extrinsic in block['extrinsics']:
            if f'0x{extrinsic.extrinsic_hash.hex()}' == result.extrinsic_hash:
                index = block['extrinsics'].index(extrinsic)
                included_block = now_block_num - i
                print(f'Extrinsic {result.extrinsic_hash} is included in block {included_block}')
                tx_identifier = f'{included_block}-{index}'
                break
        if tx_identifier:
            break
    if not tx_identifier:
        raise SubstrateRequestException(
            f'Extrinsic {result.extrinsic_hash} is not included in the block after 3 blocks, invalid')

    _wait_finalization(self, included_block)

    print(f'Extrinsic {result.extrinsic_hash} is finalized in block {included_block}')
    print(f'tx_identifier: {tx_identifier}')
    out = ExtrinsicReceipt.create_from_extrinsic_identifier(
        self,
        tx_identifier
    )
    try:
        out.retrieve_extrinsic()
        return out
    except ExtrinsicNotFound:
        print(f'Extrinsic {result.extrinsic_hash} is not found in the block {included_block}')
        # The extrinsic disappears, might due to reorg, the upper level should retry
        raise SubstrateRequestException(
            f'Extrinsic {tx_identifier} is not found in the block {included_block}, should retry because of  invalid')
