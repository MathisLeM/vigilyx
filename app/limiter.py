"""Shared slowapi rate-limiter instance.

Import `limiter` wherever you need to apply rate limits, and attach it
to the FastAPI app in main.py via `app.state.limiter`.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
