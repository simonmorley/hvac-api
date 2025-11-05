"""
Groups service - handles CRUD operations for room groups.

All business logic for groups endpoints lives here, keeping the router thin.
Manages many-to-many relationships between rooms and groups.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.models.database import Group, Room, RoomGroup
from app.utils.logging import get_logger

logger = get_logger(__name__)


class GroupsService:
    """
    Service for managing room groups.

    Handles:
    - CRUD operations on groups
    - Managing room-group associations
    - Validation and error handling
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize groups service.

        Args:
            db: Async database session
        """
        self.db = db

    def _group_to_dict(self, group: Group) -> Dict[str, Any]:
        """
        Convert Group model to dictionary.

        Args:
            group: Group database model

        Returns:
            Dict with group fields and ISO timestamps
        """
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "created_at": group.created_at.isoformat(),
            "updated_at": group.updated_at.isoformat()
        }

    async def _get_group_or_raise(self, group_id: int) -> Group:
        """
        Get group by ID or raise ValueError.

        Args:
            group_id: Group ID

        Returns:
            Group model

        Raises:
            ValueError: If group not found
        """
        query = select(Group).where(Group.id == group_id)
        result = await self.db.execute(query)
        group = result.scalar_one_or_none()

        if not group:
            logger.warning("group_not_found", group_id=group_id)
            raise ValueError(f"Group with ID {group_id} not found")

        return group

    async def list_all(self) -> Dict[str, Any]:
        """
        List all groups with room counts.

        Returns:
            Dict: {"groups": [{"id": 1, "name": "Upstairs", "room_count": 5, ...}]}
        """
        logger.info("groups_list_all_requested")

        # Query all groups with room counts
        query = (
            select(
                Group.id,
                Group.name,
                Group.description,
                Group.created_at,
                Group.updated_at,
                func.count(RoomGroup.room_id).label('room_count')
            )
            .outerjoin(RoomGroup, Group.id == RoomGroup.group_id)
            .group_by(Group.id, Group.name, Group.description, Group.created_at, Group.updated_at)
            .order_by(Group.name)
        )

        result = await self.db.execute(query)
        rows = result.all()

        groups = [
            {
                **self._group_to_dict(Group(
                    id=row.id,
                    name=row.name,
                    description=row.description,
                    created_at=row.created_at,
                    updated_at=row.updated_at
                )),
                "room_count": row.room_count
            }
            for row in rows
        ]

        logger.info("groups_list_all_success", count=len(groups))
        return {"groups": groups}

    async def get_by_id(self, group_id: int) -> Dict[str, Any]:
        """
        Get group by ID with associated rooms.

        Args:
            group_id: Group ID

        Returns:
            Dict: Group details with rooms list

        Raises:
            ValueError: If group not found
        """
        logger.info("groups_get_by_id_requested", group_id=group_id)

        # Get group (raises ValueError if not found)
        group = await self._get_group_or_raise(group_id)

        # Get associated rooms
        rooms_query = (
            select(Room)
            .join(RoomGroup, Room.id == RoomGroup.room_id)
            .where(RoomGroup.group_id == group_id)
            .order_by(Room.name)
        )

        rooms_result = await self.db.execute(rooms_query)
        rooms = rooms_result.scalars().all()

        room_list = [
            {
                "id": room.id,
                "name": room.name,
                "tado_zone": room.tado_zone,
                "mel_device": room.mel_device
            }
            for room in rooms
        ]

        group_data = {
            **self._group_to_dict(group),
            "rooms": room_list
        }

        logger.info("groups_get_by_id_success", group_id=group_id, room_count=len(room_list))
        return group_data

    async def create(self, name: str, description: Optional[str] = None) -> Dict[str, Any]:
        """
        Create new group.

        Args:
            name: Group name (must be unique)
            description: Optional description

        Returns:
            Dict: Created group data

        Raises:
            ValueError: If name is empty or already exists
        """
        # Guard clause: validate name
        if not name or not name.strip():
            logger.warning("group_create_invalid_name", name=name)
            raise ValueError("Group name cannot be empty")

        name = name.strip()
        logger.info("groups_create_requested", name=name)

        # Create group
        new_group = Group(
            name=name,
            description=description.strip() if description else None
        )

        try:
            self.db.add(new_group)
            await self.db.commit()
            await self.db.refresh(new_group)
        except IntegrityError as e:
            await self.db.rollback()
            logger.warning("group_create_duplicate_name", name=name, error=str(e))
            raise ValueError(f"Group with name '{name}' already exists")

        logger.info("groups_create_success", group_id=new_group.id, name=name)
        return {"ok": True, "group": self._group_to_dict(new_group)}

    async def update(
        self,
        group_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update group details.

        Args:
            group_id: Group ID
            name: Optional new name
            description: Optional new description

        Returns:
            Dict: Updated group data

        Raises:
            ValueError: If group not found or name already exists
        """
        logger.info("groups_update_requested", group_id=group_id)

        # Get existing group (raises ValueError if not found)
        group = await self._get_group_or_raise(group_id)

        # Guard clause: validate name if provided
        if name is not None and not name.strip():
            logger.warning("group_update_invalid_name", group_id=group_id)
            raise ValueError("Group name cannot be empty")

        # Update fields if provided
        if name is not None:
            group.name = name.strip()

        if description is not None:
            group.description = description.strip() if description else None

        try:
            await self.db.commit()
            await self.db.refresh(group)
        except IntegrityError as e:
            await self.db.rollback()
            logger.warning("group_update_duplicate_name", group_id=group_id, name=name, error=str(e))
            raise ValueError(f"Group with name '{name}' already exists")

        logger.info("groups_update_success", group_id=group_id)
        return {"ok": True, "group": self._group_to_dict(group)}

    async def delete(self, group_id: int) -> Dict[str, Any]:
        """
        Delete group (cascade removes room associations).

        Args:
            group_id: Group ID

        Returns:
            Dict: Success confirmation

        Raises:
            ValueError: If group not found
        """
        logger.info("groups_delete_requested", group_id=group_id)

        # Get group (raises ValueError if not found)
        group = await self._get_group_or_raise(group_id)

        # Delete group (cascade will remove room_groups entries)
        group_name = group.name
        await self.db.delete(group)
        await self.db.commit()

        logger.info("groups_delete_success", group_id=group_id, name=group_name)
        return {"ok": True, "message": f"Group '{group_name}' deleted"}

    async def update_rooms(self, group_id: int, room_ids: List[int]) -> Dict[str, Any]:
        """
        Replace all room associations for a group.

        Removes all existing associations and creates new ones.

        Args:
            group_id: Group ID
            room_ids: List of room IDs to associate

        Returns:
            Dict: Success confirmation with room count

        Raises:
            ValueError: If group not found or invalid room IDs
        """
        logger.info("groups_update_rooms_requested", group_id=group_id, room_ids=room_ids)

        # Get group (raises ValueError if not found)
        group = await self._get_group_or_raise(group_id)

        # Guard clause: validate room IDs exist (if any provided)
        if room_ids:
            await self._validate_room_ids(room_ids, group_id)

        # Delete existing associations
        delete_query = delete(RoomGroup).where(RoomGroup.group_id == group_id)
        await self.db.execute(delete_query)

        # Create new associations
        for room_id in room_ids:
            room_group = RoomGroup(room_id=room_id, group_id=group_id)
            self.db.add(room_group)

        await self.db.commit()

        logger.info("groups_update_rooms_success", group_id=group_id, room_count=len(room_ids))
        return {"ok": True, "message": f"Updated {len(room_ids)} room(s) for group '{group.name}'"}

    async def _validate_room_ids(self, room_ids: List[int], group_id: int) -> None:
        """
        Validate that all room IDs exist in database.

        Args:
            room_ids: List of room IDs to validate
            group_id: Group ID (for logging)

        Raises:
            ValueError: If any room IDs are invalid
        """
        rooms_query = select(Room.id).where(Room.id.in_(room_ids))
        rooms_result = await self.db.execute(rooms_query)
        existing_room_ids = {row[0] for row in rooms_result.all()}

        invalid_ids = set(room_ids) - existing_room_ids

        # Guard clause: invalid room IDs found
        if invalid_ids:
            logger.warning("invalid_room_ids", group_id=group_id, invalid_ids=list(invalid_ids))
            raise ValueError(f"Invalid room IDs: {invalid_ids}")
