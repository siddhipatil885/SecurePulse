"""
Phase 1 MQTT Verification Script
Connects to local Mosquitto MQTT broker and prints incoming Frigate telemetry & person detection events.
"""

import json
import sys
import time
import paho.mqtt.client as mqtt

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
TOPICS = [
    ("frigate/events", 0),
    ("frigate/stats", 0),
    ("frigate/+/person", 0),
    ("frigate/+/person/state", 0),
]


def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print(f"[+] Successfully connected to MQTT Broker at {MQTT_BROKER}:{MQTT_PORT}")
        for topic, qos in TOPICS:
            client.subscribe(topic, qos=qos)
            print(f"[+] Subscribed to topic: {topic}")
    else:
        print(f"[-] Connection failed with result code: {rc}")


def on_message(client, userdata, msg):
    try:
        payload_str = msg.payload.decode("utf-8")
        print(f"\n[RECEIVED EVENT] Topic: {msg.topic}")
        try:
            data = json.loads(payload_str)
            print(json.dumps(data, indent=2))
        except json.JSONDecodeError:
            print(f"Payload: {payload_str}")
    except Exception as e:
        print(f"[-] Error processing message: {e}")


def main():
    print("=== SecurePulse Phase 1 MQTT Event Subscriber Test ===")
    client = mqtt.Client(client_id="securepulse-phase1-test-subscriber")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        print(f"[...] Connecting to MQTT broker {MQTT_BROKER}:{MQTT_PORT}...")
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[*] Stopping subscriber.")
        client.disconnect()
        sys.exit(0)
    except Exception as e:
        print(f"[-] Failed to connect to MQTT broker: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
