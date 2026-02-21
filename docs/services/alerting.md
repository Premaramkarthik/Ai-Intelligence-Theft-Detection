# Alerting Service

The **Alerting Service** is responsible for external notifications. When the Inference pipeline detects a high-confidence suspicious event, this service ensures the right people are notified immediately.

## Purpose
- Decouple notification logic from the time-critical inference loop.
- Support multiple notification channels (Telegram, MQTT, Webhooks).
- Provide a summary of detected events with confidence scores.

## Technologies Used
- **Aiohttp**: Asynchronous HTTP client for non-blocking communication with external APIs (like Telegram).
- **Telegram Bot API**: Used to send instant messages and evidence snapshots to security personnel.
- **MQTT (Message Queuing Telemetry Transport)**: A lightweight messaging protocol for small sensors and mobile devices, often used for integration with IoT dashboards or smart building systems.
- **Redis Pub/Sub**: Listens for "high-confidence" prediction events published by the Inference service.

## Workflow
1. **Listen**: Subscribes to the `alerts` channel in Redis.
2. **Filter**: Checks the event confidence against `ALERT_CONF_THRESHOLD`.
3. **Dispatch**: 
    - Sends a message to Telegram using `TelegramService`.
    - Publishes a payload to an MQTT topic using `MQTTService`.
4. **Log**: Records the alert dispatch status for auditing.

## Configuration
- `TELEGRAM_TOKEN` / `TELEGRAM_CHAT_ID`: Bot credentials.
- `MQTT_HOST` / `MQTT_PORT`: Broker details.
- `ALERT_CONF_THRESHOLD`: Minimum confidence (e.g., 0.8) to trigger an external alert.
