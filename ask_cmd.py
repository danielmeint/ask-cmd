#!/usr/bin/env python3
import json
import platform
import subprocess
import sys

MODEL = "gpt-4o-mini"

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

def call_llm(user_prompt):
    cmd = [
        "llm",
        "-m", MODEL,
        "--system", SYSTEM_PROMPT
    ]
    result = subprocess.run(cmd, input=user_prompt, text=True,
                            capture_output=True)

    if result.returncode != 0:
        print(f"Error running llm: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"Failed to decode JSON from llm output:\n{result.stdout}", file=sys.stderr)
        sys.exit(1)

def main():
    if len(sys.argv) < 2:
        print("Usage: ask \"your task here\"")
        sys.exit(1)

    user_prompt = " ".join(sys.argv[1:])
    result = call_llm(user_prompt)

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
