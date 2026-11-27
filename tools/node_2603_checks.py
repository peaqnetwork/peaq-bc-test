"""
The checks tests/node_2603_test.py makes on what it recorded from the node (watch statuses, block bodies,
pending nonces, heads), kept apart so that tests/node_2603_check_test.py can run them offline, including
the red checks: each check must fail on the recording it exists to catch.

A watch status is what author_submitAndWatchExtrinsic sends: a string ("ready", "future", "dropped",
"invalid") or a one-key object ({"inBlock": hash}, {"finalized": hash}, {"usurped": hash},
{"retracted": hash}, {"broadcast": [...]}, {"finalityTimeout": hash}). A recording is a list of
(seconds, status) in the order the node sent them.
"""
import hashlib

BAD = {'dropped', 'invalid', 'usurped'}
SETTLED = {'inBlock', 'finalized'}


def status_name(status):
    return status if isinstance(status, str) else next(iter(status))


def names(recording):
    return [status_name(s) for _, s in recording]


def extrinsic_hash(hex_extrinsic):
    """The hash the node uses for a Substrate extrinsic: blake2-256 of its bytes."""
    return '0x' + hashlib.blake2b(bytes.fromhex(hex_extrinsic.removeprefix('0x')), digest_size=32).hexdigest()


def check_replaced(first, second, second_hash, body_hashes):
    """AC-39 (a): the first transaction is pushed out (Usurped or Dropped) and never in a block; the second,
    same sender and nonce with a higher tip, is InBlock and the block's body really holds it."""
    first_names, second_names = names(first), names(second)
    assert first_names and first_names[-1] in ('usurped', 'dropped'), f'the first one ended as {first_names}'
    assert 'inBlock' not in first_names, f'the first one went into a block: {first_names}'
    assert 'inBlock' in second_names, f'the second one never went into a block: {second_names}'
    assert second_hash in body_hashes, f'{second_hash} is not in the block body {body_hashes}'


def check_packed(blocks, most):
    """AC-39 (b): every transaction is in a block, and the blocks span at most `most` heights."""
    assert all(b is not None for b in blocks), f'not all included: {blocks}'
    span = max(blocks) - min(blocks) + 1
    assert span <= most, f'{len(blocks)} transactions spread over {span} blocks ({min(blocks)} to {max(blocks)})'


def check_pending_nonces(start, values):
    """AC-74: after the n-th transaction (n from 1), eth_getTransactionCount(sender, "pending") is start + n."""
    want = [start + n for n in range(1, len(values) + 1)]
    assert values == want, f'pending nonces {values}, want {want}'


def forks(heads):
    """How many heights got two different headers. heads: (number, header as JSON text) as they arrived."""
    seen = {}
    for number, header in heads:
        seen.setdefault(number, set()).add(header)
    return sum(1 for h in seen.values() if len(h) > 1)


def latest_status(recording, at):
    """The last status received at or before `at` (seconds), with its time, or None."""
    before = [(t, s) for t, s in recording if t <= at]
    return before[-1] if before else None


def check_no_drops(recordings, sent_at, samples, limit=1800, grace=2):
    """AC-41.
    recordings: {hash: [(seconds, status), ...]}; sent_at: {hash: seconds}; samples: [(seconds, set of hashes in
    author_pendingExtrinsics)]. Every transaction is finalized within `limit` seconds of being sent and never gets
    Dropped, Invalid or Usurped. At each sample, a transaction whose latest status is neither InBlock nor
    Finalized, and has stayed so for at least `grace` seconds, is in the pending set (after a Retracted too)."""
    for h, recording in recordings.items():
        statuses = names(recording)
        bad = BAD.intersection(statuses)
        assert not bad, f'{h} got {sorted(bad)}: {statuses}'
        done = [t for t, s in recording if status_name(s) == 'finalized']
        assert done and done[0] - sent_at[h] <= limit, f'{h} not finalized within {limit} s: {recording}'
    for at, pending in samples:
        for h, recording in recordings.items():
            last = latest_status(recording, at)
            if last is None or status_name(last[1]) in SETTLED or at - last[0] < grace:
                continue
            assert h in pending, f'at {at} s, {h} was {status_name(last[1])} since {last[0]} s but not pending'


def check_rejected_for_proof(ok, error):
    """AC-40: set_keys failed with Session.InvalidProof. ok, error: the receipt's is_success and error_message."""
    assert not ok, 'set_keys succeeded'
    assert isinstance(error, dict) and error.get('name') == 'InvalidProof', f'set_keys failed for another reason: {error}'


def aura_author(logs, authorities):
    """The authority whose slot a block is in: the slot is in the header's Aura PreRuntime digest item
    (0x06, engine "aura", an 8-byte SCALE Vec holding the slot as a little-endian u64), and the author is
    authorities[slot % len(authorities)], the authorities read at the parent block."""
    for log in logs:
        raw = bytes.fromhex(log.removeprefix('0x'))
        if raw[:5] == b'\x06aura' and raw[5] == 8 << 2:
            return authorities[int.from_bytes(raw[6:14], 'little') % len(authorities)]
    raise AssertionError(f'no aura PreRuntime digest in {logs}')


def check_new_key_authored(new_key, authored):
    """AC-40: once the new key is an authority, the collator authors a block with it.
    authored: (block number, author) of each block whose parent already had the new key as an authority."""
    assert authored, f'{new_key} never became an authority'
    assert any(author == new_key for _, author in authored), f'no block authored by {new_key}: {authored}'
