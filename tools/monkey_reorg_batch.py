from peaq.utils import ExtrinsicBatch
from substrateinterface.exceptions import SubstrateRequestException
import time
from peaq.utils import show_extrinsic


origin_execute_extrinsic_batch = ExtrinsicBatch._execute_extrinsic_batch


# Try to fix the reorg issue by retrying the batch
def monkey_execute_extrinsic_batch(self, substrate, kp_src, batch,
                                   wait_for_finalization=False) -> str:
    for i in range(3):
        try:
            print(f'{substrate.url}, {batch}')
            receipt = origin_execute_extrinsic_batch(self, substrate, kp_src, batch, wait_for_finalization)
            show_extrinsic(receipt, f'{substrate.url}')
            return receipt
        except SubstrateRequestException as e:
            if 'invalid' in str(e) or 'retracted' in str(e):
                print(f'Error: {e}, {batch}')
                print('Wait for 12 seconds')
                time.sleep(12)
                if i < 2:
                    continue
            else:
                raise e
        except Exception as e:
            raise e
