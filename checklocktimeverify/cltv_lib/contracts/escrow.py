"""
Escrow Contract Definition

3-party escrow: Alice/Bob 2-of-2, or Lenny arbitration after timeout.
BIP-65 Example #1: Escrow with Timeout.
"""

from .definitions import ContractDefinition, ContractType, ParamSpec, SpendingPath, KeyRole


ESCROW = ContractDefinition(
    contract_type=ContractType.ESCROW,
    name="Escrow with Timeout",
    description="3-party escrow: Alice/Bob 2-of-2, or Lenny arbitration after timeout.",
    miniscript="or_i(multi(2, alice, bob), and_v(after_drop(locktime), and_v(v:c:pk(lenny), multi(1, alice, bob))))",
    params=[
        ParamSpec("locktime", "Block height when arbitration becomes available"),
        ParamSpec("alice", "Alice's public key (party A)", param_type="pubkey", test_key_name="alice"),
        ParamSpec("bob", "Bob's public key (party B)", param_type="pubkey", test_key_name="bob"),
        ParamSpec("lenny", "Lenny's public key (arbiter)", param_type="pubkey", test_key_name="lenny"),
    ],
    taproot_leaves=[
        "multi_a(2, alice, bob)",  # Normal: 2-of-2 CHECKSIGADD-based multisig (BIP-342)
        "and_v(after_drop(locktime), and_v(v:c:pk(lenny), multi_a(1, alice, bob)))",  # Arbitration
    ],
    
    # UI metadata
    bip_reference="BIP-65 Example #1: Escrow with Timeout",
    short_description="3-party escrow with arbitration after timeout",
    use_cases=["Marketplace escrow", "Dispute resolution", "Trust-minimized trades"],
 icon="",
    
    paths=[
        SpendingPath(
            name="normal",
            display_name="Normal (Alice + Bob)",
            description="Both parties agree on the outcome",
            requires_locktime=False,
            required_keys=["alice", "bob"],
            is_cooperative=True,
            leaf_index=0,
        ),
        SpendingPath(
            name="arbitration_alice",
            display_name="Arbitration (Lenny + Alice)",
            description="Arbiter sides with Alice after timeout",
            requires_locktime=True,
            # Stack order: [alice_sig, lenny_sig] (lenny consumed first from top)
            required_keys=["alice", "lenny"],
            is_cooperative=False,
            leaf_index=1,
        ),
        SpendingPath(
            name="arbitration_bob",
            display_name="Arbitration (Lenny + Bob)",
            description="Arbiter sides with Bob after timeout",
            requires_locktime=True,
            # Stack order: [bob_sig, lenny_sig] (lenny consumed first from top)
            required_keys=["bob", "lenny"],
            is_cooperative=False,
            leaf_index=1,
        ),
    ],
    
    key_roles=[
 KeyRole("alice", "Alice", "First party (e.g., buyer)", ""),
 KeyRole("bob", "Bob", "Second party (e.g., seller)", ""),
 KeyRole("lenny", "Lenny", "Neutral arbiter", ""),
    ],
)










