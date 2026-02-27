"""
Decaying Multisig Contract Definition

A 3-of-5 multisig that decays to 2-of-5 after 60 months, then to 1-of-5 after 66 months.
This allows users to secure funds with 5 keys while allowing recovery even if 4 keys are lost.

Reference: https://github.com/coins/bitcoin-scripts/blob/master/decaying-multi-signature.md
Original idea: https://twitter.com/JWWeatherman_/status/1249101431161774080
See also: Pieter Wuille's Miniscript example "A 3-of-3 that turns into a 2-of-3 after 90 days"
"""

from .definitions import ContractDefinition, ContractType, ParamSpec, SpendingPath, KeyRole


DECAYING_MULTISIG = ContractDefinition(
    contract_type=ContractType.DECAYING_MULTISIG,
    name="Decaying Multisig",
    description="3-of-5 multisig that decays to 2-of-5 after 60 months, then 1-of-5 after 66 months",
    miniscript=(
        "or_i("
        "  multi(3, key1, key2, key3, key4, key5),"
        "  or_i("
        "    and_v(after_drop(locktime_60m), multi(2, key1, key2, key3, key4, key5)),"
        "    and_v(after_drop(locktime_66m), multi(1, key1, key2, key3, key4, key5))"
        "  )"
        ")"
    ),
    params=[
        ParamSpec("locktime_60m", "Block height after 60 months (when 2-of-5 becomes available)", param_type="locktime"),
        ParamSpec("locktime_66m", "Block height after 66 months (when 1-of-5 becomes available)", param_type="locktime"),
        ParamSpec("key1", "First public key", param_type="pubkey", test_key_name="alice"),
        ParamSpec("key2", "Second public key", param_type="pubkey", test_key_name="bob"),
        ParamSpec("key3", "Third public key", param_type="pubkey", test_key_name="lenny"),
        ParamSpec("key4", "Fourth public key", param_type="pubkey", test_key_name="hodl"),
        ParamSpec("key5", "Fifth public key", param_type="pubkey", test_key_name="alice"),  # Reuse for demo
    ],
    taproot_leaves=[
        "multi_a(3, key1, key2, key3, key4, key5)",  # Normal: 3-of-5
        "and_v(after_drop(locktime_60m), multi_a(2, key1, key2, key3, key4, key5))",  # After 60m: 2-of-5
        "and_v(after_drop(locktime_66m), multi_a(1, key1, key2, key3, key4, key5))",  # After 66m: 1-of-5
    ],
    
    # UI metadata
    bip_reference="Decaying Multisig Pattern",
    short_description="Multisig that becomes easier to spend over time",
    use_cases=[
        "Long-term cold storage with key recovery",
        "HODL wallet with backup recovery",
        "Inheritance planning with time-based access"
    ],
 icon="",
    
    paths=[
        SpendingPath(
            name="normal",
            display_name="Normal (3-of-5)",
            description="Spend with 3 of 5 keys (immediate, no timelock)",
            requires_locktime=False,
            required_keys=["key1", "key2", "key3"],  # Any 3 of 5
            is_cooperative=True,
            leaf_index=0,
        ),
        SpendingPath(
            name="decay_60m",
            display_name="After 60 Months (2-of-5)",
            description="Spend with 2 of 5 keys after 60 months",
            requires_locktime=True,
            required_keys=["key1", "key2"],  # Any 2 of 5
            is_cooperative=False,
            leaf_index=1,
        ),
        SpendingPath(
            name="decay_66m",
            display_name="After 66 Months (1-of-5)",
            description="Spend with 1 of 5 keys after 66 months",
            requires_locktime=True,
            required_keys=["key1"],  # Any 1 of 5
            is_cooperative=False,
            leaf_index=2,
        ),
    ],
    
    key_roles=[
 KeyRole("key1", "Key 1", "First backup key", ""),
 KeyRole("key2", "Key 2", "Second backup key", ""),
 KeyRole("key3", "Key 3", "Third backup key", ""),
 KeyRole("key4", "Key 4", "Fourth backup key", ""),
 KeyRole("key5", "Key 5", "Fifth backup key", ""),
    ],
)

