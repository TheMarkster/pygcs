from __future__ import annotations

from .event import broadcast_func
from typing import TYPE_CHECKING, Optional, Union

if TYPE_CHECKING:
    from .host import EventHost

# Global registry to hold the singleton
_event_host: Optional[EventHost] = None

def set_event_host(host: EventHost):
    """Set the global event host singleton"""
    global _event_host
    if _event_host is not None:
        raise RuntimeError("Event host is already set")
    _event_host = host

def get_event_host() -> EventHost:
    """Get the global event host singleton"""
    global _event_host
    if _event_host is None:
        raise RuntimeError("Event host is not set. Call set_event_host() first.")
    return _event_host

@broadcast_func
def broadcast(signal, *args, _metadata=None, **kwargs):
    """Convenience function to broadcast an event"""
    get_event_host().broadcast(signal, *args, _metadata=_metadata, **kwargs)

@broadcast_func
def local_broadcast(signal, *args, _metadata=None, **kwargs):
    """Broadcast an event that should not be forwarded to gateways"""
    _metadata = _metadata or {}
    _metadata['_local_only'] = True
    get_event_host().broadcast(signal, *args, _metadata=_metadata, **kwargs)

def consumer(signal: str):
    """Decorator to register a method as a consumer for a signal"""
    return get_event_host().consumer(signal)
