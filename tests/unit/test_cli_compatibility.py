"""Freeze the complete argparse surface independently of handler layout."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from bionexus import cli

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/cli_contract_v1.json"


class ParserCaptured(BaseException):
    pass


def parser_contract(entry):
    captured = []

    def capture(parser, *args, **kwargs):
        captured.append(parser)
        raise ParserCaptured

    with patch.object(argparse.ArgumentParser, "parse_args", capture):
        try:
            entry([])
        except ParserCaptured:
            pass
    assert len(captured) == 1

    def describe(parser):
        actions = []
        for action in parser._actions:
            required = action.required
            if action.nargs in (argparse.REMAINDER, "..."):
                required = False
            record = {"kind": type(action).__name__, "options": action.option_strings,
                      "dest": action.dest, "nargs": action.nargs, "required": required,
                      "default": action.default, "help": action.help,
                      "type": getattr(action.type, "__name__", None)}
            if isinstance(action, argparse._SubParsersAction):
                record["subcommands"] = {name: describe(child) for name, child in action.choices.items()}
            elif action.choices is not None:
                record["choices"] = list(action.choices)
            actions.append(record)
        return {"prog": parser.prog, "description": parser.description, "actions": actions}

    return describe(captured[0])


def test_all_command_arguments_aliases_defaults_and_help_remain_compatible():
    assert parser_contract(cli.main) == json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_legacy_handler_imports_remain_callable():
    # These names are imported by downstream clients and specification tests.
    for name in ("handle_audit", "handle_preflight", "handle_verify", "handle_create_plugin",
                 "handle_audit_de", "handle_registry", "handle_ivn", "handle_nextflow"):
        assert callable(getattr(cli, name))


def test_invalid_command_and_required_arguments_still_exit_two(capsys):
    for argv in (["not-a-command"], ["audit"], ["audit-de-verify"]):
        try:
            cli.main(argv)
        except SystemExit as exc:
            assert exc.code == 2
        else:
            raise AssertionError(f"Accepted invalid invocation: {argv}")
        assert "error:" in capsys.readouterr().err
