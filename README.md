# Colab-mcp

An MCP server for bridging your local agent to a Colab session in the browser.

# Supported Clients
This MCP server requires client support for `notifications/tools/list_changed` and for the client to be running locally on your device. 

Popular clients that fit these criteria include:
- Gemini CLI
- Claude Code
- Windsurf


# Setup

- Install `uv` (`pip install uv`)
- Configure for usage (eg for mcp.json style services):

```
...
  "mcpServers": {
    "colab-mcp": {
      "command": "uvx",
      "args": ["git+https://github.com/googlecolab/colab-mcp"],
      "timeout": 30000
    }
  }
...
```

(If you have a non-standard default package index (**Googlers**), you may also need to add `--index https://pypi.org/simple`)

# Reliable Chrome Profile Setup

For local development, you can force Colab MCP to open a specific Chrome profile instead of whichever browser the operating system chooses.

The signed-in profile requested for this workspace is:

- Chrome profile directory: `Default`
- Google profile name: `nothumanatall`
- Account id: `canbehumanagain@gmail.com`

Local `mcp.json` example:

```
...
  "mcpServers": {
    "colab-mcp": {
      "command": "uv",
      "args": [
        "run",
        "colab-mcp",
        "--browser-command",
        "google-chrome-stable",
        "--browser-profile",
        "Default",
        "--browser-user-data-dir",
        "/home/astra/.config/google-chrome",
        "--connection-timeout",
        "180"
      ],
      "cwd": "/home/astra/codex/Google-Colab/colab-mcp",
      "timeout": 30000
    }
  }
...
```

Equivalent environment variables:

```shell
export COLAB_MCP_BROWSER_COMMAND=google-chrome-stable
export COLAB_MCP_BROWSER_PROFILE=Default
export COLAB_MCP_BROWSER_USER_DATA_DIR=/home/astra/.config/google-chrome
export COLAB_MCP_CONNECTION_TIMEOUT=180
```

Use `--print-connection-url` or `COLAB_MCP_PRINT_CONNECTION_URL=1` only for interactive debugging. The URL is written to stderr so it does not corrupt the MCP stdio protocol, but it contains the temporary local proxy token.

# Connection Diagnostics

This fork injects two local setup tools:

- `open_colab_browser_connection`: opens Colab and waits for the browser UI to connect.
- `get_colab_connection_status`: returns redacted connection diagnostics including connected state, proxy port, timeout, browser command, browser profile, and user data directory.

If Colab runtime stops, call `get_colab_connection_status` first. If the browser UI is disconnected, call `open_colab_browser_connection` again. If the browser UI is connected but runtime-backed notebook tools are unavailable, reconnect the Colab runtime in the notebook UI.

# Issues & Discussions

We are using GitHub [discussions](https://github.com/googlecolab/colab-mcp/discussions) as the
place for issue discussion and feature requests. As discussions mature into action items, we
will add those items as issues. This helps us ensure that issues in the issue tracker are
well-understood, deduplicated, and actionable. For these reasons, **please do <u>NOT</u> open
issues directly.** 

# Contributing 
We unfortunately don't have the bandwidth to support review of external contributions, and we 
don't want user PRs to languish, so we aren't accepting any external contributions right now.

If you have a great idea or pain point, we would love to hear about it on our 
[discussions](https://github.com/googlecolab/colab-mcp/discussions) page - the preferred place 
for issue discussion and feature requests.

# Internal - For Colab Developers

### Prerequisites

- `uv` is required (`pip install uv`)
- Configure git hooks to run repo presubmits

```shell
git config core.hooksPath .githooks
```

### Gemini CLI setup

```
...
  "mcpServers": {
    "colab-mcp": {
      "command": "uv",
      "args": ["run", "colab-mcp"],
      "cwd": "/path/to/github/colab-mcp",
      "timeout": 30000
    }
  }
...
```
