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

from textwrap import dedent

import pytest
from jinja2.exceptions import UndefinedError

from airflow.providers.cncf.kubernetes.python_kubernetes_script import (
    _balance_parens,
    remove_task_decorator,
    write_python_script,
)

SCRIPT = dedent(
    """
def f():
    import funcsigs
"""
)

JINJA_CONTEXT = {
    "op_args": [1],
    "op_kwargs": {"user": "a"},
    "pickling_library": "pickle",
    "python_callable": "f",
    "python_callable_source": SCRIPT,
    "string_args_global": False,
}


@pytest.mark.parametrize(
    ("after_decorator", "expected"),
    [
        ("()\ndef f():\n    return 1", "\ndef f():\n    return 1"),
        ('(arg1="a")\ndef f():\n    return 1', "\ndef f():\n    return 1"),
        ("(foo(bar))\ndef f():\n    return 1", "\ndef f():\n    return 1"),
        ("(foo(bar(baz)))\ndef f():\n    return 1", "\ndef f():\n    return 1"),
    ],
    ids=["no_args", "with_args", "nested_parens", "deeply_nested_parens"],
)
def test_balance_parens(after_decorator, expected):
    assert _balance_parens(after_decorator) == expected


@pytest.mark.parametrize(
    ("decorators", "expected_decorators"),
    [
        (["@task.kubernetes"], []),
        (["@task.kubernetes()"], []),
        (['@task.kubernetes(namespace="default")'], []),
        (["@task.kubernetes(foo(bar))"], []),
        (["@setup", "@task.kubernetes"], []),
        (["@teardown", "@task.kubernetes"], []),
        (["@setup", "@teardown", "@task.kubernetes"], []),
        (["@foo", "@task.kubernetes", "@bar"], ["@foo", "@bar"]),
    ],
    ids=[
        "without_parens",
        "parens",
        "with_args",
        "nested_parens",
        "with_setup",
        "with_teardown",
        "with_setup_and_teardown",
        "nested_other_decorators",
    ],
)
def test_remove_task_decorator(decorators, expected_decorators):
    concated_decorators = "\n".join(decorators)
    expected_decorator = "\n".join(expected_decorators)
    py_source = concated_decorators + SCRIPT
    expected_source = (expected_decorator + SCRIPT) if expected_decorator else SCRIPT.lstrip()

    result = remove_task_decorator(python_source=py_source, task_decorator_name="@task.kubernetes")

    assert result == expected_source


def test_remove_task_decorator_absent_decorator_returns_source_unchanged():
    py_source = "@foo\n@bar\n" + SCRIPT.lstrip()

    result = remove_task_decorator(python_source=py_source, task_decorator_name="@task.kubernetes")

    assert result == py_source


def test_write_python_script(tmp_path):
    filename = tmp_path / "script.py"

    write_python_script(jinja_context=JINJA_CONTEXT, filename=str(filename))

    content = filename.read_text()
    assert "import json" in content
    assert "import pickle" in content
    assert "arg_dict = pickle.load(file)" in content
    assert 'res = f(*arg_dict["args"], **arg_dict["kwargs"])' in content
    assert "def f():" in content


def test_write_python_script_native_rendering(tmp_path):
    filename = tmp_path / "script.py"

    write_python_script(
        jinja_context=JINJA_CONTEXT, filename=str(filename), render_template_as_native_obj=True
    )

    content = filename.read_text()
    assert "import pickle" in content
    assert 'res = f(*arg_dict["args"], **arg_dict["kwargs"])' in content


def test_write_python_script_without_op_args(tmp_path):
    filename = tmp_path / "script.py"
    jinja_context = {**JINJA_CONTEXT, "op_args": [], "op_kwargs": {}}

    write_python_script(jinja_context=jinja_context, filename=str(filename))

    content = filename.read_text()
    assert 'arg_dict = {"args": [], "kwargs": {}}' in content
    assert "arg_dict = pickle.load(file)" not in content


def test_write_python_script_missing_context_variable_raises(tmp_path):
    filename = tmp_path / "script.py"

    with pytest.raises(UndefinedError):
        write_python_script(jinja_context={}, filename=str(filename))
