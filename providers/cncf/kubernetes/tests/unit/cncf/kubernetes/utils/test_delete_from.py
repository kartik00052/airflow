# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
from __future__ import annotations

from unittest import mock

import pytest
from kubernetes import client

from airflow.providers.cncf.kubernetes.utils.delete_from import (
    DEFAULT_DELETION_BODY,
    FailToDeleteError,
    _delete_from_yaml_single_item,
    delete_from_dict,
    delete_from_yaml,
)


def test_delete_from_dict_list_kind():
    api = mock.MagicMock()
    data = {
        "apiVersion": "v1",
        "kind": "PodList",
        "items": [
            {"metadata": {"name": "pod-1", "namespace": "ns1"}},
            {"metadata": {"name": "pod-2", "namespace": "ns1"}},
        ],
    }
    with mock.patch.object(client, "CoreV1Api", return_value=api):
        delete_from_dict(k8s_client=mock.MagicMock(), data=data, body=None, namespace="default")

    api.delete_namespaced_pod.assert_has_calls(
        [
            mock.call(name="pod-1", namespace="ns1", body=DEFAULT_DELETION_BODY),
            mock.call(name="pod-2", namespace="ns1", body=DEFAULT_DELETION_BODY),
        ]
    )


def test_delete_from_dict_single_items_forward_body():
    api = mock.MagicMock()
    data = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "web", "namespace": "default"},
    }
    body = {"propagation_policy": "Foreground"}
    with mock.patch.object(client, "AppsV1Api", return_value=api):
        delete_from_dict(k8s_client=mock.MagicMock(), data=data, body=body, namespace="default")

    api.delete_namespaced_deployment.assert_called_once_with(name="web", namespace="default", body=body)


def test_delete_from_dict_raises_fail_to_delete_error():
    api = mock.MagicMock()
    api_exception = client.rest.ApiException(reason="Not Found")
    api_exception.body = "pod not found"
    api.delete_namespaced_pod.side_effect = api_exception
    data = {
        "apiVersion": "v1",
        "kind": "PodList",
        "items": [
            {"metadata": {"name": "pod-1", "namespace": "ns1"}},
            {"metadata": {"name": "pod-2", "namespace": "ns1"}},
        ],
    }
    with mock.patch.object(client, "CoreV1Api", return_value=api):
        with pytest.raises(FailToDeleteError) as exc_info:
            delete_from_dict(k8s_client=mock.MagicMock(), data=data, body=None, namespace="default")

    assert len(exc_info.value.api_exceptions) == 2
    assert str(exc_info.value) == "Error from server (Not Found):pod not found\n" * 2


def test_delete_from_yaml_skips_none_and_uses_namespace_argument():
    api = mock.MagicMock()
    yaml_objects = [
        None,
        {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "pod-1"}},
        {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "pod-2"}},
        None,
    ]
    with mock.patch.object(client, "CoreV1Api", return_value=api):
        delete_from_yaml(
            k8s_client=mock.MagicMock(), yaml_objects=yaml_objects, body=None, namespace="arg-namespace"
        )

    api.delete_namespaced_pod.assert_has_calls(
        [
            mock.call(name="pod-1", namespace="arg-namespace", body=DEFAULT_DELETION_BODY),
            mock.call(name="pod-2", namespace="arg-namespace", body=DEFAULT_DELETION_BODY),
        ]
    )


def test_delete_from_yaml_single_item_cluster_scoped_kind():
    api = mock.MagicMock(spec=["delete_custom_resource_definition"])
    data = {
        "apiVersion": "apiextensions.k8s.io/v1",
        "kind": "CustomResourceDefinition",
        "metadata": {"name": "widgets.example.com"},
    }
    with mock.patch.object(client, "ApiextensionsV1Api", return_value=api):
        result = _delete_from_yaml_single_item(
            k8s_client=mock.MagicMock(), yml_document=data, body=None, namespace="default"
        )

    api.delete_custom_resource_definition.assert_called_once_with(
        name="widgets.example.com", body=DEFAULT_DELETION_BODY
    )
    assert result == api.delete_custom_resource_definition.return_value


def test_delete_from_yaml_single_item_forwards_kwargs():
    api = mock.MagicMock()
    data = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "pod-1", "namespace": "ns1"}}
    with mock.patch.object(client, "CoreV1Api", return_value=api):
        _delete_from_yaml_single_item(
            k8s_client=mock.MagicMock(),
            yml_document=data,
            body=None,
            namespace="default",
            field_validation="Strict",
        )

    api.delete_namespaced_pod.assert_called_once_with(
        name="pod-1", namespace="ns1", body=DEFAULT_DELETION_BODY, field_validation="Strict"
    )


def test_delete_from_yaml_single_item_verbose(capsys):
    api = mock.MagicMock()
    api.delete_namespaced_pod.return_value.status = "Success"
    data = {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": "pod-1", "namespace": "ns1"}}
    with mock.patch.object(client, "CoreV1Api", return_value=api):
        _delete_from_yaml_single_item(
            k8s_client=mock.MagicMock(), yml_document=data, body=None, namespace="default", verbose=True
        )

    assert "pod deleted. status='Success'" in capsys.readouterr().out
