import logging
import requests
from jsonrpcclient.responses import Ok, parse
from jsonrpcclient.requests import request
from typing import Any, Dict, Tuple, Union, Optional
from warnet.warnetd import WARNETD_PORT

logger = logging.getLogger(__name__)


def rpc_call(rpc_method, params: Optional[Union[Dict[str, Any], Tuple[Any, ...]]]):
    payload = request(rpc_method, params)
    logger.debug(f"Constructed rpc call: {payload}")
    response = requests.post(f"http://localhost:{WARNETD_PORT}/api", json=payload)
    logger.debug(f"RPC respose: {response.status_code}, {response.text}")
    parsed = parse(response.json())

    if isinstance(parsed, Ok):
        return parsed.result
    else:
        error_message = getattr(parsed, 'message', 'Unknown RPC error')
        raise Exception(error_message)

