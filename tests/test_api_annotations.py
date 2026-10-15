"""Annotations of the API and its new services must evaluate.

CI and release builds run Python 3.11, which evaluates annotations when a
function is defined; the dev machine runs 3.14, which defers them (PEP 649)
until something reads them. A method named like a builtin (ServersApi.list)
then broke ``-> list[Task]`` on 3.11 only. Reading every annotation here
evaluates it on any version, so the mistake fails locally too.
"""

import importlib
import inspect
import pkgutil
import typing

import pytest

import app.api

MODULES = sorted(
    [f"app.api.{m.name}" for m in pkgutil.iter_modules(app.api.__path__)]
    + ["app.services.mod_content", "app.services.mod_icons", "app.services.server_paths"])


def _functions(module):
    for _, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and obj.__module__ == module.__name__:
            for _, member in inspect.getmembers(obj):
                fn = getattr(member, "fget", member)
                if inspect.isfunction(fn):
                    yield fn
        elif inspect.isfunction(obj) and obj.__module__ == module.__name__:
            yield obj


@pytest.mark.parametrize("name", MODULES)
def test_every_annotation_evaluates(name):
    module = importlib.import_module(name)
    functions = list(_functions(module))
    assert functions
    for fn in functions:
        typing.get_type_hints(fn)


@pytest.mark.parametrize("name", MODULES)
def test_annotations_are_postponed(name):
    """`from __future__ import annotations` keeps 3.11 from evaluating them
    at definition time (the same behavior as the dev machine's 3.14)."""
    module = importlib.import_module(name)
    assert getattr(module, "annotations", None) is not None
    assert module.annotations.compiler_flag
