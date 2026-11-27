"""
Offline tests (no node) for tools/node_2603_checks.py, including the red checks of AC-39, AC-41 and AC-74 from
the spec: each check passes on a good recording and fails on the same recording with the one change the check
exists to catch (a lower tip, an inserted Dropped, a pending nonce one lower).
"""
import unittest

from tools.node_2603_checks import (
    aura_author, check_new_key_authored, check_no_drops, check_packed, check_pending_nonces,
    check_rejected_for_proof, check_replaced, extrinsic_hash, forks_in_window)

B1, B2 = '0x' + '11' * 32, '0x' + '22' * 32
SECOND = '0x' + 'ab' * 32


class TestNode2603Checks(unittest.TestCase):
    def test_extrinsic_hash(self):
        # blake2-256 of the empty input, from RFC 7693's reference implementation
        self.assertEqual(extrinsic_hash('0x'),
                         '0x0e5751c026e543b2e8ab2eb06099daa1d1e5df47778f7787faab45cdf12fe3a8')

    def test_replaced(self):
        first = [(0, 'ready'), (1, {'usurped': SECOND})]
        second = [(1, 'ready'), (6, {'inBlock': B1}), (30, {'finalized': B1})]
        check_replaced(first, second, SECOND, [SECOND])
        check_replaced([(0, 'ready'), (1, 'dropped')], second, SECOND, [SECOND])
        # red check: the second one's tip lower, so the first one stays and goes into the block
        lower_tip = [(0, 'ready'), (6, {'inBlock': B1}), (30, {'finalized': B1})]
        for name, args in [('lower tip', (lower_tip, [], SECOND, [])),
                           ('not in the body', (first, second, SECOND, ['0x' + 'cd' * 32])),
                           ('second never in a block', (first, [(1, 'ready')], SECOND, [SECOND]))]:
            with self.subTest(name), self.assertRaises(AssertionError):
                check_replaced(*args)

    def test_packed(self):
        check_packed([5, 5, 6, 14], 4, 10)
        # 'late': in 10 consecutive blocks, but they started 100 blocks after sending
        for name, blocks in [('11 blocks', [5, 15]), ('one missing', [5, None]), ('late', [104, 105])]:
            with self.subTest(name), self.assertRaises(AssertionError):
                check_packed(blocks, 4, 10)

    def test_pending_nonces(self):
        recorded = [8, 9, 10, 11]
        check_pending_nonces(7, recorded)
        # red check: one of the recorded values one lower
        with self.assertRaises(AssertionError):
            check_pending_nonces(7, [8, 9, 9, 11])

    def test_forks_in_window(self):
        heads = [(1, 5, 'a'), (2, 6, 'b'), (3, 6, 'b'), (4, 6, 'c'), (9, 7, 'd'), (10, 7, 'e')]
        self.assertEqual(forks_in_window(heads, 0, 20), [6, 7])
        # the fork at height 6 had ended (second header at 4 s) before the window starts at 5 s
        self.assertEqual(forks_in_window(heads, 5, 20), [7])
        self.assertEqual(forks_in_window(heads, 5, 8), [])

    def test_no_drops(self):
        h1, h2 = '0x01', '0x02'
        recordings = {
            h1: [(0, 'ready'), (6, {'inBlock': B1}), (9, {'retracted': B1}), (12, {'inBlock': B2}),
                 (40, {'finalized': B2})],
            h2: [(1, 'ready'), (12, {'inBlock': B2}), (40, {'finalized': B2})],
        }
        sent = {h1: 0, h2: 1}
        samples = [(4, {h1, h2}), (11.5, {h1, h2}), (20, set())]
        check_no_drops(recordings, sent, samples)
        # 1 s after Retracted is inside the 2 s grace, so h1 may be missing from that sample
        check_no_drops(recordings, sent, [(10, {h2})])
        dropped = dict(recordings)
        dropped[h2] = [(1, 'ready'), (8, 'dropped'), (40, {'finalized': B2})]
        for name, args in [
                # red check: a Dropped inserted into the recording
                ('dropped', (dropped, sent, samples)),
                ('not finalized in time', (recordings, sent, samples, 30)),
                ('ready but not pending', (recordings, sent, [(4, {h1})])),
                ('retracted but not pending', (recordings, sent, [(11.5, {h2})]))]:
            with self.subTest(name), self.assertRaises(AssertionError):
                check_no_drops(*args)

    def test_rejected_for_proof(self):
        check_rejected_for_proof(False, {'type': 'Module', 'name': 'InvalidProof', 'docs': ['Invalid ownership proof.']})
        # red check from the spec: the "rejected" assertion on the call with the right proof
        for name, args in [('accepted', (True, None)),
                           ('other error', (False, {'type': 'Module', 'name': 'NoAssociatedValidatorId'}))]:
            with self.subTest(name), self.assertRaises(AssertionError):
                check_rejected_for_proof(*args)

    def test_aura_author(self):
        # PreRuntime "aura" with slot 5 (little-endian u64), and a Seal item that must be skipped
        pre = '0x06' + b'aura'.hex() + '20' + (5).to_bytes(8, 'little').hex()
        seal = '0x05' + b'aura'.hex() + '0101' + '00' * 64
        self.assertEqual(aura_author([seal, pre], ['a', 'b']), 'b')
        self.assertEqual(aura_author([pre], ['a', 'b', 'c']), 'c')
        with self.assertRaises(AssertionError):
            aura_author([seal], ['a'])

    def test_new_key_authored(self):
        check_new_key_authored('new', [(30, 'old'), (31, 'new')])
        for name, authored in [('never an authority', []), ('only the other collator', [(30, 'eve'), (31, 'eve')])]:
            with self.subTest(name), self.assertRaises(AssertionError):
                check_new_key_authored('new', authored)
