import unittest
import pytest

from substrateinterface import SubstrateInterface
from tools.constants import WS_URL


@pytest.mark.substrate
class TestMetadata(unittest.TestCase):
    def setUp(self):
        self.substrate = SubstrateInterface(url=WS_URL)

    def test_check_meta(self):
        metadata = self.substrate.get_block_metadata()
        self.assertTrue('frame_metadata_hash_extension' in str(metadata.value))
        self.assertTrue('CheckMetadataHash' in str(metadata.value))
