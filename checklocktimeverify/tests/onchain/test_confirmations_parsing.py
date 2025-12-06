import pytest
from pathlib import Path
import json

# Import function from script
from modern_batch_funding import parse_confirmations_output

@pytest.mark.parametrize("text,expected", [
    ("{\"confirmations\": 0}", 0),
    ("{\"confirmations\": 3, \"other\": true}", 3),
    ("confirmations: 5", 5),
    ("   confirmations = 12", 12),
    ("no confirmations here", None),
    ("{\"foo\":1}", None),
    ("", None),
])
def test_parse_confirmations_output(text, expected):
    assert parse_confirmations_output(text) == expected
