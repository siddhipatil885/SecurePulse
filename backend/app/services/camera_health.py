"""Short-lived live Frigate health projection; no telemetry rows stored in Neon."""
import asyncio
import math
from time import monotonic

import httpx

_cache = {}
_lock = asyncio.Lock()


async def camera_states(cameras, settings):
    key = (settings.frigate_url, settings.frigate_username, settings.frigate_password, settings.frigate_verify_ssl)
    async with _lock:
        cached = _cache.get(key)
        if not cached or monotonic() - cached[0] >= 5:
            stats = {}
            try:
                async with httpx.AsyncClient(timeout=3, verify=settings.frigate_verify_ssl, trust_env=False) as client:
                    if settings.frigate_username and settings.frigate_password:
                        response = await client.post(settings.frigate_url.rstrip('/') + '/api/login',
                            json={'user': settings.frigate_username, 'password': settings.frigate_password})
                        response.raise_for_status()
                    response = await client.get(settings.frigate_url.rstrip('/') + '/api/stats')
                    response.raise_for_status()
                    payload = response.json()
                    if isinstance(payload, dict) and isinstance(payload.get('cameras'), dict):
                        stats = payload['cameras']
            except (httpx.HTTPError, ValueError, TypeError, AttributeError):
                pass
            if len(_cache) > 8:
                _cache.clear()
            _cache[key] = (monotonic(), stats)
        stats = _cache[key][1]
    result = {}
    for camera in cameras:
        status = 'disabled' if not camera.enabled else 'unknown'
        item = stats.get(camera.frigate_camera_name)
        if camera.enabled and isinstance(item, dict):
            fps = item.get('camera_fps')
            if isinstance(fps, (int, float)) and not isinstance(fps, bool) and math.isfinite(fps):
                status = 'online' if fps > 0 else 'offline'
        result[camera.id] = status
    return result
