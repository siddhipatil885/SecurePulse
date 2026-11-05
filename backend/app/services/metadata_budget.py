"""Keep camera metadata bounded; media bytes never belong in SQL JSON columns."""
import hashlib
import json


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')


def metadata_digest(value):
    return hashlib.sha256(encoded(value)).hexdigest()


def compact_metadata(metadata, max_bytes=8192):
    changed = False
    media_keys = {'image', 'image_base64', 'thumbnail', 'thumbnail_base64', 'snapshot',
                  'video', 'video_base64', 'frame', 'raw_frame', 'clip_bytes', 'image_bytes', 'video_bytes'}
    def bounded(value, depth=0):
        nonlocal changed
        if isinstance(value, bytes):
            changed = True
            return '[binary omitted; media stored on host]'
        if isinstance(value, str):
            if len(value) > 1024:
                changed = True
                return value[:1024] + '[truncated]'
            return value
        if isinstance(value, (dict, list)) and depth >= 4:
            changed = True
            return '[nested metadata omitted]'
        if isinstance(value, dict):
            result = {}
            for index, (key, item) in enumerate(value.items()):
                if index >= 64:
                    changed = True
                    break
                if str(key).lower() in media_keys and not isinstance(item, (bool, int, float, type(None))):
                    changed = True
                    continue
                name = str(key)[:128]
                changed |= name != key
                result[name] = bounded(item, depth + 1)
            return result
        if isinstance(value, list):
            changed |= len(value) > 32
            return [bounded(item, depth + 1) for item in value[:32]]
        return value
    result = bounded(metadata)
    # Preserve common rule/track fields first when a payload still exceeds budget.
    important = {'zones', 'zone', 'lifecycle', 'revision', 'start_time', 'end_time', 'has_snapshot',
                 'track_id', 'tracking_state', 'bounding_box_normalized', 'security_decision'}
    while len(encoded(result)) > max_bytes - 128 and result:
        candidates = [key for key in result if key not in important] or list(result)
        largest = max(candidates, key=lambda key: len(encoded(result[key])))
        del result[largest]
        changed = True
    if changed:
        result['_metadata_truncated'] = True
        result['_original_metadata_sha256'] = metadata_digest(metadata)
    return result
