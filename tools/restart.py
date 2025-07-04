import warnings
# Ignore warnings about config keys changing in V2 from the python_on_whales
warnings.filterwarnings("ignore", "Valid config keys have changed in V2")

import sys
sys.path.append('.')

import time
from python_on_whales import docker, DockerClient
from substrateinterface import SubstrateInterface
from tools.constants import WS_URL, PARACHAIN_WS_URL, ACA_WS_URL
from tools.constants import BLOCK_GENERATE_TIME
from websocket import WebSocketConnectionClosedException
from tools.coretime_utils import get_parachain_id, setup_coretime


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
    wait_time = 120
    while count_down < wait_time:
        try:
            SubstrateInterface(
                url=WS_URL,
            )
            # Let us wait longer
            time.sleep(BLOCK_GENERATE_TIME * 3)

            # Setup coretime for both parachains
            # First parachain at port 10044
            parachain_id_1 = get_parachain_id(PARACHAIN_WS_URL)
            if parachain_id_1:
                print(f"Setting up coretime for parachain {parachain_id_1} (port 10044)")
                setup_coretime(parachain_id_1, start_core=0)
            else:
                print("Warning: Failed to get parachain ID for port 10044")

            # Second parachain at port 10144 - start after first parachain's cores
            parachain_id_2 = get_parachain_id(ACA_WS_URL)
            if parachain_id_2:
                # Determine how many cores the first parachain should have
                from tools.constants import PARACHAIN_CORE_MAP, CORETIME_CORES
                expected_cores_1 = PARACHAIN_CORE_MAP.get(parachain_id_1, CORETIME_CORES) if parachain_id_1 else 0
                start_core_2 = expected_cores_1  # Start where first parachain's allocation ends

                print(f"Setting up coretime for parachain {parachain_id_2} (port 10144) starting at core {start_core_2}")
                setup_coretime(parachain_id_2, start_core=start_core_2)
            else:
                print("Warning: Failed to get parachain ID for port 10144")

            if not parachain_id_1 and not parachain_id_2:
                raise IOError("Failed to get any parachain IDs - cannot proceed without coretime setup")

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
