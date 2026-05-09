import pytest
from app.server_events import EventBus

def test_subscribe_and_emit():
    bus = EventBus()
    received = []
    
    def handler(data):
        received.append(data)
        
    bus.subscribe("test_event", handler)
    bus.emit("test_event", "hello")
    bus.emit("test_event", "world")
    
    assert received == ["hello", "world"]

def test_unsubscribe():
    bus = EventBus()
    received = []
    
    def handler(data):
        received.append(data)
        
    bus.subscribe("test_event", handler)
    bus.emit("test_event", "1")
    bus.unsubscribe("test_event", handler)
    bus.emit("test_event", "2")
    
    assert received == ["1"]

def test_resilience_to_crashing_handlers():
    bus = EventBus()
    received = []
    
    def bad_handler(data):
        raise ValueError("I crash")
        
    def good_handler(data):
        received.append(data)
        
    bus.subscribe("test_event", bad_handler)
    bus.subscribe("test_event", good_handler)
    
    # Should not raise exception
    bus.emit("test_event", "safe")
    
    assert received == ["safe"]

def test_no_op_on_empty():
    bus = EventBus()
    # Should not crash
    bus.emit("non_existent", "data")
    bus.unsubscribe("non_existent", lambda x: x)
