import pytest

from app.services.metadata_budget import compact_metadata, encoded, metadata_digest
from tests.test_event_processor import make_detection, make_processor


def test_normal_rule_metadata_is_preserved():
    metadata = {'zones': ['entrance'], 'lifecycle': 'new', 'confidence': .91,
                'box': [0.1, 0.2, 0.3, 0.4], 'has_snapshot': True}
    assert compact_metadata(metadata) == metadata


def test_large_metadata_is_bounded_without_modifying_security_input():
    original = {'zones': ['entrance'], 'lifecycle': 'update', 'image_base64': 'x' * 100_000,
                'path': list(range(1000)), **{f'custom_{i}': 'y' * 6000 for i in range(40)}}
    compact = compact_metadata(original)
    assert len(encoded(compact)) <= 8192
    assert 'image_base64' not in compact
    assert compact['zones'] == ['entrance']
    assert compact['_metadata_truncated'] is True
    assert compact['_original_metadata_sha256'] == metadata_digest(original)
    assert len(original['image_base64']) == 100_000 and len(original['path']) == 1000


@pytest.mark.asyncio
async def test_receipts_store_fingerprint_instead_of_repeated_payload():
    processor, _, _, repository = make_processor()
    detection = make_detection(metadata={'zones': ['entrance'], 'image_base64': 'x' * 100_000})
    result = await processor.process(detection)
    receipt = repository.create_receipt.call_args.args[0]
    assert receipt.payload == {'object_type': 'person', 'metadata_sha256': metadata_digest(detection.metadata)}
    assert len(encoded(receipt.payload)) < 160
    assert 'image_base64' not in result.event.event_metadata
