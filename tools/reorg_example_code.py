import sys

sys.path.append("./")
import time
import importlib

from substrateinterface import SubstrateInterface, Keypair
from tools.constants import WS_URL
from peaq.utils import ExtrinsicBatch
from peaq.did import did_add_payload

from tools.monkey.monkey_3rd_substrate_interface import monkey_submit_extrinsic

SubstrateInterface.submit_extrinsic = monkey_submit_extrinsic

from tools.monkey.monkey_reorg_batch import monkey_execute_extrinsic_batch

ExtrinsicBatch._execute_extrinsic_batch = monkey_execute_extrinsic_batch


if "substrateinterface" in sys.modules:
    importlib.reload(sys.modules["substrateinterface"])
if "peaq.utils" in sys.modules:
    importlib.reload(sys.modules["peaq.utils"])


if __name__ == "__main__":
    substrate = SubstrateInterface(url=WS_URL)
    kp_src = Keypair.create_from_uri("//Alice")

    batch = ExtrinsicBatch(substrate, kp_src)

    key = f"0x{int(time.time())}"
    value = "0x02"
    did_add_payload(batch, kp_src.ss58_address, key, value)
    receipt = batch.execute_n_clear()

    print(
        f"After batch: {receipt.extrinsic_hash}, {receipt.get_extrinsic_identifier()}"
    )
