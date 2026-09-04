"""Regression test for eth_subscribe("newHeads").

Background: peaq node at one point shipped a wiring bug where MappingSyncWorker
and EthPubSub were given two *different* `pubsub_notification_sinks` Arcs. The
RPC subscription returned a sub ID but no headers were ever delivered, while
chain_subscribeNewHeads kept working (substrate native path).

eth_subscribe("logs") sits on the same channel and is broken/fixed together
with newHeads, but logs is silent on an idle chain so it makes a poor regression
signal. newHeads fires once per block, so it is the reliable assertion target.

Two tests:
  * test_eth_subscribe_new_heads_delivers_headers — fast smoke test, just checks
    that headers arrive at all (catches the "sub ID returned but channel dead"
    regression).
  * test_eth_subscribe_aligns_with_substrate_live_blocks — strong test that runs
    eth_subscribe in parallel with substrate's chain head polling and verifies
    notifications track 1:1 with live block production. Catches the case where
    notifications only arrive during startup catchup but not for live blocks.
"""
import json
import threading
import time
import unittest

import pytest
from substrateinterface import SubstrateInterface
from websocket import create_connection

from tools.constants import WS_URL


# Block time is ~6s. Two notifications inside 60s gives plenty of margin while
# still catching the "subscription returns ID but never delivers" regression.
TIMEOUT_SECONDS = 60
EXPECTED_HEADERS = 2
NEWHEAD_KEYS = {"hash", "parentHash", "number"}

# Strong-alignment test parameters.
ALIGN_WINDOW_SECONDS = 30  # ≈ 5 blocks at 6s/block.
ALIGN_TOLERANCE_BLOCKS = 1  # boundary race between substrate poll and ws frame


def _recv_json(ws):
    return json.loads(ws.recv())


def _open_eth_sub(ws_url, kind="newHeads", timeout=TIMEOUT_SECONDS):
    ws = create_connection(ws_url, timeout=timeout)
    ws.send(json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "eth_subscribe", "params": [kind],
    }))
    resp = _recv_json(ws)
    if "error" in resp or "result" not in resp:
        ws.close()
        raise RuntimeError(f"eth_subscribe failed: {resp}")
    return ws, resp["result"]


@pytest.mark.eth
class TestEthSubscribeNewHeads(unittest.TestCase):
    def test_eth_subscribe_new_heads_delivers_headers(self):
        ws, sub_id = _open_eth_sub(WS_URL)
        try:
            self.assertIsInstance(sub_id, str)
            self.assertTrue(sub_id.startswith("0x"), f"unexpected sub id: {sub_id}")

            ws.settimeout(TIMEOUT_SECONDS)
            headers = []
            while len(headers) < EXPECTED_HEADERS:
                frame = _recv_json(ws)
                if frame.get("method") != "eth_subscription":
                    continue
                params = frame.get("params", {})
                if params.get("subscription") != sub_id:
                    continue
                headers.append(params.get("result"))

            self.assertEqual(len(headers), EXPECTED_HEADERS)
            for h in headers:
                self.assertIsInstance(h, dict, f"header is not an object: {h}")
                missing = NEWHEAD_KEYS - h.keys()
                self.assertFalse(missing, f"header missing fields {missing}: {h}")

            numbers = [int(h["number"], 16) for h in headers]
            self.assertEqual(
                sorted(numbers), numbers,
                f"newHeads delivered out of order: {numbers}",
            )
        finally:
            ws.close()

    def test_eth_subscribe_aligns_with_substrate_live_blocks(self):
        """Run eth_subscribe in parallel with substrate polling for ALIGN_WINDOW.

        Asserts (a) the chain produced at least one live block and (b) the eth
        subscription delivered roughly one notification per block. Without the
        fix, (b) would be zero even when (a) is non-zero.
        """
        substrate = SubstrateInterface(url=WS_URL)
        ws, sub_id = _open_eth_sub(WS_URL)

        eth_numbers = []
        listener_done = threading.Event()

        def listener():
            deadline = time.time() + ALIGN_WINDOW_SECONDS
            try:
                while time.time() < deadline:
                    ws.settimeout(max(0.1, deadline - time.time()))
                    try:
                        frame = _recv_json(ws)
                    except Exception:
                        break
                    if frame.get("method") != "eth_subscription":
                        continue
                    if frame.get("params", {}).get("subscription") != sub_id:
                        continue
                    eth_numbers.append(int(frame["params"]["result"]["number"], 16))
            finally:
                listener_done.set()

        try:
            best_before = substrate.get_block_number(substrate.get_chain_head())
            t = threading.Thread(target=listener, daemon=True)
            t.start()
            time.sleep(ALIGN_WINDOW_SECONDS)
            listener_done.wait(timeout=5)
            best_after = substrate.get_block_number(substrate.get_chain_head())
        finally:
            ws.close()

        substrate_delta = best_after - best_before
        eth_count = len(eth_numbers)

        self.assertGreater(
            substrate_delta, 0,
            f"substrate produced no blocks in {ALIGN_WINDOW_SECONDS}s "
            f"(best {best_before} → {best_after}); chain stalled, test invalid",
        )
        self.assertGreater(
            eth_count, 0,
            f"substrate produced {substrate_delta} live blocks but "
            f"eth_subscribe delivered ZERO notifications — sink wiring broken",
        )
        diff = abs(eth_count - substrate_delta)
        self.assertLessEqual(
            diff, ALIGN_TOLERANCE_BLOCKS,
            f"eth_subscribe delivered {eth_count} notifications but substrate "
            f"produced {substrate_delta} blocks "
            f"(diff {diff} > tolerance {ALIGN_TOLERANCE_BLOCKS}); "
            f"eth numbers: {eth_numbers}",
        )

        sorted_nums = sorted(eth_numbers)
        self.assertEqual(
            eth_numbers, sorted_nums,
            f"eth_subscribe delivered out of order: {eth_numbers}",
        )
