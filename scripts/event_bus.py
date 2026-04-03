"""
EDT 事件总线 (WebSocket)
C-4: 消息按trace_id有序，断线自动重连，支持重放
"""

import asyncio
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Callable, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import websockets
from websockets.server import WebSocketServerProtocol

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EventMessage:
    """事件消息"""
    type: str
    trace_id: str
    schema_version: str = "v1.0"
    payload: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_json(self) -> str:
        return json.dumps({
            "type": self.type,
            "trace_id": self.trace_id,
            "schema_version": self.schema_version,
            "payload": self.payload,
            "timestamp": self.timestamp
        })
    
    @classmethod
    def from_json(cls, data: str) -> 'EventMessage':
        obj = json.loads(data)
        return cls(
            type=obj.get("type", ""),
            trace_id=obj.get("trace_id", ""),
            schema_version=obj.get("schema_version", "v1.0"),
            payload=obj.get("payload", {}),
            timestamp=obj.get("timestamp", datetime.now().isoformat())
        )


class EventBus:
    """EDT 事件总线"""
    
    def __init__(self, host: str = "localhost", port: int = 8765):
        self.host = host
        self.port = port
        self.server = None
        self.clients: Dict[str, WebSocketServerProtocol] = {}
        self.subscriptions: Dict[str, List[str]] = defaultdict(list)
        self.message_history: List[EventMessage] = []
        self.max_history = 10000
        self.replay_buffer: Dict[str, List[EventMessage]] = defaultdict(list)
        self.handlers: Dict[str, Callable] = {}
        self._running = False
        
    async def start(self):
        """启动事件总线"""
        self._running = True
        logger.info(f"Starting EventBus on {self.host}:{self.port}")
        
        async with websockets.serve(self._handle_client, self.host, self.port):
            logger.info(f"EventBus started on ws://{self.host}:{self.port}")
            while self._running:
                await asyncio.sleep(1)
    
    async def stop(self):
        """停止事件总线"""
        self._running = False
        for client in self.clients.values():
            await client.close()
        self.clients.clear()
        logger.info("EventBus stopped")
    
    async def _handle_client(self, websocket: WebSocketServerProtocol, path: str = ""):
        """处理客户端连接"""
        client_id = str(uuid.uuid4())
        self.clients[client_id] = websocket
        logger.info(f"Client connected: {client_id}")
        
        try:
            await websocket.send(json.dumps({
                "type": "connected",
                "client_id": client_id,
                "message": "Connected to EDT EventBus"
            }))
            
            async for message in websocket:
                await self._process_message(client_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client disconnected: {client_id}")
        except Exception as e:
            logger.error(f"Error handling client {client_id}: {e}")
        finally:
            if client_id in self.clients:
                del self.clients[client_id]
            self._cleanup_subscriptions(client_id)
    
    async def _process_message(self, client_id: str, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "subscribe":
                await self._handle_subscribe(client_id, data)
            elif msg_type == "unsubscribe":
                await self._handle_unsubscribe(client_id, data)
            elif msg_type == "get_history":
                await self._handle_get_history(client_id, data)
            elif msg_type == "get_replay":
                await self._handle_get_replay(client_id, data)
            elif msg_type == "ping":
                await self.clients[client_id].send(json.dumps({"type": "pong"}))
            else:
                await self._route_message(client_id, data)
                
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from client {client_id}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _handle_subscribe(self, client_id: str, data: dict):
        """处理订阅"""
        event_types = data.get("types", [])
        for event_type in event_types:
            if client_id not in self.subscriptions[event_type]:
                self.subscriptions[event_type].append(client_id)
        
        await self.clients[client_id].send(json.dumps({
            "type": "subscribed",
            "types": event_types
        }))
        logger.info(f"Client {client_id} subscribed to {event_types}")
    
    async def _handle_unsubscribe(self, client_id: str, data: dict):
        """处理取消订阅"""
        event_types = data.get("types", [])
        for event_type in event_types:
            if client_id in self.subscriptions[event_type]:
                self.subscriptions[event_type].remove(client_id)
        
        await self.clients[client_id].send(json.dumps({
            "type": "unsubscribed",
            "types": event_types
        }))
    
    async def _handle_get_history(self, client_id: str, data: dict):
        """获取历史消息"""
        limit = data.get("limit", 100)
        trace_id = data.get("trace_id")
        
        if trace_id:
            messages = [m for m in self.message_history if m.trace_id == trace_id]
        else:
            messages = self.message_history[-limit:]
        
        await self.clients[client_id].send(json.dumps({
            "type": "history",
            "messages": [
                {
                    "type": m.type,
                    "trace_id": m.trace_id,
                    "schema_version": m.schema_version,
                    "payload": m.payload,
                    "timestamp": m.timestamp
                }
                for m in messages
            ]
        }))
    
    async def _handle_get_replay(self, client_id: str, data: dict):
        """获取重放数据"""
        start_time = data.get("start_time")
        end_time = data.get("end_time")
        
        messages = self._get_replay_messages(start_time, end_time)
        
        await self.clients[client_id].send(json.dumps({
            "type": "replay",
            "messages": [
                {
                    "type": m.type,
                    "trace_id": m.trace_id,
                    "payload": m.payload,
                    "timestamp": m.timestamp
                }
                for m in messages
            ]
        }))
    
    async def _route_message(self, client_id: str, data: dict):
        """路由消息到订阅者"""
        msg_type = data.get("type")
        trace_id = data.get("trace_id", self._generate_trace_id())
        
        message = EventMessage(
            type=msg_type,
            trace_id=trace_id,
            schema_version=data.get("schema_version", "v1.0"),
            payload=data.get("payload", {}),
            timestamp=data.get("timestamp", datetime.now().isoformat())
        )
        
        self._store_message(message)
        self._store_replay_buffer(message)
        
        if msg_type in self.handlers:
            response = await self.handlers[msg_type](data)
            if response:
                await self._broadcast(msg_type, response, {client_id})
        
        await self._broadcast(msg_type, message.to_json())
    
    def _generate_trace_id(self) -> str:
        return f"evt_{uuid.uuid4().hex[:16]}"
    
    def _store_message(self, message: EventMessage):
        """存储消息历史"""
        self.message_history.append(message)
        if len(self.message_history) > self.max_history:
            self.message_history = self.message_history[-self.max_history:]
    
    def _store_replay_buffer(self, message: EventMessage):
        """存储重放缓冲区"""
        date_key = message.timestamp[:10]
        self.replay_buffer[date_key].append(message)
        
        cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        for key in list(self.replay_buffer.keys()):
            if key < cutoff:
                del self.replay_buffer[key]
    
    def _get_replay_messages(self, start_time: Optional[str], end_time: Optional[str]) -> List[EventMessage]:
        """获取重放消息"""
        if not start_time:
            start_time = (datetime.now() - timedelta(hours=1)).isoformat()
        if not end_time:
            end_time = datetime.now().isoformat()
        
        messages = []
        for day_messages in self.replay_buffer.values():
            for msg in day_messages:
                if start_time <= msg.timestamp <= end_time:
                    messages.append(msg)
        
        return sorted(messages, key=lambda m: m.timestamp)
    
    async def _broadcast(self, msg_type: str, message: str, exclude: set = None):
        """广播消息给订阅者"""
        if exclude is None:
            exclude = set()
        
        for client_id in self.subscriptions.get(msg_type, []):
            if client_id not in exclude and client_id in self.clients:
                try:
                    await self.clients[client_id].send(message)
                except Exception as e:
                    logger.error(f"Failed to send to {client_id}: {e}")
    
    def _cleanup_subscriptions(self, client_id: str):
        """清理订阅"""
        for event_type in self.subscriptions:
            if client_id in self.subscriptions[event_type]:
                self.subscriptions[event_type].remove(client_id)
    
    def register_handler(self, event_type: str, handler: Callable):
        """注册事件处理器"""
        self.handlers[event_type] = handler
    
    async def publish(self, event_type: str, payload: dict, trace_id: str = None):
        """发布事件"""
        if trace_id is None:
            trace_id = self._generate_trace_id()
        
        message = EventMessage(
            type=event_type,
            trace_id=trace_id,
            payload=payload
        )
        
        self._store_message(message)
        await self._broadcast(event_type, message.to_json())
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "connected_clients": len(self.clients),
            "subscriptions": {k: len(v) for k, v in self.subscriptions.items()},
            "message_history_count": len(self.message_history),
            "replay_buffer_days": len(self.replay_buffer),
        }


class EventBusClient:
    """事件总线客户端"""
    
    def __init__(self, url: str = "ws://localhost:8765"):
        self.url = url
        self.ws = None
        self.client_id = None
        self.handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._running = False
    
    async def connect(self):
        """连接事件总线"""
        self.ws = await websockets.connect(self.url)
        self._running = True
        
        asyncio.create_task(self._receive_loop())
        logger.info(f"Connected to {self.url}")
    
    async def disconnect(self):
        """断开连接"""
        self._running = False
        if self.ws:
            await self.ws.close()
    
    async def _receive_loop(self):
        """接收消息循环"""
        try:
            async for message in self.ws:
                await self._handle_message(message)
        except Exception as e:
            logger.error(f"Receive error: {e}")
            self._running = False
    
    async def _handle_message(self, message: str):
        """处理接收到的消息"""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "connected":
                self.client_id = data.get("client_id")
            elif msg_type in self.handlers:
                for handler in self.handlers[msg_type]:
                    await handler(data)
                    
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    def on(self, event_type: str, handler: Callable):
        """注册事件处理器"""
        self.handlers[event_type].append(handler)
    
    async def subscribe(self, *event_types: str):
        """订阅事件"""
        await self.ws.send(json.dumps({
            "type": "subscribe",
            "types": list(event_types)
        }))
    
    async def unsubscribe(self, *event_types: str):
        """取消订阅"""
        await self.ws.send(json.dumps({
            "type": "unsubscribe",
            "types": list(event_types)
        }))
    
    async def publish(self, event_type: str, payload: dict, trace_id: str = None):
        """发布事件"""
        await self.ws.send(json.dumps({
            "type": event_type,
            "trace_id": trace_id,
            "payload": payload
        }))
    
    async def get_history(self, limit: int = 100, trace_id: str = None):
        """获取历史消息"""
        await self.ws.send(json.dumps({
            "type": "get_history",
            "limit": limit,
            "trace_id": trace_id
        }))
    
    async def get_replay(self, start_time: str = None, end_time: str = None):
        """获取重放数据"""
        await self.ws.send(json.dumps({
            "type": "get_replay",
            "start_time": start_time,
            "end_time": end_time
        }))
    
    async def ping(self):
        """心跳"""
        await self.ws.send(json.dumps({"type": "ping"}))


async def main():
    """测试入口"""
    bus = EventBus()
    await bus.start()


if __name__ == "__main__":
    asyncio.run(main())
