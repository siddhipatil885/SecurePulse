# Phase 1 Setup & Operation Guide

## Overview

Phase 1 initializes the edge-first perception infrastructure for SecurePulse using Frigate NVR, Eclipse Mosquitto MQTT Broker, and RTSP stream ingestion.

---

## Prerequisites

1. **Docker Engine (v20.10+)** & **Docker Compose (v2.0+)** installed on host machine.
2. **IP Camera RTSP URL** or sample video for local stream simulation.
3. **Python 3.10+** (with `paho-mqtt` installed for local verification).

---

## Directory Structure

```text
SecurePulse/
├── frigate/
│   ├── config/
│   │   └── frigate.yml       # Frigate NVR configuration
│   └── media/                # Recorded event video clips & snapshots
├── deployment/
│   ├── docker-compose.yml    # Services: frigate, mqtt, rtsp-sim
│   ├── .env.example          # Environment variables template
│   └── mosquitto/
│       └── config/
│           └── mosquitto.conf # MQTT Broker configuration
├── tests/
│   └── test_mqtt_subscriber.py # MQTT Event consumer verification
└── docs/
    └── phase1_setup.md       # Setup documentation
```

---

## Step 1: Environment Configuration

Copy the sample environment file to `.env`:

```bash
cd deployment
cp .env.example .env
```

If connecting to a physical IP camera, update `RTSP_STREAM_URL` in `.env`:
```env
RTSP_STREAM_URL=rtsp://admin:password@192.168.1.100:554/h264
```

---

## Step 2: Start Containers

Launch Frigate NVR and Mosquitto MQTT broker:

```bash
docker compose up -d
```

Check service status:
```bash
docker compose ps
```

---

## Step 3: Verify Services

1. **Frigate Web UI**: Open `http://localhost:5000` in your web browser to view:
   - Live RTSP video stream (`front_door`).
   - Real-time person detection bounding boxes and tracking IDs.
   - Event snapshots and recorded clips.
2. **MQTT Broker**: Verify port `1883` is open and accepting subscriber connections.

---

## Step 4: Verify MQTT Event Consumption

Run the Python verification subscriber to confirm Frigate event publishing:

```bash
pip install paho-mqtt
python ../tests/test_mqtt_subscriber.py
```

Expected JSON Output on Person Detection:
```json
{
  "type": "new",
  "before": {},
  "after": {
    "id": "16928371-person",
    "camera": "front_door",
    "label": "person",
    "top_score": 0.88,
    "has_snapshot": true,
    "has_clip": true
  }
}
```

---

## Next Phase

Once Phase 1 verification is confirmed, proceed to **Phase 2: FastAPI Backend & Event Schema Normalization**.
