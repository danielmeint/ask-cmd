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

## Run in the current shell (`cd`, `export`, …)

`ask` runs the command in a subprocess, so `cd`/`export`/`source` don't persist.
For those, use `-p` (prints the confirmed command to stdout) via a shell function
that `eval`s it in your shell:

```zsh
ask() { local cmd; cmd=$(command ask -p "$@") || return; eval "$cmd"; }
```

## Configuration

This uses [llm](https://llm.datasette.io/) under the hood. Make sure you have configured an API key:

```bash
brew install llm
llm keys set openai
```
