"""
EDT 时间线回放测试
C-5: 底部时间轴组件，支持7天回放，模式切换
"""

import pytest
import json
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.timeline_manager import (
    TimelineManager, TimelineEvent, PlaybackState, PlaybackMode
)


class TestTimelineEvent:
    """测试时间线事件"""
    
    def test_create_event(self):
        event = TimelineEvent(
            trace_id="evt_test",
            type="sector_update",
            timestamp=datetime.now(),
            data={"key": "value"}
        )
        
        assert event.trace_id == "evt_test"
        assert event.type == "sector_update"
        assert event.data["key"] == "value"
    
    def test_time_str(self):
        event = TimelineEvent(
            trace_id="evt_test",
            type="test",
            timestamp=datetime(2026, 4, 3, 10, 30, 45)
        )
        
        assert event.time_str == "10:30:45"


class TestTimelineManager:
    """测试时间线管理器"""
    
    @pytest.fixture
    def manager(self):
        return TimelineManager(max_days=7)
    
    def test_init(self, manager):
        assert manager.max_days == 7
        assert len(manager.events) == 0
        assert manager.state.mode == PlaybackMode.LIVE
    
    def test_add_event(self, manager):
        now = datetime.now()
        manager.add_event("evt_1", "test", now, {"data": 1})
        
        assert len(manager.events) == 1
        assert manager.events[0].trace_id == "evt_1"
    
    def test_cleanup_old_events(self, manager):
        now = datetime.now()
        manager.add_event("evt_old", "test", now - timedelta(days=10), {})
        manager.add_event("evt_new", "test", now, {})
        
        manager._cleanup_old_events()
        
        assert len(manager.events) == 1
        assert manager.events[0].trace_id == "evt_new"
    
    def test_sort_events(self, manager):
        now = datetime.now()
        manager.add_event("evt_2", "test", now + timedelta(minutes=10), {})
        manager.add_event("evt_1", "test", now, {})
        
        assert manager.events[0].trace_id == "evt_1"
    
    def test_get_events_in_range(self, manager):
        now = datetime.now()
        manager.add_event("evt_1", "test", now, {})
        manager.add_event("evt_2", "test", now + timedelta(hours=1), {})
        manager.add_event("evt_3", "test", now + timedelta(days=1), {})
        
        events = manager.get_events_in_range(
            now, now + timedelta(hours=2)
        )
        
        assert len(events) == 2
    
    def test_get_events_by_trace_id(self, manager):
        now = datetime.now()
        manager.add_event("evt_trace", "sector", now, {})
        manager.add_event("evt_trace", "opportunity", now + timedelta(minutes=1), {})
        manager.add_event("evt_other", "test", now, {})
        
        events = manager.get_events_by_trace_id("evt_trace")
        
        assert len(events) == 2
    
    def test_set_mode_live(self, manager):
        manager.set_mode(PlaybackMode.PLAYBACK)
        manager.set_mode(PlaybackMode.LIVE)
        
        assert manager.state.mode == PlaybackMode.LIVE
    
    def test_set_mode_playback(self, manager):
        manager.set_mode(PlaybackMode.PLAYBACK)
        
        assert manager.state.mode == PlaybackMode.PLAYBACK
    
    def test_seek_to(self, manager):
        now = datetime.now()
        for i in range(5):
            manager.add_event(f"evt_{i}", "test", now + timedelta(minutes=i), {})
        
        manager.seek_to(2)
        
        assert manager.state.current_index == 2
    
    def test_seek_to_percent(self, manager):
        now = datetime.now()
        for i in range(10):
            manager.add_event(f"evt_{i}", "test", now + timedelta(minutes=i), {})
        
        manager.seek_to_percent(50)
        
        assert manager.state.current_index == 4
    
    def test_next_event(self, manager):
        now = datetime.now()
        for i in range(3):
            manager.add_event(f"evt_{i}", "test", now + timedelta(minutes=i), {})
        
        manager.state.current_index = 0
        manager.next_event()
        
        assert manager.state.current_index == 1
    
    def test_prev_event(self, manager):
        now = datetime.now()
        for i in range(3):
            manager.add_event(f"evt_{i}", "test", now + timedelta(minutes=i), {})
        
        manager.state.current_index = 2
        manager.prev_event()
        
        assert manager.state.current_index == 1
    
    def test_set_speed(self, manager):
        manager.set_speed(2.0)
        
        assert manager.state.playback_speed == 2.0
    
    def test_set_speed_clamped(self, manager):
        manager.set_speed(10.0)
        
        assert manager.state.playback_speed == 4.0
    
    def test_get_current_event(self, manager):
        now = datetime.now()
        manager.add_event("evt_current", "test", now, {})
        
        event = manager.get_current_event()
        
        assert event.trace_id == "evt_current"
    
    def test_get_progress(self, manager):
        now = datetime.now()
        for i in range(4):
            manager.add_event(f"evt_{i}", "test", now + timedelta(minutes=i), {})
        
        manager.state.current_index = 2
        
        assert manager.get_progress() == pytest.approx(66.67, rel=0.1)
    
    def test_get_timeline_data(self, manager):
        now = datetime.now()
        manager.add_event("evt_1", "test", now, {"key": "value"})
        
        data = manager.get_timeline_data()
        
        assert data["mode"] == "live"
        assert len(data["events"]) == 1
        assert data["total_events"] == 1
    
    def test_on_change_callback(self, manager):
        callback_called = []
        
        def callback(data):
            callback_called.append(data)
        
        manager.on_change(callback)
        
        manager.set_mode(PlaybackMode.PLAYBACK)
        
        assert len(callback_called) > 0


class TestPlaybackMode:
    """测试播放模式"""
    
    def test_mode_values(self):
        assert PlaybackMode.LIVE.value == "live"
        assert PlaybackMode.PLAYBACK.value == "playback"
        assert PlaybackMode.PAUSED.value == "paused"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
