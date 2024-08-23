from substrateinterface import SubstrateInterface
import datetime
import time
from tools.constants import BLOCK_GENERATIME_TIME


WS = 'wss://docker-test.peaq.network'

while 1:
    before = datetime.datetime.now()
    substrate = SubstrateInterface(
        url=WS,
    )
    substrate.get_block_metadata()
    after = datetime.datetime.now()
    print(f'{after}: {after - before}')
    time.sleep(BLOCK_GENERATIME_TIME)
    substrate.close()
