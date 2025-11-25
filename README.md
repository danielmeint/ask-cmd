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

## Configuration

This uses [llm](https://llm.datasette.io/) under the hood. Make sure you have configured an API key:

```bash
brew install llm
llm keys set openai
```
