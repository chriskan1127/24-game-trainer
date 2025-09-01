#!/usr/bin/env python3
"""
Development server startup script for 24-Game Multiplayer Server.
"""

import uvicorn
from config import settings

if __name__ == "__main__":
    print(f"Starting 24-Game Multiplayer Server...")
    print(f"Environment: {settings.environment}")
    print(f"Host: {settings.host}:{settings.port}")
    print(f"Debug mode: {settings.debug}")
    
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info" if not settings.debug else "debug"
    ) 