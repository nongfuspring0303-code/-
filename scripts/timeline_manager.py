"""
EDT 时间线回放组件
C-5: 底部时间轴组件，支持7天回放，模式切换
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class PlaybackMode(Enum):
    LIVE = "live"
    PLAYBACK = "playback"
    PAUSED = "paused"


@dataclass
class TimelineEvent:
    """时间线事件"""
    trace_id: str
    type: str
    timestamp: datetime
    data: dict = field(default_factory=dict)
    
    @property
    def time_str(self) -> str:
        return self.timestamp.strftime("%H:%M:%S")


@dataclass
class PlaybackState:
    """播放状态"""
    mode: PlaybackMode = PlaybackMode.LIVE
    current_index: int = 0
    playback_speed: float = 1.0
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


class TimelineManager:
    """时间线管理器"""
    
    def __init__(self, event_bus=None, max_days: int = 7):
        self.event_bus = event_bus
        self.max_days = max_days
        self.events: List[TimelineEvent] = []
        self.state = PlaybackState()
        self.callbacks: List[Callable] = []
        self._playback_timer = None
        
    def add_event(self, trace_id: str, event_type: str, timestamp: datetime, data: dict = None):
        """添加事件到时间线"""
        event = TimelineEvent(
            trace_id=trace_id,
            type=event_type,
            timestamp=timestamp,
            data=data or {}
        )
        self.events.append(event)
        self._cleanup_old_events()
        self._sort_events()
        
    def _cleanup_old_events(self):
        """清理过期事件"""
        cutoff = datetime.now() - timedelta(days=self.max_days)
        self.events = [e for e in self.events if e.timestamp > cutoff]
    
    def _sort_events(self):
        """按时间排序"""
        self.events.sort(key=lambda e: e.timestamp)
    
    def get_events_in_range(self, start: datetime, end: datetime) -> List[TimelineEvent]:
        """获取时间范围内的事件"""
        return [e for e in self.events if start <= e.timestamp <= end]
    
    def get_events_by_trace_id(self, trace_id: str) -> List[TimelineEvent]:
        """获取指定trace_id的所有事件"""
        return [e for e in self.events if e.trace_id == trace_id]
    
    def get_timeline_data(self, limit: int = 100) -> dict:
        """获取时间线数据用于前端渲染"""
        if self.state.mode == PlaybackMode.LIVE:
            display_events = self.events[-limit:]
        else:
            display_events = self.events[:self.state.current_index + 1]
        
        return {
            "mode": self.state.mode.value,
            "events": [
                {
                    "trace_id": e.trace_id,
                    "type": e.type,
                    "timestamp": e.timestamp.isoformat(),
                    "time_str": e.time_str,
                    "data": e.data
                }
                for e in display_events
            ],
            "current_index": self.state.current_index,
            "total_events": len(self.events),
            "start_time": self.events[0].timestamp.isoformat() if self.events else None,
            "end_time": self.events[-1].timestamp.isoformat() if self.events else None,
            "playback_speed": self.state.playback_speed,
        }
    
    def set_mode(self, mode: PlaybackMode):
        """设置播放模式"""
        old_mode = self.state.mode
        self.state.mode = mode
        
        if mode == PlaybackMode.LIVE:
            self._stop_playback()
            self.state.current_index = len(self.events) - 1
        elif mode == PlaybackMode.PAUSED:
            self._stop_playback()
        elif mode == PlaybackMode.PLAYBACK:
            if old_mode == PlaybackMode.LIVE:
                self.state.current_index = 0
            self._start_playback()
        
        self._notify_change()
    
    def seek_to(self, index: int):
        """跳转到指定索引"""
        if 0 <= index < len(self.events):
            self.state.current_index = index
            
            if self.state.mode == PlaybackMode.LIVE:
                self.set_mode(PlaybackMode.PLAYBACK)
            
            self._notify_change()
    
    def seek_to_time(self, target_time: datetime):
        """跳转到指定时间"""
        if not self.events:
            return
            
        for i, event in enumerate(self.events):
            if event.timestamp >= target_time:
                self.seek_to(i)
                return
        
        self.seek_to(len(self.events) - 1)
    
    def seek_to_percent(self, percent: float):
        """按百分比跳转 (0-100)"""
        if not self.events:
            return
            
        index = int((percent / 100) * (len(self.events) - 1))
        self.seek_to(index)
    
    def next_event(self):
        """跳到下一个事件"""
        if self.state.current_index < len(self.events) - 1:
            self.seek_to(self.state.current_index + 1)
    
    def prev_event(self):
        """跳到上一个事件"""
        if self.state.current_index > 0:
            self.seek_to(self.state.current_index - 1)
    
    def set_speed(self, speed: float):
        """设置播放速度 (0.5x, 1x, 2x, 4x)"""
        self.state.playback_speed = max(0.5, min(4.0, speed))
    
    def _start_playback(self):
        """开始播放"""
        if self._playback_timer:
            return
            
        def tick():
            if self.state.mode != PlaybackMode.PLAYBACK:
                return
                
            delay = 1000 / self.state.playback_speed
            
            if self.state.current_index < len(self.events) - 1:
                self.state.current_index += 1
                self._notify_change()
            else:
                self.set_mode(PlaybackMode.PAUSED)
            
            self._playback_timer = setTimeout(tick, delay)
        
        def setTimeout(func, delay):
            import threading
            timer = threading.Timer(delay / 1000, func)
            timer.start()
            return timer
        
        tick()
    
    def _stop_playback(self):
        """停止播放"""
        if self._playback_timer:
            self._playback_timer.cancel()
            self._playback_timer = None
    
    def _notify_change(self):
        """通知状态变化"""
        for callback in self.callbacks:
            try:
                callback(self.get_timeline_data())
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    def on_change(self, callback: Callable):
        """注册状态变化回调"""
        self.callbacks.append(callback)
    
    def get_current_event(self) -> Optional[TimelineEvent]:
        """获取当前事件"""
        if 0 <= self.state.current_index < len(self.events):
            return self.events[self.state.current_index]
        return None
    
    def get_progress(self) -> float:
        """获取播放进度百分比"""
        if not self.events:
            return 0
        return (self.state.current_index / (len(self.events) - 1)) * 100


class TimelineFrontend:
    """前端时间线组件辅助类"""
    
    @staticmethod
    def generate_js() -> str:
        """生成前端JS代码"""
        return """
class TimelineManager {
    constructor(eventBus) {
        this.eventBus = eventBus;
        this.state = {
            mode: 'live',
            events: [],
            currentIndex: 0,
            totalEvents: 0,
            playbackSpeed: 1
        };
        this.isPlaying = false;
    }
    
    init() {
        this.setupEventListeners();
        this.startLiveMode();
    }
    
    setupEventListeners() {
        document.getElementById('playPauseBtn').addEventListener('click', () => this.togglePlayPause());
        document.getElementById('liveModeBtn').addEventListener('click', () => this.setLiveMode());
        
        document.getElementById('timelineTrack').addEventListener('click', (e) => {
            const rect = e.target.getBoundingClientRect();
            const percent = ((e.clientX - rect.left) / rect.width) * 100;
            this.seekToPercent(percent);
        });
        
        document.addEventListener('keydown', (e) => {
            if (e.key === ' ') {
                e.preventDefault();
                this.togglePlayPause();
            } else if (e.key === 'ArrowRight') {
                this.nextEvent();
            } else if (e.key === 'ArrowLeft') {
                this.prevEvent();
            }
        });
    }
    
    togglePlayPause() {
        if (this.state.mode === 'live') {
            this.setPlaybackMode();
            return;
        }
        
        this.isPlaying = !this.isPlaying;
        const btn = document.getElementById('playPauseBtn');
        btn.textContent = this.isPlaying ? '⏸' : '▶';
        btn.classList.toggle('active', this.isPlaying);
        
        if (this.isPlaying) {
            this.startPlayback();
        } else {
            this.pausePlayback();
        }
    }
    
    setLiveMode() {
        this.state.mode = 'live';
        this.isPlaying = false;
        this.updateUI();
        
        if (this.eventBus) {
            this.eventBus.publish('timeline_mode_change', { mode: 'live' });
        }
    }
    
    setPlaybackMode() {
        this.state.mode = 'playback';
        this.state.currentIndex = 0;
        this.isPlaying = true;
        this.updateUI();
        
        if (this.eventBus) {
            this.eventBus.publish('timeline_mode_change', { mode: 'playback' });
        }
        
        this.startPlayback();
    }
    
    startPlayback() {
        if (!this.isPlaying || this.state.mode === 'live') return;
        
        const delay = 1000 / this.state.playbackSpeed;
        
        if (this.state.currentIndex < this.state.totalEvents - 1) {
            this.state.currentIndex++;
            this.updateUI();
            setTimeout(() => this.startPlayback(), delay);
        } else {
            this.pausePlayback();
        }
    }
    
    pausePlayback() {
        this.isPlaying = false;
        const btn = document.getElementById('playPauseBtn');
        btn.textContent = '▶';
        btn.classList.remove('active');
        this.state.mode = 'paused';
    }
    
    seekToPercent(percent) {
        if (this.state.totalEvents === 0) return;
        
        const index = Math.floor((percent / 100) * (this.state.totalEvents - 1));
        this.state.currentIndex = index;
        this.state.mode = 'playback';
        this.isPlaying = false;
        this.updateUI();
        
        if (this.eventBus) {
            const event = this.state.events[index];
            if (event) {
                this.eventBus.publish('timeline_seek', {
                    trace_id: event.trace_id,
                    type: event.type
                });
            }
        }
    }
    
    nextEvent() {
        if (this.state.currentIndex < this.state.totalEvents - 1) {
            this.state.currentIndex++;
            this.updateUI();
        }
    }
    
    prevEvent() {
        if (this.state.currentIndex > 0) {
            this.state.currentIndex--;
            this.updateUI();
        }
    }
    
    updateUI() {
        const progress = document.getElementById('timelineProgress');
        const timeEl = document.getElementById('timelineTime');
        const liveBtn = document.getElementById('liveModeBtn');
        
        if (this.state.totalEvents > 0) {
            const percent = (this.state.currentIndex / (this.state.totalEvents - 1)) * 100;
            progress.style.width = percent + '%';
            
            const event = this.state.events[this.state.currentIndex];
            if (event) {
                timeEl.textContent = event.time_str;
            }
        }
        
        liveBtn.classList.toggle('active', this.state.mode === 'live');
    }
    
    startLiveMode() {
        this.state.mode = 'live';
        this.updateUI();
    }
    
    onEventReceived(event) {
        if (this.state.mode === 'live') {
            this.state.events.push(event);
            this.state.totalEvents = this.state.events.length;
            this.state.currentIndex = this.state.totalEvents - 1;
            this.updateUI();
        }
    }
}

window.TimelineManager = TimelineManager;
"""
    
    @staticmethod
    def generate_html() -> str:
        """生成前端HTML代码"""
        return """
<div class="timeline-bar" id="timelineBar">
    <div class="timeline-controls">
        <button class="btn-timeline" id="playPauseBtn" title="播放/暂停 (空格)">▶</button>
        <button class="btn-timeline active" id="liveModeBtn" title="实时模式">LIVE</button>
        <select class="speed-select" id="speedSelect" title="播放速度">
            <option value="0.5">0.5x</option>
            <option value="1" selected>1x</option>
            <option value="2">2x</option>
            <option value="4">4x</option>
        </select>
    </div>
    <div class="timeline-track" id="timelineTrack">
        <div class="timeline-progress" id="timelineProgress" style="width: 100%"></div>
    </div>
    <div class="timeline-time" id="timelineTime">--:--:--</div>
    <div class="timeline-info" id="timelineInfo">
        <span class="event-count">0 事件</span>
    </div>
</div>
"""
    
    @staticmethod
    def generate_css() -> str:
        """生成前端CSS代码"""
        return """
.timeline-bar {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: 60px;
    background: var(--bg-secondary);
    border-top: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    padding: 0 16px;
    gap: 16px;
}

.timeline-controls {
    display: flex;
    gap: 8px;
    align-items: center;
}

.btn-timeline {
    background: var(--bg-tertiary);
    border: 1px solid var(--border-color);
    color: var(--text-primary);
    padding: 8px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 12px;
    font-weight: 500;
    transition: all 0.2s;
}

.btn-timeline:hover {
    background: var(--accent-blue);
    border-color: var(--accent-blue);
}

.btn-timeline.active {
    background: var(--accent-green);
    border-color: var(--accent-green);
}

.speed-select {
    background: var(--bg-tertiary);
    color: var(--text-primary);
    border: 1px solid var(--border-color);
    padding: 6px 8px;
    border-radius: 4px;
    font-size: 12px;
}

.timeline-track {
    flex: 1;
    height: 8px;
    background: var(--bg-tertiary);
    border-radius: 4px;
    cursor: pointer;
    position: relative;
}

.timeline-progress {
    position: absolute;
    left: 0;
    top: 0;
    height: 100%;
    background: var(--accent-blue);
    border-radius: 4px;
    transition: width 0.1s linear;
}

.timeline-time {
    font-size: 12px;
    font-family: monospace;
    color: var(--text-secondary);
    min-width: 80px;
}

.timeline-info {
    font-size: 11px;
    color: var(--text-muted);
}

.event-count {
    white-space: nowrap;
}
"""


if __name__ == "__main__":
    manager = TimelineManager(max_days=7)
    
    now = datetime.now()
    for i in range(10):
        manager.add_event(
            trace_id=f"evt_{i}",
            event_type="test",
            timestamp=now + timedelta(minutes=i),
            data={"index": i}
        )
    
    print(f"Total events: {len(manager.events)}")
    print(f"Timeline data: {json.dumps(manager.get_timeline_data(), indent=2, default=str)}")
