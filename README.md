# ask-cmd

A simple command-line assistant that proposes shell commands using via [llm](https://llm.datasette.io/) and may execute
after confirmation.

Pretty much my personal replacement for the [retired
`gh-copilot` CLI extension](https://github.blog/changelog/2025-09-25-upcoming-deprecation-of-gh-copilot-cli-extension/).

## Installation

```bash
pipx install git+https://github.com/danielmeint/ask-cmd.git
```

## Usage

```bash
ask "kill process on port 8080" # you can also drop the quotes
```

## Retry on failure

If the command exits non-zero, `ask` sends the exit code and stderr back to the
model and proposes a fix (confirmation still required), up to `--max-retries`
times (default 3). Ctrl-C (exit 130) never triggers a retry. When there is nothing
sensible to fix, the model proposes no command and says why.

## Run in the current shell (`cd`, `export`, …)

`ask` runs the command in a subprocess, so `cd`/`export`/`source` don't persist.
For those, use `-p` (prints the confirmed command to stdout) via a shell function
that `eval`s it in your shell. `--session`/`--exit-code` let the function keep the
retry loop:

```zsh
ask() {
  local __ask_dir __ask_cmd __ask_rc __ask_tries=0
  __ask_dir=$(mktemp -d "${TMPDIR:-/tmp}/ask.XXXXXX") || return
  __ask_cmd=$(command ask -p --session "$__ask_dir" "$@") || { rm -rf "$__ask_dir"; return 1; }
  while :; do
    eval "$__ask_cmd" 2>&2 2>"$__ask_dir/stderr"   # zsh MULTIOS: show + save stderr
    __ask_rc=$?
    (( __ask_rc == 0 || __ask_rc == 130 || ++__ask_tries > 3 )) && break
    __ask_cmd=$(command ask -p --session "$__ask_dir" --exit-code $__ask_rc "$@") || break
  done
  rm -rf "$__ask_dir"
  return $__ask_rc
}
```

## Configuration

This uses [llm](https://llm.datasette.io/) under the hood. Make sure you have configured an API key:

```bash
brew install llm
llm keys set openai
```

Pick the model with `-m`, `$ASK_CMD_MODEL`, or llm's default (`llm models default`).
llm's built-in default is `gpt-4o-mini`. A better cheap choice is `gpt-5.6-luna` with
reasoning off, set through `$ASK_CMD_OPTIONS` (llm model options as comma-separated
`key=value` pairs; keys a model doesn't support are skipped):

```bash
export ASK_CMD_MODEL=gpt-5.6-luna
export ASK_CMD_OPTIONS=reasoning_effort=none
```

Replies are constrained to a `{command, explanation}` JSON schema on models that
support structured output.
