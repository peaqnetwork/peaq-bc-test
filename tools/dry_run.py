"""DryRunApi and XcmPaymentApi through a raw state_call, plus the checks the tests make on the results.

substrate-interface has no definition for these two runtime APIs, so the arguments are encoded and
the results decoded with the type ids from the chain's own metadata, looked up by type path.

Decoded values keep the shape scalecodec gives them, for example a location is
{'V5': {'parents': 1, 'interior': {'X1': [{'Parachain': 1000}]}}}, an instruction is either a
name ('ClearOrigin') or a one-key dict ({'WithdrawAsset': [...]}), and an event is
{'event_index': '0402', 'module_id': 'Balances', 'event_id': 'Transfer', 'attributes': {...}}. The check functions only read
that shape, so the offline tests can feed them hand-made results. check_xcm_issuance (AC-30) is here
too, so that those tests can import it without connecting to a node.
"""
from scalecodec.base import ScaleBytes

XCM_VERSION = 5
ASSET_HUB = (1, ({'Parachain': 1000},))
PARENT = (1, ())
DRY_RUN_ERRORS = ['Unimplemented', 'VersionedConversionFailed']
FEE_ERRORS = ['Unimplemented', 'VersionedConversionFailed', 'WeightNotComputable', 'UnhandledXcmVersion',
              'AssetNotFound', 'Unroutable']


class XcmRuntimeApis:
    """Calls DryRunApi and XcmPaymentApi of the runtime behind `substrate`, at its best block."""

    def __init__(self, substrate):
        self.si = substrate
        self.si.init_runtime()
        self.md = self.si.metadata
        types = self.md.portable_registry['types']
        runtime = next(
            t['type']['path'].value[0] for t in types
            if t['type']['path'].value[1:] == ['RuntimeEvent'] and t['type']['path'].value[0].endswith('_runtime'))
        self.t_event = self._type_id(runtime, 'RuntimeEvent')
        self.t_origin = self._type_id(runtime, 'OriginCaller')
        self.t_weight = self._type_id('sp_weights', 'weight_v2', 'Weight')
        self.t_dispatch_error = self._type_id('sp_runtime', 'DispatchError')
        self.t_location = self._type_id('xcm', 'VersionedLocation')
        self.t_asset_id = self._type_id('xcm', 'VersionedAssetId')
        self.t_assets = self._type_id('xcm', 'VersionedAssets')
        # VersionedXcm<()>, the type PolkadotXcm.send takes
        send = next(c for c in self.md.get_metadata_pallet('PolkadotXcm').calls if c.name == 'send')
        self.t_xcm = next(a.type for a in send.args if a.name == 'message')

    def _type_id(self, *path):
        hits = [t['id'].value for t in self.md.portable_registry['types'] if tuple(t['type']['path'].value) == path]
        if len(hits) != 1:
            raise KeyError(f'type {path}: {hits}')
        return f'scale_info::{hits[0]}'

    def _encode(self, type_string, value):
        return self.si.runtime_config.create_scale_object(type_string, metadata=self.md).encode(value).data

    def _state_call(self, method, args):
        resp = self.si.rpc_request('state_call', [method, '0x' + b''.join(args).hex(), None])
        if 'result' not in resp:
            raise RuntimeError(f'{method}: {resp}')
        return _Reader(self, resp['result'])

    def dry_run_call(self, origin_address, call):
        """
        Dry-runs `call` (a composed GenericCall) signed by `origin_address`. Returns the decoded
        CallDryRunEffects as a dict; raises RuntimeError when the API itself returns an error.
        """
        rd = self._state_call('DryRunApi_dry_run_call', [
            self._encode(self.t_origin, {'system': {'Signed': origin_address}}),
            call.data.data,
            self._encode('u32', XCM_VERSION)])
        if rd.byte() != 0:  # the Result tag; on Err the next byte is the error variant
            raise RuntimeError(f'DryRunApi_dry_run_call returned Err({DRY_RUN_ERRORS[rd.byte()]})')
        tag = rd.byte()
        actual_weight, pays = rd.obj(f'Option<{self.t_weight}>'), rd.byte()
        if tag == 0:
            execution_result = ('Ok', {'actual_weight': actual_weight, 'pays': pays})
        else:
            execution_result = ('Err', rd.obj(self.t_dispatch_error))
        effects = {
            'execution_result': execution_result,
            'emitted_events': rd.vec(lambda: rd.obj(self.t_event)),
            'local_xcm': rd.obj(f'Option<{self.t_xcm}>'),
            'forwarded_xcms': rd.vec(lambda: (rd.obj(self.t_location), rd.vec(lambda: rd.obj(self.t_xcm)))),
        }
        rd.assert_done()
        return effects

    def query_delivery_fees(self, destination, message, asset_id):
        """XcmPaymentApi_query_delivery_fees; returns ('Ok', assets) or ('Err', error name)."""
        rd = self._state_call('XcmPaymentApi_query_delivery_fees', [
            self._encode(self.t_location, destination),
            self._encode(self.t_xcm, message),
            self._encode(self.t_asset_id, asset_id)])
        # the Result tag, then on Err the error variant
        result = ('Ok', rd.obj(self.t_assets)) if rd.byte() == 0 else ('Err', FEE_ERRORS[rd.byte()])
        rd.assert_done()
        return result


class _Reader:
    def __init__(self, apis, hexstr):
        self.apis, self.sb = apis, ScaleBytes(hexstr)

    def byte(self):
        return self.sb.get_next_bytes(1)[0]

    def obj(self, type_string):
        o = self.apis.si.runtime_config.create_scale_object(type_string, data=self.sb, metadata=self.apis.md)
        return o.decode(check_remaining=False)

    def vec(self, read_one):
        return [read_one() for _ in range(self.obj('Compact<u32>'))]

    def assert_done(self):
        if self.sb.offset != len(self.sb.data):
            raise RuntimeError(f'{len(self.sb.data) - self.sb.offset} bytes left after decoding the result')


def unversion(versioned):
    """{'V5': x} -> x"""
    (value,) = versioned.values()
    return value


def location(versioned_or_plain):
    """A decoded location as (parents, junctions), e.g. (1, ({'Parachain': 1000},))."""
    loc = versioned_or_plain
    if 'parents' not in loc:
        loc = unversion(loc)
    interior = loc['interior']
    junctions = () if interior == 'Here' else tuple(unversion(interior))
    return int(loc['parents']), junctions


def instruction_names(message):
    return [i if isinstance(i, str) else next(iter(i)) for i in message]


def instruction(message, name):
    return next(i[name] for i in message if not isinstance(i, str) and name in i)


def check_routed_via_asset_hub(effects, reserve_dest=None):
    """
    AC-28 / AC-29: the dry run of an XTokens.transfer of the relay token forwarded exactly one XCM,
    to Asset Hub, and nothing to the relay. Without `reserve_dest` the beneficiary is on Asset Hub
    or the relay, and the message is WithdrawAsset, ClearOrigin, BuyExecution, DepositAsset; with it
    the last one is DepositReserveAsset to `reserve_dest`, a (parents, junctions) location as Asset
    Hub sees it. A trailing SetTopic is ignored.
    """
    assert effects['execution_result'][0] == 'Ok', f"the transfer failed: {effects['execution_result']}"
    forwarded = effects['forwarded_xcms']
    destinations = [location(dest) for dest, _ in forwarded]
    assert PARENT not in destinations, f'an XCM was forwarded to the relay: {destinations}'
    assert destinations == [ASSET_HUB], f'expected one XCM forwarded to Asset Hub, got {destinations}'
    messages = forwarded[0][1]
    assert len(messages) == 1, f'expected one message to Asset Hub, got {len(messages)}'
    message = unversion(messages[0])
    last = 'DepositReserveAsset' if reserve_dest else 'DepositAsset'
    names = instruction_names(message)
    if names[-1] == 'SetTopic':  # the router's WithUniqueTopic appends it to every message
        names = names[:-1]
    expected = ['WithdrawAsset', 'ClearOrigin', 'BuyExecution', last]
    assert names == expected, f'expected the instructions {expected}, got {names}'
    withdrawn = [location(a['id']) for a in instruction(message, 'WithdrawAsset')]
    assert withdrawn == [PARENT], f'expected the relay token (1, Here) withdrawn on Asset Hub, got {withdrawn}'
    if reserve_dest:
        got = location(instruction(message, 'DepositReserveAsset')['dest'])
        assert got == reserve_dest, f'DepositReserveAsset goes to {got}, expected {reserve_dest}'


def check_transfer_event(effects, sender, receiver, amount):
    """AC-81 (1): the dry run of a transfer emitted Balances.Transfer sender -> receiver of amount."""
    assert effects['execution_result'][0] == 'Ok', f"the transfer failed: {effects['execution_result']}"
    want = {'from': sender, 'to': receiver, 'amount': amount}
    transfers = [e['attributes'] for e in effects['emitted_events']
                 if (e['module_id'], e['event_id']) == ('Balances', 'Transfer')]
    assert want in transfers, f'no Balances.Transfer {want} in the emitted events: {effects["emitted_events"]}'


def check_local_xcm_recorded(effects):
    """AC-81 (3): the dispatch succeeded and the XCM it ran locally was recorded."""
    assert effects['execution_result'][0] == 'Ok', f"the call failed: {effects['execution_result']}"
    assert effects['local_xcm'] is not None, 'local_xcm is None: the XCM run locally was not recorded'


def check_xcm_issuance(r):
    """
    AC-30 on the readings of block N-1 and block N, the block that ran the sibling's XCM:
    - TotalIssuance moved by exactly the block reward minted in N, so the XCM minted nothing;
    - the BlockReward sinks gained the block reward plus the PEAQ execution fee the sovereign paid;
    - the second fee, paid in the relay token, reached the TakeRevenue account.
    """
    minted_by_xcm = r['issuance_after'] - r['issuance_before'] - r['block_reward']
    assert minted_by_xcm == 0, (
        f"TotalIssuance {r['issuance_before']} -> {r['issuance_after']} is not the block reward "
        f"{r['block_reward']} alone: the XCM changed it by {minted_by_xcm}")
    assert r['native_fee'] > 0, 'no PEAQ execution fee was charged'
    sink_gain = r['sinks_after'] - r['sinks_before'] - r['block_reward']
    assert sink_gain == r['native_fee'], (
        f"the BlockReward sinks gained {sink_gain} besides the block reward, "
        f"expected the execution fee {r['native_fee']}")
    assert r['foreign_fee'] > 0, 'no relay-token fee was charged by the second BuyExecution'
    revenue_gain = r['revenue_after'] - r['revenue_before']
    assert revenue_gain == r['foreign_fee'], (
        f"the TakeRevenue account gained {revenue_gain} of the relay token, expected {r['foreign_fee']}")
