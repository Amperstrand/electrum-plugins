import os, json, subprocess
import pytest
from pathlib import Path

from cltv_lib import get_builder, generate_address
from test_keys import get_test_pubkey

from fund_all_paths import build_all_path_outputs, btc_amt

EXPECTED_TOTAL = 12  # 1 (simple) + 2 (escrow 2-party) + 3 (escrow 3-party) + 2 (payment channel) + 2 (twofactor) + 2 (data publishing)

def test_build_all_path_outputs_structure():
    outputs = build_all_path_outputs()
    assert len(outputs) == EXPECTED_TOTAL
    # Ensure required keys
    for o in outputs:
        for k in ('script_id', 'address', 'lockheight', 'path_name'):
            assert k in o
        assert o['address'].startswith('tb1q')
    # Path uniqueness within (script_id, path_name)
    combos = {(o['script_id'], o['path_name']) for o in outputs}
    assert len(combos) == EXPECTED_TOTAL

def test_manual_paytomany_string():
    outputs = build_all_path_outputs()
    pay_cmd = '; '.join(f"{o['address']}, {btc_amt(1000)}" for o in outputs)
    # Should contain exactly EXPECTED_TOTAL occurrences of ', '
    assert pay_cmd.count(',') == EXPECTED_TOTAL
    # Semicolon separators
    assert pay_cmd.count(';') == EXPECTED_TOTAL - 1
