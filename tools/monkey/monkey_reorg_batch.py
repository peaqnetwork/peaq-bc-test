from peaq.utils import ExtrinsicBatch
from substrateinterface.exceptions import SubstrateRequestException
import time
from peaq.utils import show_extrinsic
from tools.constants import BLOCK_GENERATE_TIME

BACKTRACE_BLOCK_NUM = 10

origin_execute_extrinsic_batch = ExtrinsicBatch._execute_extrinsic_batch


def _backtrace_blocks_by_extrinsic(substrate, extrinsic_hash):
    now_block_num = substrate.get_block_number(None)
    for i in range(BACKTRACE_BLOCK_NUM):
        block_hash = substrate.get_block_hash(now_block_num - i)
        extrinsics = substrate.get_block(block_hash)['extrinsics']
        for tx in extrinsics:
            if tx.extrinsic_hash.hex() == extrinsic_hash:
                print(f'{tx.extrinsic_hash.hex()} found at block: {block_hash}')
                return block_hash
    print(f'Extrinsic {extrinsic_hash} not found in the last {BACKTRACE_BLOCK_NUM} blocks')
    return None


# Try to fix the reorg issue by retrying the batch
def monkey_execute_extrinsic_batch(self, substrate, kp_src, batch,
                                   wait_for_finalization=False,
                                   tip=0) -> str:
    RETRY_TIMES = 3
    for i in range(RETRY_TIMES):
        try:
            print(f'{substrate.url}, {batch}')
            receipt = origin_execute_extrinsic_batch(self, substrate, kp_src, batch, wait_for_finalization, tip)
            show_extrinsic(receipt, f'{substrate.url}')
            return receipt
        except SubstrateRequestException as e:
            if 'invalid' in str(e):
                print(f'Error: {e}, {batch}')
                print('Wait for 30 seconds')
                time.sleep(BLOCK_GENERATE_TIME * 5)
                block_hash = _backtrace_blocks_by_extrinsic(
                    substrate, self.submit_extrinsic.extrinsic_hash.hex())
                if block_hash:
                    print(f'Found the extrinsic in block: {block_hash}')
                    out = substrate.retrieve_extrinsic_by_hash(
                        block_hash, f'0x{self.submit_extrinsic.extrinsic_hash.hex()}')
                    out.retrieve_extrinsic()
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
