"""Keep normal test suites isolated from locally configured cloud services.

Cloud acceptance is explicit; its script reads root Neon env independently.
"""
import os

os.environ.setdefault("NEON_AUTH_BASE_URL", "")
os.environ.setdefault("EVIDENCE_STORAGE", "local")
os.environ.setdefault("AUTH_ENABLED", "false")
os.environ.setdefault("FRIGATE_URL", "http://localhost:5000")
os.environ.setdefault("MQTT_USERNAME", "")
os.environ.setdefault("MQTT_PASSWORD", "")
