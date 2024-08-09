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
    for event in events[::-1]:
        print(f'Event index: {event["event_index"]}')
        time.sleep(1)
        data = get_detail_balance_set_event(event['event_index'])
        if data['addr'] == SUDO_ADDR:
            previous_block_hash = get_block_hash(ws, data['block_num'] - 1)
            result = ws.query('System', 'Account', [SUDO_SUBSTRATE_ADDR], previous_block_hash)
            prev_balance = int(result['data']['free'].value)
            if prev_balance < data['amount']:
                print(f'Self: {data["addr"], data["amount"] - prev_balance}, increase')
                self_lists.append(data['amount'] - prev_balance)
            else:
                print(f'Self: {data["addr"], data["amount"] - prev_balance, data["amount"], prev_balance}, decrease')
                # Add because it reset value
                self_lists.append(data['amount'])
        else:
            if data['addr'] not in other_dict:
                print(f'Other: {data["addr"], data["amount"]}, not exist')
            else:
                print(f'Other: {data["addr"], data["amount"]}, exists...')
            other_dict[data['addr']] = data['amount']
    print(f'Set total event number: {len(events)}')
    print(f'All setup balance: {sum(other_dict.values()) / 10 ** 18 + sum(self_lists) / 10 ** 18} Krest')
    print(f'Self: {sum(self_lists) / 10 ** 18} Krest')
    print(f'Other: {sum(other_dict.values()) / 10 ** 18} Krest')
