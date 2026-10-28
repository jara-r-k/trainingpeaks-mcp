"""Tests for workout library tools."""

from unittest.mock import AsyncMock, patch

import pytest

from tp_mcp.client.http import APIResponse
from tp_mcp.server import call_tool, list_tools
from tp_mcp.tools.library import (
    tp_create_library,
    tp_create_library_item,
    tp_delete_library,
    tp_get_libraries,
    tp_get_library_items,
    tp_schedule_library_workout,
)


class TestGetLibraries:
    @pytest.mark.asyncio
    async def test_list_libraries_maps_real_api_fields(self):
        # Field names as the live /exerciselibrary/v2/libraries endpoint returns them.
        listing = [
            {"exerciseLibraryId": 1, "libraryName": "My Workouts", "ownerName": "Coach", "isDefaultContent": False},
            {"exerciseLibraryId": 2, "libraryName": "Default", "ownerName": "TP", "isDefaultContent": True},
        ]
        responses = {
            "/exerciselibrary/v2/libraries": APIResponse(success=True, data=listing),
            "/exerciselibrary/v2/libraries/1/items": APIResponse(success=True, data=[{}] * 5),
            "/exerciselibrary/v2/libraries/2/items": APIResponse(success=True, data=[]),
        }
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(side_effect=lambda endpoint, **_: responses[endpoint])
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_libraries()

        assert result["count"] == 2
        first, second = result["libraries"]
        assert first == {"id": 1, "name": "My Workouts", "owner": "Coach", "is_default": False, "item_count": 5}
        assert second["name"] == "Default"
        assert second["is_default"] is True
        assert second["item_count"] == 0

    @pytest.mark.asyncio
    async def test_item_count_is_none_when_items_unreadable(self):
        listing = [{"exerciseLibraryId": 7, "libraryName": "Shared"}]
        responses = {
            "/exerciselibrary/v2/libraries": APIResponse(success=True, data=listing),
            "/exerciselibrary/v2/libraries/7/items": APIResponse(success=False, message="Forbidden"),
        }
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(side_effect=lambda endpoint, **_: responses[endpoint])
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_libraries()

        assert result["libraries"][0]["name"] == "Shared"
        assert result["libraries"][0]["item_count"] is None

    @pytest.mark.asyncio
    async def test_empty_listing(self):
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=APIResponse(success=True, data=[]))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_libraries()

        assert result == {"libraries": [], "count": 0}


class TestGetLibraryItems:
    @pytest.mark.asyncio
    async def test_list_items(self):
        data = [
            {"exerciseLibraryItemId": 10, "itemName": "Sweet Spot", "workoutTypeFamilyId": 2, "totalTimePlanned": 1.5, "tssPlanned": 80},
        ]
        response = APIResponse(success=True, data=data)
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_library_items("1")

        assert result["count"] == 1
        assert result["items"][0]["name"] == "Sweet Spot"
        assert result["items"][0]["sport"] == "Bike"  # integer family ids map to names too

    @pytest.mark.asyncio
    async def test_items_map_workout_type_id_and_distance(self):
        # The live items endpoint sends workoutTypeId (1 = Swim), not workoutTypeFamilyId.
        data = [
            {
                "exerciseLibraryItemId": 11,
                "itemName": "CSS test",
                "workoutTypeId": 1,
                "totalTimePlanned": 1.2,
                "tssPlanned": 31,
                "distancePlanned": 2000.0,
            }
        ]
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.get = AsyncMock(return_value=APIResponse(success=True, data=data))
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_get_library_items("1")

        assert result["items"][0]["sport"] == "Swim"
        assert result["items"][0]["distance_m"] == 2000.0


class TestCreateLibrary:
    @pytest.mark.asyncio
    async def test_create_sends_library_name_and_person_id(self):
        response = APIResponse(success=True, data={"exerciseLibraryId": 3})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance._get_user_data = AsyncMock(return_value={"personId": 456})
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_library("  Race Prep  ")

        assert result["success"] is True
        assert result["library_id"] == 3
        payload = mock_instance.post.call_args[1]["json"]
        assert payload == {"libraryName": "Race Prep", "ownerId": 456}
        mock_instance._get_user_data.assert_awaited_once()

    @pytest.mark.parametrize("user_data", [None, {}, {"personId": None}, {"personId": 0}])
    @pytest.mark.asyncio
    async def test_create_refuses_without_person_id(self, user_data):
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance._get_user_data = AsyncMock(return_value=user_data)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_library("Race Prep")

        assert result["error_code"] == "AUTH_INVALID"
        assert "personId" in result["message"]
        mock_instance.post.assert_not_awaited()


class TestDeleteLibrary:
    @pytest.mark.asyncio
    async def test_delete(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.delete = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_delete_library("1")

        assert result["success"] is True


class TestCreateLibraryItem:
    @pytest.mark.parametrize(
        "optional",
        [
            {},
            {"coach_comments": None},
            {"coach_comments": ""},
            {"coach_comments": " \t\n"},
            {"coach_comments": "  Keep café efforts controlled. 😀\nFinish easy.  "},
        ],
    )
    async def test_create_coach_comments_exact_body(self, optional):
        response = APIResponse(success=True, data={"exerciseLibraryItemId": 20})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            client = AsyncMock()
            client.ensure_athlete_id.return_value = 123
            client.post.return_value = response
            mock_client.return_value.__aenter__.return_value = client
            result = await tp_create_library_item(
                library_id="1", name="Synthetic swim", sport_family_id=1, sport_type_id=1, **optional
            )

        assert result["success"] is True
        expected = {"exerciseLibraryId": 1, "itemName": "Synthetic swim", "workoutTypeId": 1}
        if optional.get("coach_comments"):
            expected["coachComments"] = optional["coach_comments"]
        client.post.assert_awaited_once_with("/exerciselibrary/v1/libraries/1/items", json=expected)

    async def test_create_coach_comments_schema_and_dispatch(self):
        tool = next(tool for tool in await list_tools() if tool.name == "tp_create_library_item")
        assert tool.inputSchema["properties"]["coach_comments"]["type"] == "string"
        assert "coach_comments" not in tool.inputSchema["required"]
        comments = "  Keep the last effort controlled.\nFinish easy.  "
        with patch("tp_mcp.server.tp_create_library_item", new_callable=AsyncMock) as create_item:
            create_item.return_value = {"success": True}
            await call_tool(
                "tp_create_library_item",
                {
                    "library_id": "1",
                    "name": "Synthetic swim",
                    "sport_family_id": 1,
                    "sport_type_id": 1,
                    "coach_comments": comments,
                },
            )
        assert create_item.await_args.kwargs["coach_comments"] == comments

    @pytest.mark.asyncio
    async def test_create_includes_distance_planned(self):
        response = APIResponse(success=True, data={"exerciseLibraryItemId": 20})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_library_item(
                library_id="1", name="Swim", sport_family_id=1, sport_type_id=1, distance_m=1500.0
            )

        assert result["success"] is True
        assert mock_instance.post.call_args[1]["json"]["distancePlanned"] == 1500.0

    @pytest.mark.asyncio
    async def test_create_with_structure_nested_object(self):
        """Library item structure should be nested object, not string."""
        structure = {"structure": [{"type": "step"}]}
        response = APIResponse(success=True, data={"exerciseLibraryItemId": 20})
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_create_library_item(
                library_id="1", name="Tempo",
                sport_family_id=2, sport_type_id=3,
                duration_hours=0.75, tss=50, description="Synthetic intervals", structure=structure,
            )

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert "distancePlanned" not in payload
        # Structure should be nested object, NOT JSON string
        assert isinstance(payload["structure"], dict)
        assert payload == {
            "exerciseLibraryId": 1,
            "itemName": "Tempo",
            "workoutTypeId": 3,
            "totalTimePlanned": 0.75,
            "tssPlanned": 50,
            "description": "Synthetic intervals",
            "structure": structure,
        }

    @pytest.mark.parametrize("distance_m", [0, -1])
    @pytest.mark.asyncio
    async def test_create_rejects_non_positive_distance(self, distance_m):
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            result = await tp_create_library_item(
                library_id="1",
                name="Swim",
                sport_family_id=1,
                sport_type_id=1,
                distance_m=distance_m,
            )

        assert result["error_code"] == "VALIDATION_ERROR"
        mock_client.assert_not_called()

    @pytest.mark.parametrize("distance_m", [float("nan"), float("inf")])
    @pytest.mark.asyncio
    async def test_create_rejects_non_finite_distance(self, distance_m):
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            result = await tp_create_library_item(
                library_id="1",
                name="Swim",
                sport_family_id=1,
                sport_type_id=1,
                distance_m=distance_m,
            )

        assert result["error_code"] == "VALIDATION_ERROR"
        mock_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_schema_and_dispatch_include_distance_m(self):
        tools = await list_tools()
        tool = next(tool for tool in tools if tool.name == "tp_create_library_item")
        assert tool.inputSchema["properties"]["distance_m"]["exclusiveMinimum"] == 0
        assert "distance_m" not in tool.inputSchema["required"]

        with patch("tp_mcp.server.tp_create_library_item", new_callable=AsyncMock) as create_item:
            create_item.return_value = {"success": True}
            await call_tool(
                "tp_create_library_item",
                {
                    "library_id": "1",
                    "name": "Swim",
                    "sport_family_id": 1,
                    "sport_type_id": 1,
                    "distance_m": 1500.0,
                },
            )

        assert create_item.await_args.kwargs["distance_m"] == 1500.0


class TestScheduleLibraryWorkout:
    @pytest.mark.asyncio
    async def test_schedule_to_date(self):
        response = APIResponse(success=True, data=None)
        with patch("tp_mcp.tools.library.TPClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.ensure_athlete_id = AsyncMock(return_value=123)
            mock_instance.post = AsyncMock(return_value=response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await tp_schedule_library_workout("1", "10", "2026-04-01")

        assert result["success"] is True
        payload = mock_instance.post.call_args[1]["json"]
        assert payload["exerciseLibraryId"] == 1
        assert payload["exerciseLibraryItemId"] == 10
        assert payload["date"] == "2026-04-01T00:00:00"
