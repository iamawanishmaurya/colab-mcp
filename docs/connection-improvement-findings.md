# Colab MCP Connection Improvement Findings

## Current connection flow

1. The local MCP server starts a localhost WebSocket server with an auth token.
2. The injected `open_colab_browser_connection` tool opens a Colab scratch notebook URL with `mcpProxyToken` and `mcpProxyPort` in the fragment.
3. The Colab frontend connects back to the localhost WebSocket.
4. Once connected, the local MCP server proxies tools exposed by the Colab session.

## Findings

- Browser launch is currently delegated to `webbrowser.open_new(...)`, which opens the system default browser and cannot reliably choose a signed-in Chrome profile.
- The requested local Chrome identity maps to Chrome profile directory `Default`, with Gaia name `nothumanatall` and account id `canbehumanagain@gmail.com`.
- The connection wait is fixed at 60 seconds, so slow Colab startup, profile selection, or login prompts can cause false negative connection attempts.
- The MCP client has no explicit status/diagnostic tool. When connection fails, the agent only gets a boolean and progress text, not the URL, port, profile, timeout, or connection state.
- Runtime stops are not the same as browser WebSocket disconnects. The local server can improve browser reconnection and diagnostics, but Colab runtime availability is ultimately controlled by Colab.
- Upstream `README.md` states that external contributions are not currently accepted, so these improvements should be treated as a local fork/workspace patch unless an upstream discussion is opened.

## Improvement options

### Option A: Configurable browser launcher and timeout

- Add CLI/env configuration for Chrome executable, user data directory, profile directory, and UI connection timeout.
- Use `subprocess.Popen` for explicit Chrome launches when configured, and keep `webbrowser.open_new` as fallback.
- Best for the requested profile flow because it can open `google-chrome-stable --profile-directory=Default`.

Trade-off: This improves local reliability but does not change Colab runtime lifetime.

### Option B: Add an explicit connection status tool

- Inject a diagnostic tool that returns connected state, proxy URL, port, timeout, and browser launch configuration.
- Best for debugging repeated MCP connection failures without guessing.

Trade-off: It exposes local connection details to the MCP client, so token values must remain redacted or omitted from normal status output.

### Option C: Auto-retry browser opening in the server

- Retry opening Colab multiple times during the connection wait window.
- Helps with transient browser startup delays.

Trade-off: It can create duplicate Colab tabs and annoy users. This is less clean than explicit status plus longer timeout.

## Chosen first implementation

Implement Option A and Option B together:

- Add `--browser-command`, `--browser-profile`, `--browser-user-data-dir`, `--connection-timeout`, and `--print-connection-url`.
- Add environment variable support with CLI options taking precedence.
- Add an injected `get_colab_connection_status` tool with redacted token handling.
- Update tests and README with a Chrome profile example for `nothumanatall` / `Default`.

## Confidence and validation

Confidence for this bounded implementation is 100%.

Why:

- It only changes local server behavior and injected diagnostics.
- It keeps current defaults for existing users.
- It does not depend on private Colab frontend changes.
- Baseline tests already pass, and the change can be covered by unit tests.

Validation required before completion:

- `uv run pytest`
- `uv run colab-mcp --help`
- Verify the generated Chrome launch URL/command behavior in tests.
- Check git status before commit and tag.
