"""WebSocket endpoints for real-time notifications."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from typing import Dict, Set, Optional
import asyncio
import json
import logging
import redis.asyncio as aioredis
import os

logger = logging.getLogger("uvicorn")


router = APIRouter(tags=["websocket"])


# Connection manager for WebSocket connections
class ConnectionManager:
    """
    Manages WebSocket connections and Redis pub/sub for real-time notifications.

    Uses Redis pub/sub to support multiple backend instances (horizontal scaling).
    Each user has a dedicated channel: user:{user_id}:notifications
    """

    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self._redis_client: Optional[aioredis.Redis] = None
        self._pubsub_task: Optional[asyncio.Task] = None

    async def get_redis(self) -> aioredis.Redis:
        """Get or create Redis connection."""
        if self._redis_client is None:
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            self._redis_client = await aioredis.from_url(redis_url)
        return self._redis_client

    async def connect(self, websocket: WebSocket, user_id: str):
        """
        Accept a new WebSocket connection and subscribe to user's notification channel.
        """
        await websocket.accept()

        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)

        logger.info(f"WebSocket connected for user {user_id}. Active connections: {len(self.active_connections[user_id])}")

        # Start Redis pub/sub listener if not running
        if self._pubsub_task is None or self._pubsub_task.done():
            self._pubsub_task = asyncio.create_task(self._redis_listener())

    async def disconnect(self, websocket: WebSocket, user_id: str):
        """
        Remove a WebSocket connection.
        """
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

        logger.info(f"WebSocket disconnected for user {user_id}")

    async def send_personal_message(self, message: dict, user_id: str):
        """
        Send a message to all connections for a specific user.
        """
        if user_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Failed to send to user {user_id}: {e}")
                    disconnected.append(connection)

            # Remove failed connections
            for conn in disconnected:
                self.active_connections[user_id].discard(conn)

    async def broadcast(self, message: dict):
        """
        Broadcast a message to all connected users.
        """
        for user_id in list(self.active_connections.keys()):
            await self.send_personal_message(message, user_id)

    async def _redis_listener(self):
        """
        Listen for Redis pub/sub messages and forward to WebSocket connections.
        """
        try:
            redis = await self.get_redis()
            pubsub = redis.pubsub()

            # Subscribe to pattern for all user notifications
            await pubsub.psubscribe("user:*:notifications")

            logger.info("Redis pub/sub listener started")

            async for message in pubsub.listen():
                if message["type"] == "pmessage":
                    try:
                        # Extract user_id from channel name (user:{user_id}:notifications)
                        channel = message["channel"].decode() if isinstance(message["channel"], bytes) else message["channel"]
                        parts = channel.split(":")
                        if len(parts) >= 2:
                            user_id = parts[1]
                            data = json.loads(message["data"])
                            await self.send_personal_message(data, user_id)
                    except Exception as e:
                        logger.error(f"Error processing Redis message: {e}")

        except asyncio.CancelledError:
            logger.info("Redis pub/sub listener cancelled")
        except Exception as e:
            logger.error(f"Redis pub/sub listener error: {e}")

    async def publish_notification(self, user_id: str, notification: dict):
        """
        Publish a notification via Redis (for cross-process delivery).
        """
        try:
            redis = await self.get_redis()
            channel = f"user:{user_id}:notifications"
            await redis.publish(channel, json.dumps(notification))
            logger.debug(f"Published notification to {channel}")
        except Exception as e:
            logger.error(f"Failed to publish notification: {e}")


# Global connection manager
manager = ConnectionManager()


async def verify_websocket_token(token: str) -> Optional[dict]:
    """
    Verify JWT token for WebSocket authentication.

    Returns user dict if valid, None otherwise.
    """
    try:
        from auth import verify_access_token
        return verify_access_token(token)
    except Exception as e:
        logger.warning(f"WebSocket token verification failed: {e}")
        return None


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(..., description="JWT access token")
):
    """
    WebSocket endpoint for real-time notifications.

    Connect with: ws://host/ws?token=<jwt_token>

    Message types received:
    - approval_submitted: An article was submitted for your approval
    - approval_processed: Your approval request was processed
    - task_complete: A background task completed
    - task_failed: A background task failed

    You can also send messages:
    - {"type": "ping"}: Server responds with {"type": "pong"}
    - {"type": "subscribe", "channel": "approvals"}: Subscribe to a topic
    """
    # Verify token
    user = await verify_websocket_token(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    user_id = str(user.get("sub"))

    # Connect
    await manager.connect(websocket, user_id)

    try:
        # Send welcome message
        await websocket.send_json({
            "type": "connected",
            "user_id": user_id,
            "message": "WebSocket connection established"
        })

        # Listen for messages
        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0  # Send ping every 30s if no message
                )

                # Handle different message types
                msg_type = data.get("type")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})

                elif msg_type == "subscribe":
                    # Handle subscription requests (future feature)
                    channel = data.get("channel")
                    await websocket.send_json({
                        "type": "subscribed",
                        "channel": channel
                    })

                else:
                    logger.debug(f"Unknown WebSocket message type: {msg_type}")

            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
    finally:
        await manager.disconnect(websocket, user_id)


@router.websocket("/ws/{user_id}")
async def websocket_endpoint_with_user(
    websocket: WebSocket,
    user_id: str,
    token: str = Query(..., description="JWT access token")
):
    """
    WebSocket endpoint with explicit user_id in path.

    This endpoint validates that the token matches the requested user_id.
    Connect with: ws://host/ws/{user_id}?token=<jwt_token>
    """
    # Verify token
    user = await verify_websocket_token(token)
    if not user:
        await websocket.close(code=4001, reason="Invalid or expired token")
        return

    token_user_id = str(user.get("sub"))

    # Verify user_id matches token (unless admin)
    scopes = user.get("scopes", [])
    if token_user_id != user_id and "global:admin" not in scopes:
        await websocket.close(code=4003, reason="User ID mismatch")
        return

    # Connect using the requested user_id
    await manager.connect(websocket, user_id)

    try:
        await websocket.send_json({
            "type": "connected",
            "user_id": user_id,
            "message": "WebSocket connection established"
        })

        while True:
            try:
                data = await asyncio.wait_for(
                    websocket.receive_json(),
                    timeout=30.0
                )

                msg_type = data.get("type")

                if msg_type == "ping":
                    await websocket.send_json({"type": "pong"})
                elif msg_type == "subscribe":
                    channel = data.get("channel")
                    await websocket.send_json({
                        "type": "subscribed",
                        "channel": channel
                    })

            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error for user {user_id}: {e}")
    finally:
        await manager.disconnect(websocket, user_id)


# Utility function to send notifications from other parts of the application
async def send_notification(user_id: str, notification: dict):
    """
    Send a notification to a user via WebSocket.

    This can be called from anywhere in the application.
    Uses Redis pub/sub for cross-process delivery.
    """
    await manager.publish_notification(user_id, notification)


def send_notification_sync(user_id: str, notification: dict):
    """
    Synchronous version for use in background tasks.

    Uses standard Redis client instead of async.
    """
    try:
        import redis
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url)
        channel = f"user:{user_id}:notifications"
        r.publish(channel, json.dumps(notification))
        logger.debug(f"Published sync notification to {channel}")
    except Exception as e:
        logger.error(f"Failed to publish sync notification: {e}")
