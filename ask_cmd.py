#!/usr/bin/env python3
import argparse
import json
import os
import platform
import subprocess
import sys

import llm


def get_os_info():
    """Returns a simple string describing the current OS."""
    system = platform.system()
    if system == "Darwin":
        return "macOS"
    elif system == "Linux":
        try:
            # Try to get distro info on Linux
            import distro

            return f"Linux ({distro.name()} {distro.version()})"
        except ImportError:
            return "Linux"
    return system


SHELL = os.path.basename(os.environ.get("SHELL", "sh"))

# Cap on how much of a failed command's stderr goes back to the model.
STDERR_TAIL = 4000

SYSTEM_PROMPT = f"""
You are a command-line assistant running on {get_os_info()} in {SHELL}.
Given a user task, propose exactly one safe shell command that accomplishes the task.

Return output in JSON:
{{
  "command": "<single command>",
  "explanation": "<short explanation>"
}}

- No backticks
- No multiple alternatives
- No placeholder text; use real commands
- Never execute anything yourself.
- Quote arguments containing shell metacharacters (URLs with ? or &, globs, spaces)
  so {SHELL} passes them through literally.
- If you are shown previous attempts that failed, propose a corrected command based
  on their error output. Never repeat a command that already failed. If the failure
  is expected or can't be fixed without more information from the user, return an
  empty "command" and say why in "explanation".
"""


def build_prompt(query, attempts):
    """The task plus every earlier attempt of this session and how it failed."""
    if not attempts:
        return query
    parts = [f"Task: {query}", "", "Previous attempts that failed:"]
    for i, a in enumerate(attempts, 1):
        parts.append(f"\n{i}. {a['command']}\n   exit code: {a.get('exit_code')}")
        if a.get("stderr"):
            parts.append("   stderr:\n" + a["stderr"])
    return "\n".join(parts)


# Enforced via structured outputs where the model supports it, so the reply is
# guaranteed to parse; the JSON shape in SYSTEM_PROMPT covers models that don't.
SCHEMA = {
    "type": "object",
    "properties": {
        "command": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["command", "explanation"],
    "additionalProperties": False,
}


def parse_json(text):
    """Parse a reply, tolerating a ```json fence around it."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


def model_options(model):
    """llm options from $ASK_CMD_OPTIONS, as key=value pairs separated by commas,
    e.g. reasoning_effort=none. Keys the model doesn't accept are dropped, so
    `-m` can switch to a model without that option and still work."""
    options = {}
    for pair in filter(None, os.environ.get("ASK_CMD_OPTIONS", "").split(",")):
        key, sep, value = pair.partition("=")
        if not sep:
            print(f"Ignoring ASK_CMD_OPTIONS entry without '=': {pair}", file=sys.stderr)
            continue
        options[key.strip()] = value.strip()
    return {k: v for k, v in options.items() if k in model.Options.model_fields}


def call_llm(user_prompt, model_id):
    try:
        model = llm.get_model(model_id)
    except Exception as e:
        print(f"Error loading model '{model_id}': {e}", file=sys.stderr)
        sys.exit(1)

    schema = SCHEMA if model.supports_schema else None
    text = None
    try:
        text = model.prompt(
            user_prompt, system=SYSTEM_PROMPT, schema=schema, **model_options(model)
        ).text()
        return parse_json(text)
    except json.JSONDecodeError:
        print(f"Failed to decode JSON from llm output:\n{text}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error running llm: {e}", file=sys.stderr)
        sys.exit(1)


def confirm(result, model_id, ui):
    """Show the proposal and ask; True only on an explicit y."""
    command = result["command"]
    print(f"\nModel: {model_id}", file=ui)
    if not command:
        print("\nNo command proposed:", file=ui)
        print("  ", result["explanation"], file=ui)
        return False
    print("\nProposed command:", file=ui)
    print("  ", command, file=ui)
    print("\nExplanation:", file=ui)
    print("  ", result["explanation"], file=ui)

    try:
        print("\nExecute? [y/N]: ", end="", file=ui)
        ui.flush()
        answer = input().strip().lower()
    except EOFError:
        print("\nInput stream closed.", file=ui)
        return False
    if answer != "y":
        print("Aborted.", file=ui)
        return False
    return True


def run_captured(command):
    """Run in a subprocess, echoing stderr live while keeping its tail."""
    proc = subprocess.Popen(command, shell=True, stderr=subprocess.PIPE, text=True)
    tail = ""
    for line in proc.stderr:
        sys.stderr.write(line)
        tail = (tail + line)[-STDERR_TAIL:]
    return proc.wait(), tail


def load_session(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return []


def main():
    parser = argparse.ArgumentParser(description="Generate shell commands using LLMs.")
    parser.add_argument("query", nargs="+", help="The task you want to accomplish")
    parser.add_argument("--model", "-m", help="The LLM model to use")
    parser.add_argument(
        "--print", "-p", dest="print_only", action="store_true",
        help=(
            "On confirm, print the command to stdout instead of running it. "
            "Lets a shell-function wrapper `eval` it in the CURRENT shell so "
            "state-changing commands (cd, export, source, venv activate) "
            "persist — a subprocess can't change its parent shell. All "
            "diagnostics and the prompt go to stderr so stdout is only the command."
        ),
    )
    parser.add_argument(
        "--session", metavar="DIR",
        help=(
            "With -p: a directory the wrapper keeps across retries. The attempts "
            "so far are recorded in DIR/attempts.json so a retry sees them all."
        ),
    )
    parser.add_argument(
        "--exit-code", type=int, metavar="N",
        help=(
            "With --session: the last printed command failed with exit code N "
            "(its stderr is in DIR/stderr); propose a fix instead of a fresh command."
        ),
    )
    parser.add_argument(
        "--max-retries", type=int, default=3, metavar="N",
        help="Without -p: how many times to ask for a fix after a failure (default 3).",
    )

    args = parser.parse_args()

    # Determine model: Flag > Env Var > llm's configured default
    model_id = args.model or os.environ.get("ASK_CMD_MODEL") or llm.get_default_model()
    query = " ".join(args.query)

    if args.print_only:
        # Everything human-facing goes to stderr, leaving stdout to carry only
        # the confirmed command (captured by the wrapper). The wrapper runs the
        # command, so retries span processes: history lives in the session dir.
        ui = sys.stderr
        attempts, session_file = [], None
        if args.session:
            session_file = os.path.join(args.session, "attempts.json")
            attempts = load_session(session_file)
        if args.exit_code is not None and attempts:
            attempts[-1]["exit_code"] = args.exit_code
            try:
                with open(os.path.join(args.session, "stderr")) as f:
                    attempts[-1]["stderr"] = f.read()[-STDERR_TAIL:]
            except FileNotFoundError:
                pass
            print(f"\n✗ Exit code {args.exit_code} — asking for a fix...", file=ui)

        result = call_llm(build_prompt(query, attempts), model_id)
        if session_file:
            attempts.append({"command": result["command"]})
            with open(session_file, "w") as f:
                json.dump(attempts, f)
        if not confirm(result, model_id, ui):
            sys.exit(1)
        print(result["command"])
        return

    attempts = []
    while True:
        result = call_llm(build_prompt(query, attempts), model_id)
        if not confirm(result, model_id, sys.stdout):
            sys.exit(1)
        print("\n→ Executing...\n")
        rc, stderr = run_captured(result["command"])
        # 130 = Ctrl-C: the user stopped it on purpose, nothing to fix.
        if rc in (0, 130) or len(attempts) >= args.max_retries:
            sys.exit(rc)
        attempts.append({"command": result["command"], "exit_code": rc, "stderr": stderr})
        print(f"\n✗ Exit code {rc} — asking for a fix...")


if __name__ == "__main__":
    main()
