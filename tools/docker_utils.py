from python_on_whales import docker, DockerClient


PEAQ_PARACHAIN_IDS = [2000, 2241, 3338, 3013]


def _compose_partial_container_name(container_names, node_type, target):
    # yoyo-relaychain-charlie, yoyo-parachain-2241-1, yoyo-parachain-3000-0
    if node_type == 'relay':
        data = [name for name in container_names if '-relaychain-alice-' in name]
        if len(data) > 0:
            return data[0]
        else:
            raise ValueError(f'No relaychain container found in {container_names}')
    elif node_type == 'peaq':
        partial_names = [f'-parachain-{s}-{target}' for s in PEAQ_PARACHAIN_IDS]
        data = [name for name in container_names if any([f in name for f in partial_names])]
        if len(data) > 0:
            return data[0]
        raise ValueError(f'No parachain container found in {container_names}')
    elif node_type == '3rd':
        filter_name = ['-relaychain-'] + [f'-parachain-{s}-' for s in PEAQ_PARACHAIN_IDS]
        data = [name for name in container_names if not any([f in name for f in filter_name])]
        if len(data) > 0:
            return data[0]
        else:
            raise ValueError(f'No 3rd party container found in {container_names}')
    else:
        raise ValueError(f'Unknown node type {node_type}')


def get_docker_service(in_type, target=0):
    projects = docker.compose.ls()
    project = [p for p in projects if 'parachain-launch' in str(p.config_files[0])]
    if len(project) == 0 or len(project) > 1:
        raise IOError(f'Found {len(project)} parachain-launch projects, {project}')

    compose_file = str(project[0].config_files[0])
    my_docker = DockerClient(compose_files=[compose_file])
    container_name = _compose_partial_container_name(
        [container.name for container in my_docker.container.list()],
        in_type,
        target)
    container = [n for n in my_docker.container.list() if n.name == container_name]
    return container[0]
