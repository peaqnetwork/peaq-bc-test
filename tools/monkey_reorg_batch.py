from peaq.utils import ExtrinsicBatch
from substrateinterface.exceptions import SubstrateRequestException
import time


origin_execute_extrinsic_batch = ExtrinsicBatch._execute_extrinsic_batch


# Try to fix the reorg issue by retrying the batch
def monkey_execute_extrinsic_batch(self, substrate, kp_src, batch,
                                   wait_for_finalization=False) -> str:
    for i in range(3):
        try:
            out = origin_execute_extrinsic_batch(self, substrate, kp_src, batch, wait_for_finalization)
            if out is None:
                import pdb
                pdb.set_trace()
            return out
        except SubstrateRequestException as e:
            if 'invalid' in str(e) or 'retracted' in str(e):
                print(f'Error: {e}, {batch}')
                print('Wait for 12 seconds')
                time.sleep(12)
                continue
        except Exception as e:
            raise e
