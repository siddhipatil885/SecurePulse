"""Managed email OTP recovery without account enumeration or token URLs."""
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import get_settings
from app.core.dependencies import get_session
from app.core.exceptions import ApplicationError
from app.core.rate_limit import SlidingWindowRateLimiter
from app.integrations.neon_auth import NeonAuth
from app.models import User
from app.models.operations import UserDeviceToken

router = APIRouter(prefix='/auth/recovery', tags=['account-recovery'])
limiter = SlidingWindowRateLimiter(5)


class RecoveryRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254, pattern=r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
    purpose: Literal['password', 'verification'] = 'password'

    @field_validator('email', mode='before')
    @classmethod
    def normalize(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class RecoveryCode(RecoveryRequest):
    code: str = Field(min_length=4, max_length=12, pattern=r'^\d+$')


class RecoveryPassword(RecoveryCode):
    new_password: str = Field(min_length=12, max_length=128)


async def enabled(request: Request):
    if not get_settings().auth_enabled or not get_settings().neon_auth_base_url:
        raise ApplicationError('RECOVERY_NOT_CONFIGURED', 'Contact your administrator for account recovery.', 503)
    retry = await limiter.check(request.client.host if request.client else 'unknown')
    if retry:
        raise ApplicationError('RATE_LIMITED', 'Too many attempts. Please try again later.', 429, {'Retry-After': str(retry)})


@router.post('/request', status_code=202, dependencies=[Depends(enabled)])
async def request_code(body: RecoveryRequest):
    try:
        await NeonAuth().public_operation('/email-otp/send-verification-otp',
            {'email': body.email, 'type': 'forget-password' if body.purpose == 'password' else 'email-verification'})
    except ApplicationError as error:
        if error.status_code != 401:
            raise
    return {'message': 'If this is an eligible managed account, a code has been sent. Check your email and spam folder.'}


async def verify_operation(path, body):
    try:
        return await NeonAuth().public_operation(path, body)
    except ApplicationError as error:
        if error.status_code == 401:
            raise ApplicationError('INVALID_RECOVERY_CODE', 'The code is invalid or expired. Request a new code.', 400) from None
        raise


@router.post('/verify', dependencies=[Depends(enabled)])
async def verify_email(body: RecoveryCode):
    await verify_operation('/email-otp/verify-email', {'email': body.email, 'otp': body.code})
    return {'message': 'Email verified. You can now sign in.'}


@router.post('/reset', dependencies=[Depends(enabled)])
async def reset_password(body: RecoveryPassword, session: AsyncSession = Depends(get_session)):
    await verify_operation('/email-otp/reset-password', {'email': body.email, 'otp': body.code, 'password': body.new_password})
    # The OTP is consumed by the provider. Retry local revocation independently,
    # without attempting a second remote password reset.
    for attempt in range(3):
        try:
            ids = select(User.id).where(User.email == body.email, User.subject.like('neon:%'))
            await session.execute(update(UserDeviceToken).where(UserDeviceToken.user_id.in_(ids)).values(active=False))
            await session.execute(update(User).where(User.email == body.email, User.subject.like('neon:%')).values(token_version=User.token_version + 1))
            await session.commit()
            break
        except SQLAlchemyError:
            await session.rollback()
            if attempt == 2:
                # Managed sign-in always completes both local revocations before
                # issuing a JWT, including after a restart or prolonged outage.
                raise ApplicationError('RESET_REVOCATION_PENDING', 'Your password was reset. Sign in with the new password to finish ending previous sessions; retry sign-in if the server is unavailable.', 503) from None
    return {'message': 'Password reset. Sign in with your new password. Older administrator-managed accounts need administrator assistance.'}
