import pytest
import unittest
from substrateinterface import SubstrateInterface, Keypair
from tools.utils import get_existential_deposit
from tools.constants import WS_URL


@pytest.mark.substrate
@pytest.mark.skip(reason="Only test for the charging simulator")
class TestExitentialDeposits(unittest.TestCase):
    def get_existential_deposit(self):
        return get_existential_deposit(self.substrate)

    def setUp(self):
        self.substrate = SubstrateInterface(url=WS_URL,)
        self.alice = Keypair.create_from_uri('//Alice')
        self.kp = Keypair.create_from_mnemonic(Keypair.generate_mnemonic())

    def test_local_token(self):
        token = self.get_existential_deposit()
        self.assertEqual(token, 0)
