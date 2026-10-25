"""Local administrator provisioning. Never exposed through the API."""
import argparse
import asyncio
import getpass
import re
from uuid import uuid4

from sqlalchemy import select
from app.core.reporter_auth import hash_password
from app.database.database import get_session_factory
from app.models import Camera, Property, PropertyMembership, User


async def provision(args, password: str) -> None:
    async with get_session_factory()() as session, session.begin():
        email = args.email.strip().lower()
        if await session.scalar(select(User).where(User.email == email)):
            raise ValueError("Account already exists; no changes made.")
        if args.property_id:
            property_record = await session.get(Property, args.property_id)
            if property_record is None:
                raise ValueError("Property does not exist.")
        else:
            slug = re.sub(r"[^a-z0-9]+", "-", args.property_name.lower()).strip("-") or "property"
            property_record = Property(slug=f"{slug}-{uuid4().hex[:8]}", name=args.property_name)
            session.add(property_record)
            await session.flush()
        for camera_id in set(args.camera_id):
            if await session.get(Camera, camera_id) is None:
                raise ValueError(f"Camera {camera_id} does not exist.")
            camera = await session.get(Camera, camera_id)
            if camera.property_id != property_record.id:
                raise ValueError(f"Camera {camera_id} already belongs to another property.")
        user = User(subject=email, email=email, display_name=args.name, password_hash=hash_password(password))
        session.add(user)
        await session.flush()
        session.add(PropertyMembership(user_id=user.id, property_id=property_record.id, role=args.role))
    print(f"Created reporter account {user.id} for property {property_record.id}.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", choices=["owner", "reporter"], required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--property-name")
    group.add_argument("--property-id", type=int)
    parser.add_argument("--camera-id", action="append", type=int, default=[])
    args = parser.parse_args()
    if not (3 <= len(args.email) <= 254 and "@" in args.email and 1 <= len(args.name) <= 120):
        parser.error("Provide a valid email and a name of 1–120 characters.")
    if args.property_name is not None and not 1 <= len(args.property_name) <= 200:
        parser.error("Property name must be 1–200 characters.")
    password = getpass.getpass("Password (12–128 characters): ")
    if not 12 <= len(password) <= 128 or password != getpass.getpass("Confirm password: "):
        parser.error("Passwords must match and contain 12–128 characters.")
    asyncio.run(provision(args, password))


if __name__ == "__main__":
    main()
