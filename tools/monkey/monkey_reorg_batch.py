from peaq.utils import ExtrinsicBatch
from substrateinterface.exceptions import SubstrateRequestException
from peaq.utils import show_extrinsic
from peaq.utils import wait_for_n_blocks
from substrateinterface.base import ExtrinsicReceipt


BACKTRACE_BLOCK_NUM = 10
RETRY_TIMES = 3

origin_execute_extrinsic_batch = ExtrinsicBatch._execute_extrinsic_batch


def _backtrace_blocks_by_extrinsic(substrate, extrinsic_hash):
    now_block_num = substrate.get_block_number(None)
    for i in range(BACKTRACE_BLOCK_NUM):
        block_hash = substrate.get_block_hash(now_block_num - i)
        extrinsics = substrate.get_block(block_hash)['extrinsics']
        for tx in extrinsics:
            if tx.extrinsic_hash.hex() == extrinsic_hash:
                print(f'{tx.extrinsic_hash.hex()} found at block: {block_hash}')
                return f'{now_block_num - i}-{extrinsics.index(tx)}'
    print(f'Extrinsic {extrinsic_hash} not found in the last {BACKTRACE_BLOCK_NUM} blocks')
    return None


def short_print(batch):
    if len(str(batch)) > 512:
        return f'{str(batch)[:512]}...'
    else:
        return f'{batch}'


# Try to fix the reorg issue by retrying the batch
def monkey_execute_extrinsic_batch(self, substrate, kp_src, batch,
                                   wait_for_finalization=False,
                                   tip=0) -> str:

    for i in range(RETRY_TIMES):
        try:
            print(f'{substrate.url}, {short_print(batch)}')
            receipt = origin_execute_extrinsic_batch(self, substrate, kp_src, batch, wait_for_finalization, tip)
            show_extrinsic(receipt, f'{substrate.url}')
            return receipt
        except SubstrateRequestException as e:
            if 'invalid' in str(e):
                print(f'Error: {e}, {short_print(batch)}')
                for j in range(4):
                    print('Wait for next 4 block')
                    wait_for_n_blocks(substrate, 4)
                    tx_identifer = _backtrace_blocks_by_extrinsic(
                        substrate, self.submit_extrinsic.extrinsic_hash.hex())
                    if tx_identifer:
                        # Update the Tx receipt
                        print(f'Found the extrinsic: {tx_identifer}')
                        out = ExtrinsicReceipt.create_from_extrinsic_identifier(
                            substrate,
                            tx_identifer
                        )
                        out.retrieve_extrinsic()
                        out.extrinsic_hash = self.submit_extrinsic.extrinsic_hash.hex()
                        return out
                # Maybe the extrinsic is still in the pool
                print(f'Error: {e}, {batch}')
                print(f'Retry {i + 1} times')
                if i == RETRY_TIMES - 1:
                    print(f'Retry {RETRY_TIMES} times, still failed')
                    raise e
            else:
                raise e
        except Exception as e:
            raise e
