"""
Integration tests for all multiplayer core components working together

Tests cover:
- Full system integration scenarios
- Component interaction and data flow
- End-to-end game simulation
- Error propagation and recovery
- Performance and concurrency
"""

import pytest
import asyncio
from datetime import datetime, timezone
from uuid import uuid4

# Add project paths for imports
import sys
import os
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, '..', '..'))
plans_dir = os.path.join(project_root, 'plans')

if plans_dir not in sys.path:
    sys.path.insert(0, plans_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

from multiplayer_core.managers.room_manager import RoomManager
from multiplayer_core.managers.player_manager import PlayerManager
from multiplayer_core.managers.game_state_manager import GameStateManager
from pydantic_schemas import Problem, SubmissionRecord


class MockProblemPoolService:
    """Mock problem pool service for integration testing"""
    
    async def generate_problems_for_game(self, count):
        problems = []
        for i in range(count):
            problem = Problem(
                numbers=[1, 2, 3, 4 + i],
                canonical_solution=f"1+2+3+{4+i}*6"
            )
            problems.append(problem)
        return problems


class MockMessageBroadcaster:
    """Mock message broadcaster for integration testing"""
    
    def __init__(self):
        self.messages = []
    
    async def broadcast_to_room(self, room_code, message, room_manager):
        self.messages.append({
            'room_code': room_code,
            'type': message.type,
            'payload': message.payload,
            'timestamp': datetime.now(timezone.utc)
        })


class TestMultiplayerCoreIntegration:
    """Integration tests for all multiplayer core components"""
    
    def setup_method(self):
        """Set up integrated system"""
        self.problem_service = MockProblemPoolService()
        self.room_manager = RoomManager(self.problem_service)
        self.player_manager = PlayerManager()
        self.message_broadcaster = MockMessageBroadcaster()
        
        self.game_state_manager = GameStateManager(
            room_manager=self.room_manager,
            player_manager=self.player_manager,
            message_broadcaster=self.message_broadcaster
        )
    
    @pytest.mark.asyncio
    async def test_complete_game_flow(self):
        """Test complete game flow from room creation to game end"""
        # 1. Create room
        create_result = await self.room_manager.create_room("GameHost")
        room_code = create_result.room_code
        host_id = create_result.host_player_id
        host_token = create_result.host_session_token
        
        # Verify room creation
        room = self.room_manager.get_room(room_code)
        assert room is not None
        assert len(room.players) == 1
        assert len(room.problems) == 10  # Generated problems
        
        # 2. Join players
        player_results = []
        for i in range(3):
            join_result = await self.room_manager.join_room(
                room_code, f"Player{i+1}"
            )
            player_results.append(join_result)
        
        # Verify players joined
        assert len(room.players) == 4
        
        # 3. Start game
        await self.game_state_manager.start_game(room_code, host_id, host_token)
        
        # Verify game started
        assert room.state == "RUNNING"
        assert room.round_index == 0
        assert room.current_round_state is not None
        
        # Verify players scores reset
        for player in room.players.values():
            assert player.score == 0
            assert player.streak == 0
        
        # 4. Simulate game progression
        for round_num in range(3):  # Test 3 rounds
            # Handle countdown -> active -> results cycle
            await self.game_state_manager.handle_countdown_complete(room_code)
            
            # Simulate some players answering
            answering_players = list(room.players.values())[:2]  # First 2 players answer
            
            for i, player in enumerate(answering_players):
                submission = SubmissionRecord(
                    room_code=room_code,
                    round_index=round_num,
                    player_id=player.player_id,
                    expression=f"1+2+3+{4+round_num}*6",
                    used_numbers=[1, 2, 3, 4+round_num],
                    client_eval_is_valid=True
                )
                
                time_left = 25.0 - (i * 5.0)  # Different answer times
                points, player_scored = self.player_manager.process_submission(
                    room_code, player, submission, time_left
                )
                
                assert points > 0
                assert player.score > 0
                assert player.streak == round_num + 1
            
            # End round
            await self.game_state_manager.handle_round_timeout(room_code)
            await self.game_state_manager.handle_results_complete(room_code)
            
            # Verify round progression
            assert room.round_index == round_num + 1
        
        # 5. Verify game state
        leaderboard = self.player_manager.get_leaderboard(room.players)
        assert len(leaderboard) == 4
        
        # Players who answered should have higher scores
        answering_player_ids = {p.player_id for p in answering_players}
        top_scorers = {entry.player_id for entry in leaderboard[:2]}
        assert answering_player_ids == top_scorers
        
        # 6. Check message broadcasting
        assert len(self.message_broadcaster.messages) > 0
        
        message_types = [msg['type'] for msg in self.message_broadcaster.messages]
        assert 'countdown.start' in message_types
        assert 'round.start' in message_types
        assert 'round.end' in message_types
        
        # 7. Force end game
        await self.game_state_manager.force_end_game(room_code, "Integration test complete")
        
        assert room.state == "FINISHED"
        assert room.current_round_state is None
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_games(self):
        """Test multiple games running concurrently"""
        # Create 3 concurrent games
        games = []
        
        for i in range(3):
            # Create room
            create_result = await self.room_manager.create_room(f"Host{i}")
            
            # Join one player
            await self.room_manager.join_room(create_result.room_code, f"Player{i}")
            
            games.append({
                'room_code': create_result.room_code,
                'host_id': create_result.host_player_id,
                'host_token': create_result.host_session_token
            })
        
        # Start all games
        for game in games:
            await self.game_state_manager.start_game(
                game['room_code'], game['host_id'], game['host_token']
            )
        
        # Verify all games started
        for game in games:
            room = self.room_manager.get_room(game['room_code'])
            assert room.state == "RUNNING"
            assert room.current_round_state is not None
        
        # Progress games independently
        for i, game in enumerate(games):
            # Progress each game by different amounts
            for _ in range(i + 1):
                await self.game_state_manager.handle_countdown_complete(game['room_code'])
                await self.game_state_manager.handle_round_timeout(game['room_code'])
                await self.game_state_manager.handle_results_complete(game['room_code'])
        
        # Verify games have different states
        round_indices = []
        for game in games:
            room = self.room_manager.get_room(game['room_code'])
            round_indices.append(room.round_index)
        
        # Should have different round indices
        assert len(set(round_indices)) > 1
        
        # Clean up all games
        for game in games:
            await self.game_state_manager.force_end_game(game['room_code'])
    
    @pytest.mark.asyncio
    async def test_player_reconnection_during_game(self):
        """Test player reconnection during active game"""
        # Create room and join players
        create_result = await self.room_manager.create_room("Host")
        room_code = create_result.room_code
        
        join_result = await self.room_manager.join_room(room_code, "Player1")
        player_id = join_result.player_id
        session_token = join_result.session_token
        
        # Start game
        await self.game_state_manager.start_game(
            room_code, create_result.host_player_id, create_result.host_session_token
        )
        
        # Simulate player getting some score
        room = self.room_manager.get_room(room_code)
        player = room.players[player_id]
        player.score = 50
        player.streak = 3
        
        # Remove player (simulate disconnection)
        await self.room_manager.remove_player(room_code, player_id)
        assert player_id not in room.players
        
        # Player tries to reconnect (should fail - game in progress)
        with pytest.raises(Exception):  # Should be GameInProgressError
            await self.room_manager.join_room(room_code, "Player1")
        
        # Clean up
        await self.game_state_manager.force_end_game(room_code)
    
    @pytest.mark.asyncio
    async def test_scoring_accuracy_integration(self):
        """Test scoring accuracy across all components"""
        # Create room with 2 players
        create_result = await self.room_manager.create_room("Host")
        room_code = create_result.room_code
        
        join_result = await self.room_manager.join_room(room_code, "Player1")
        player_id = join_result.player_id
        
        # Start game
        await self.game_state_manager.start_game(
            room_code, create_result.host_player_id, create_result.host_session_token
        )
        
        room = self.room_manager.get_room(room_code)
        player = room.players[player_id]
        
        # Progress to active phase
        await self.game_state_manager.handle_countdown_complete(room_code)
        
        # Test scoring with specific scenarios
        test_scenarios = [
            (30.0, 0, 10 + 5 + 0),   # Perfect timing, no streak: 15 points
            (15.0, 1, 10 + 3 + 2),   # Half time, 1 streak: 15 points 
            (6.0, 2, 10 + 1 + 4),    # Low time, 2 streak: 15 points
        ]
        
        for time_left, initial_streak, expected_points in test_scenarios:
            # Set up player state
            player.streak = initial_streak
            initial_score = player.score
            
            # Submit answer
            submission = SubmissionRecord(
                room_code=room_code,
                round_index=0,
                player_id=player_id,
                expression="1+2+3+18",
                used_numbers=[1, 2, 3, 18],
                client_eval_is_valid=True
            )
            
            points, player_scored = self.player_manager.process_submission(
                room_code, player, submission, time_left, time_limit=30.0
            )
            
            assert points == expected_points
            assert player.score == initial_score + expected_points
            assert player_scored.time_left == time_left
            
            # Reset for next test
            self.player_manager.reset_round_scoring(room_code)
        
        # Clean up
        await self.game_state_manager.force_end_game(room_code)
    
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self):
        """Test system error handling and recovery"""
        # Create room
        create_result = await self.room_manager.create_room("Host")
        room_code = create_result.room_code
        
        # Test with non-existent room
        fake_room = "FAKE"
        
        # Should handle gracefully
        await self.game_state_manager.start_round(fake_room)
        await self.game_state_manager.handle_countdown_complete(fake_room)
        await self.game_state_manager.end_round(fake_room)
        
        # No crashes should occur
        assert True  # If we get here, error handling worked
        
        # Test invalid operations on real room
        room = self.room_manager.get_room(room_code)
        room.state = "RUNNING"
        
        # Try to start game again (should fail)
        with pytest.raises(Exception):
            await self.game_state_manager.start_game(
                room_code, create_result.host_player_id, create_result.host_session_token
            )
        
        # System should remain stable
        assert self.room_manager.get_room(room_code) is not None
    
    @pytest.mark.asyncio
    async def test_statistics_and_monitoring(self):
        """Test statistics collection across all components"""
        # Get initial statistics
        room_stats = self.room_manager.get_room_stats()
        player_stats = self.player_manager.get_player_stats()
        game_stats = self.game_state_manager.get_game_stats()
        
        initial_rooms_created = room_stats['lifetime_stats']['rooms_created']
        initial_games_started = game_stats['global_stats']['games_started']
        
        # Create room and start game
        create_result = await self.room_manager.create_room("Host")
        await self.room_manager.join_room(create_result.room_code, "Player1")
        
        await self.game_state_manager.start_game(
            create_result.room_code, 
            create_result.host_player_id, 
            create_result.host_session_token
        )
        
        # Check updated statistics
        new_room_stats = self.room_manager.get_room_stats()
        new_game_stats = self.game_state_manager.get_game_stats()
        
        assert new_room_stats['lifetime_stats']['rooms_created'] == initial_rooms_created + 1
        assert new_game_stats['global_stats']['games_started'] == initial_games_started + 1
        
        # Test room-specific stats
        room_specific_stats = self.game_state_manager.get_game_stats(create_result.room_code)
        assert room_specific_stats['room_code'] == create_result.room_code
        assert room_specific_stats['state'] == "RUNNING"
        
        # Clean up
        await self.game_state_manager.force_end_game(create_result.room_code)
    
    @pytest.mark.asyncio
    async def test_data_consistency(self):
        """Test data consistency across components"""
        # Create room
        create_result = await self.room_manager.create_room("Host")
        room_code = create_result.room_code
        
        # Join players
        player_results = []
        for i in range(3):
            result = await self.room_manager.join_room(room_code, f"Player{i}")
            player_results.append(result)
        
        # Start game
        await self.game_state_manager.start_game(
            room_code, create_result.host_player_id, create_result.host_session_token
        )
        
        # Verify consistency between managers
        room = self.room_manager.get_room(room_code)
        game_stats = self.game_state_manager.get_game_stats(room_code)
        
        # Player counts should match
        assert len(room.players) == game_stats['players_count']
        assert game_stats['state'] == room.state
        assert game_stats['current_round'] == room.round_index + 1
        
        # Progress game and verify consistency
        await self.game_state_manager.handle_countdown_complete(room_code)
        
        # Submit some answers
        for i, result in enumerate(player_results[:2]):
            player = room.players[result.player_id]
            submission = SubmissionRecord(
                room_code=room_code,
                round_index=0,
                player_id=result.player_id,
                expression="1+2+3+18",
                used_numbers=[1, 2, 3, 18],
                client_eval_is_valid=True
            )
            
            self.player_manager.process_submission(
                room_code, player, submission, time_left=20.0 - i*5
            )
        
        # Verify scoring consistency
        leaderboard = self.player_manager.get_leaderboard(room.players)
        score_updates = self.player_manager.get_score_updates(room.players)
        
        # Leaderboard and score updates should be consistent
        for entry in leaderboard:
            matching_update = next(
                (u for u in score_updates if u.player_id == entry.player_id), 
                None
            )
            assert matching_update is not None
            assert matching_update.score == entry.score
        
        # Clean up
        await self.game_state_manager.force_end_game(room_code)
    
    @pytest.mark.asyncio
    async def test_performance_benchmark(self):
        """Basic performance benchmark test"""
        import time
        
        # Measure room creation performance
        start_time = time.time()
        
        rooms = []
        for i in range(10):
            result = await self.room_manager.create_room(f"Host{i}")
            rooms.append(result)
        
        creation_time = time.time() - start_time
        
        # Should create 10 rooms quickly
        assert creation_time < 1.0  # Less than 1 second
        
        # Measure game operations performance
        start_time = time.time()
        
        for room_result in rooms[:5]:  # Test with 5 rooms
            # Join a player
            await self.room_manager.join_room(room_result.room_code, "Player1")
            
            # Start game
            await self.game_state_manager.start_game(
                room_result.room_code,
                room_result.host_player_id,
                room_result.host_session_token
            )
            
            # Quick round
            await self.game_state_manager.handle_countdown_complete(room_result.room_code)
            await self.game_state_manager.handle_round_timeout(room_result.room_code)
            await self.game_state_manager.handle_results_complete(room_result.room_code)
        
        operation_time = time.time() - start_time
        
        # Should handle operations quickly
        assert operation_time < 2.0  # Less than 2 seconds for all operations
        
        # Clean up
        for room_result in rooms:
            try:
                await self.game_state_manager.force_end_game(room_result.room_code)
            except:
                pass  # Some may already be ended


if __name__ == "__main__":
    pytest.main([__file__, "-v"])