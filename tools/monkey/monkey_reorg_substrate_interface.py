from substrateinterface.exceptions import SubstrateRequestException
from scalecodec.types import GenericExtrinsic
from substrateinterface.base import ExtrinsicReceipt


def monkey_submit_extrinsic(self, extrinsic: GenericExtrinsic, wait_for_inclusion: bool = False,
                            wait_for_finalization: bool = False) -> "ExtrinsicReceipt":

    """
    Submit an extrinsic to the connected node, with the possibility to wait until the extrinsic is included
     in a block and/or the block is finalized. The receipt returned provided information about the block and
     triggered events

    Parameters
    ----------
    extrinsic: Extrinsic The extrinsic to be sent to the network
    wait_for_inclusion: wait until extrinsic is included in a block (only works for websocket connections)
    wait_for_finalization: wait until extrinsic is finalized (only works for websocket connections)

    Returns
    -------
    ExtrinsicReceipt

    """

    # Check requirements
    if not isinstance(extrinsic, GenericExtrinsic):
        raise TypeError("'extrinsic' must be of type Extrinsics")

    def result_handler(message, update_nr, subscription_id):
        if 'params' in message and message['params']['result'] == 'invalid':
            self.rpc_request('author_unwatchExtrinsic', [subscription_id])
            raise SubstrateRequestException(f'{message} inavlid')

        # Check if extrinsic is included and finalized
        if 'params' in message and type(message['params']['result']) is dict:

            # Convert result enum to lower for backwards compatibility
            message_result = {k.lower(): v for k, v in message['params']['result'].items()}

            if 'finalized' in message_result and wait_for_finalization:
                self.rpc_request('author_unwatchExtrinsic', [subscription_id])
                return {
                    'block_hash': message_result['finalized'],
                    'extrinsic_hash': '0x{}'.format(extrinsic.extrinsic_hash.hex()),
                    'finalized': True
                }
            elif 'inblock' in message_result and wait_for_inclusion and not wait_for_finalization:
                self.rpc_request('author_unwatchExtrinsic', [subscription_id])
                return {
                    'block_hash': message_result['inblock'],
                    'extrinsic_hash': '0x{}'.format(extrinsic.extrinsic_hash.hex()),
                    'finalized': False
                }

    if wait_for_inclusion or wait_for_finalization:
        response = self.rpc_request(
            "author_submitAndWatchExtrinsic",
            [str(extrinsic.data)],
            result_handler=result_handler
        )

        result = ExtrinsicReceipt(
            substrate=self,
            extrinsic_hash=response['extrinsic_hash'],
            block_hash=response['block_hash'],
            finalized=response['finalized']
        )

    else:

        response = self.rpc_request("author_submitExtrinsic", [str(extrinsic.data)])

        if 'result' not in response:
            raise SubstrateRequestException(response.get('error'))

        result = ExtrinsicReceipt(
            substrate=self,
            extrinsic_hash=response['result']
        )

    return result
