import argparse
from substrateinterface import SubstrateInterface
from datetime import datetime, timezone, timedelta
import pprint
from colorama import Fore, Style, init


pp = pprint.PrettyPrinter(indent=4)

# Initialize colorama (important for Windows compatibility)
init(autoreset=True)


# Average block time for Substrate chains (6 seconds as requested)
AVERAGE_BLOCK_TIME_SECONDS = 6


def get_block_timestamp(
    substrate: SubstrateInterface,
    block_number: int,
    current_block_number: int,
    current_block_time: datetime
):
    """
    Retrieves the timestamp of a given block number. If the block has not yet occurred,
    it estimates the time based on the average block time.

    Args:
        substrate (SubstrateInterface): The SubstrateInterface instance.
        block_number (int): The block number to query or estimate.
        current_block_number (int): The current latest block number on the chain.
        current_block_time (datetime): The datetime of the current latest block.

    Returns:
        datetime.datetime: The datetime object representing the block's timestamp in local time,
                           or None if an unrecoverable error occurs.
    """
    if block_number <= current_block_number:
        # Block has already occurred, get actual timestamp
        try:
            block_hash = substrate.get_block_hash(block_id=block_number)
            if not block_hash:
                # This warning is kept as it indicates a potential issue even
                # if block number is theoretically valid
                print(f"Warning: Could not get block hash for block number "
                      f"{block_number} (even though it's <= current).")
                return None

            timestamp_ms = substrate.query(
                module='Timestamp',
                storage_function='Now',
                block_hash=block_hash,
            ).value
            # Convert to local timezone
            utc_datetime = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc)
            return utc_datetime.astimezone()
        except Exception as e:
            print(f"Error getting actual timestamp for block {block_number}: {e}")
            return None
    else:
        # Block has not occurred, estimate time
        blocks_to_future = block_number - current_block_number
        estimated_time_delta = timedelta(seconds=blocks_to_future * AVERAGE_BLOCK_TIME_SECONDS)
        # Ensure it's in local timezone
        estimated_datetime = current_block_time + estimated_time_delta
        return estimated_datetime.astimezone()


def print_session_times(
    substrate: SubstrateInterface,
    session_name: str,
    base_block: int,
    current_block_number: int,
    current_block_time_local: datetime
):
    """
    Helper function to print times for a specific session's base block, +100, and +1500.
    """
    print(f"\n--- {session_name} Session (Base Block: {base_block}) ---")

    # Get timestamp for base block (no color)
    base_block_time = get_block_timestamp(
        substrate, base_block, current_block_number, current_block_time_local
    )
    if base_block_time:
        formatted_time = base_block_time.strftime('%Y-%m-%d %H:%M:%S %Z%z')
        print(f"Local time for base block ({base_block}): {formatted_time}")

    # Get timestamp for base + 100 block (yellow color)
    block_plus_100 = base_block + 100
    time_plus_100 = get_block_timestamp(
        substrate, block_plus_100, current_block_number, current_block_time_local
    )
    if time_plus_100:
        status = " (Actual Time)" if block_plus_100 <= current_block_number else \
                 " (Estimated Time)"
        formatted_time = time_plus_100.strftime('%Y-%m-%d %H:%M:%S %Z%z')
        print(f"Local time for block {block_plus_100} (+100): "
              f"{Fore.YELLOW}{formatted_time}{Style.RESET_ALL}{status}")

    # Get timestamp for base + 1500 block (yellow color)
    block_plus_1500 = base_block + 1500
    time_plus_1500 = get_block_timestamp(
        substrate, block_plus_1500, current_block_number, current_block_time_local
    )
    if time_plus_1500:
        status = " (Actual Time)" if block_plus_1500 <= current_block_number else \
                 " (Estimated Time)"
        formatted_time = time_plus_1500.strftime('%Y-%m-%d %H:%M:%S %Z%z')
        print(f"Local time for block {block_plus_1500} (+1500): "
              f"{Fore.YELLOW}{formatted_time}{Style.RESET_ALL}{status}")


def get_parachain_staking_round(url: str):
    """
    Connects to a Substrate node, retrieves ParachainStaking Round information,
    and then calculates and prints local times for three consecutive sessions.
    Connection and query messages are suppressed.

    Args:
        url (str): The WebSocket URL of the Substrate node.

    Returns:
        dict: A dictionary containing the Round information of the first session,
              or None if an error occurs.
    """
    try:
        substrate = SubstrateInterface(url=url)

        current_block_number = substrate.get_block_number(None)
        current_block_hash = substrate.get_block_hash()
        current_timestamp_ms = substrate.query(
            module='Timestamp',
            storage_function='Now',
            block_hash=current_block_hash,
        ).value
        current_block_time_utc = datetime.fromtimestamp(current_timestamp_ms / 1000, tz=timezone.utc)
        current_block_time_local = current_block_time_utc.astimezone()

        # Query ParachainStaking.Round storage
        parachain_staking_round_data = substrate.query(
            module='ParachainStaking',
            storage_function='Round',
        ).value  # Directly get the value if query is successful

        # Check if the query returned valid data
        if parachain_staking_round_data:
            print("\nParachainStaking Round Information (Current Session):")
            pp.pprint(parachain_staking_round_data)

            first_block_current_session = parachain_staking_round_data['first']
            length_current_session = parachain_staking_round_data['length']

            # Print times for Current Session
            print_session_times(
                substrate, "Current",
                first_block_current_session,
                current_block_number,
                current_block_time_local
            )

            # Calculate and print times for Next Session
            first_block_next_session = first_block_current_session + length_current_session
            print_session_times(
                substrate, "Next",
                first_block_next_session,
                current_block_number,
                current_block_time_local
            )

            # Calculate and print times for Two Sessions Ahead
            # We assume the length of the next session is the same as the current one for estimation
            first_block_two_sessions_ahead = first_block_next_session + length_current_session
            print_session_times(
                substrate, "Two Sessions Ahead",
                first_block_two_sessions_ahead,
                current_block_number,
                current_block_time_local
            )

            return parachain_staking_round_data
        else:
            # This block handles the case where round_info.value might be empty or
            # not what's expected (though substrate.query typically raises an
            # exception for true failures)
            print("Error: Could not retrieve valid ParachainStaking.Round information.")
            return None

    except ConnectionRefusedError:
        print(f"Error: Connection to {url} was refused. "
              f"Please ensure the node is running and accessible.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Get ParachainStaking Round information and calculate block '
                    'times for 3 sessions from a Substrate chain.'
    )
    parser.add_argument(
        '-u', '--url', type=str, required=True,
        help='The WebSocket URL of the Substrate node (e.g., ws://127.0.0.1:9944)'
    )

    args = parser.parse_args()

    get_parachain_staking_round(args.url)
