# Alerting Service: Real-Time Notifications

The **Alerting Service** acts as the bridge between the internal AI intelligence and the human security team. It ensures that high-priority shoplifting events are dispatched to the right people via external channels like Telegram and MQTT.

---

## 1. Event Flow

1.  **Subscription**: The service monitors a dedicated Redis broadcast channel (e.g., `detections:*`).
2.  **Filtering**: It extracts the `action` label. If the label is `shoplifting` and the confidence scores exceed the configured `ALERT_THRESHOLD`, it triggers the notification sequence.
3.  **Dispatching**:
    -   **Telegram**: Sends a structured message to the security group containing the Camera ID, Event Category, and Confidence.
    -   **MQTT**: Publishes a JSON payload to the IoT broker, which can be picked up by smart lighting, sirens, or third-party physical security systems.

---

## 2. Key Features

- **Decoupled Architecture**: By running as a separate service, the high-latency of external APIs (like the Telegram Bot API) never blocks the real-time inference loop.
- **Evidence Ready**: The service logic is designed to support future "evidence snapshot" payloads (jpegs) attached to alerts.
- **Multi-Destination**: Supports simultaneous dispatch to both professional IoT brokers (MQTT) and consumer messaging apps (Telegram).

---

## 3. Configuration

| Variable | Description |
| :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Your BotFather API token. |
| `TELEGRAM_ADMIN_CHAT_IDS` | Comma-separated chat IDs that receive alerts. |
| `ALERT_CONFIDENCE_THRESHOLD` | Minimum threshold (e.g., 0.85) to trigger an external message. |

---

## 🛠️ Testing Alerts
You can verify the alerting flow by running the `tests/integration/test_video_pipeline.py` script with a video that contains a shoplifting event and ensuring your Telegram bot receives the message.
