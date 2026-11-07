"""Private identity data: independent encryption key, local encrypted documents."""
from datetime import date
from io import BytesIO
import json
import os
from pathlib import Path
import re
from typing import Literal
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field, field_validator, model_validator
from app.core.exceptions import ApplicationError

CONSENT_VERSION = 'marshal-onboarding-v1'


class IdentityDetails(BaseModel):
    legal_name: str = Field(min_length=2, max_length=120)
    date_of_birth: date
    phone: str
    address: str = Field(min_length=10, max_length=1000)
    id_type: Literal['DRIVING_LICENCE', 'PASSPORT', 'VOTER_ID']
    id_number: str = Field(min_length=5, max_length=32)
    emergency_name: str = Field(min_length=2, max_length=120)
    emergency_phone: str
    emergency_relationship: Literal['spouse', 'parent', 'sibling', 'friend', 'other']
    consent: Literal[True]
    emergency_contact_informed: Literal[True]

    @field_validator('legal_name', 'address', 'emergency_name', mode='before')
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator('phone', 'emergency_phone')
    @classmethod
    def phone_number(cls, value):
        value = re.sub(r'[\s()-]', '', value)
        if re.fullmatch(r'[6-9]\d{9}', value):
            value = '+91' + value
        if not re.fullmatch(r'\+[1-9]\d{9,14}', value) or len(set(value[-10:])) < 2:
            raise ValueError('Enter a valid phone number with country code.')
        return value

    @field_validator('id_number')
    @classmethod
    def id_format(cls, value):
        value = value.strip().upper()
        if not re.fullmatch(r'[A-Z0-9 -]{5,32}', value):
            raise ValueError('Enter a valid government ID number.')
        # Aadhaar is not accepted through this photo-review flow.
        if re.fullmatch(r'\d{12}', re.sub(r'[ -]', '', value)):
            raise ValueError('Use a passport, driving licence or voter ID; do not enter an Aadhaar number.')
        return value

    @model_validator(mode='after')
    def validate_person(self):
        today = date.today()
        age = today.year - self.date_of_birth.year - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
        if not 18 <= age <= 100:
            raise ValueError('Marshals must be adults; check the date of birth.')
        if self.phone == self.emergency_phone:
            raise ValueError('Emergency contact must use a different phone number.')
        return self


class IdentityVault:
    def __init__(self, settings):
        try:
            if not settings.marshal_identity_key or not settings.marshal_identity_root:
                raise ValueError()
            self.crypto = Fernet(settings.marshal_identity_key.encode())
            self.root = Path(settings.marshal_identity_root).resolve()
        except (ValueError, TypeError):
            raise ApplicationError('IDENTITY_NOT_CONFIGURED', 'Private identity storage is not configured. Contact your administrator.', 503) from None

    def encrypt_details(self, details):
        return self.crypto.encrypt(details.model_dump_json().encode())

    def details(self, data):
        try:
            return json.loads(self.crypto.decrypt(data))
        except (InvalidToken, ValueError):
            raise ApplicationError('IDENTITY_UNAVAILABLE', 'Identity data could not be opened. Contact your administrator.', 503) from None

    def _path(self, name):
        if not re.fullmatch(r'[a-f0-9]{32}\.bin', name):
            raise ApplicationError('NOT_FOUND', 'Document not found.', 404)
        return self.root / name

    def save_photo(self, raw):
        try:
            with Image.open(BytesIO(raw), formats=['JPEG', 'PNG']) as image:
                if image.format not in {'JPEG', 'PNG'} or image.width * image.height > 20_000_000 or min(image.size) < 300:
                    raise ValueError()
                image.load()
                cleaned = ImageOps.exif_transpose(image).convert('RGB')
                cleaned.thumbnail((1800, 1800))
                output = BytesIO()
                cleaned.save(output, format='JPEG', quality=88)
        except (UnidentifiedImageError, ValueError, OSError, Image.DecompressionBombError):
            raise ApplicationError('INVALID_IDENTITY_PHOTO', 'Upload a clear JPG or PNG, at least 300 pixels on each side.', 422) from None
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = uuid4().hex + '.bin'
        with os.fdopen(os.open(self._path(name), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as target:
            target.write(self.crypto.encrypt(output.getvalue()))
        return name

    def photo(self, name):
        try:
            return self.crypto.decrypt(self._path(name).read_bytes())
        except (FileNotFoundError, InvalidToken):
            raise ApplicationError('NOT_FOUND', 'Document is unavailable.', 404) from None

    def discard(self, documents):
        for name in documents.values():
            self._path(name).unlink(missing_ok=True)
