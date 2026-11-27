"""
Node behaviour that changed with polkadot-sdk stable2603, on a local network with two slot-based collators
(ferdie on 10044, eve on 10055; run_pr12.sh starts one):
- AC-39 the fork-aware transaction pool: a higher-tip replacement pushes the first transaction out, 50 EVM
  transactions with consecutive nonces are packed into at most 10 blocks, and --pool-best-blocks-only exists;
- AC-40 session.set_keys needs a real ownership proof, and the collator authors with the new key;
- AC-41 no transaction is lost while the chain forks (600 transfers, one a second, every one watched);
- AC-74 eth_getTransactionCount(sender, "pending") counts every sent transaction while the chain forks.
Transactions go to ferdie. AC-41 and AC-74 fork the chain by pausing eve's container (PR12_PAUSE_CONTAINER) for
30 s, about five slots; they count the heights that got two different headers (chain_subscribeAllHeads on
ferdie) and only check a try that forked. After three tries without a fork the test skips as partial ("could
not fork the chain"), which the spec counts as neither passed nor failed. AC-39 (c) runs peaq-node --help in
ferdie's container (PR12_COLLATOR_CONTAINER). The checks themselves are in tools/node_2603_checks.py.
"""
import json
import os
import subprocess
import threading
import time
import unittest

import pytest
import websocket
from eth_account import Account
from peaq.eth import calculate_evm_account
from peaq.utils import ExtrinsicBatch
from substrateinterface import Keypair, SubstrateInterface
from web3 import Web3

from tools import eth_raw_tx as T
from tools.constants import ETH_URL, KP_GLOBAL_SUDO, WS_URL
from tools.node_2603_checks import (
    aura_author, check_new_key_authored, check_no_drops, check_packed, check_pending_nonces,
    check_rejected_for_proof, check_replaced, extrinsic_hash, forks, status_name)
from tools.utils import batch_fund

FUNDS = 10 ** 24
PAUSE_SECONDS = 30
TRIES = 3
EVM_TO = '0x' + '22' * 20  # any address: the EVM transfers only need a recipient
TERMINAL = {'finalized', 'usurped', 'dropped', 'invalid', 'finalityTimeout'}


def fund(*addresses):
    substrate = SubstrateInterface(url=WS_URL)
    batch = ExtrinsicBatch(substrate, KP_GLOBAL_SUDO)
    for a in addresses:
        batch_fund(batch, a, FUNDS)
    receipt = batch.execute()
    assert receipt.is_success, f'funding failed: {receipt.error_message}'


def new_substrate_account():
    kp = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())
    fund(kp.ss58_address)
    return kp


def new_evm_account():
    a = Account.create()
    fund(calculate_evm_account(a.address))
    return bytes(a.key), a.address


def transfer(substrate, kp, nonce, tip=0):
    call = substrate.compose_call('Balances', 'transfer_keep_alive',
                                  {'dest': KP_GLOBAL_SUDO.ss58_address, 'value': 10 ** 15})
    return str(substrate.create_signed_extrinsic(call=call, keypair=kp, nonce=nonce, tip=tip).data)


class Watcher:
    """One websocket to ferdie: author_submitAndWatchExtrinsic for each transaction, a thread recording every
    status as (seconds since t0, status) per extrinsic hash. A refused submission is recorded as "invalid"."""

    def __init__(self, t0):
        self.t0, self.lock, self.next_id = t0, threading.Lock(), 100
        self.ws = websocket.create_connection(WS_URL, timeout=10)
        self.by_request, self.by_sub, self.recordings, self.early = {}, {}, {}, {}
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.running = True
        self.reader.start()

    def submit(self, hex_extrinsic):
        h = extrinsic_hash(hex_extrinsic)
        with self.lock:
            self.next_id += 1
            self.by_request[self.next_id] = h
            self.recordings[h] = []
            self.ws.send(json.dumps({'jsonrpc': '2.0', 'id': self.next_id,
                                     'method': 'author_submitAndWatchExtrinsic', 'params': [hex_extrinsic]}))
        return h

    def _record(self, h, status):
        self.recordings[h].append((time.monotonic() - self.t0, status))

    def _read(self):
        while self.running:
            try:
                message = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except (websocket.WebSocketConnectionClosedException, OSError, ValueError):
                return
            with self.lock:
                if 'id' in message and message['id'] in self.by_request:
                    h = self.by_request[message['id']]
                    if 'error' in message:
                        self._record(h, 'invalid')
                        print('submission refused', h, message['error'], flush=True)
                    else:
                        self.by_sub[message['result']] = h
                        for status in self.early.pop(message['result'], []):
                            self._record(h, status)
                elif message.get('method') == 'author_extrinsicUpdate':
                    sub, status = message['params']['subscription'], message['params']['result']
                    if sub in self.by_sub:
                        self._record(self.by_sub[sub], status)
                    else:
                        self.early.setdefault(sub, []).append(status)

    def wait_terminal(self, hashes, timeout):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                left = [h for h in hashes
                        if not any(status_name(s) in TERMINAL for _, s in self.recordings[h])]
            if not left:
                return
            time.sleep(2)

    def close(self):
        self.running = False
        self.ws.close()
        self.reader.join(timeout=20)


class Heads:
    """chain_subscribeAllHeads on ferdie, every header as (number, JSON text) in arrival order."""

    def __init__(self):
        self.heads, self.times, self.running = [], [], True
        self.ws = websocket.create_connection(WS_URL, timeout=10)
        self.ws.send(json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'chain_subscribeAllHeads', 'params': []}))
        self.thread = threading.Thread(target=self._read, daemon=True)
        self.thread.start()

    def _read(self):
        while self.running:
            try:
                message = json.loads(self.ws.recv())
            except websocket.WebSocketTimeoutException:
                continue
            except (websocket.WebSocketConnectionClosedException, OSError, ValueError):
                return
            if message.get('method') == 'chain_allHead':
                header = message['params']['result']
                self.heads.append((int(header['number'], 16), json.dumps(header, sort_keys=True)))
                self.times.append(time.strftime('%H:%M:%S'))

    def close(self):
        self.running = False
        self.ws.close()
        self.thread.join(timeout=20)
        seen = {}
        for (number, header), at in zip(self.heads, self.times):
            seen.setdefault(number, {}).setdefault(header, at)
        print('heights with two headers (number: first seen at):',
              {n: sorted(h.values()) for n, h in seen.items() if len(h) > 1}, flush=True)
        return forks(self.heads)


def pause_eve(after, seconds=PAUSE_SECONDS):
    """Pause eve's container `after` seconds from now for `seconds`, in a thread; returns the thread."""
    container = os.environ['PR12_PAUSE_CONTAINER']

    def run():
        time.sleep(after)
        subprocess.run(['docker', 'pause', container], check=True, capture_output=True)
        print(time.strftime('%H:%M:%S'), 'paused', container, flush=True)
        time.sleep(seconds)
        subprocess.run(['docker', 'unpause', container], check=True, capture_output=True)
        print(time.strftime('%H:%M:%S'), 'unpaused', container, flush=True)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread


def wait_new_block(substrate):
    start = substrate.get_block_header()['header']['number']
    while substrate.get_block_header()['header']['number'] == start:
        time.sleep(0.5)


@pytest.mark.substrate
class TestNode2603(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('PR12_PAUSE_CONTAINER'):
            raise unittest.SkipTest('needs the run_pr12.sh network (PR12_PAUSE_CONTAINER)')
        cls.substrate = SubstrateInterface(url=WS_URL)
        cls.w3 = Web3(Web3.HTTPProvider(ETH_URL, request_kwargs={'timeout': 120}))
        cls.chain_id = cls.w3.eth.chain_id

    def eth_transfer(self, key, sender, nonce):
        price = self.w3.eth.gas_price
        tx = {'type': 2, 'chainId': self.chain_id, 'nonce': nonce, 'maxPriorityFeePerGas': 0,
              'maxFeePerGas': 2 * price, 'gas': 21000, 'to': T.address_bytes(EVM_TO), 'value': 1,
              'data': b'', 'accessList': []}
        return self.w3.provider.make_request('eth_sendRawTransaction', ['0x' + T.encode(T.sign(tx, key)).hex()])

    def test_ac39_higher_tip_replaces(self):
        kp = new_substrate_account()
        nonce = self.substrate.get_account_nonce(kp.ss58_address)
        first_hex, second_hex = transfer(self.substrate, kp, nonce), transfer(self.substrate, kp, nonce, tip=10 ** 15)
        watcher = Watcher(time.monotonic())
        try:
            wait_new_block(self.substrate)  # both in the same slot, right after a block
            first = watcher.submit(first_hex)
            second = watcher.submit(second_hex)
            watcher.wait_terminal([first, second], 300)
        finally:
            watcher.close()
        print('first', first, watcher.recordings[first], flush=True)
        print('second', second, watcher.recordings[second], flush=True)
        in_block = [s['inBlock'] for _, s in watcher.recordings[second] if status_name(s) == 'inBlock']
        self.assertTrue(in_block, f'the second one never went into a block: {watcher.recordings[second]}')
        body = self.substrate.rpc_request('chain_getBlock', [in_block[-1]])['result']['block']['extrinsics']
        check_replaced(watcher.recordings[first], watcher.recordings[second], second,
                       [extrinsic_hash(x) for x in body])

    def test_ac39_fifty_evm_transactions_packed(self):
        key, sender = new_evm_account()
        start = self.w3.eth.get_transaction_count(sender, 'pending')
        hashes = []
        for n in range(50):
            response = self.eth_transfer(key, sender, start + n)
            self.assertIn('result', response, f'transaction {n} refused: {response}')
            hashes.append(response['result'])
        blocks = [self.w3.eth.wait_for_transaction_receipt(h, timeout=300)['blockNumber'] for h in hashes]
        print('blocks of the 50 transactions:', blocks, flush=True)
        check_packed(blocks, 10)

    def test_ac39_pool_best_blocks_only_flag(self):
        out = subprocess.run(['docker', 'exec', os.environ['PR12_COLLATOR_CONTAINER'], '/usr/local/bin/peaq-node',
                              '--help'], check=True, capture_output=True, text=True).stdout
        line = [x.strip() for x in out.splitlines() if '--pool-best-blocks-only' in x]
        print('peaq-node --help:', line, flush=True)
        self.assertTrue(line, 'peaq-node --help has no --pool-best-blocks-only')

    def _set_keys(self, kp, keys, proof):
        call = self.substrate.compose_call('Session', 'set_keys', {'keys': {'aura': keys}, 'proof': proof})
        extrinsic = self.substrate.create_signed_extrinsic(call=call, keypair=kp)
        receipt = self.substrate.submit_extrinsic(extrinsic, wait_for_inclusion=True, wait_for_finalization=False)
        return receipt.is_success, receipt.error_message

    def _authorities(self, block_hash):
        return [str(a).lower() for a in self.substrate.query('Aura', 'Authorities', block_hash=block_hash).value]

    def test_ac40_set_keys_needs_an_ownership_proof(self):
        ferdie = Keypair.create_from_uri('//Ferdie')
        owner = '0x' + ferdie.public_key.hex()  # set_keys checks the proof against the SCALE-encoded AccountId32
        generated = self.substrate.rpc_request('author_rotateKeysWithOwner', [owner])['result']
        print('author_rotateKeysWithOwner:', generated, flush=True)
        keys, proof = generated['keys'], generated['proof']
        self.assertEqual(len(bytes.fromhex(keys[2:])), 32, 'peaq-dev session keys are one aura key')

        rejected = self._set_keys(ferdie, keys, '0x00')
        print('set_keys with proof 0x00:', rejected, flush=True)
        check_rejected_for_proof(*rejected)
        accepted = self._set_keys(ferdie, keys, proof)
        print('set_keys with the generated proof:', accepted, flush=True)
        self.assertTrue(accepted[0], f'set_keys with the generated proof failed: {accepted[1]}')
        # red check from the spec: the "rejected" assertion fails on the call with the right proof
        with self.assertRaises(AssertionError):
            check_rejected_for_proof(*accepted)

        new_key = keys.lower()  # Aura.Authorities reads back as hex public keys, like `keys`
        start = self.substrate.get_block_header()['header']['number']
        authored, deadline = [], time.time() + 1800
        while not authored and time.time() < deadline:
            time.sleep(6)
            best = self.substrate.get_block_header()['header']['number']
            for number in range(start + 1, best + 1):
                block_hash = self.substrate.get_block_hash(number)
                header = self.substrate.rpc_request('chain_getHeader', [block_hash])['result']
                authorities = self._authorities(header['parentHash'])
                author = aura_author(header['digest']['logs'], authorities)
                if new_key in authorities:
                    authored.append((number, author))
            start = best
        session = self.substrate.query('Session', 'CurrentIndex').value
        print('blocks since the new key became an authority (number, author):', authored, 'session', session,
              flush=True)
        check_new_key_authored(new_key, authored)

    def _forked_try(self, attempt):
        """Runs attempt() up to TRIES times; returns its result from the first try that forked, or skips."""
        for n in range(1, TRIES + 1):
            heads = Heads()
            try:
                result = attempt()
            finally:
                count = heads.close()
            print(f'try {n}: {count} heights with two different headers', flush=True)
            if count:
                return result
        pytest.skip(f'partial: could not fork the chain in {TRIES} tries (no height got two headers)')

    def test_ac41_no_transaction_lost_in_a_fork(self):
        kp = new_substrate_account()

        def attempt():
            nonce = self.substrate.get_account_nonce(kp.ss58_address)
            t0 = time.monotonic()
            watcher, sampler = Watcher(t0), SubstrateInterface(url=WS_URL)
            sent_at, samples = {}, []
            pause = pause_eve(150)
            try:
                for i in range(600):
                    due = t0 + i
                    time.sleep(max(0, due - time.monotonic()))
                    h = watcher.submit(transfer(self.substrate, kp, nonce + i))
                    sent_at[h] = time.monotonic() - t0
                    if i % 6 == 0:
                        pending = sampler.rpc_request('author_pendingExtrinsics', [])['result']
                        samples.append((time.monotonic() - t0, {extrinsic_hash(x) for x in pending}))
                pause.join()
                watcher.wait_terminal(list(sent_at), 1800)
            finally:
                watcher.close()
            return watcher.recordings, sent_at, samples

        recordings, sent_at, samples = self._forked_try(attempt)
        names = [status_name(r[-1][1]) if r else None for r in recordings.values()]
        print('last statuses:', {n: names.count(n) for n in set(names)}, 'samples', len(samples), flush=True)
        check_no_drops(recordings, sent_at, samples)

    def test_ac74_pending_nonce_in_a_fork(self):
        key, sender = new_evm_account()

        def attempt():
            start = self.w3.eth.get_transaction_count(sender, 'pending')
            values, hashes, pause = [], [], pause_eve(0)
            time.sleep(PAUSE_SECONDS - 10)
            for n in range(20):  # 20 transactions 2 s apart, the unpause at about the fifth
                response = self.eth_transfer(key, sender, start + n)
                self.assertIn('result', response, f'transaction {n} refused: {response}')
                hashes.append(response['result'])
                values.append(self.w3.eth.get_transaction_count(sender, 'pending'))
                time.sleep(2)
            pause.join()
            time.sleep(90)  # eve's first blocks after the pause, which can fork, come some time after the unpause
            return start, values, hashes

        start, values, hashes = self._forked_try(attempt)
        print('start', start, 'pending nonces', values, flush=True)
        check_pending_nonces(start, values)
        deadline = time.time() + 1800
        for h in hashes:
            receipt = self.w3.eth.wait_for_transaction_receipt(h, timeout=max(1, deadline - time.time()))
            while self.substrate.get_block_header(
                    self.substrate.get_chain_finalised_head())['header']['number'] < receipt['blockNumber']:
                self.assertLess(time.time(), deadline, f'{h} not finalized within 30 min')
                time.sleep(6)
            canonical = self.w3.eth.get_block(receipt['blockNumber'])['hash']
            self.assertEqual(canonical, receipt['blockHash'], f'{h}: receipt from a block that is not canonical')
