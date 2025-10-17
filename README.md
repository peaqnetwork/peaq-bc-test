# peaq-bc-test

- [Introduction](#introduction)
- [Preparation](#preparation)
- [EVM Migration Tests](#evm-migration-tests)
- [Limitation](#limitation)
- [QA](#QA)

# Introduction

This project is used for the integration test on the peaq's parachain/standalone chain. Therefore, several fundamental functionalities tests are included.

# Preparation

1. Install the related library. If you want, you can use the virtual environment to install your libraries.

```
python3 -m venv ~/venv.test
source ~/venv.test/bin/activate
pip3 install -r requirements.txt
```
2. Please run the peaq parachain/standalone on your local machine if you want. You can follow the [parachain-launch](https://github.com/peaqnetwork/parachain-launch) to launch the parachain.
3. Change the related URL in the tools/utils.py.

3.1. Please change the WS URL for the targeted parachain/standalone chain. For example:
```
WS_URL =  'ws://127.0.0.1:9947'
```
3.2. Please change the RPC URL for your targeted parachain/standalone chain.
```
ETH_URL = 'http://127.0.0.1:9936'
```
4. Run the integration test
```
pytest
```

# Runtime upgrade test
```
RUNTIME_UPGRADE_PATH=~/PublicSMB/peaq_dev_runtime.compact.compressed.0.0.8.wasm python3 tools/runtime_upgrade.py
RUNTIME_UPGRADE_PATH=~/PublicSMB/peaq_dev_runtime.compact.compressed.0.0.8.wasm pytest
```

# EVM Migration Tests

The EVM migration test suite provides comprehensive validation of EVM functionality during runtime upgrades. Tests are organized into 5 specialized files covering 19 different smart contracts.

## Test Structure

### 📁 Test Files
- **`evm_migration_tokens_test.py`** - Token standards (ERC20, ERC721, ERC1155)
- **`evm_migration_calls_test.py`** - Call operations (DelegateCall, CallTest, Reentry, Calldata)
- **`evm_migration_storage_test.py`** - Storage operations (Storage, Upgrade, Struct)
- **`evm_migration_precompile_test.py`** - Precompile operations (ecrecover, sha256, etc.)
- **`evm_migration_advanced_test.py`** - Advanced features (Events, Gas, EIP-1153, EIP-5656)

### 🧪 Test Execution Modes
1. **Pre-Migration Tests**: Validate functionality before runtime upgrade
2. **Post-Migration Tests**: Verify consistency after runtime upgrade with automatic comparison

## Running EVM Migration Tests

### Run All Migration Tests
```bash
pytest tests/evm_migration_*_test.py -v -m eth
```

### Run Specific Categories
```bash
# Token standards testing
pytest tests/evm_migration_tokens_test.py -v

# Call operations testing
pytest tests/evm_migration_calls_test.py -v

# Storage operations testing
pytest tests/evm_migration_storage_test.py -v

# Precompile operations testing
pytest tests/evm_migration_precompile_test.py -v

# Advanced features testing
pytest tests/evm_migration_advanced_test.py -v
```

### Run Individual Tests
```bash
# Test specific contract before migration
pytest tests/evm_migration_tokens_test.py::TestEVMTokensMigration::test_erc20_before_migration -v

# Test with runtime upgrade
RUNTIME_UPGRADE_PATH=~/path/to/runtime.wasm pytest tests/evm_migration_tokens_test.py::TestEVMTokensMigration::test_erc20_after_migration -v
```

### View Test Output
```bash
# See detailed output including print statements
pytest tests/evm_migration_advanced_test.py -v -s
```

## Gas Tolerance Mechanism

The framework includes **smart gas tolerance handling** for tests sensitive to gas cost changes:

- **Gas-sensitive tests**: EIP-1153 (transient storage), EIP-5656 (MCOPY), gas consumption tests
- **Behavior**: Compares all functional fields while ignoring gas-related fields
- **Logging**: Reports gas changes as informational (not failures)

**Example Output:**
```
✅ Gas changes detected in transient_storage_tests (expected behavior):
   total_gas_used: 136152 → 116252 (-14.6%)
```

**Why needed**: Gas costs legitimately change during runtime upgrades due to optimizations and EVM improvements.

## Test Coverage

| Category | Contracts | Coverage |
|----------|-----------|----------|
| **Token Standards** | ERC20, ERC721, ERC1155 | Standard token operations, minting, transfers |
| **Call Operations** | DelegateCall, CallTest, Reentry, Calldata | Proxy patterns, reentrancy protection, data handling |
| **Storage** | Storage, Upgrade, Struct | State persistence, upgradeable contracts, complex data |
| **Precompiles** | Standard Ethereum precompiles | ecrecover, sha256, ripemd160, identity, modexp |
| **Advanced** | Events, Gas, EIP-1153, EIP-5656 | Logging, optimization, transient storage, MCOPY |

## Migration Testing Flow

1. **Setup**: Deploy contracts and fund test accounts
2. **Pre-Migration**: Execute and store baseline behavior
3. **Runtime Upgrade**: Perform blockchain runtime upgrade
4. **Post-Migration**: Re-execute and compare with baseline
5. **Validation**: Ensure functional consistency (with gas tolerance)

For detailed information, see [EVM_MIGRATION_TESTS_README.md](tests/EVM_MIGRATION_TESTS_README.md).

## Trade-offs and Performance Considerations

**Sequential Execution Required:**
- EVM migration tests **cannot run in parallel** due to shared parachain instance
- Each test file performs `restart_with_setup()` = full parachain restart
- Running all 5 files = 5 separate parachain restarts

**Time Implications:**
- Total time = (5 × parachain_restart_time) + actual_test_time
- Each restart includes blockchain initialization, genesis setup, funding accounts
- Consider this when planning CI/CD pipeline timing

**Recommended Usage:**
- **Development**: Run individual files (`pytest tests/evm_migration_tokens_test.py`)
- **CI/CD**: Run full suite sequentially for comprehensive validation
- **Debugging**: Target specific domains to reduce restart overhead

# Limitation
1. In the peaq network, the standalone chain and parachain have different features and parameters; therefore, some tests may not pass, for example, the block creation time test and DID RPC test.
2. This project requires the dependent libraries whose version is higher than 0.9.29 because of the weight structure.
3. In the current implementation, the related account (Alice/Bob/Alice//stash/Bob//stash) should have enough tokens; otherwise, the test cases will fail. It means we can only directly run the integration test for Agung/Krest network in the local environment after we change the genesis settings, but not in the production environment.
4. This project can only test the peaq related chain. If we run for the rococo chain, some runtime errors happen.
5. In the future, we should refine these integration tests.

# QA
1. If you enounter the issue when installing the dependant library
```
  ERROR: Command errored out with exit status 1:
   command: /home/jaypan/venv.test/bin/python3 -u -c 'import sys, setuptools, tokenize; sys.argv[0] = '"'"'/tmp/pip-install-6gjnxc
vd/parsimonious/setup.py'"'"'; __file__='"'"'/tmp/pip-install-6gjnxcvd/parsimonious/setup.py'"'"';f=getattr(tokenize, '"'"'open'"'
"', open)(__file__);code=f.read().replace('"'"'\r\n'"'"', '"'"'\n'"'"');f.close();exec(compile(code, __file__, '"'"'exec'"'"'))' b
dist_wheel -d /tmp/pip-wheel-dolzicpn
       cwd: /tmp/pip-install-6gjnxcvd/parsimonious/
  Complete output (6 lines):
  usage: setup.py [global_opts] cmd1 [cmd1_opts] [cmd2 [cmd2_opts] ...]
     or: setup.py --help [cmd1 cmd2 ...]                                                                                               or: setup.py --help-commands                                                                                                      or: setup.py cmd --help                                                                                                                                                                                                                                          error: invalid command 'bdist_wheel'
  ----------------------------------------
  ERROR: Failed building wheel for parsimonious
```

Solution: Please install the wheel and reinstall the dependency library again. [Ref](https://stackoverflow.com/questions/34819221/why-is-python-setup-py-saying-invalid-command-bdist-wheel-on-travis-ci)
```
pip3 install wheel
pip3 install -r requirements.txt
```

# Enviroment parameter
- RUNTIME_UPGRADE_PATH: The runtime upgrade path. If we want to test the runtime upgrade, we should set this parameter.

# Stress tools
```
python3 tools/stress/stress_token_economy_v2.py -r wss://docker-test.peaq.network --test-session-num 10 -t distribution
python3 tools/stress/stress_token_economy_v2.py -r wss://docker-test.peaq.network --test-session-num 10 -t validator
python3 tools/stress/stress_token_economy_v2.py -r wss://docker-test.peaq.network --test-session-num 10 -t traverse    
```
