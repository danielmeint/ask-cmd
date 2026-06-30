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


SYSTEM_PROMPT = f"""
You are a command-line assistant running on {get_os_info()}. 
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
"""


def call_llm(user_prompt, model_id):
    try:
        model = llm.get_model(model_id)
    except Exception as e:
        print(f"Error loading model '{model_id}': {e}", file=sys.stderr)
        sys.exit(1)

    response = None
    try:
        response = model.prompt(user_prompt, system=SYSTEM_PROMPT).text()
        return json.loads(response)
    except json.JSONDecodeError:
        if response is None:
            print("Failed to get a response from the model.", file=sys.stderr)
            sys.exit(1)
        # Fallback: sometimes models might wrap json in markdown code blocks
        clean_response = response.strip()
        if clean_response.startswith("```json"):
            clean_response = clean_response.split("```json")[1]
            if clean_response.endswith("```"):
                clean_response = clean_response.rsplit("```", 1)[0]
            try:
                return json.loads(clean_response)
            except json.JSONDecodeError:
                pass

        print(f"Failed to decode JSON from llm output:\n{response}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error running llm: {e}", file=sys.stderr)
        sys.exit(1)


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

    args = parser.parse_args()

    # Determine model: Flag > Env Var > llm's configured default
    model_id = args.model or os.environ.get("ASK_CMD_MODEL") or llm.get_default_model()

    user_prompt = " ".join(args.query)

    result = call_llm(user_prompt, model_id)
    command = result["command"]

    # In --print mode everything human-facing goes to stderr, leaving stdout to
    # carry only the confirmed command (captured by the wrapper).
    ui = sys.stderr if args.print_only else sys.stdout

    print(f"\nModel: {model_id}", file=ui)
    print("\nProposed command:", file=ui)
    print("  ", command, file=ui)
    print("\nExplanation:", file=ui)
    print("  ", result["explanation"], file=ui)

    try:
        print("\nExecute? [y/N]: ", end="", file=ui)
        ui.flush()
        confirm = input().strip().lower()
    except EOFError:
        print("\nInput stream closed.", file=ui)
        sys.exit(1)

    if confirm != "y":
        print("Aborted.", file=ui)
        sys.exit(1)

    if args.print_only:
        # Emit the command for the wrapper to eval in the current shell.
        print(command)
    else:
        print("\n→ Executing...\n", file=ui)
        subprocess.run(command, shell=True)


if __name__ == "__main__":
    main()
