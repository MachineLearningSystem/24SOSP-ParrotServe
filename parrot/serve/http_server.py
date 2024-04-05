# Copyright (c) 2023 by Microsoft Corporation.
# Licensed under the MIT license.


import os
import argparse
import asyncio
import traceback
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from uvicorn import Config, Server

from parrot.pfunc.function import SemanticCall, NativeCall
from parrot.serve.core import PCore
from parrot.serve.os_creator import create_os
from Parrot.parrot.os.engine.engine_node import EngineRuntimeInfo
from parrot.engine.config import EngineConfig
from parrot.utils import (
    get_logger,
    create_task_in_loop,
    set_log_output_file,
    redirect_stdout_stderr_to_file,
)
from parrot.exceptions import ParrotCoreUserError, ParrotCoreInternalError
from parrot.testing.latency_simulator import get_latency


logger = get_logger("OS Server")

# FastAPI app
app = FastAPI()

# Engine
pcore: Optional[PCore] = None

# Mode
release_mode = False


@app.exception_handler(ParrotCoreUserError)
async def parrot_os_internal_error_handler(request: Request, exc: ParrotCoreUserError):
    traceback_info = "" if release_mode else traceback.format_exc()
    return JSONResponse(
        status_code=500,
        content={
            "error": repr(exc),
            "traceback": traceback_info,
        },
    )


@app.exception_handler(ParrotCoreInternalError)
async def parrot_os_internal_error_handler(
    request: Request, exc: ParrotCoreInternalError
):
    raise exc


"""
Public APIs.
"""

API_VERSION = "v1"


@app.post(f"/{API_VERSION}/session")
async def create_session(request: Request):
    payload = await request.json()
    session_id = await pcore.create_session()
    return {"session_id": session_id}


"""
Internal APIs.
"""


@app.post("/engine_heartbeat")
async def engine_heartbeat(request: Request):
    payload = await request.json()
    engine_id = payload["engine_id"]
    engine_name = payload["engine_name"]
    logger.debug(f"Engine {engine_name} (id={engine_id}) heartbeat received.")
    engine_info = EngineRuntimeInfo(**payload["runtime_info"])
    await pcore.engine_heartbeat(engine_id, engine_info)
    return {}


@app.post("/register_engine")
async def register_engine(request: Request):
    payload = await request.json()
    logger.debug(f"Register engine received.")
    engine_config = EngineConfig(**payload["engine_config"])
    engine_id = await pcore.register_engine(engine_config)
    return {"engine_id": engine_id}


def start_server(
    os_config_path: str,
    release_mode: bool = False,
    override_args: dict = {},
):
    global pcore
    global app

    # The Operating System Core
    pcore = create_os(
        os_config_path=os_config_path,
        release_mode=release_mode,
        override_args=override_args,
    )

    loop = asyncio.new_event_loop()
    config = Config(
        app=app,
        loop=loop,
        host=pcore.os_config.host,
        port=pcore.os_config.port,
        log_level="info",
    )
    uvicorn_server = Server(config)
    # NOTE(chaofan): We use `fail_fast` because this project is still in development
    # For real deployment, maybe we don't need to quit the backend when there is an error
    create_task_in_loop(pcore.os_loop(), loop=loop, fail_fast=True)
    loop.run_until_complete(uvicorn_server.serve())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parrot OS server")

    parser.add_argument(
        "--host",
        type=str,
        help="Host of OS server",
    )

    parser.add_argument(
        "--port",
        type=int,
        help="Port of OS server",
    )

    parser.add_argument(
        "--config_path",
        type=str,
        help="Path to the config file of PCore.",
        required=True,
    )

    parser.add_argument(
        "--log_dir",
        type=str,
        default=None,
        help="Path to the log directory. If not set, logs will be printed to stdout.",
    )

    parser.add_argument(
        "--log_filename",
        type=str,
        default="os.log",
        help="Filename of the OS server.",
    )

    parser.add_argument(
        "--release_mode",
        action="store_true",
        help="Run in release mode. In debug mode, "
        "OS will print logs and expose extra information to clients.",
    )

    args = parser.parse_args()
    release_mode = args.release_mode

    if release_mode:
        # Disable logging
        import logging

        # We don't disable the error log
        logging.disable(logging.DEBUG)
        logging.disable(logging.INFO)

    # Set log output file
    if args.log_dir is not None:
        set_log_output_file(
            log_file_dir_path=args.log_dir,
            log_file_name=args.log_filename,
        )

        redirect_stdout_stderr_to_file(
            log_file_dir_path=args.log_dir,
            file_name="os_stdout.out",
        )

    override_args = {}
    if args.host is not None:
        override_args["host"] = args.host
    if args.port is not None:
        override_args["port"] = args.port

    start_server(
        os_config_path=args.config_path,
        release_mode=release_mode,
        override_args=override_args,
    )
