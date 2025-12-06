"""
Data Publishing (PayPub) Contract Definition

Hash-locked data reveal or buyer refund after timeout.
BIP-65 Example #5: Data Publishing (PayPub).
"""

from .definitions import ContractDefinition, ContractType, ParamSpec, SpendingPath, KeyRole


DATA_PUBLISHING = ContractDefinition(
    contract_type=ContractType.DATA_PUBLISHING,
    name="Data Publishing (PayPub)",
    description="Hash-locked data reveal or buyer refund after timeout.",
    miniscript="or_i(and_v(hash160_simple(data_hash), c:pk(publisher)), and_v(after_drop(locktime), c:pk(buyer)))",
    params=[
        ParamSpec("locktime", "Block height when buyer can refund"),
        ParamSpec("publisher", "Publisher's public key", param_type="pubkey", test_key_name="publisher"),
        ParamSpec("buyer", "Buyer's public key", param_type="pubkey", test_key_name="buyer"),
        ParamSpec("data_hash", "HASH160 of the data (derived from preimage)", param_type="hash160"),
        # data_preimage is special: not in script, but needed for spending
        ParamSpec(
            "data_preimage",
            "The actual data (reveals on-chain when claiming)",
            param_type="preimage",
            required=False,  # Only needed for publisher path
            sensitive=True,  # Should be hidden in UI
        ),
    ],
    taproot_leaves=[
        "and_v(hash160_simple(data_hash), c:pk(publisher))",  # Reveal
        "and_v(after_drop(locktime), c:pk(buyer))",  # Refund
    ],
    
    # UI metadata
    bip_reference="BIP-65 Example #5: Data Publishing (PayPub)",
    short_description="Pay for data: Publisher reveals preimage to claim, or buyer refunds",
    use_cases=["Paid data release", "Encryption key sale", "Trustless data exchange"],
    icon="📝",
    
    paths=[
        SpendingPath(
            name="publisher",
            display_name="Claim (Publisher)",
            description="Publisher reveals data preimage to claim payment",
            requires_locktime=False,
            required_keys=["publisher"],
            is_cooperative=True,
            requires_preimage=True,
            warning="⚠️ This will reveal your data on the blockchain permanently!",
            leaf_index=0,
        ),
        SpendingPath(
            name="buyer_refund",
            display_name="Refund (Buyer)",
            description="Buyer reclaims funds if data not revealed by timeout",
            requires_locktime=True,
            required_keys=["buyer"],
            is_cooperative=False,
            leaf_index=1,
        ),
    ],
    
    key_roles=[
        KeyRole("publisher", "Publisher", "Sells the data", "📤"),
        KeyRole("buyer", "Buyer", "Pays for the data", "💰"),
    ],
)

