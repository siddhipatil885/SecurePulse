"""Local administrator review; never expose identity documents in owner APIs."""
import argparse
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from app.core.config import get_settings
from app.database.database import get_session_factory
from app.models import AuditRecord, MarshalOnboarding, MarshalProfile
from app.services.marshal_identity import IdentityVault


async def review(profile_id, decision, reviewer, reason, confirm_checks=False):
    async with get_session_factory()() as session:
        profile = await session.scalar(select(MarshalProfile).where(MarshalProfile.id == profile_id).with_for_update())
        record = await session.get(MarshalOnboarding, profile_id)
        if not profile or not record or profile.verification_status != 'PENDING':
            raise ValueError('No pending submission for this marshal.')
        if decision == 'APPROVED' and not confirm_checks:
            raise ValueError('Review the original ID, portrait, adult age and both contacts; then pass --confirm-checks.')
        profile.verification_status = decision
        record.reviewed_by = reviewer
        record.reviewed_at = datetime.now(timezone.utc)
        record.review_note = reason
        session.add(AuditRecord(property_id=profile.property_id, actor_subject='administrator:' + reviewer,
            action='MARSHAL_ONBOARDING_' + decision, resource_type='marshal_onboarding', resource_id=str(profile.id),
            correlation_id=uuid4().hex, details={}))
        await session.commit()


async def run(args):
    if args.approve or args.reject:
        if not args.reviewer or not args.reason or len(args.reason.strip()) < 5:
            raise ValueError('Provide --reviewer and a useful --reason (shown to the marshal).')
        await review(args.approve or args.reject, 'APPROVED' if args.approve else 'REJECTED', args.reviewer, args.reason.strip(), args.confirm_checks)
        print('Review saved. No phone OTP or government verification is implied by this manual approval.')
        return
    async with get_session_factory()() as session:
        if args.inspect:
            record = await session.get(MarshalOnboarding, args.inspect)
            profile = await session.get(MarshalProfile, args.inspect)
            if not record or not profile:
                raise ValueError('Submission not found.')
            if not args.output_dir or not args.reviewer:
                raise ValueError('--inspect requires --output-dir and --reviewer. Files contain private personal data.')
            vault = IdentityVault(get_settings())
            folder = Path(args.output_dir).resolve()
            folder.mkdir(parents=True, exist_ok=False, mode=0o700)
            # Explicit administrator export only. Nothing is written to app media storage.
            import os
            for name, content in [('details.json', json.dumps(vault.details(record.encrypted_details), indent=2).encode()),
                                  *[(kind + '.jpg', vault.photo(reference)) for kind, reference in record.documents.items()]]:
                with os.fdopen(os.open(folder / name, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), 'wb') as target:
                    target.write(content)
            session.add(AuditRecord(property_id=profile.property_id, actor_subject='administrator:' + args.reviewer,
                action='MARSHAL_IDENTITY_ADMIN_EXPORT', resource_type='marshal_onboarding', resource_id=str(profile.id),
                correlation_id=uuid4().hex, details={}))
            await session.commit()
            print('Private review files exported to:', folder)
        else:
            rows = (await session.execute(select(MarshalProfile.id, MarshalProfile.verification_status,
                MarshalOnboarding.submitted_at).outerjoin(MarshalOnboarding, MarshalOnboarding.marshal_profile_id == MarshalProfile.id))).all()
            for row in rows:
                print('Marshal', row.id, row.verification_status, row.submitted_at or '')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--inspect', type=int); group.add_argument('--approve', type=int); group.add_argument('--reject', type=int)
    parser.add_argument('--reviewer'); parser.add_argument('--reason'); parser.add_argument('--output-dir')
    parser.add_argument('--confirm-checks', action='store_true')
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except ValueError as error:
        parser.error(str(error))
