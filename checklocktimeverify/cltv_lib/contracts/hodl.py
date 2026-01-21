"""
HODL Contract Definition

Simple time-locked single signature. Funds locked until locktime.
BIP-65 Basic Example.
"""

from .definitions import ContractDefinition, ContractType, ParamSpec, SpendingPath, KeyRole


HODL = ContractDefinition(
    contract_type=ContractType.HODL,
    name="HODL",
    description="Time-locked single signature. Funds locked until locktime.",
    miniscript="and_v(after_drop(locktime), c:pk(pubkey))",
    params=[
        ParamSpec("locktime", "Block height when funds unlock"),
        ParamSpec("pubkey", "Owner's public key", test_key_name="hodl"),
    ],
    taproot_leaves=["and_v(after_drop(locktime), c:pk(pubkey))"],
    
    # UI metadata
    bip_reference="BIP-65 Basic Example",
    short_description="Lock funds until a specific block height",
    use_cases=["Long-term savings", "HODL commitment", "Time-delayed inheritance"],
    icon="⏰",
    
    paths=[
        SpendingPath(
            name="sweep",
            display_name="Sweep Funds",
            description="Spend funds after the locktime has passed",
            requires_locktime=True,
            required_keys=["pubkey"],
            is_cooperative=False,
            leaf_index=0,
        ),
    ],
    
    key_roles=[
        KeyRole("pubkey", "Owner", "The key that can spend after locktime", "👤"),
    ],
)










