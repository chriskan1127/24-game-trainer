"""
Test cases for Message Broadcaster Service
"""

import pytest
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4
from datetime import datetime, timezone
import sys
import os

# Add project paths for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..'))
server_dir = os.path.join(project_root, 'server')
plans_dir = os.path.join(project_root, 'plans')

for path in [server_dir, plans_dir]:
    if path not in sys.path:
        sys.path.insert(0, path)

from message_broadcaster import MessageBroadcaster
from pydantic_schemas import (
    OutgoingWSMessage, RoundStartMessage, RoundStartPayload,
    CountdownStartMessage, CountdownStartPayload,
    RoundEndMessage, RoundEndPayload,
    PlayerJoinedMessage, PlayerJoinedPayload, PlayerPublic
)


class MockWebSocket:
    """Mock WebSocket for testing"""
    
    def __init__(self, should_fail=False):
        self.should_fail = should_fail
        self.sent_messages = []
        
    async def send_text(self, message):
        if self.should_fail:
            raise Exception("Connection failed")
        self.sent_messages.append(message)


class MockRoomManager:
    """Mock room manager for testing"""
    
    def __init__(self):
        self.rooms = {}
    
    def get_room(self, room_code):
        return self.rooms.get(room_code)


class TestMessageBroadcaster:
    """Test Message Broadcaster functionality"""

    @pytest.fixture
    def broadcaster(self):
        """Create a message broadcaster"""
        return MessageBroadcaster()

    @pytest.fixture
    def mock_room_manager(self):
        """Create mock room manager"""
        return MockRoomManager()

    @pytest.fixture
    def sample_room(self, mock_room_manager):
        """Create a sample room with players"""
        from pydantic_schemas import Room, PlayerInternal, MVPRoomSettings
        
        room_code = "TEST"
        player1_id = uuid4()
        player2_id = uuid4()
        
        player1 = PlayerInternal(
            player_id=player1_id,
            username="Player1",
            score=10,
            streak=1,
            session_token="token1",
            joined_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc)
        )
        
        player2 = PlayerInternal(
            player_id=player2_id,
            username="Player2",
            score=5,
            streak=0,
            session_token="token2",
            joined_at=datetime.now(timezone.utc),
            last_seen_at=datetime.now(timezone.utc)
        )
        
        room = Room(
            room_code=room_code,
            host_player_id=player1_id,
            settings=MVPRoomSettings(),
            players={player1_id: player1, player2_id: player2},
            problems=[],
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc)
        )
        
        mock_room_manager.rooms[room_code] = room
        return room_code, player1_id, player2_id, room

    @pytest.fixture
    def setup_connections(self, broadcaster, sample_room):
        """Set up mock WebSocket connections"""
        room_code, player1_id, player2_id, room = sample_room
        
        # Create mock websockets
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        
        # Set up connection mappings
        active_connections = {
            "conn1": ws1,
            "conn2": ws2
        }
        
        player_connections = {
            player1_id: "conn1",
            player2_id: "conn2"
        }
        
        broadcaster.set_connection_manager(active_connections, player_connections)
        
        return ws1, ws2, active_connections, player_connections

    @pytest.mark.asyncio
    async def test_broadcast_to_room(self, broadcaster, mock_room_manager, sample_room, setup_connections):
        """Test broadcasting to all players in a room"""
        room_code, player1_id, player2_id, room = sample_room
        ws1, ws2, active_connections, player_connections = setup_connections
        
        # Create test message
        message = CountdownStartMessage(
            type="countdown.start",
            payload=CountdownStartPayload(
                round_index=0,
                countdown_seconds=3,
                server_time=datetime.now(timezone.utc)
            )
        )
        
        # Broadcast message
        await broadcaster.broadcast_to_room(room_code, message, mock_room_manager)
        
        # Verify both websockets received the message
        assert len(ws1.sent_messages) == 1
        assert len(ws2.sent_messages) == 1
        
        # Verify message content
        sent_message1 = json.loads(ws1.sent_messages[0])
        sent_message2 = json.loads(ws2.sent_messages[0])
        
        assert sent_message1["type"] == "countdown.start"
        assert sent_message2["type"] == "countdown.start"
        assert sent_message1["payload"]["countdown_seconds"] == 3
        assert sent_message2["payload"]["countdown_seconds"] == 3

    @pytest.mark.asyncio
    async def test_broadcast_to_room_except(self, broadcaster, mock_room_manager, sample_room, setup_connections):
        """Test broadcasting to all players except one"""
        room_code, player1_id, player2_id, room = sample_room
        ws1, ws2, active_connections, player_connections = setup_connections
        
        # Create test message
        message = PlayerJoinedMessage(
            type="player.joined",
            payload=PlayerJoinedPayload(
                player=PlayerPublic(
                    player_id=player2_id,
                    username="Player2",
                    score=5,
                    streak=0
                ),
                total_players=2
            )
        )
        
        # Broadcast to all except player2
        await broadcaster.broadcast_to_room_except(room_code, message, exclude_player_id=player2_id)
        
        # Only player1 should receive the message
        assert len(ws1.sent_messages) == 1
        assert len(ws2.sent_messages) == 0
        
        # Verify message content
        sent_message = json.loads(ws1.sent_messages[0])
        assert sent_message["type"] == "player.joined"
        assert sent_message["payload"]["player"]["username"] == "Player2"

    @pytest.mark.asyncio
    async def test_send_to_player(self, broadcaster, mock_room_manager, sample_room, setup_connections):
        """Test sending message to specific player"""
        room_code, player1_id, player2_id, room = sample_room
        ws1, ws2, active_connections, player_connections = setup_connections
        
        # Create test message
        message = CountdownStartMessage(
            type="countdown.start",
            payload=CountdownStartPayload(
                round_index=0,
                countdown_seconds=3,
                server_time=datetime.now(timezone.utc)
            )
        )
        
        # Send to specific player
        await broadcaster.send_to_player(player2_id, message)
        
        # Only player2 should receive the message
        assert len(ws1.sent_messages) == 0
        assert len(ws2.sent_messages) == 1
        
        # Verify message content
        sent_message = json.loads(ws2.sent_messages[0])
        assert sent_message["type"] == "countdown.start"

    @pytest.mark.asyncio
    async def test_broadcast_connection_failure(self, broadcaster, mock_room_manager, sample_room):
        """Test broadcasting when a connection fails"""
        room_code, player1_id, player2_id, room = sample_room
        
        # Create mock websockets - one will fail
        ws1 = MockWebSocket()
        ws2 = MockWebSocket(should_fail=True)
        
        active_connections = {
            "conn1": ws1,
            "conn2": ws2
        }
        
        player_connections = {
            player1_id: "conn1",
            player2_id: "conn2"
        }
        
        broadcaster.set_connection_manager(active_connections, player_connections)
        
        # Create test message
        message = CountdownStartMessage(
            type="countdown.start",
            payload=CountdownStartPayload(
                round_index=0,
                countdown_seconds=3,
                server_time=datetime.now(timezone.utc)
            )
        )
        
        # Broadcast should handle the failure gracefully
        await broadcaster.broadcast_to_room(room_code, message, mock_room_manager)
        
        # Good connection should still receive message
        assert len(ws1.sent_messages) == 1
        # Failed connection should have no messages
        assert len(ws2.sent_messages) == 0

    @pytest.mark.asyncio
    async def test_broadcast_to_nonexistent_room(self, broadcaster, mock_room_manager):
        """Test broadcasting to a room that doesn't exist"""
        # Set up empty connections
        broadcaster.set_connection_manager({}, {})
        
        message = CountdownStartMessage(
            type="countdown.start",
            payload=CountdownStartPayload(
                round_index=0,
                countdown_seconds=3,
                server_time=datetime.now(timezone.utc)
            )
        )
        
        # Should not raise an exception
        await broadcaster.broadcast_to_room("NONEXISTENT", message, mock_room_manager)

    @pytest.mark.asyncio
    async def test_broadcast_with_disconnected_player(self, broadcaster, mock_room_manager, sample_room):
        """Test broadcasting when a player is disconnected"""
        room_code, player1_id, player2_id, room = sample_room
        
        # Set up connections with only one player connected
        ws1 = MockWebSocket()
        
        active_connections = {
            "conn1": ws1,
            # conn2 is missing (player2 disconnected)
        }
        
        player_connections = {
            player1_id: "conn1",
            player2_id: "conn2"  # Points to non-existent connection
        }
        
        broadcaster.set_connection_manager(active_connections, player_connections)
        
        message = CountdownStartMessage(
            type="countdown.start",
            payload=CountdownStartPayload(
                round_index=0,
                countdown_seconds=3,
                server_time=datetime.now(timezone.utc)
            )
        )
        
        # Should handle disconnected player gracefully
        await broadcaster.broadcast_to_room(room_code, message, mock_room_manager)
        
        # Connected player should receive message
        assert len(ws1.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_player(self, broadcaster):
        """Test sending to a player that doesn't exist"""
        broadcaster.set_connection_manager({}, {})
        
        message = CountdownStartMessage(
            type="countdown.start",
            payload=CountdownStartPayload(
                round_index=0,
                countdown_seconds=3,
                server_time=datetime.now(timezone.utc)
            )
        )
        
        # Should not raise an exception
        await broadcaster.send_to_player(uuid4(), message)

    def test_connection_manager_not_initialized(self, broadcaster, mock_room_manager):
        """Test that broadcasting fails gracefully when connection manager not set"""
        
        async def test_broadcast():
            message = CountdownStartMessage(
                type="countdown.start",
                payload=CountdownStartPayload(
                    round_index=0,
                    countdown_seconds=3,
                    server_time=datetime.now(timezone.utc)
                )
            )
            
            # Should log error but not crash
            await broadcaster.broadcast_to_room("TEST", message, mock_room_manager)
        
        # Should not raise an exception
        asyncio.run(test_broadcast())

    @pytest.mark.asyncio
    async def test_get_connected_players(self, broadcaster, sample_room, setup_connections):
        """Test getting list of connected players"""
        room_code, player1_id, player2_id, room = sample_room
        ws1, ws2, active_connections, player_connections = setup_connections
        
        connected = broadcaster.get_connected_players_in_room(room_code, room)
        
        # Both players should be connected
        assert len(connected) == 2
        assert player1_id in connected
        assert player2_id in connected

    @pytest.mark.asyncio
    async def test_get_connected_players_with_disconnected(self, broadcaster, sample_room):
        """Test getting connected players when some are disconnected"""
        room_code, player1_id, player2_id, room = sample_room
        
        # Only player1 is connected
        ws1 = MockWebSocket()
        
        active_connections = {
            "conn1": ws1,
        }
        
        player_connections = {
            player1_id: "conn1",
            # player2 not in connections (disconnected)
        }
        
        broadcaster.set_connection_manager(active_connections, player_connections)
        
        connected = broadcaster.get_connected_players_in_room(room_code, room)
        
        # Only player1 should be connected
        assert len(connected) == 1
        assert player1_id in connected
        assert player2_id not in connected

    @pytest.mark.asyncio
    async def test_concurrent_broadcasts(self, broadcaster, mock_room_manager, sample_room, setup_connections):
        """Test concurrent broadcasting to multiple rooms"""
        room_code, player1_id, player2_id, room = sample_room
        ws1, ws2, active_connections, player_connections = setup_connections
        
        # Create multiple messages
        messages = [
            CountdownStartMessage(
                type="countdown.start",
                payload=CountdownStartPayload(
                    round_index=i,
                    countdown_seconds=3,
                    server_time=datetime.now(timezone.utc)
                )
            )
            for i in range(5)
        ]
        
        # Broadcast all concurrently
        tasks = [
            broadcaster.broadcast_to_room(room_code, msg, mock_room_manager)
            for msg in messages
        ]
        
        await asyncio.gather(*tasks)
        
        # Each websocket should have received all messages
        assert len(ws1.sent_messages) == 5
        assert len(ws2.sent_messages) == 5