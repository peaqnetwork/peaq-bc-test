import warnings
# Ignore warnings about config keys changing in V2 from the python_on_whales
warnings.filterwarnings("ignore", "Valid config keys have changed in V2")

import sys
sys.path.append('.')

import time
from python_on_whales import docker, DockerClient
from substrateinterface import SubstrateInterface
from tools.constants import WS_URL
from tools.constants import BLOCK_GENERATE_TIME
from websocket import WebSocketConnectionClosedException


def restart_parachain_launch():
    projects = docker.compose.ls()
    project = [p for p in projects if 'parachain-launch' in str(p.config_files[0]) or 'yoyo' == p.name]
    if len(project) == 0 or len(project) > 1:
        raise IOError(f'Found {len(project)} parachain-launch projects, {project}')

    compose_file = str(project[0].config_files[0])
    my_docker = DockerClient(compose_files=[compose_file])

    my_docker.compose.down(volumes=True)
    my_docker.compose.up(detach=True, build=True)
    count_down = 0
    wait_time = 150
    while count_down < wait_time:
        try:
            SubstrateInterface(
                url=WS_URL,
            )
            # Let us wait longer
            time.sleep(BLOCK_GENERATE_TIME * 3)
            return
        except (ConnectionResetError, WebSocketConnectionClosedException) as e:
            print(f'Cannot connect to {WS_URL}, {e}')
            count_down += 5
            time.sleep(BLOCK_GENERATE_TIME)
            continue
        except Exception:
            raise IOError(f'Cannot connect to {WS_URL}')
    raise IOError(f'Cannot connect to {WS_URL} after {wait_time} seconds')


if __name__ == '__main__':
    restart_parachain_launch()
