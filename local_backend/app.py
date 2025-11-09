"""FastAPI application factory for the local responses service."""

from __future__ import annotations

import logging
import re
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterator, Sequence

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse


def create_app(config: ServiceConfig | None = None) -> FastAPI:
    service_config = config or ServiceConfig()
    logging.basicConfig(level=logging.INFO)
    state = ServiceState(service_config)

    app = FastAPI(title="Local Responses Service", version="0.1.0")
    app.state.service_state = state

    
    return app
