import os
from substrateinterface import Keypair

BLOCK_GENERATE_TIME = 6

TOKEN_NUM_BASE = pow(10, 3)
TOKEN_NUM_BASE_DEV = pow(10, 18)
RELAYCHAIN_WS_URL = 'ws://127.0.0.1:9944'
STANDALONE_WS_URL = 'ws://127.0.0.1:9944'

PARACHAIN_WS_URL = 'ws://127.0.0.1:10044'
ACA_WS_URL = 'ws://127.0.0.1:10144'
RELAYCHAIN_ETH_URL = 'http://127.0.0.1:9933'
PARACHAIN_ETH_URL = 'http://127.0.0.1:10044'
ACA_ETH_URL = 'http://127.0.0.1:10144'
# PARACHAIN_WS_URL = 'wss://wsspc1.agung.peaq.network'
# PARACHAIN_ETH_URL = 'https://rpcpc1.agung.peaq.network'
# WS_URL = 'ws://127.0.0.1:9944'
# ETH_URL = 'http://127.0.0.1:9933'
AUTOTEST_URI = os.environ.get('AUTOTEST_URI')
ETH_TIMEOUT = 6 * 5

if AUTOTEST_URI:
    PARACHAIN_WS_URL = 'wss://' + AUTOTEST_URI
    PARACHAIN_ETH_URL = 'https://' + AUTOTEST_URI

WS_URL = PARACHAIN_WS_URL
ETH_URL = PARACHAIN_ETH_URL

# WS_URL = 'ws://192.168.178.23:9944'
# ETH_URL = 'http://192.168.178.23:9933'
# WS_URL = 'wss://wss.test.peaq.network'
# ETH_URL = 'https://erpc.test.peaq.network:443'
URI_GLOBAL_SUDO = '//Alice'
KP_GLOBAL_SUDO = Keypair.create_from_uri(URI_GLOBAL_SUDO)
KP_COLLATOR = Keypair.create_from_uri('//Ferdie')
ACA_PD_CHAIN_ID = 3000
