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

import argparse
import asyncio
import datetime
import logging
import os
import tempfile
import sys

from fastmcp import FastMCP
from fastmcp.utilities import logging as fastmcp_logger

from colab_mcp.session import BrowserLaunchConfig, ColabSessionProxy


mcp = FastMCP(name="ColabMCP")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    return positive_float(value)


def positive_float(value: str | float) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def init_logger(logdir):
    log_filename = datetime.datetime.now().strftime(
        f"{logdir}/colab-mcp.%Y-%m-%d_%H-%M-%S.log"
    )
    logging.basicConfig(
        format="%(asctime)s %(levelname)s:%(message)s",
        datefmt="%m/%d/%Y %I:%M:%S %p",
        filename=log_filename,
        level=logging.INFO,  # Set the minimum logging level to capture
    )
    fastmcp_logger.get_logger("colab-mcp").info("logging to %s" % log_filename)


def parse_args(v):
    parser = argparse.ArgumentParser(
        description="ColabMCP is an MCP server that lets you interact with Colab."
    )
    parser.add_argument(
        "-l",
        "--log",
        help="if set, use this directory as a location for logfiles (if unset, will log to %s/colab-mcp-logs/)"
        % tempfile.gettempdir(),
        action="store",
        default=tempfile.mkdtemp(prefix="colab-mcp-logs-"),
    )
    parser.add_argument(
        "-p",
        "--enable-proxy",
        help="if set, enable the runtime proxy (enabled by default).",
        action="store_true",
        default=True,
    )
    parser.add_argument(
        "--browser-command",
        help=(
            "browser executable or command used to open Colab. "
            "Defaults to COLAB_MCP_BROWSER_COMMAND, or an auto-detected "
            "Chrome/Chromium binary when profile options are set."
        ),
        default=os.environ.get("COLAB_MCP_BROWSER_COMMAND"),
    )
    parser.add_argument(
        "--browser-profile",
        help=(
            "Chrome profile directory to open, for example 'Default'. "
            "Defaults to COLAB_MCP_BROWSER_PROFILE."
        ),
        default=os.environ.get("COLAB_MCP_BROWSER_PROFILE"),
    )
    parser.add_argument(
        "--browser-user-data-dir",
        help=(
            "Chrome user data directory, for example ~/.config/google-chrome. "
            "Defaults to COLAB_MCP_BROWSER_USER_DATA_DIR."
        ),
        default=os.environ.get("COLAB_MCP_BROWSER_USER_DATA_DIR"),
    )
    parser.add_argument(
        "--connection-timeout",
        help=(
            "seconds to wait for the Colab browser UI to connect. "
            "Defaults to COLAB_MCP_CONNECTION_TIMEOUT or 60."
        ),
        type=positive_float,
        default=env_float("COLAB_MCP_CONNECTION_TIMEOUT", 60.0),
    )
    parser.add_argument(
        "--print-connection-url",
        help=(
            "write the generated Colab connection URL to stderr when opening "
            "the browser. Defaults to COLAB_MCP_PRINT_CONNECTION_URL."
        ),
        action="store_true",
        default=env_bool("COLAB_MCP_PRINT_CONNECTION_URL"),
    )
    return parser.parse_args(v)


async def main_async():
    args = parse_args(sys.argv[1:])
    init_logger(args.log)

    if args.enable_proxy:
        logging.info("enabling session proxy tools")
        session_mcp = ColabSessionProxy(
            BrowserLaunchConfig(
                command=args.browser_command,
                profile=args.browser_profile,
                user_data_dir=args.browser_user_data_dir,
                connection_timeout=args.connection_timeout,
                print_connection_url=args.print_connection_url,
            )
        )
        await session_mcp.start_proxy_server()
        mcp.mount(session_mcp.proxy_server)
        for middleware in session_mcp.middleware:
            mcp.add_middleware(middleware)

    try:
        await mcp.run_async()

    finally:
        if args.enable_proxy:
            await session_mcp.cleanup()


def main() -> None:
    asyncio.run(main_async())
