import json
from typing import Any

from pydantic_core import to_jsonable_python


def get_json_line(json_dict: dict) -> str:
    # to_jsonable_python, not the stdlib default: `.model_dump()` leaves UUIDs
    # and datetimes in nested models as objects (search_doc.id is a UUID), and
    # raising here kills the stream after the answer is already saved -- the
    # browser sees ERR_INCOMPLETE_CHUNKED_ENCODING and the answer only appears
    # on reload.
    return json.dumps(json_dict, default=to_jsonable_python) + "\n"


def mask_string(sensitive_str: str) -> str:
    return "****...**" + sensitive_str[-4:]


def mask_credential_dict(credential_dict: dict[str, Any]) -> dict[str, str]:
    masked_creds = {}
    for key, val in credential_dict.items():
        if not isinstance(val, str):
            raise ValueError(
                f"Unable to mask credentials of type other than string, cannot process request."
                f"Recieved type: {type(val)}"
            )

        masked_creds[key] = mask_string(val)
    return masked_creds
