import time
from peaq.utils import get_block_height
from tools.constants import DEFAULT_BLOCK_TIME, POLL_INTERVAL


def wait_for_n_blocks_with_timeout(substrate, n=1, timeout=None):
    """Waits until the next block has been created with timeout support"""
    if timeout is None:
        timeout = n * DEFAULT_BLOCK_TIME

    start_time = time.time()
    height = get_block_height(substrate)
    wait_height = height + n
    blocks_processed = 0

    while blocks_processed < n:
        # Check timeout
        elapsed = time.time() - start_time
        if elapsed > timeout:
            raise TimeoutError(f"Timeout waiting for blocks. Waited {elapsed:.1f}s for {n} blocks. "
                               f"Got {blocks_processed}/{n} blocks. Current height: {height}, target: {wait_height}")

        next_height = get_block_height(substrate)
        if height == next_height:
            time.sleep(POLL_INTERVAL)
        else:
            print(f'Current block: {height}, but waiting at {wait_height}')
            height = next_height
            blocks_processed = blocks_processed + 1


def monkey_patch_wait_for_blocks():
    """Apply monkey patch to replace wait_for_n_blocks with timeout version"""
    import peaq.utils

    # Store original function for potential restoration
    if not hasattr(peaq.utils, '_original_wait_for_n_blocks'):
        peaq.utils._original_wait_for_n_blocks = peaq.utils.wait_for_n_blocks

    # Replace with timeout version
    peaq.utils.wait_for_n_blocks = wait_for_n_blocks_with_timeout
    print("Monkey patched wait_for_n_blocks with timeout support")


def restore_original_wait_for_blocks():
    """Restore original wait_for_n_blocks function"""
    import peaq.utils

    if hasattr(peaq.utils, '_original_wait_for_n_blocks'):
        peaq.utils.wait_for_n_blocks = peaq.utils._original_wait_for_n_blocks
        delattr(peaq.utils, '_original_wait_for_n_blocks')
        print("Restored original wait_for_n_blocks function")
