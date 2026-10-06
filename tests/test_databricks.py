"""The Databricks job definition: consistent with its notebooks, without a workspace or Spark."""

import ast
import importlib.util
import re

from decision_platform.config import ROOT

NOTEBOOKS = ROOT / "databricks" / "notebooks"


def _run_job():
    spec = importlib.util.spec_from_file_location("run_job", ROOT / "databricks" / "run_job.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_job_resolves_every_variable():
    job = _run_job().job_definition({"customers": "5000"}, "/Workspace/Users/someone/corridor")
    parameters = {p["name"]: p["default"] for p in job["parameters"]}
    assert parameters["code_root"] == "/Workspace/Users/someone/corridor"
    assert parameters["customers"] == "5000"
    assert not any("${" in str(value) for value in parameters.values())


def test_tasks_point_at_notebooks_that_exist_and_compile():
    job = _run_job().job_definition({}, "/x")
    keys = {task["task_key"] for task in job["tasks"]}
    for task in job["tasks"]:
        path = ROOT / task["notebook_task"]["notebook_path"]
        assert path.exists(), path
        source = path.read_text(encoding="utf-8")
        assert source.startswith("# Databricks notebook source")
        ast.parse(source)
        assert {d["task_key"] for d in task.get("depends_on", [])} <= keys


def test_every_widget_a_notebook_reads_is_a_job_parameter():
    job = _run_job().job_definition({}, "/x")
    parameters = {p["name"] for p in job["parameters"]}
    for path in NOTEBOOKS.glob("*.py"):
        widgets = set(re.findall(r'dbutils\.widgets\.get\("(\w+)"\)', path.read_text(encoding="utf-8")))
        assert widgets <= parameters, (path.name, widgets - parameters)


def test_task_values_are_read_from_tasks_that_set_them():
    produced = {}
    for path in NOTEBOOKS.glob("*.py"):
        task = path.stem.split("_", 1)[1]
        source = path.read_text(encoding="utf-8")
        produced[task] = set(re.findall(r'taskValues\.set\(key="(\w+)"', source))
    for path in NOTEBOOKS.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for task, key in re.findall(r'taskKey="(\w+)",\s*key="(\w+)"', source):
            assert key in produced[task], (path.name, task, key)
        for task, key in re.findall(r'task_value\("(\w+)", "(\w+)"\)', source):
            assert key in produced[task], (path.name, task, key)


def test_uploads_cover_what_the_notebooks_import():
    uploads = {folder for folder, _pattern in _run_job().UPLOADS}
    assert {"src/decision_platform", "sql"} <= uploads
    for path in NOTEBOOKS.glob("*.py"):
        for module in re.findall(r"from decision_platform\.(\w+) import", path.read_text(encoding="utf-8")):
            assert (ROOT / "src" / "decision_platform" / f"{module}.py").exists(), module
