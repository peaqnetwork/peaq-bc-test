# Offline tests of the checks in tools/runtime_upgrade.upgrade(): fake parachain and relay RPCs, no
# network. They make an upgrade that was sent but did not take effect, and check that the log
# names the reason, (a) or (b), with the best and finalized heights of both chains.
import unittest
from unittest import mock

import tools.runtime_upgrade as runtime_upgrade


def canonical_hash(number):
    return f'0x{number:064x}'


class FakeChain:
    def __init__(self, best, finalized, pending_at=(), extra_blocks=None):
        self.best, self.finalized = best, finalized
        self.pending_at = set(pending_at)
        self.numbers = {canonical_hash(n): n for n in range(best + 1)}
        self.numbers.update(extra_blocks or {})

    def get_chain_head(self):
        return canonical_hash(self.best)

    def get_chain_finalised_head(self):
        return canonical_hash(self.finalized)

    def get_block_hash(self, block_id=None):
        return canonical_hash(self.best if block_id is None else block_id)

    def get_block_number(self, block_hash):
        return self.numbers[block_hash]

    def query(self, module, storage_function, params=None, block_hash=None):
        assert (module, storage_function) == ('ParachainSystem', 'PendingValidationCode')
        return mock.Mock(value='0x0061736d' if self.numbers[block_hash] in self.pending_at else '0x')


class TestUpgradeChecks(unittest.TestCase):
    def run_upgrade(self, para, block_hash):
        relay = FakeChain(best=40, finalized=38)
        receipt = mock.Mock(is_success=True, block_hash=block_hash)
        with mock.patch.object(runtime_upgrade, 'SubstrateInterface',
                               side_effect=lambda url, **kw: relay if url == runtime_upgrade.RELAYCHAIN_WS_URL else para), \
                mock.patch.object(runtime_upgrade, 'send_upgrade_call', return_value=receipt), \
                mock.patch.object(runtime_upgrade, 'show_extrinsic'), \
                mock.patch.object(runtime_upgrade, 'wait_for_n_blocks'), \
                mock.patch.object(runtime_upgrade, 'wait_relay_upgrade_block'), \
                mock.patch.object(runtime_upgrade.time, 'sleep'), \
                mock.patch('builtins.print') as fake_print:
            error = None
            try:
                runtime_upgrade.upgrade('runtime.wasm')
            except IOError as e:
                error = e
        log = '\n'.join(' '.join(str(a) for a in c.args) for c in fake_print.call_args_list)
        return error, log

    def assert_reported(self, error, log, reason):
        self.assertIn(reason, log, f'the log does not name {reason}:\n{log}')
        self.assertIsNotNone(error, f'upgrade() did not fail:\n{log}')
        self.assertIn(reason, str(error))
        for heights in ('parachain best #20 finalized #18', 'relay best #40 finalized #38'):
            self.assertIn(heights, log)

    def test_upgrade_block_off_the_finalized_chain_is_reported_as_a(self):
        # The upgrade went into a fork block at #5 that lost: #5 on the finalized chain is another block.
        para = FakeChain(best=20, finalized=18, pending_at=range(20), extra_blocks={'0xfork5': 5})
        error, log = self.run_upgrade(para, '0xfork5')
        self.assert_reported(error, log, '(a)')

    def test_pending_validation_code_never_set_is_reported_as_b(self):
        para = FakeChain(best=20, finalized=18)
        error, log = self.run_upgrade(para, canonical_hash(5))
        self.assert_reported(error, log, '(b)')

    def test_an_upgrade_that_landed_passes(self):
        para = FakeChain(best=20, finalized=18, pending_at=[5, 6, 7])
        error, log = self.run_upgrade(para, canonical_hash(5))
        self.assertIsNone(error, log)
        self.assertNotIn('Upgrade check failed', log)
