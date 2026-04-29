#!/usr/bin/env python3
"""Run the API Chaos Agent server."""

import uvicorn

from api_chaos_agent.core.config import settings


def main() -> None:
    uvicorn.run(
        "api_chaos_agent.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
    )


if __name__ == "__main__":
    main()
