import functools
import ipaddress
import json
import logging
import os
import random
import re
import stat
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

from test_framework.messages import ser_uint256
from test_framework.p2p import MESSAGEMAP

logger = logging.getLogger("utils")


class NonErrorFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool | logging.LogRecord:
        return record.levelno <= logging.INFO


def exponential_backoff(max_retries=5, base_delay=1, max_delay=32):
    """
    A decorator for exponential backoff.

    Parameters:
    - max_retries: Maximum number of retries before giving up.
    - base_delay: Initial delay in seconds.
    - max_delay: Maximum delay in seconds.
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            retries = 0
            while retries < max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    error_msg = str(e).replace("\n", " ").replace("\t", " ")
                    logger.error(f"rpc error: {error_msg}")
                    retries += 1
                    if retries == max_retries:
                        raise e
                    delay = min(base_delay * (2**retries), max_delay)
                    logger.warning(f"exponential_backoff: retry in {delay} seconds...")
                    time.sleep(delay)

        return wrapper

    return decorator


def handle_json(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = ""
        try:
            result = func(*args, **kwargs)
            logger.debug(f"{result=:}")
            if isinstance(result, dict):
                return result
            parsed_result = json.loads(result)
            return parsed_result
        except json.JSONDecodeError as e:
            logging.error(
                f"JSON parsing error in {func.__name__}: {e}. Undecodable result: {result}"
            )
            raise
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            raise

    return wrapper


def get_architecture():
    """
    Get the architecture of the machine.
    :return: The architecture of the machine or None if an error occurred
    """
    result = subprocess.run(["uname", "-m"], stdout=subprocess.PIPE)
    arch = result.stdout.decode("utf-8").strip()
    if arch == "x86_64":
        arch = "amd64"
    if arch is None:
        raise Exception("Failed to detect architecture.")
    return arch


def generate_ipv4_addr(subnet):
    """
    Generate a valid random IPv4 address within the given subnet.

    :param subnet: Subnet in CIDR notation (e.g., '100.0.0.0/8')
    :return: Random IP address within the subnet
    """
    reserved_ips = [
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.0.0.0/24",
        "192.0.2.0/24",
        "192.88.99.0/24",
        "192.168.0.0/16",
        "198.18.0.0/15",
        "198.51.100.0/24",
        "203.0.113.0/24",
        "224.0.0.0/4",
    ]

    def is_public(ip):
        for reserved in reserved_ips:
            if ipaddress.ip_address(ip) in ipaddress.ip_network(reserved, strict=False):
                return False
        return True

    network = ipaddress.ip_network(subnet, strict=False)

    # Generate a random IP within the subnet range
    while True:
        ip_int = random.randint(int(network.network_address), int(network.broadcast_address))
        ip_str = str(ipaddress.ip_address(ip_int))
        if is_public(ip_str):
            return ip_str


def sanitize_tc_netem_command(command: str) -> bool:
    """
    Sanitize the tc-netem command to ensure it's valid and safe to execute, as we run it as root on a container.

    Args:
    - command (str): The tc-netem command to sanitize.

    Returns:
    - bool: True if the command is valid and safe, False otherwise.
    """
    if not command.startswith("tc qdisc add dev eth0 root netem"):
        return False

    tokens = command.split()[7:]  # Skip the prefix

    # Valid tc-netem parameters and their patterns
    valid_params = {
        "delay": r"^\d+ms(\s\d+ms)?(\sdistribution\s(normal|pareto|paretonormal|uniform))?$",
        "loss": r"^\d+(\.\d+)?%$",
        "duplicate": r"^\d+(\.\d+)?%$",
        "corrupt": r"^\d+(\.\d+)?%$",
        "reorder": r"^\d+(\.\d+)?%\s\d+(\.\d+)?%$",
        "rate": r"^\d+(kbit|mbit|gbit)$",
    }

    # Validate each param
    i = 0
    while i < len(tokens):
        param = tokens[i]
        if param not in valid_params:
            return False
        i += 1
        value_tokens = []
        while i < len(tokens) and tokens[i] not in valid_params:
            value_tokens.append(tokens[i])
            i += 1
        value = " ".join(value_tokens)
        if not re.match(valid_params[param], value):
            return False

    return True


def to_jsonable(obj):
    HASH_INTS = [
        "blockhash",
        "block_hash",
        "hash",
        "hashMerkleRoot",
        "hashPrevBlock",
        "hashstop",
        "prev_header",
        "sha256",
        "stop_hash",
    ]

    HASH_INT_VECTORS = [
        "hashes",
        "headers",
        "vHave",
        "vHash",
    ]

    if hasattr(obj, "__dict__"):
        return obj.__dict__
    elif hasattr(obj, "__slots__"):
        ret = {}  # type: Any
        for slot in obj.__slots__:
            val = getattr(obj, slot, None)
            if slot in HASH_INTS and isinstance(val, int):
                ret[slot] = ser_uint256(val).hex()
            elif slot in HASH_INT_VECTORS and all(isinstance(a, int) for a in val):
                ret[slot] = [ser_uint256(a).hex() for a in val]
            else:
                ret[slot] = to_jsonable(val)
        return ret
    elif isinstance(obj, list):
        return [to_jsonable(a) for a in obj]
    elif isinstance(obj, bytes):
        return obj.hex()
    else:
        return obj


# This function is a hacked-up copy of process_file() from
# Bitcoin Core contrib/message-capture/message-capture-parser.py
def parse_raw_messages(blob, outbound):
    TIME_SIZE = 8
    LENGTH_SIZE = 4
    MSGTYPE_SIZE = 12

    messages = []
    offset = 0
    while True:
        # Read the Header
        header_len = TIME_SIZE + LENGTH_SIZE + MSGTYPE_SIZE
        tmp_header_raw = blob[offset : offset + header_len]

        offset = offset + header_len
        if not tmp_header_raw:
            break
        tmp_header = BytesIO(tmp_header_raw)
        time = int.from_bytes(tmp_header.read(TIME_SIZE), "little")  # type: int
        msgtype = tmp_header.read(MSGTYPE_SIZE).split(b"\x00", 1)[0]  # type: bytes
        length = int.from_bytes(tmp_header.read(LENGTH_SIZE), "little")  # type: int

        # Start converting the message to a dictionary
        msg_dict = {}
        msg_dict["outbound"] = outbound
        msg_dict["time"] = time
        msg_dict["size"] = length  # "size" is less readable here, but more readable in the output

        msg_ser = BytesIO(blob[offset : offset + length])
        offset = offset + length

        # Determine message type
        if msgtype not in MESSAGEMAP:
            # Unrecognized message type
            try:
                msgtype_tmp = msgtype.decode()
                if not msgtype_tmp.isprintable():
                    raise UnicodeDecodeError
                msg_dict["msgtype"] = msgtype_tmp
            except UnicodeDecodeError:
                msg_dict["msgtype"] = "UNREADABLE"
            msg_dict["body"] = msg_ser.read().hex()
            msg_dict["error"] = "Unrecognized message type."
            messages.append(msg_dict)
            print(f"WARNING - Unrecognized message type {msgtype}", file=sys.stderr)
            continue

        # Deserialize the message
        msg = MESSAGEMAP[msgtype]()
        msg_dict["msgtype"] = msgtype.decode()

        try:
            msg.deserialize(msg_ser)
        except KeyboardInterrupt:
            raise
        except Exception:
            # Unable to deserialize message body
            msg_ser.seek(0, os.SEEK_SET)
            msg_dict["body"] = msg_ser.read().hex()
            msg_dict["error"] = "Unable to deserialize message."
            messages.append(msg_dict)
            print("WARNING - Unable to deserialize message", file=sys.stderr)
            continue

        # Convert body of message into a jsonable object
        if length:
            msg_dict["body"] = to_jsonable(msg)
        messages.append(msg_dict)
    return messages


def gen_config_dir(network: str) -> Path:
    """
    Determine a config dir based on network name
    """
    config_dir = os.getenv("XDG_CONFIG_HOME", os.path.expanduser("~/.warnet"))
    config_dir = Path(config_dir) / "warnet" / network
    return config_dir


def remove_version_prefix(version_str):
    if version_str.startswith("0."):
        return version_str[2:]
    return version_str


def set_execute_permission(file_path):
    current_permissions = os.stat(file_path).st_mode
    os.chmod(file_path, current_permissions | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def policy_match(pol1, pol2):
    return (
        max(int(pol1["time_lock_delta"]), 18) == max(int(pol2["time_lock_delta"]), 18)
        and max(int(pol1["min_htlc"]), 1) == max(int(pol2["min_htlc"]), 1)
        and pol1["fee_base_msat"] == pol2["fee_base_msat"]
        and pol1["fee_rate_milli_msat"] == pol2["fee_rate_milli_msat"]
        # Ignoring this for now since we use capacity/2
        # and pol1["max_htlc_msat"] == pol2["max_htlc_msat"]
    )


def channel_match(ch1, ch2, allow_flip=False):
    if ch1["capacity"] != ch2["capacity"]:
        return False
    if policy_match(ch1["node1_policy"], ch2["node1_policy"]) and policy_match(
        ch1["node2_policy"], ch2["node2_policy"]
    ):
        return True
    if not allow_flip:
        return False
    else:
        return policy_match(ch1["node1_policy"], ch2["node2_policy"]) and policy_match(
            ch1["node2_policy"], ch2["node1_policy"]
        )
