"""
EDT 事件总线测试
C-4: WebSocket 消息按trace_id有序，断线自动重连，支持重放
"""

import pytest
import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.event_bus import EventBus, EventMessage


class TestEventMessage:
    """测试事件消息"""
    
    def test_create_message(self):
        msg = EventMessage(
            type="sector_update",
            trace_id="evt_test123",
            payload={"sectors": []}
        )
        
        assert msg.type == "sector_update"
        assert msg.trace_id == "evt_test123"
        assert msg.schema_version == "v1.0"
    
    def test_to_json(self):
        msg = EventMessage(
            type="test",
            trace_id="evt_abc",
            payload={"key": "value"}
        )
        
        data = json.loads(msg.to_json())
        
        assert data["type"] == "test"
        assert data["trace_id"] == "evt_abc"
        assert data["payload"]["key"] == "value"
    
    def test_from_json(self):
        json_str = '{"type": "test", "trace_id": "evt_xyz", "payload": {}}'
        
        msg = EventMessage.from_json(json_str)
        
        assert msg.type == "test"
        assert msg.trace_id == "evt_xyz"


class TestEventBus:
    """测试事件总线"""
    
    @pytest.fixture
    def bus(self):
        return EventBus(host="localhost", port=8766)
    
    def test_init(self, bus):
        assert bus.host == "localhost"
        assert bus.port == 8766
        assert len(bus.clients) == 0
        assert len(bus.subscriptions) == 0
    
    def test_generate_trace_id(self, bus):
        trace_id = bus._generate_trace_id()
        
        assert trace_id.startswith("evt_")
        assert len(trace_id) == 20
    
    def test_store_message(self, bus):
        msg = EventMessage(
            type="test",
            trace_id="evt_store",
            payload={}
        )
        
        bus._store_message(msg)
        
        assert len(bus.message_history) == 1
        assert bus.message_history[0].trace_id == "evt_store"
    
    def test_message_history_limit(self, bus):
        bus.max_history = 10
        
        for i in range(15):
            msg = EventMessage(type="test", trace_id=f"evt_{i}", payload={})
            bus._store_message(msg)
        
        assert len(bus.message_history) == 10
        assert bus.message_history[0].trace_id == "evt_5"
    
    def test_get_replay_messages_empty(self, bus):
        messages = bus._get_replay_messages(
            "2026-01-01T00:00:00",
            "2026-01-02T00:00:00"
        )
        
        assert len(messages) == 0
    
    def test_store_replay_buffer(self, bus):
        msg = EventMessage(
            type="test",
            trace_id="evt_replay",
            payload={},
            timestamp="2026-04-03T10:00:00"
        )
        
        bus._store_replay_buffer(msg)
        
        assert "2026-04-03" in bus.replay_buffer
        assert len(bus.replay_buffer["2026-04-03"]) == 1
    
    def test_register_handler(self, bus):
        async def handler(data):
            return {"result": "ok"}
        
        bus.register_handler("test_event", handler)
        
        assert "test_event" in bus.handlers
    
    def test_get_stats(self, bus):
        stats = bus.get_stats()
        
        assert "connected_clients" in stats
        assert "subscriptions" in stats
        assert "message_history_count" in stats
        assert "replay_buffer_days" in stats


class TestEventBusIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_message_flow(self):
        bus = EventBus(host="127.0.0.1", port=8767)
        
        handler_called = False
        
        async def test_handler(data):
            nonlocal handler_called
            handler_called = True
            return {"processed": True}
        
        bus.register_handler("test_flow", test_handler)
        
        await bus.publish("test_flow", {"data": "test"}, "evt_flow_test")
        
        assert handler_called
        assert len(bus.message_history) == 1
        
        await bus.stop()
    
    @pytest.mark.asyncio
    async def test_trace_id_consistency(self):
        bus = EventBus(host="127.0.0.1", port=8768)
        
        trace_id = "evt_consistency_test"
        
        await bus.publish("event1", {"step": 1}, trace_id)
        await bus.publish("event2", {"step": 2}, trace_id)
        
        messages = [m for m in bus.message_history if m.trace_id == trace_id]
        
        assert len(messages) == 2
        
        await bus.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
