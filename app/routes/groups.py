"""
Groups CRUD endpoints.

This is a thin HTTP adapter - all business logic is in GroupsService.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.utils.auth import validate_api_key
from app.services.groups_service import GroupsService
from app.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


def handle_service_error(error: ValueError, operation: str, group_id: Optional[int] = None) -> HTTPException:
    """
    Convert service layer ValueError to appropriate HTTPException.

    Args:
        error: ValueError from service layer
        operation: Operation name for logging (e.g., "get_group", "create_group")
        group_id: Optional group ID for logging context

    Returns:
        HTTPException with appropriate status code
    """
    error_msg = str(error)

    # Determine if this is a 404 or 400 error
    is_not_found = "not found" in error_msg.lower()

    if is_not_found:
        status_code = status.HTTP_404_NOT_FOUND
        log_context = {"operation": operation, "error": error_msg}
        if group_id:
            log_context["group_id"] = group_id
        logger.warning(f"{operation}_not_found", **log_context)
    else:
        status_code = status.HTTP_400_BAD_REQUEST
        log_context = {"operation": operation, "error": error_msg}
        if group_id:
            log_context["group_id"] = group_id
        logger.warning(f"{operation}_failed", **log_context)

    return HTTPException(status_code=status_code, detail=error_msg)


class GroupCreateRequest(BaseModel):
    """Request model for creating a group."""
    name: str = Field(..., min_length=1, max_length=100, description="Group name (must be unique)")
    description: Optional[str] = Field(None, max_length=500, description="Optional group description")


class GroupUpdateRequest(BaseModel):
    """Request model for updating a group."""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="New group name")
    description: Optional[str] = Field(None, max_length=500, description="New group description")


class GroupRoomsUpdateRequest(BaseModel):
    """Request model for updating group room assignments."""
    room_ids: List[int] = Field(..., description="List of room IDs to assign to this group")


@router.get("/groups")
async def list_groups(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    List all groups with room counts.

    Returns:
        dict: {
            "groups": [
                {
                    "id": 1,
                    "name": "Upstairs",
                    "description": "Upper floor rooms",
                    "room_count": 5,
                    "created_at": "2025-11-03T10:00:00Z",
                    "updated_at": "2025-11-03T10:00:00Z"
                },
                ...
            ]
        }
    """
    service = GroupsService(db)
    return await service.list_all()


@router.get("/groups/{group_id}")
async def get_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Get group details with associated rooms.

    Args:
        group_id: Group ID

    Returns:
        dict: {
            "id": 1,
            "name": "Upstairs",
            "description": "Upper floor rooms",
            "created_at": "2025-11-03T10:00:00Z",
            "updated_at": "2025-11-03T10:00:00Z",
            "rooms": [
                {
                    "id": 1,
                    "name": "Master",
                    "tado_zone": "Main Bed",
                    "mel_device": "Master bedroom"
                },
                ...
            ]
        }

    Raises:
        HTTPException: 404 if group not found
    """
    service = GroupsService(db)

    try:
        return await service.get_by_id(group_id)
    except ValueError as e:
        raise handle_service_error(e, "get_group", group_id)


@router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(
    request: GroupCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Create a new group.

    Args:
        request: Group details (name, optional description)

    Returns:
        dict: {
            "ok": true,
            "group": {
                "id": 3,
                "name": "Bedrooms",
                "description": "All bedroom zones",
                "created_at": "2025-11-03T10:00:00Z",
                "updated_at": "2025-11-03T10:00:00Z"
            }
        }

    Raises:
        HTTPException: 400 if name is invalid or already exists
    """
    service = GroupsService(db)

    try:
        return await service.create(request.name, request.description)
    except ValueError as e:
        raise handle_service_error(e, "create_group")


@router.put("/groups/{group_id}")
async def update_group(
    group_id: int,
    request: GroupUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Update group details.

    Args:
        group_id: Group ID
        request: Updated fields (name and/or description)

    Returns:
        dict: {
            "ok": true,
            "group": {
                "id": 3,
                "name": "Updated Name",
                "description": "Updated description",
                "created_at": "2025-11-03T10:00:00Z",
                "updated_at": "2025-11-03T11:00:00Z"
            }
        }

    Raises:
        HTTPException: 404 if group not found, 400 if name invalid/duplicate
    """
    service = GroupsService(db)

    try:
        return await service.update(group_id, request.name, request.description)
    except ValueError as e:
        raise handle_service_error(e, "update_group", group_id)


@router.delete("/groups/{group_id}")
async def delete_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Delete a group.

    Cascade removes all room associations but does NOT delete rooms.

    Args:
        group_id: Group ID

    Returns:
        dict: {
            "ok": true,
            "message": "Group 'Upstairs' deleted"
        }

    Raises:
        HTTPException: 404 if group not found
    """
    service = GroupsService(db)

    try:
        return await service.delete(group_id)
    except ValueError as e:
        raise handle_service_error(e, "delete_group", group_id)


@router.put("/groups/{group_id}/rooms")
async def update_group_rooms(
    group_id: int,
    request: GroupRoomsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(validate_api_key)
):
    """
    Update room assignments for a group.

    Replaces all existing room associations with the provided list.
    Pass empty list to remove all rooms from the group.

    Args:
        group_id: Group ID
        request: List of room IDs to assign

    Returns:
        dict: {
            "ok": true,
            "message": "Updated 3 room(s) for group 'Upstairs'"
        }

    Raises:
        HTTPException: 404 if group not found, 400 if invalid room IDs
    """
    service = GroupsService(db)

    try:
        return await service.update_rooms(group_id, request.room_ids)
    except ValueError as e:
        raise handle_service_error(e, "update_group_rooms", group_id)
