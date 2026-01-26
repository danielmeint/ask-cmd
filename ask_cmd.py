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

    args = parser.parse_args()

    # Determine model: Flag > Env Var > llm's configured default
    model_id = args.model or os.environ.get("ASK_CMD_MODEL") or llm.get_default_model()

    user_prompt = " ".join(args.query)

    result = call_llm(user_prompt, model_id)

    print(f"\nModel: {model_id}")
    print("\nProposed command:")
    print("  ", result["command"])
    print("\nExplanation:")
    print("  ", result["explanation"])

    try:
        confirm = input("\nExecute? [y/N]: ").strip().lower()
    except EOFError:
        print("\nInput stream closed.")
        return

    if confirm == "y":
        print("\n→ Executing...\n")
        subprocess.run(result["command"], shell=True)
    else:
        print("Aborted.")


if __name__ == "__main__":
    main()
