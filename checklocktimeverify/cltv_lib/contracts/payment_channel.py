"""
Payment Channel Contract Definition

Bi-directional payment channel with timeout refund.
BIP-65 Example #4: Payment Channel.
"""

from .definitions import ContractDefinition, ContractType, ParamSpec, SpendingPath, KeyRole


PAYMENT_CHANNEL = ContractDefinition(
    contract_type=ContractType.PAYMENT_CHANNEL,
    name="Payment Channel",
    description="Bi-directional payment channel with timeout refund.",
    miniscript="or_i(multi(2, sender, receiver), and_v(after_drop(locktime), c:pk(sender)))",
    params=[
        ParamSpec("locktime", "Block height after which sender can refund"),
        ParamSpec("sender", "Sender's public key (funds the channel)", param_type="pubkey", test_key_name="sender"),
        ParamSpec("receiver", "Receiver's public key (receives payments)", param_type="pubkey", test_key_name="receiver"),
    ],
    taproot_leaves=[
        "multi_a(2, sender, receiver)",  # Cooperative close - CHECKSIGADD-based multisig (BIP-342)
        "and_v(after_drop(locktime), c:pk(sender))",  # Timeout refund
    ],
    
    # UI metadata
    bip_reference="BIP-65 Example #4: Payment Channel",
    short_description="Bi-directional payment channel with refund timeout",
    use_cases=["Micro-payments", "Streaming payments", "Off-chain transactions"],
    icon="💸",
    
    paths=[
        SpendingPath(
            name="cooperative",
            display_name="Cooperative Close",
            description="Both sender and receiver agree to close the channel",
            requires_locktime=False,
            required_keys=["sender", "receiver"],
            is_cooperative=True,
            leaf_index=0,
        ),
        SpendingPath(
            name="refund",
            display_name="Sender Refund",
            description="Sender reclaims funds after timeout (receiver unresponsive)",
            requires_locktime=True,
            required_keys=["sender"],
            is_cooperative=False,
            leaf_index=1,
        ),
    ],
    
    key_roles=[
        KeyRole("sender", "Sender", "The party funding the channel", "📤"),
        KeyRole("receiver", "Receiver", "The party receiving payments", "📥"),
    ],
)










