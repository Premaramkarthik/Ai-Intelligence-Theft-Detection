# Signaling Service

The **Signaling Service** provides the external interface for the pipeline. It handles administrative tasks, live monitoring, and real-time event streaming.

## Purpose
- Provide a REST API for system management (ROI configuration, health checks).
- Stream live detection results via WebSockets.
- Handle user authentication and authorization.

## Technologies Used
- **FastAPI**: A modern, high-performance web framework for building APIs with Python 3.7+ based on standard Python type hints.
- **WebSockets**: Enables bi-directional, real-time communication between the backend and the frontend for live video overlays.
- **JWT (JSON Web Tokens)**: Securely transmits information between parties as a JSON object, used for API authentication.
- **Pydantic**: Data validation and settings management using Python type annotations.
- **SlowAPI**: Rate limiting for FastAPI to prevent abuse of the `/auth/token` and `/ws` endpoints.

## Key Features
- **Live WebSocket Feed**: Subscribes to the Redis "predictions" channel and broadcasts events to connected clients.
- **Dynamic Config**: Allows administrators to update Camera ROIs and Confidence Thresholds live via REST endpoints. These updates are reflected across all services via Redis.
- **Safety**: Robust input validation and audit logging for all administrative actions.

## API Documentation
See the dedicated [API Documentation](../api.md) for endpoint details.
