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

DEFAULT_COLLATOR_PATH = os.path.join(
    os.path.expanduser('~'), 'Work', 'peaq', 'peaq-network-node', 'target', 'release', 'peaq-node')
DEFAULT_BINARY_CHAIN_PATH = os.path.join(
    os.path.expanduser('~'), 'Work', 'peaq', 'peaq-network-node', 'collator')
DEFAULT_DOCKER_COMPOSE_FOLDER = os.path.join(
    os.path.expanduser('~'), 'Work', 'peaq', 'parachain-launch', 'yoyo')

# Runtime upgrade constants
UPGRADE_WAIT_BLOCKS = 15
DEFAULT_BLOCK_TIME = 12  # seconds per block
UPGRADE_TIMEOUT = UPGRADE_WAIT_BLOCKS * DEFAULT_BLOCK_TIME
POST_UPGRADE_WAIT_TIME = DEFAULT_BLOCK_TIME * 5

# Balance constants (in Wei)
MIN_BALANCE_THRESHOLD = 1 * 10 ** 18
TRANSFER_AMOUNT = 3 * 10 ** 18
SUDO_MIN_BALANCE = 0.5 * 10 ** 18
FUNDING_AMOUNT_BASE = 302231 * 10 ** 18

# Collator constants
COLLATOR_STOP_WAIT_TIME = 12  # seconds
COLLATOR_START_WAIT_TIME = 120  # seconds
POLL_INTERVAL = 1  # seconds

# Network ports
FORK_COLLATOR_PORT = 10044
PARACHAIN_PORT = 40333
RELAYCHAIN_PORT = 50345
RPC_PORT = 30055

# XCM configuration
XCM_VERSION = 4
RELAY_ASSET_ID = 1

DEFAULT_COLLATOR_DICT = {
    'collator_binary': None,
    'chain_data': None,
    'enable_collator_binary': False,
    'docker_compose_folder': None,
}
