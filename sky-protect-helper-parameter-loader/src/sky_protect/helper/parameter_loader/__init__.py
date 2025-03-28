"""
The sky-protect-helper-parameter-loader package providers a way
to load AWS Systems Manager Parameter Store parameters.

Usage
_____

.. code:: python

    # Copy this snippet into your code
    from sky_protect.helper.parameter_loader import ParameterLoader

    ParameterLoader().load_parameters()

    # Your code here ...
"""

import logging
import os
from typing import Optional
import boto3

logger = logging.getLogger(__name__)

ssm = boto3.client("ssm")


def _parameter_paths() -> list[str]:
    # Always load common
    paths = ["/common/"]

    # Load group parameters if ECS_SERVICE_GROUP or LAMBDA_GROUP is set
    group = os.environ.get("ECS_SERVICE_GROUP") or os.environ.get("LAMBDA_GROUP")
    if not group:
        logger.warning(
            "ECS_SERVICE_GROUP or LAMBDA_GROUP environment variable is not set"
        )
    else:
        paths.append(f"/{group}/common/")

    # Load service parameters if ECS_SERVICE or LAMBDA_NAME is set
    name = os.environ.get("ECS_SERVICE") or os.environ.get("LAMBDA_NAME")
    if not name:
        logger.warning("ECS_SERVICE or LAMBDA_NAME environment variable is not set")
    else:
        paths.append(f"/{group}/{name}/")

    return paths


def _get_parameters_by_path(path: str) -> list[dict]:
    logger.info(f"Loading parameters from path: {path}")
    next_token = ""
    parameters = []
    while True:
        response = ssm.get_parameters_by_path(
            Path=path, Recursive=True, WithDecryption=True, NextToken=next_token
        )
        parameters.extend(response["Parameters"])
        next_token = response.get("NextToken")
        if not next_token:
            break

    return parameters


def _export_parameters(parameters: list[dict]) -> list[str]:
    exported = []
    for parameter in parameters:
        full_name = parameter.get("Name")
        p_type = parameter.get("Type")
        value = parameter.get("Value")

        if full_name is None or p_type is None or value is None:
            logger.warning("Skipping invalid parameter")
            logger.debug(parameter)
            continue

        name = full_name.split("/")[-1]

        if p_type == "StringList":
            value = value.rstrip(",")

        logger.debug(f"Exporting parameter: {name}={value}")
        if name in os.environ:
            logger.warning(f"Overwriting environment variable: {name}")
        os.environ[name] = value
        exported.append(name)
    return exported


class ParameterLoader:
    required_environment_variables: Optional[list[str]]

    def __init__(self, required_variables=None) -> None:
        self.required_environment_variables = required_variables

    def load_parameters(self) -> None:
        for path in _parameter_paths():
            parameters = _get_parameters_by_path(path)
            _export_parameters(parameters)
        self.__check_required_environment()

    def __check_required_environment(self) -> None:
        if not self.required_environment_variables:
            return

        missing = []
        for variable in self.required_environment_variables:
            if variable not in os.environ:
                missing.append(variable)
        if missing:
            raise ValueError(
                f"Required environment variables not found: {', '.join(missing)}"
            )
