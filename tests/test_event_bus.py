"""
EDT 事件总线测试
C-4: WebSocket 消息按trace_id有序，断线自动重连，支持重放
"""

import pytest
import asyncio
import json
import sys
import os
from pathlib import Path
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.event_bus import EventBus, EventMessage
import scripts.event_bus as event_bus_mod


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
    def bus(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            event_bus_mod,
            "DEFAULT_EVENT_BUS_HISTORY_FILE",
            Path(tmp_path) / "event_bus_history.jsonl",
            raising=False,
        )
        return EventBus(host="localhost", port=8766)
    
    def test_init(self, bus):
        assert bus.host == "localhost"
        assert bus.port == 8766
        assert len(bus.clients) == 0
        assert len(bus.subscriptions) == 0

    def test_authorized_path(self):
        bus = EventBus(host="localhost", port=8766, auth_token="secret-token")
        assert bus._is_authorized_path("/?token=secret-token") is True
        assert bus._is_authorized_path("/?token=wrong") is False
    
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

    def test_publish_persists_history_jsonl(self, tmp_path: Path):
        async def run():
            history_file = tmp_path / "event_bus_history.jsonl"
            bus = EventBus(host="localhost", port=8766, history_file=str(history_file))

            await bus.publish("persist_event", {"value": 1}, "evt_persist_001")

            assert history_file.exists()
            lines = history_file.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 1

            payload = json.loads(lines[0])
            assert payload["type"] == "persist_event"
            assert payload["trace_id"] == "evt_persist_001"
            assert payload["payload"] == {"value": 1}

            await bus.stop()

        asyncio.run(run())

    def test_startup_reload_history_jsonl(self, tmp_path: Path):
        history_file = tmp_path / "event_bus_history.jsonl"
        history_file.write_text(
            "\n".join([
                json.dumps(
                    {
                        "type": "event_update",
                        "trace_id": "evt_reload_001",
                        "schema_version": "v1.0",
                        "payload": {"step": 1},
                        "timestamp": "2026-04-08T09:00:00",
                    }
                ),
                json.dumps(
                    {
                        "type": "sector_update",
                        "trace_id": "evt_reload_001",
                        "schema_version": "v1.0",
                        "payload": {"step": 2},
                        "timestamp": "2026-04-08T09:00:01",
                    }
                ),
            ])
            + "\n",
            encoding="utf-8",
        )

        bus = EventBus(host="localhost", port=8766, history_file=str(history_file))

        assert len(bus.message_history) == 2
        assert bus.message_history[0].trace_id == "evt_reload_001"
        assert bus.message_history[1].type == "sector_update"
        assert "2026-04-08" in bus.replay_buffer
        assert len(bus.replay_buffer["2026-04-08"]) == 2

    def test_startup_reload_skips_invalid_history_lines(self, tmp_path: Path):
        history_file = tmp_path / "event_bus_history.jsonl"
        history_file.write_text(
            "{invalid json}\n"
            + json.dumps(
                {
                    "type": "event_update",
                    "trace_id": "evt_valid_001",
                    "schema_version": "v1.0",
                    "payload": {"ok": True},
                    "timestamp": "2026-04-08T09:00:00",
                }
            )
            + "\n",
            encoding="utf-8",
        )

        bus = EventBus(host="localhost", port=8766, history_file=str(history_file))
        assert len(bus.message_history) == 1
        assert bus.message_history[0].trace_id == "evt_valid_001"

    def test_persisted_history_compacts_to_max_history(self, tmp_path: Path):
        async def run():
            history_file = tmp_path / "event_bus_history.jsonl"
            bus = EventBus(host="localhost", port=8766, history_file=str(history_file))
            bus.max_history = 3
            for i in range(5):
                await bus.publish("event_update", {"i": i}, f"evt_{i}")

            lines = history_file.read_text(encoding="utf-8").strip().splitlines()
            assert len(lines) == 3
            first = json.loads(lines[0])
            last = json.loads(lines[-1])
            assert first["trace_id"] == "evt_2"
            assert last["trace_id"] == "evt_4"

        asyncio.run(run())

    def test_default_history_file_is_enabled(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            event_bus_mod,
            "DEFAULT_EVENT_BUS_HISTORY_FILE",
            Path(tmp_path) / "event_bus_history.jsonl",
            raising=False,
        )
        bus = event_bus_mod.EventBus(host="localhost", port=8769)
        assert bus.history_file.name == "event_bus_history.jsonl"
        assert bus.history_file.parent == Path(tmp_path)


class TestEventBusIntegration:
    """集成测试"""
    
    def test_message_flow(self, tmp_path, monkeypatch):
        async def run():
            monkeypatch.setattr(
                event_bus_mod,
                "DEFAULT_EVENT_BUS_HISTORY_FILE",
                Path(tmp_path) / "event_bus_history.jsonl",
                raising=False,
            )
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

        asyncio.run(run())

    def test_trace_id_consistency(self, tmp_path, monkeypatch):
        async def run():
            monkeypatch.setattr(
                event_bus_mod,
                "DEFAULT_EVENT_BUS_HISTORY_FILE",
                Path(tmp_path) / "event_bus_history.jsonl",
                raising=False,
            )
            bus = EventBus(host="127.0.0.1", port=8768)

            trace_id = "evt_consistency_test"

            await bus.publish("event1", {"step": 1}, trace_id)
            await bus.publish("event2", {"step": 2}, trace_id)

            messages = [m for m in bus.message_history if m.trace_id == trace_id]

            assert len(messages) == 2

            await bus.stop()

        asyncio.run(run())

    def test_websocket_auth_handshake_valid_and_invalid_token(self):
        async def run():
            bus = EventBus(host="127.0.0.1", port=8790, auth_token="secure-token")
            server_task = asyncio.create_task(bus.start())
            await asyncio.sleep(0.1)

            try:
                async with connect("ws://127.0.0.1:8790?token=secure-token") as ws:
                    msg = json.loads(await ws.recv())
                    assert msg.get("type") == "connected"

                async with connect("ws://127.0.0.1:8790?token=bad-token") as ws:
                    with pytest.raises(ConnectionClosed) as exc_info:
                        await ws.recv()
                    assert exc_info.value.rcvd and exc_info.value.rcvd.code == 4401
            finally:
                await bus.stop()
                server_task.cancel()

        asyncio.run(run())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
