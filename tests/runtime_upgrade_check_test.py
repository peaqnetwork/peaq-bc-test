# Offline tests of the checks in tools/runtime_upgrade.upgrade(): fake parachain and relay RPCs, no
# network. They make an upgrade that was sent but did not take effect, and check that the log
# names the reason, (a) or (b), with the best and finalized heights of both chains.
import itertools
import unittest
from unittest import mock

from substrateinterface.utils.hasher import blake2_256

import tools.runtime_upgrade as runtime_upgrade

UPGRADE_TX = '0x' + 'ab' * 32
THIS_CODE = b'\x00asm this wasm'
OTHER_CODE = b'\x00asm an older pending upgrade'


def canonical_hash(number):
    return f'0x{number:064x}'


class FakeChain:
    """
    A chain #0..#best on one fork. `tx_at` is the block that holds the upgrade tx, `pending` maps a
    block number to the code PendingValidationCode holds there, `extra_blocks` are fork blocks
    (hash -> number) that are not on this chain.
    """
    def __init__(self, best, finalized, tx_at=None, pending=None, extra_blocks=None):
        self.best, self.finalized = best, finalized
        self.tx_at = tx_at
        self.pending = pending or {}
        self.numbers = {canonical_hash(n): n for n in range(best + 1)}
        self.numbers.update(extra_blocks or {})

    def get_chain_head(self):
        return canonical_hash(self.best)

    def get_chain_finalised_head(self):
        return canonical_hash(self.finalized)

    def get_block_hash(self, block_id=None):
        return canonical_hash(self.best if block_id is None else block_id)

    def get_block_number(self, block_hash):
        # None, like the node, for a block whose header it does not have.
        return self.numbers.get(block_hash)

    def get_block(self, block_hash):
        held = [UPGRADE_TX] if self.numbers[block_hash] == self.tx_at else []
        return {'extrinsics': [mock.Mock(extrinsic_hash=bytes.fromhex(h[2:])) for h in held + ['0x' + '00' * 32]]}

    def query(self, module, storage_function, params=None, block_hash=None):
        assert (module, storage_function) == ('ParachainSystem', 'PendingValidationCode')
        code = self.pending.get(self.numbers[block_hash])
        # scalecodec decodes an empty Vec<u8> as ''.
        return mock.Mock(value=f'0x{code.hex()}' if code else '')


def pending_from(first, last, code=THIS_CODE):
    return {n: code for n in range(first, last + 1)}


class TestUpgradeChecks(unittest.TestCase):
    def run_upgrade(self, para, block_hash):
        relay = FakeChain(best=40, finalized=38)
        receipt = mock.Mock(is_success=True, block_hash=block_hash, extrinsic_hash=UPGRADE_TX)
        # Each time.time() call moves the clock on by a minute, so a wait that never ends times out.
        fake_time = mock.Mock(time=mock.Mock(side_effect=itertools.count(0, 60)))
        with mock.patch.object(runtime_upgrade, 'SubstrateInterface',
                               side_effect=lambda url, **kw: relay if url == runtime_upgrade.RELAYCHAIN_WS_URL else para), \
                mock.patch.object(runtime_upgrade, 'send_upgrade_call', return_value=receipt), \
                mock.patch.object(runtime_upgrade, 'wasm_code_hash', create=True,
                                  return_value=f'0x{blake2_256(THIS_CODE).hex()}'), \
                mock.patch.object(runtime_upgrade, 'show_extrinsic'), \
                mock.patch.object(runtime_upgrade, 'wait_for_n_blocks'), \
                mock.patch.object(runtime_upgrade, 'wait_relay_upgrade_block'), \
                mock.patch.object(runtime_upgrade, 'time', fake_time), \
                mock.patch('builtins.print') as fake_print:
            error = None
            try:
                runtime_upgrade.upgrade('runtime.wasm')
            except IOError as e:
                error = e
        log = '\n'.join(' '.join(str(a) for a in c.args) for c in fake_print.call_args_list)
        return error, log

    def assert_reported(self, error, log, reason, para_heights='parachain best #20 finalized #18'):
        self.assertIn(reason, log, f'the log does not name {reason}:\n{log}')
        self.assertIsNotNone(error, f'upgrade() did not fail:\n{log}')
        self.assertIn(reason, str(error))
        for heights in (para_heights, 'relay best #40 finalized #38'):
            self.assertIn(heights, log)

    def test_upgrade_tx_in_no_finalized_block_is_reported_as_a(self):
        # The tx went into a fork block at #5 that lost, and no finalized block holds it.
        para = FakeChain(best=20, finalized=18, pending=pending_from(5, 20), extra_blocks={'0xfork5': 5})
        error, log = self.run_upgrade(para, '0xfork5')
        self.assert_reported(error, log, '(a)')

    def test_upgrade_tx_moved_to_another_finalized_block_passes(self):
        # The fork block at #5 lost, the pool sent the tx again, and it landed in finalized #7.
        para = FakeChain(best=20, finalized=18, tx_at=7, pending=pending_from(7, 20), extra_blocks={'0xfork5': 5})
        error, log = self.run_upgrade(para, '0xfork5')
        self.assertIsNone(error, log)
        self.assertIn('finalized block #7', log)

    def test_upgrade_block_without_a_header_is_reported_as_a(self):
        # The node has no header for the receipt's block, so its number is unknown.
        para = FakeChain(best=20, finalized=20, pending=pending_from(5, 20))
        error, log = self.run_upgrade(para, '0xunknown')
        self.assert_reported(error, log, '(a)', para_heights='parachain best #20 finalized #20')

    def test_upgrade_block_never_finalized_is_reported_as_a(self):
        para = FakeChain(best=20, finalized=3, tx_at=5, pending=pending_from(5, 20))
        error, log = self.run_upgrade(para, canonical_hash(5))
        self.assert_reported(error, log, '(a)', para_heights='parachain best #20 finalized #3')
        self.assertIn('did not finalize', log)

    def test_pending_validation_code_never_set_is_reported_as_b(self):
        para = FakeChain(best=20, finalized=18, tx_at=5)
        error, log = self.run_upgrade(para, canonical_hash(5))
        self.assert_reported(error, log, '(b)')

    def test_another_pending_code_is_reported_as_b(self):
        # An earlier upgrade is still pending, so applying this one failed inside sudo.
        para = FakeChain(best=20, finalized=18, tx_at=5, pending=pending_from(0, 20, OTHER_CODE))
        error, log = self.run_upgrade(para, canonical_hash(5))
        self.assert_reported(error, log, '(b)')
        self.assertIn('another code', log)

    def test_an_upgrade_that_landed_passes(self):
        para = FakeChain(best=20, finalized=18, tx_at=5, pending=pending_from(5, 7))
        error, log = self.run_upgrade(para, canonical_hash(5))
        self.assertIsNone(error, log)
        self.assertNotIn('Upgrade check failed', log)
