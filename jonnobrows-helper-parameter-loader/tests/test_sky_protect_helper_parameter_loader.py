import os
import pytest
from botocore.stub import Stubber
from jonnobrows.helper.parameter_loader import ParameterLoader, ssm
from unittest import mock


ECS_SERVICE_GROUP = "sky_protect_key_parameter_loader_ecs_group"
ECS_SERVICE = "sky_protect_key_parameter_loader_ecs_service"
LAMBDA_GROUP = "sky_protect_key_parameter_loader_lambda_group"
LAMBDA_NAME = "sky_protect_key_parameter_loader_lambda"


@pytest.fixture(autouse=True)
def ssm_stub():
    with Stubber(ssm) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()


def expected_params(path):
    return {"Path": path, "WithDecryption": True, "Recursive": True, "NextToken": ""}


def test_load_parameters_default(monkeypatch, ssm_stub):
    monkeypatch.delenv("ECS_SERVICE_GROUP", raising=False)
    monkeypatch.delenv("LAMBDA_GROUP", raising=False)
    monkeypatch.delenv("ECS_SERVICE", raising=False)
    monkeypatch.delenv("LAMBDA_NAME", raising=False)

    ssm_stub.add_response(
        "get_parameters_by_path",
        {
            "Parameters": [
                {"Name": "/common/PARAM_ONE", "Value": "value1", "Type": "String"},
                {
                    "Name": "/common/PARAM_TWO",
                    "Value": "value2,value3,value4,",
                    "Type": "StringList",
                },
                {
                    "Name": "/common/PARAM_THREE",
                    "Value": "secret_value1",
                    "Type": "SecureString",
                },
            ]
        },
        expected_params=expected_params("/common/"),
    )

    ParameterLoader().load_parameters()

    assert os.environ.get("PARAM_ONE") == "value1"
    assert os.environ.get("PARAM_TWO") == "value2,value3,value4"
    assert os.environ.get("PARAM_THREE") == "secret_value1"


def test_load_parameters_ecs(monkeypatch, ssm_stub):
    monkeypatch.delenv("LAMBDA_GROUP", raising=False)
    monkeypatch.delenv("LAMBDA_NAME", raising=False)
    monkeypatch.setenv("ECS_SERVICE_GROUP", value=ECS_SERVICE_GROUP)
    monkeypatch.setenv("ECS_SERVICE", value=ECS_SERVICE)

    ssm_stub.add_response(
        "get_parameters_by_path",
        {
            "Parameters": [
                {"Name": "/common/COMMON_PARAM", "Value": "common", "Type": "String"},
            ]
        },
        expected_params=expected_params("/common/"),
    )
    ssm_stub.add_response(
        "get_parameters_by_path",
        {
            "Parameters": [
                {
                    "Name": f"/{ECS_SERVICE_GROUP}/common/GROUP_PARAM",
                    "Value": "group",
                    "Type": "String",
                },
            ]
        },
        expected_params=expected_params(f"/{ECS_SERVICE_GROUP}/common/"),
    )
    ssm_stub.add_response(
        "get_parameters_by_path",
        {
            "Parameters": [
                {
                    "Name": f"/{ECS_SERVICE_GROUP}/{ECS_SERVICE}/SERVICE_PARAM",
                    "Value": "service",
                    "Type": "String",
                },
            ]
        },
        expected_params=expected_params(f"/{ECS_SERVICE_GROUP}/{ECS_SERVICE}/"),
    )

    ParameterLoader().load_parameters()

    assert os.environ.get("COMMON_PARAM") == "common"
    assert os.environ.get("GROUP_PARAM") == "group"
    assert os.environ.get("SERVICE_PARAM") == "service"


def test_load_parameters_lambda(monkeypatch, ssm_stub):
    monkeypatch.setenv("LAMBDA_GROUP", value=LAMBDA_GROUP)
    monkeypatch.setenv("LAMBDA_NAME", value=LAMBDA_NAME)
    monkeypatch.delenv("ECS_SERVICE_GROUP", raising=False)
    monkeypatch.delenv("ECS_SERVICE", raising=False)

    ssm_stub.add_response(
        "get_parameters_by_path",
        {
            "Parameters": [
                {"Name": "/common/COMMON_PARAM", "Value": "common", "Type": "String"},
            ]
        },
        expected_params=expected_params("/common/"),
    )
    ssm_stub.add_response(
        "get_parameters_by_path",
        {
            "Parameters": [
                {
                    "Name": f"/{LAMBDA_GROUP}/common/GROUP_PARAM",
                    "Value": "group",
                    "Type": "String",
                },
            ]
        },
        expected_params=expected_params(f"/{LAMBDA_GROUP}/common/"),
    )
    ssm_stub.add_response(
        "get_parameters_by_path",
        {
            "Parameters": [
                {
                    "Name": f"/{LAMBDA_GROUP}/{LAMBDA_NAME}/SERVICE_PARAM",
                    "Value": "service",
                    "Type": "String",
                },
            ]
        },
        expected_params=expected_params(f"/{LAMBDA_GROUP}/{LAMBDA_NAME}/"),
    )

    ParameterLoader().load_parameters()

    assert os.environ.get("COMMON_PARAM") == "common"
    assert os.environ.get("GROUP_PARAM") == "group"
    assert os.environ.get("SERVICE_PARAM") == "service"


def test_overrides(monkeypatch, ssm_stub):
    monkeypatch.setenv("LAMBDA_GROUP", value=LAMBDA_GROUP)
    monkeypatch.setenv("LAMBDA_NAME", value=LAMBDA_NAME)
    monkeypatch.delenv("ECS_SERVICE_GROUP", raising=False)
    monkeypatch.delenv("ECS_SERVICE", raising=False)

    ssm_stub.add_response(
        "get_parameters_by_path",
        {
            "Parameters": [
                {"Name": "/common/MY_TEST_PARAM", "Value": "common", "Type": "String"},
            ]
        },
        expected_params=expected_params("/common/"),
    )
    ssm_stub.add_response(
        "get_parameters_by_path",
        {
            "Parameters": [
                {
                    "Name": f"/{LAMBDA_GROUP}/common/MY_TEST_PARAM",
                    "Value": "group",
                    "Type": "String",
                },
            ]
        },
        expected_params=expected_params(f"/{LAMBDA_GROUP}/common/"),
    )
    ssm_stub.add_response(
        "get_parameters_by_path",
        {"Parameters": []},
        expected_params=expected_params(f"/{LAMBDA_GROUP}/{LAMBDA_NAME}/"),
    )

    ParameterLoader().load_parameters()

    assert os.environ.get("MY_TEST_PARAM") == "group"


def test_required_params_missing(monkeypatch, ssm_stub):
    ssm_stub.add_response("get_parameters_by_path", {"Parameters": []})
    with pytest.raises(ValueError) as excinfo:
        ParameterLoader(required=["PARAM_A", "PARAM_B", "PARAM_C"]).load_parameters()

        assert "Missing required environment variables" in str(excinfo.value)
        assert "PARAM_A" in str(excinfo.value)
        assert "PARAM_B" in str(excinfo.value)
        assert "PARAM_C" in str(excinfo.value)


def test_required_params_with_env(monkeypatch, ssm_stub):
    monkeypatch.setenv("PARAM_A", value="value_a")
    ssm_stub.add_response("get_parameters_by_path", {"Parameters": []})
    with pytest.raises(ValueError) as excinfo:
        ParameterLoader(required=["PARAM_A", "PARAM_B", "PARAM_C"]).load_parameters()

        assert "Missing required environment variables" in str(excinfo.value)
        assert "PARAM_B" in str(excinfo.value)
        assert "PARAM_C" in str(excinfo.value)

        assert "PARAM_A" not in str(excinfo.value)


@mock.patch.dict(os.environ, {"PARAM_A": "value_a"})
def test_required_params_with_env_and_ssm(monkeypatch, ssm_stub):
    ssm_stub.add_response(
        "get_parameters_by_path",
        {
            "Parameters": [
                {"Name": "/common/PARAM_B", "Value": "value_b", "Type": "String"}
            ]
        },
        expected_params=expected_params("/common/"),
    )

    with pytest.raises(ValueError) as excinfo:
        ParameterLoader(required=["PARAM_A", "PARAM_B", "PARAM_C"]).load_parameters()

        assert "Missing required environment variables" in str(excinfo.value)
        assert "PARAM_C" in str(excinfo.value)

        assert "PARAM_A" not in str(excinfo.value)
        assert "PARAM_B" not in str(excinfo.value)
