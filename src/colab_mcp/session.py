# Copyright 2026 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
from collections.abc import AsyncIterator
import contextlib
from contextlib import AsyncExitStack
from dataclasses import dataclass
from fastmcp import FastMCP, Client
from fastmcp.client.transports import ClientTransport
from fastmcp.dependencies import CurrentContext
from fastmcp.server.context import Context
from fastmcp.server.middleware import Middleware, MiddlewareContext
from fastmcp.server.middleware.tool_injection import ToolInjectionMiddleware
from fastmcp.server.proxy import FastMCPProxy
from fastmcp.tools.tool import Tool, ToolResult
from mcp.client.session import ClientSession
from mcp.types import TextContent
import logging
import shlex
import shutil
import subprocess
import sys
import webbrowser

from colab_mcp.websocket_server import ColabWebSocketServer, COLAB, SCRATCH_PATH

DEFAULT_UI_CONNECTION_TIMEOUT = 60.0  # secs

FE_CONNECTED_KEY = "fe_connected"
PROXY_TOKEN_KEY = "proxy_token"
PROXY_PORT_KEY = "proxy_port"
PROXY_CONNECTION_URL_KEY = "proxy_connection_url"
PROXY_CONNECTION_TIMEOUT_KEY = "proxy_connection_timeout"
PROXY_BROWSER_COMMAND_KEY = "proxy_browser_command"
PROXY_BROWSER_PROFILE_KEY = "proxy_browser_profile"
PROXY_BROWSER_USER_DATA_DIR_KEY = "proxy_browser_user_data_dir"
PROXY_PRINT_CONNECTION_URL_KEY = "proxy_print_connection_url"
INJECTED_TOOL_NAME = "open_colab_browser_connection"
STATUS_TOOL_NAME = "get_colab_connection_status"

CHROME_COMMAND_CANDIDATES = (
    "google-chrome-stable",
    "google-chrome",
    "chrome",
    "chromium",
    "chromium-browser",
)


@dataclass(frozen=True)
class BrowserLaunchConfig:
    command: str | None = None
    profile: str | None = None
    user_data_dir: str | None = None
    connection_timeout: float = DEFAULT_UI_CONNECTION_TIMEOUT
    print_connection_url: bool = False

    def uses_explicit_browser(self) -> bool:
        return bool(self.command or self.profile or self.user_data_dir)


def build_colab_connection_url(token: str, port: int | str) -> str:
    return f"{COLAB}{SCRATCH_PATH}#mcpProxyToken={token}&mcpProxyPort={port}"


def redact_connection_url(url: str, token: str | None) -> str:
    if not token:
        return url
    return url.replace(f"mcpProxyToken={token}", "mcpProxyToken=<redacted>")


def resolve_browser_command(config: BrowserLaunchConfig) -> str | None:
    if config.command:
        return config.command
    if not config.uses_explicit_browser():
        return None
    for candidate in CHROME_COMMAND_CANDIDATES:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError(
        "A Chrome profile or user data directory was configured, but no Chrome "
        "or Chromium executable was found. Set --browser-command or "
        "COLAB_MCP_BROWSER_COMMAND."
    )


def browser_launch_args(url: str, config: BrowserLaunchConfig) -> list[str] | None:
    command = resolve_browser_command(config)
    if not command:
        return None
    args = shlex.split(command)
    if config.user_data_dir:
        args.append(f"--user-data-dir={config.user_data_dir}")
    if config.profile:
        args.append(f"--profile-directory={config.profile}")
    args.append(url)
    return args


def open_colab_browser(url: str, config: BrowserLaunchConfig) -> None:
    if config.print_connection_url:
        print(f"Colab MCP connection URL: {url}", file=sys.stderr, flush=True)
    args = browser_launch_args(url, config)
    if args is None:
        webbrowser.open_new(url)
        return
    logging.info("Opening Colab with browser command: %s", shlex.join(args[:-1]))
    subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


class ColabTransport(ClientTransport):
    def __init__(self, wss: ColabWebSocketServer):
        self.wss = wss

    @contextlib.asynccontextmanager
    async def connect_session(self, **session_kwargs) -> AsyncIterator[ClientSession]:
        async with ClientSession(
            self.wss.read_stream, self.wss.write_stream, **session_kwargs
        ) as session:
            yield session

    def __repr__(self) -> str:
        return "<ColabSessionProxyTransport>"


class ColabProxyClient:
    def __init__(
        self,
        wss: ColabWebSocketServer,
        browser_config: BrowserLaunchConfig | None = None,
    ):
        self.wss = wss
        self.browser_config = browser_config or BrowserLaunchConfig()
        self.stubbed_mcp_client = Client(FastMCP())
        self.proxy_mcp_client: Client | None = None
        self._exit_stack = AsyncExitStack()
        self._start_task = None

    def is_connected(self):
        return self.wss.connection_live.is_set() and self.proxy_mcp_client is not None

    async def await_proxy_connection(self):
        with contextlib.suppress(asyncio.TimeoutError):
            # wait for the connection to be live and for the proxy client to fully initialize
            connection_tasks = asyncio.gather(
                self.wss.connection_live.wait(), self._start_task
            )
            await asyncio.wait_for(
                connection_tasks,
                timeout=self.browser_config.connection_timeout,
            )

    def client_factory(self):
        if self.is_connected():
            return self.proxy_mcp_client
        # return a client mapped to a stubbed mcp server if there is no session proxy
        return self.stubbed_mcp_client

    async def _start_proxy_client(self):
        # blocks until a websocket connection is made successfully
        self.proxy_mcp_client = await self._exit_stack.enter_async_context(
            Client(ColabTransport(self.wss))
        )

    async def __aenter__(self):
        self._start_task = asyncio.create_task(self._start_proxy_client())
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._start_task:
            self._start_task.cancel()
        await self._exit_stack.aclose()


class ColabProxyMiddleware(Middleware):
    def __init__(self, proxy_client: ColabProxyClient):
        self.proxy_client = proxy_client
        self.last_message_connected = self.proxy_client.is_connected()

    async def on_message(self, context: MiddlewareContext, call_next):
        """
        Check for a change to Colab session connectivity on any communication with this MCP server and
        notify the client when the connectivity status has changed.
        """
        context.fastmcp_context.set_state(
            FE_CONNECTED_KEY, self.proxy_client.is_connected()
        )
        context.fastmcp_context.set_state(PROXY_TOKEN_KEY, self.proxy_client.wss.token)
        context.fastmcp_context.set_state(PROXY_PORT_KEY, self.proxy_client.wss.port)
        context.fastmcp_context.set_state(
            PROXY_CONNECTION_URL_KEY,
            build_colab_connection_url(
                self.proxy_client.wss.token, self.proxy_client.wss.port
            ),
        )
        context.fastmcp_context.set_state(
            PROXY_CONNECTION_TIMEOUT_KEY,
            self.proxy_client.browser_config.connection_timeout,
        )
        context.fastmcp_context.set_state(
            PROXY_BROWSER_COMMAND_KEY, self.proxy_client.browser_config.command
        )
        context.fastmcp_context.set_state(
            PROXY_BROWSER_PROFILE_KEY, self.proxy_client.browser_config.profile
        )
        context.fastmcp_context.set_state(
            PROXY_BROWSER_USER_DATA_DIR_KEY,
            self.proxy_client.browser_config.user_data_dir,
        )
        context.fastmcp_context.set_state(
            PROXY_PRINT_CONNECTION_URL_KEY,
            self.proxy_client.browser_config.print_connection_url,
        )

        result = await call_next(context)

        connected = self.proxy_client.is_connected()
        connection_state_changed = connected != self.last_message_connected
        self.last_message_connected = connected
        if connection_state_changed:
            await context.fastmcp_context.send_tool_list_changed()

        return result

    async def on_call_tool(self, context, call_next):
        result = await call_next(context)
        if context.message.name != INJECTED_TOOL_NAME:
            return result
        if self.proxy_client.is_connected():
            return result
        # if the tool call was for open_colab_browser_connection and there is no existing connection, try to await full connection
        await context.fastmcp_context.report_progress(
            progress=1, total=3, message="The user is not connected to the Colab UI"
        )
        await context.fastmcp_context.report_progress(
            progress=2,
            total=3,
            message=(
                "Waiting for user to connect in Colab - will wait for "
                f"{self.proxy_client.browser_config.connection_timeout:g}s"
            ),
        )
        await self.proxy_client.await_proxy_connection()
        if self.proxy_client.is_connected():
            await context.fastmcp_context.report_progress(
                progress=3, total=3, message="The Colab UI is successfully connected!"
            )
            return ToolResult(
                content=[TextContent(type="text", text="true")],
                structured_content={"result": True},
            )
        else:
            await context.fastmcp_context.report_progress(
                progress=3,
                total=3,
                message="Timeout while waiting for the user to connect.",
            )
            return ToolResult(
                content=[TextContent(type="text", text="false")],
                structured_content={"result": False},
            )


async def check_session_proxy_tool_fn(ctx: Context = CurrentContext()) -> bool:
    fe_connected = ctx.get_state(FE_CONNECTED_KEY)
    token = ctx.get_state(PROXY_TOKEN_KEY)
    port = ctx.get_state(PROXY_PORT_KEY)
    if fe_connected:
        return True
    url = ctx.get_state(PROXY_CONNECTION_URL_KEY) or build_colab_connection_url(
        token, port
    )
    config = BrowserLaunchConfig(
        command=ctx.get_state(PROXY_BROWSER_COMMAND_KEY),
        profile=ctx.get_state(PROXY_BROWSER_PROFILE_KEY),
        user_data_dir=ctx.get_state(PROXY_BROWSER_USER_DATA_DIR_KEY),
        connection_timeout=ctx.get_state(PROXY_CONNECTION_TIMEOUT_KEY)
        or DEFAULT_UI_CONNECTION_TIMEOUT,
        print_connection_url=bool(ctx.get_state(PROXY_PRINT_CONNECTION_URL_KEY)),
    )
    open_colab_browser(url, config)
    return False


async def get_colab_connection_status_tool_fn(
    ctx: Context = CurrentContext(),
) -> dict[str, object]:
    fe_connected = bool(ctx.get_state(FE_CONNECTED_KEY))
    token = ctx.get_state(PROXY_TOKEN_KEY)
    port = ctx.get_state(PROXY_PORT_KEY)
    url = ctx.get_state(PROXY_CONNECTION_URL_KEY) or build_colab_connection_url(
        token, port
    )
    return {
        "connected": fe_connected,
        "proxy_port": port,
        "connection_url_redacted": redact_connection_url(url, token),
        "connection_timeout_seconds": ctx.get_state(PROXY_CONNECTION_TIMEOUT_KEY)
        or DEFAULT_UI_CONNECTION_TIMEOUT,
        "browser": {
            "command": ctx.get_state(PROXY_BROWSER_COMMAND_KEY),
            "profile": ctx.get_state(PROXY_BROWSER_PROFILE_KEY),
            "user_data_dir": ctx.get_state(PROXY_BROWSER_USER_DATA_DIR_KEY),
            "print_connection_url": bool(
                ctx.get_state(PROXY_PRINT_CONNECTION_URL_KEY)
            ),
        },
    }


check_session_proxy_tool = Tool.from_function(
    fn=check_session_proxy_tool_fn,
    name=INJECTED_TOOL_NAME,
    description="Opens a connection to a Google Colab browser session and unlocks notebook editing tools. Returns a boolean representing whether the connection attempt succeeded",
)

get_colab_connection_status_tool = Tool.from_function(
    fn=get_colab_connection_status_tool_fn,
    name=STATUS_TOOL_NAME,
    description="Returns redacted Colab MCP connection diagnostics including browser configuration, proxy port, timeout, and connected state.",
)


class ColabSessionProxy:
    def __init__(self, browser_config: BrowserLaunchConfig | None = None):
        self._exit_stack = AsyncExitStack()
        self.browser_config = browser_config or BrowserLaunchConfig()
        self.proxy_server: FastMCPProxy | None = None
        # list order matters, see: https://gofastmcp.com/servers/middleware#multiple-middleware
        self.middleware: list[Middleware] = []
        self.wss: ColabWebSocketServer | None = None

    async def start_proxy_server(self):
        self.wss = await self._exit_stack.enter_async_context(ColabWebSocketServer())
        proxy_client = await self._exit_stack.enter_async_context(
            ColabProxyClient(self.wss, self.browser_config)
        )
        self.proxy_server = FastMCPProxy(
            client_factory=proxy_client.client_factory,
            instructions="Connects to a user's Google Colab session in a browser and allows for interactions with their Google Colab notebook",
        )
        # ColabProxyMiddleware must be first because it sets the fe_connected state
        self.middleware.append(ColabProxyMiddleware(proxy_client))
        self.middleware.append(
            ToolInjectionMiddleware(
                tools=[
                    check_session_proxy_tool,
                    get_colab_connection_status_tool,
                ]
            )
        )

    async def cleanup(self):
        await self._exit_stack.aclose()
