"""
Two-Factor Wallet Contract Definition

2FA with service co-signer, user-only recovery after timeout.
BIP-65 Example #3: Two-Factor Wallet.
"""

from .definitions import ContractDefinition, ContractType, ParamSpec, SpendingPath, KeyRole


TWOFACTOR = ContractDefinition(
    contract_type=ContractType.TWOFACTOR,
    name="Two-Factor Wallet",
    description="2FA with service co-signer, user-only recovery after timeout.",
    miniscript="or_i(and_v(v:c:pk(service), c:pk(user)), and_v(after_drop(locktime), c:pk(user)))",
    params=[
        ParamSpec("locktime", "Block height when recovery becomes available"),
        ParamSpec("user", "User's public key (your key)", param_type="pubkey", test_key_name="user"),
        ParamSpec("service", "Service's public key (2FA provider)", param_type="pubkey", test_key_name="service"),
    ],
    taproot_leaves=[
        "and_v(v:c:pk(service), c:pk(user))",  # Normal: 2-of-2
        "and_v(after_drop(locktime), c:pk(user))",  # Recovery
    ],
    
    # UI metadata
    bip_reference="BIP-65 Example #3: Two-Factor Wallet",
    short_description="2FA spending with emergency recovery after timeout",
    use_cases=["Secure wallet", "Business continuity", "Lost device recovery"],
    icon="🔐",
    
    paths=[
        SpendingPath(
            name="normal",
            display_name="Normal (User + Service)",
            description="Both user and 2FA service sign together",
            requires_locktime=False,
            # Stack order: [user_sig, service_sig] (service consumed first from top)
            required_keys=["user", "service"],
            is_cooperative=True,
            leaf_index=0,
        ),
        SpendingPath(
            name="recovery",
            display_name="Recovery (User Only)",
            description="User alone after timeout (if service unavailable)",
            requires_locktime=True,
            required_keys=["user"],
            is_cooperative=False,
            leaf_index=1,
        ),
    ],
    
    key_roles=[
        KeyRole("user", "User", "Your personal key", "👤"),
        KeyRole("service", "Service", "2FA provider's key", "🏢"),
    ],
)










