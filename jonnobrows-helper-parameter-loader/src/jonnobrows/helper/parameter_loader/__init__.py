"""
The jonnobrows-helper-parameter-loader package providers a way
to load AWS Systems Manager Parameter Store parameters.

Usage
_____

.. code:: python

    # Copy this snippet into your code
    from jonnobrows.helper.parameter_loader import ParameterLoader

    ParameterLoader().load_parameters()

    # Your code here ...
"""

import logging
import os

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


def _format_parameters(parameters: list[dict]) -> dict:
    formatted = {}
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
        formatted[name] = value
    return formatted


def _export_parameters(parameters: list[dict], allow_list: list[str]) -> None:
    formatted_parameters = _format_parameters(parameters)
    for key, value in formatted_parameters.items():
        if allow_list and key not in allow_list:
            logger.info(f"Skipping parameter as not in allow list: {key}")
            continue

        logger.debug(f"Exporting parameter: {key}={value}")
        if key in os.environ:
            logger.warning(f"Overwriting environment variable: {key}")
        os.environ[key] = value


def _load_required_params(filename) -> list[str]:
    logger.info(
        "Trying to load required variable names from file: %s",
        filename,
    )
    params = []
    try:
        with open(filename, "r") as f:
            params = f.read().splitlines()
    except Exception as exc:
        logger.warning(
            "Exception when trying to load required parameters file: %s",
            exc_info=exc,
        )
    return sorted(set([r for r in params if r]))


class ParameterLoaderError(ValueError):
    pass


class ParameterLoader:
    _required: list[str]
    _ignore_other: bool = False

    def __init__(self, required=None, required_file=None, ignore_other=False) -> None:
        all_required = required or []
        all_required.extend(_load_required_params(required_file))
        all_required = sorted(set([r for r in all_required if r]))
        self._required = all_required
        self._ignore_other = ignore_other

    @property
    def _allow_list(self) -> list[str]:
        return self._required if self._ignore_other else []

    def load_parameters(self) -> None:
        """
        Load parameters from AWS Systems Manager Parameter Store
        and export them as environment variables.

        Runs validation against required environment variables.
        """
        for path in _parameter_paths():
            parameters = _get_parameters_by_path(path)
            _export_parameters(parameters, self._allow_list)
        self.__check_required_parameters(dict(os.environ))

    def check_parameters(self) -> None:
        """
        Check parameters exist in AWS Systems Manager Parameter Store.
        """
        all_formatted_parameters = {}
        for path in _parameter_paths():
            parameters = _get_parameters_by_path(path)
            all_formatted_parameters = {
                **all_formatted_parameters,
                **_format_parameters(parameters),
            }
        self.__check_required_parameters(all_formatted_parameters)

    def __check_required_parameters(self, location: dict) -> None:
        if not self._required:
            return

        missing = []
        for variable in self._required:
            if variable not in location:
                missing.append(variable)
        if missing:
            raise ParameterLoaderError(
                f"Required environment variables not found: {', '.join(missing)}"
            )
