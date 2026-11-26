# Changelog

## polkadot-sdk stable2603-8 (peaq-dev spec 110, peaq spec 114)

The tests and tools for the node built on polkadot-sdk stable2603-8. Each change is one commit
on this branch.

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

The IDs below (AC-24 to AC-27) are the acceptance criteria of this change in the stable2603-8
upgrade plan. A fork run is `simple-ci-poc` `fork.chain.test.py` on a fork of agung (peaq-dev,
spec 109), with the node and runtime built from peaq-network-node `ef7ed7d2`, upgraded to
spec 110.

- AC-24: rewritten commits keep their content, checked on 2026-11-26 at the tip: the stable patch-ids of 92a25cb, 8596c4d, 4793368 and 0389a10 are all on the branch, the three earlier fork fixes 63eb77a, 28728c4 and 2d7db9d keep their hashes, every newer commit is authored by jaypan <pan@eotlabs.io>, and `MIN_SPEC_VERSION` is peaq 114 and peaq-dev 110.
- AC-24: fork run of e7badfe on 2026-11-26: 15 passed, 1 skipped (only test_from_relay_to_peaq, with its reason printed).
- AC-25: fork run of e7badfe on 2026-11-26: test_lp_asset_from_peaq_to_aca passed; the version before the sudo mint (0389a10) fails waiting for the relay token ("balance 0 not changed on peaq").
- AC-26: fork run of e7badfe on 2026-11-26: test_relay_token_from_relay_to_peaq_is_stuck passed; the same test on spec 109, with the upgrade left out, fails because peaq receives the relay token ("peaq received the relay token: 0 -> 99999999999999997500").
- AC-27: the fork run of e7badfe on 2026-11-26 upgraded with both checks passing ("PendingValidationCode holds this wasm at block #32").
