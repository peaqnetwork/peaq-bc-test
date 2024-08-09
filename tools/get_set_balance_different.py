import requests
import sys
sys.path.append('./')
from substrateinterface import SubstrateInterface
from peaq.utils import get_block_hash
import time


# Two situation
# 1. set_balance to other account directly
# 2. set_balance to self and transfer to other account
# Set the request parameters
EVENTS_URL = 'https://krest.webapi.subscan.io/api/v2/scan/events'
EVENT_URL = 'https://krest.webapi.subscan.io/api/scan/event'

SUDO_ADDR = '0xbaa6e3c1c492a2324f2ce9bd7f05418597d2e8319924c54e827e52cf51b0747a'
SUDO_SUBSTRATE_ADDR = '5GHSLh39LSAe1papNix88CQ4aWccBEJTD8cQtiQZooe2bmfF'
WS = 'wss://archive-node.peaq.network'


def get_balance_set_event():
    payload = {
        'address': '',
        'event_id': 'balanceset',
        'module': 'balances',
        'page': 0,
        'row': 100,
    }
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    }
    response = requests.post(EVENTS_URL, json=payload, headers=headers)
    return response.json()


def get_detail_balance_set_event(event_idx):
    payload = {
        'event_index': event_idx,
    }
    headers = {
        'Content-Type': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    }
    response = requests.post(EVENT_URL, json=payload, headers=headers)
    data = response.json()
    return {
        'block_num': int(data['data']['block_num']),
        'addr': data['data']['params'][0]['value'],
        'amount': int(data['data']['params'][1]['value']),
    }


if __name__ == '__main__':
    ws = SubstrateInterface(url=WS)
    events = get_balance_set_event()
    events = events['data']['events']
    other_dict = {}
    self_lists = []
    print('event index, addr, previous balance, now balance, difference, note')
    for event in events[::-1]:
        time.sleep(1)
        data = get_detail_balance_set_event(event['event_index'])

        previous_block_hash = get_block_hash(ws, data['block_num'] - 1)
        now_block_hash = get_block_hash(ws, data['block_num'])
        addr = data['addr']
        if not addr.startswith('0x'):
            addr = f'0x{addr}'

        result = ws.query('System', 'Account', [addr], previous_block_hash)
        now_result = ws.query('System', 'Account', [addr], now_block_hash)
        diff = now_result["data"]["free"].value - result["data"]["free"].value
        event_idx = event["event_index"]
        prev_free = result["data"]["free"].value
        now_free = now_result["data"]["free"].value
        if addr == '0xbaa6e3c1c492a2324f2ce9bd7f05418597d2e8319924c54e827e52cf51b0747a' and diff == 0:
            print(f'{event_idx}, {addr}, {prev_free}, {now_free}, {data["amount"]}, sudo transfer in the same block')
        else:
            print(f'{event_idx}, {addr}, {prev_free}, {now_free}, {diff},')
