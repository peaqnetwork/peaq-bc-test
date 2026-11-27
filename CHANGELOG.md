# Changelog

## polkadot-sdk stable2603-8 (peaq-dev spec 110, peaq spec 114)

The tests and tools for the node built on polkadot-sdk stable2603-8. Each change is one commit
on this branch.

### Added

- `tools/dry_run.py`: calls `DryRunApi_dry_run_call` and `XcmPaymentApi_query_delivery_fees`
  through `state_call`. substrate-interface has no definition of either API, so the arguments
  are encoded and the results decoded with the chain's own metadata types. It also holds the
  checks the tests below make on the results, so they can be tested offline.
- `tests/xcm_dry_run_test.py` needs a local network with a para 1000 standing in for Asset Hub
  and HRMP channels from the chain to para 1000 and para 3000:
  - `XTokens.transfer` of the relay token to the relay, or to Asset Hub, forwards one XCM to
    para 1000 and nothing to the relay: WithdrawAsset, ClearOrigin, BuyExecution, DepositAsset.
  - The relay token sent to para 3000 also goes to para 1000, which sends it on to para 3000
    with DepositReserveAsset.
  - The dry run of a Balances transfer lists its `Balances.Transfer`, the delivery fee to the
    relay is `Unimplemented`, and the dry run of a `PolkadotXcm.transfer_assets` records the XCM
    it ran locally (`local_xcm`).

  Without a channel to para 1000 the transfer fails and its forwarded XCM is rolled back, so the
  first two tests are skipped on a network that has none, such as the usual CI network.
- `tests/xcm_dry_run_check_test.py`: the checks above, offline, on results taken from a
  local-network run and on the same results with the checked part broken.
- `tests/xcm_fee_blockreward_test.py`: new test `test_xcm_execution_mints_nothing`. Para 3000
  sends an XCM that buys execution first in PEAQ and then in the relay token. In the block that
  ran it, TotalIssuance grows by the block reward alone, the BlockReward sinks grow by the block
  reward plus the PEAQ fee, and the relay-token fee reaches the TakeRevenue account. A block with
  a signed extrinsic, another XCM, a `Balances.DustLost` or a `ParachainStaking.Rewarded` moves
  these sums for other reasons, so the test sends again, up to 3 times.

- `tools/eth_raw_tx.py`: builds and signs raw EVM transactions of every type, including EIP-7702
  (type 4) with its authorization list, and turns a signature into its high-s version. eth-account
  0.9.0 cannot sign type 4, and it never makes a high-s signature.
- `tools/evm_2603_checks.py`: the checks the EVM tests below make on the node's answers, so they
  can be tested offline.
- `tests/evm_2603_test.py`, the EVM behaviour of stable2603-8. It needs a local network, and its
  `TestEvm2603RpcNode` tests also need a non-collator RPC node on port 20044 started with
  `--ethapi=debug,trace,txpool` and a tracing override wasm:
  - EIP-7702: a type-4 transaction delegates an EOA to a contract, the EOA then runs the
    contract's code, and a second authorization to the zero address clears it.
  - An EOA delegated to a contract cannot call the Batch or XcmUtils precompiles ("Function not
    callable by smart contracts"); a plain EOA can.
  - The calldata floor: 4,096 non-zero bytes with gas 21,000 + 16 per byte are refused
    ("intrinsic gas too low") and the nonce does not move; with 21,000 + 40 per byte they are
    accepted and use exactly that; `eth_estimateGas` is at least that. Also prints the gas of a
    DID `addAttribute` with a 2 KB value.
  - Legacy transactions without a chain id are accepted, a wrong chain id is refused, and gas of
    72,000,000 - 1 is not refused by Frontier's per-transaction gas cap
    (`TransactionGasLimitExceedsCap`): it is accepted, or refused for the block's resources.
  - A transaction signed with a high-s signature is refused ("invalid sender") by the collator
    and by the RPC node, for all 4 transaction types.
  - Tracing: `debug_traceTransaction` with callTracer and `withLog` returns the log in the
    receipt; `debug_traceBlockByNumber("latest")` is the best block; a block made by an earlier
    runtime is traced through that runtime's override.
  - The logs journal: blocks whose logs are just under and just over each limit, with a logs
    subscription and a filter open on the contract. Over a limit, the node sends none of the
    block's logs, closes the subscription (`eth_unsubscribe` answers false) and drops the filter
    ("incomplete reorg journal entry ... recreate the filter", then "Filter id N does not
    exist"). Its last block, 129 logs of 32 KiB, stops the chain (the relay validators refuse
    it), so the test runs only with `PR11_AC35=1`, alone on its network.
  - `eth_blockNumber` keeps answering, keeps up with the chain and never goes back, from 30 to 60
    seconds after the RPC node restarts.
  - `eth_getLogs` and `eth_newFilter` refuse a range with `to - from` over 1,024, more than 4
    topics and more than 1,024 addresses, each by its own message, and accept 1,024, 4 and 1,024.
- `tests/evm_2603_check_test.py`: the raw transaction encoding (checked against eth-account for
  the types it can sign) and the checks above, offline, on node answers copied from the runs
  below and on the answers each check exists to reject.

- `tools/node_2603_checks.py`: the checks the node tests below make on what they record (watch
  statuses, block bodies, pending nonces, headers), so they can be tested offline.
- `tests/node_2603_test.py`, the node behaviour of stable2603-8. It needs a local network with
  two collators (ferdie and eve) and the names of their containers in `PR12_COLLATOR_CONTAINER`
  and `PR12_PAUSE_CONTAINER`; without them it is skipped. To fork the chain it pauses eve's
  container for 30 seconds, and it counts a fork only when a height gets a second, different
  header while the test is sending.
  - The fork-aware transaction pool: a second transaction with the same sender and nonce and a
    higher tip pushes the first one out (`usurped`), and it is the one in the block; with a lower
    tip the first one stays. 50 EVM transactions with consecutive nonces are all in the 10 blocks
    after sending. `peaq-node --help` has `--pool-best-blocks-only`.
  - `session.set_keys` with proof `0x00` fails with `Session.InvalidProof`; with the keys and
    proof from `author_rotateKeysWithOwner` it succeeds, and once the key is an aura authority
    the collator authors a block with it.
  - While the chain forks: 600 Substrate transfers, one a second, each watched with
    `author_submitAndWatchExtrinsic`, are all finalized and none is dropped, invalid or usurped,
    and a transaction that is not in a block is in `author_pendingExtrinsics`; and
    `eth_getTransactionCount(sender, "pending")` counts every one of 20 EVM transactions sent,
    which are then finalized in canonical blocks.

  Each part tries up to 3 times to fork the chain, and is skipped as partial when it never forks.
- `tests/node_2603_check_test.py`: the checks above, offline, each on a good recording and on
  the same recording with the one change the check exists to catch.

### Changed

- `tests/runtime_api_test.py`: `MIN_SPEC_VERSION` is peaq 114 and peaq-dev 110.
- `tests/xcm_transfer_test.py`:
  - `test_from_relay_to_peaq` is skipped. Since ORML #1035 the reserve of the relay token is
    Asset Hub (para 1000), and the local network has no para 1000, so a transfer straight from
    the relay is refused on peaq (`UntrustedReserveLocation`).
  - New test `test_relay_token_from_relay_to_peaq_is_stuck`. It sends the relay token from the
    relay to peaq and checks what happens now: the relay moves the amount to peaq's sovereign
    account, peaq refuses the message (a `MessageQueue.Processed` event from `Parent` with
    `success: false`), and the receiver's balance does not change. Funds sent this way stay
    in peaq's sovereign account on the relay.
  - `test_lp_asset_from_peaq_to_aca` gets its relay tokens from a sudo `Assets.mint` by the
    asset's issuer instead of a relay transfer, which no longer arrives.
- `tools/runtime_upgrade.py`: after sending the upgrade, `upgrade()` checks that it took
  effect and fails with the reason if it did not:
  - (a) the upgrade transaction is in a block on the finalized chain. When a fork replaced
    the block the receipt names, the transaction is looked for in the finalized blocks within
    10 of it.
  - (b) `ParachainSystem.PendingValidationCode` at that block holds this wasm (same blake2
    hash), so an earlier upgrade that is still pending is reported too.

  Each failure names (a) or (b) and prints the best and finalized heights of the parachain
  and the relay. `tests/runtime_upgrade_check_test.py` covers both with fake RPCs, offline.

### Verification

The IDs below (AC-24 to AC-30, AC-81) are the acceptance criteria of this change in the
stable2603-8 upgrade plan. A fork run is `simple-ci-poc` `fork.chain.test.py` on a fork of agung (peaq-dev,
spec 109), with the node and runtime built from peaq-network-node `ef7ed7d2`, upgraded to
spec 110.

- AC-24: rewritten commits keep their content, checked on 2026-11-26 at the tip: the stable patch-ids of 92a25cb, 8596c4d, 4793368 and 0389a10 are all on the branch, the three earlier fork fixes 63eb77a, 28728c4 and 2d7db9d keep their hashes, every newer commit is authored by jaypan <pan@eotlabs.io>, and `MIN_SPEC_VERSION` is peaq 114 and peaq-dev 110.
- AC-24: fork run of e7badfe on 2026-11-26: 15 passed, 1 skipped (only test_from_relay_to_peaq, with its reason printed).
- AC-25: fork run of e7badfe on 2026-11-26: test_lp_asset_from_peaq_to_aca passed; the version before the sudo mint (0389a10) fails waiting for the relay token ("balance 0 not changed on peaq").
- AC-26: fork run of e7badfe on 2026-11-26: test_relay_token_from_relay_to_peaq_is_stuck passed; the same test on spec 109, with the upgrade left out, fails because peaq receives the relay token ("peaq received the relay token: 0 -> 99999999999999997500").
- AC-27: the fork run of e7badfe on 2026-11-26 upgraded with both checks passing ("PendingValidationCode holds this wasm at block #32").

A local-network run is a new network of the relay (`parity/polkadot:stable2506-2`, rococo-local),
the chain under test as para 2000, a peaq-dev para 3000 and a peaq-dev para 1000 standing in for
Asset Hub, with HRMP channels 2000 to 3000, 3000 to 2000, 2000 to 1000 and 1000 to 2000. Each
runs `tests/xcm_dry_run_test.py` and `tests/xcm_fee_blockreward_test.py` at 2c9d275, on a node
built from peaq-network-node `ef7ed7d2`, once with peaq-dev (`dev-local`) and once with peaq
(`peaq-local`) as para 2000. The red runs use the node from `d6a32578`, before the XcmRecorder
fix.

- AC-28, AC-29, AC-30, AC-81: local-network runs on 2026-11-26: 7 passed, 0 skipped, for both peaq-dev and peaq.
- AC-28: the transfer to the relay and the transfer to Asset Hub each forwarded one XCM, to para 1000, of WithdrawAsset((1, Here)), ClearOrigin, BuyExecution, DepositAsset and SetTopic. Offline, the same check rejects that XCM addressed to the relay, and the same XCM with a DepositReserveAsset to the relay added.
- AC-29: the transfer to para 3000 forwarded one XCM, to para 1000, ending in DepositReserveAsset to (1, Parachain 3000). Offline, the check rejects it addressed to the relay.
- AC-30: in the block that ran the XCM (#59 on peaq-dev, #55 on peaq), TotalIssuance grew by exactly that block's reward, the sinks grew by the reward plus the PEAQ fee (462290928925 on peaq-dev, 80692881644276375 on peaq), and 500 of the relay token reached the TakeRevenue account. Offline, the check rejects the same readings with TotalIssuance one higher.
- AC-81: the transfer's dry run lists `Balances.Transfer` Alice to Bob of 1 PEAQ, the delivery fee to the relay is `Err(Unimplemented)`, and the `transfer_assets` dry run is Ok with `local_xcm` recorded. Offline, the check rejects the transfer with no events. On the `d6a32578` node, for both runtimes, the transfer check still passes and the `transfer_assets` check fails with "local_xcm is None".

The IDs below (AC-31 to AC-38, AC-77) are the EVM acceptance criteria. Each run is a new local
network (relay `parity/polkadot:stable2506-2`, rococo-local, 6 validators; para 2000 on
`dev-local`), plus an RPC node on the host with a database of its own. "The 2603 node" is
peaq-network-node `ef7ed7d2`; "the tracing node" is the same commit built with the tracing
runtime, with the spec-110 (and, for an upgrade, spec-109) tracing wasm as overrides; "the 2503
node" is v0.0.109 (spec 109). Logs of every run are in the PR-11 evidence of the upgrade report.

- AC-31, AC-32, AC-33, AC-34, AC-36, AC-37, AC-38, AC-77: run `green4` on 2026-11-26, the 2603 node with the tracing node as RPC node, the whole of `tests/evm_2603_test.py`: 12 passed, 2 skipped (AC-35, which runs only with `PR11_AC35=1`, and the earlier-runtime trace, which has no earlier runtime on a new chain). It waited until block 2010 for AC-37.
- AC-31: on the 2503 node the type-4 transaction is refused ("decode transaction failed"); on the 2603 node the delegation and the clearing both took effect.
- AC-32: from the delegated EOA, `eth_call` of Batch.batchAll and of XcmUtils reverts "Function not callable by smart contracts" and the sent transaction fails; from a plain EOA both succeed.
- AC-33: on the 2603 node, (a) is refused "intrinsic gas too low" and the nonce does not move, (b) uses 184,840 gas, exactly the floor, and the estimate is 185,640. On the 2503 node (a) is accepted, using 86,536, and the estimate is 88,108. The DID `addAttribute` with a 2 KB value uses 106,370 gas on the 2603 node and 82,469 on the 2503 node.
- AC-34: callTracer with `withLog` returned the receipt's log; the trace of "latest" had the transaction and eth latest was the same block. Run `upgrade3`: a chain started on spec 109 (2503 genesis), upgrade set at block #21 and spec 110 running by #37; block #17 (spec 109, the emitter's deployment) traced with the spec-109 override, 2 passed with `tests/test_evm_event_only.py`, and simple-ci's 4 debug traces and 3 txpool reads (`evm.wasm.test.py`'s checks) passed against the RPC node.
- AC-34 red check: run `nooverride`, the same node as RPC node with an empty override directory: both trace tests fail on their assertions (`DispatchError: Other("")`). The node has no evm-tracing feature of its own, so a node "built without evm-tracing" still serves `debug_*` and traces with a tracing override (run `notracing`, 2 passed); the override is what matters.
- AC-35: run `ac35e`, alone on its network with `PR11_AC35=1`: 1 passed. Journal entries close at 8,193 LOG0 (8,192 does not) and at 127 logs of 32 KiB (126 does not): Frontier counts each block's bytes by Vec capacity. On default settings a logs subscription also closes after 64 logs of one block, for its buffers (the 2503 node does the same, run `ac35-2503b`); so only 50 LOG0 is checked in full, and the other open cases check that logs arrived and that the filter returned all of them. The 129 x 32 KiB block stops the chain (the relay validators log errors validating it; the cause is not settled yet, see the stall finding in the PR-11 evidence); run AC-35 alone and last.
- AC-36: largest lag between `eth_blockNumber` and the RPC node's best block was 0 and it never went back; the last sample (second 59) was #102 on both, and the collator was at #102 right after.
- AC-37: `toBlock - fromBlock` of 1,025 is refused ("block range is too wide (maximum 1024)") and 1,024 returns the log; `eth_newFilter` from latest - 2000 is refused the same way and from latest - 1024 is accepted; 5 topics are refused as invalid params ("out of bounds") by `eth_getLogs` and `eth_newFilter`, and 4 are accepted; 1,025 addresses are refused as invalid params ("too big array") by both, and 1,024 addresses, the emitter among them, return the log.
- AC-38: gas 72,000,000 - 1 is refused "exceeds block gas limit", which is Frontier's message for `ExhaustsResources`, not for its per-transaction cap; an unprotected legacy transaction is accepted; a wrong chain id is refused "invalid chain id".
- AC-77: the collator and the RPC node both answer "invalid sender" to a high-s signature of each of the 4 types; an unfunded sender gets "insufficient funds for gas * price + value".

The IDs below (AC-39, AC-40, AC-41, AC-74) are the node acceptance criteria. The run is a new
local network (relay `parity/polkadot:stable2506-2`, rococo-local; para 2000 on `dev-local` with
two collators, ferdie and eve, both on the node from peaq-network-node `ef7ed7d2`). Run `green2`
on 2026-11-27, at aef3742, ran `tests/node_2603_test.py` and `tests/node_2603_check_test.py`: 16
passed, 0 skipped. Logs of every run are in the PR-12 evidence of the upgrade report.

- AC-39: (a) the first transaction got `usurped` by the second, which was in block 0xcc4e19a0; with the second tip lower, the second one got `usurped` and the first was in its block, so the replace check fails on it as it should; (b) all 50 EVM transactions were in block #10, sent at best block #9; (c) `peaq-node --help` lists `--pool-best-blocks-only`.
- AC-40: `set_keys` with proof `0x00` failed with `Session.InvalidProof`; with the keys and proof from `author_rotateKeysWithOwner` it succeeded, and block #81, the first block after the key became an aura authority, was authored by the new key 0xc8805a21. The collator steps are in the runbook draft of the PR-12 evidence.
- AC-41: on the first try, 10 heights got a second header while sending, at 54.9 s and then about every 60 s up to 594.9 s; eve was paused from 150 s to 180 s, so only the one at 180.8 s (height 112) follows the pause, and the other 9 came without it; all 600 transfers were finalized and none was dropped, invalid or usurped; the same check fails on the recording with a Dropped inserted.
- AC-74: eve was paused 30 s; height 190 got a second header 38.3 s after the first send, on the first try; `eth_getTransactionCount(sender, "pending")` returned 1 to 20 after each of the 20 sends, none was refused, all 20 were finalized in canonical blocks; the same check fails on the recording with one value lowered by 1.
