# Third-Party Vendored Code

This directory contains reference implementations vendored for test-only purposes.

## Files

### `bip_0340_reference.py`
- **Purpose**: BIP-340 Schnorr Signature reference implementation
- **Source**: https://github.com/bitcoin/bips/blob/master/bip-0340/reference.py
- **Authors**: Pieter Wuille, Jonas Nick, Tim Ruffing, and Bitcoin Core contributors
- **License**: BSD-2-Clause (Bitcoin BIPs repository)
- **BIP**: [BIP-340 - Schnorr Signatures for secp256k1](https://github.com/bitcoin/bips/blob/master/bip-0340.mediawiki)
- **Used for**: Taproot transaction signing and verification in E2E tests

### `bip_350_bech32_reference.py`
- **Purpose**: Bech32/Bech32m address encoding reference implementation
- **Source**: https://github.com/sipa/bech32/blob/master/ref/python/segwit_addr.py
- **Author**: Pieter Wuille
- **License**: MIT License
- **BIPs**: 
  - [BIP-173 - Base32 address format for native v0-16 witness outputs](https://github.com/bitcoin/bips/blob/master/bip-0173.mediawiki)
  - [BIP-350 - Bech32m format for v1+ witness addresses](https://github.com/bitcoin/bips/blob/master/bip-0350.mediawiki)
- **Used for**: Taproot (v1 witness) address generation and parsing in E2E tests

## Why Vendored?

These files are copied here instead of using external dependencies to:
1. Keep the test suite self-contained and reproducible
2. Avoid dependency management complexity for reference implementations
3. Match exact BIP specifications without version drift
4. Enable offline testing without package installation

## Attribution

All original copyright notices, licenses, and attributions are preserved in each file's header. The code is used in compliance with the respective open-source licenses (BSD-2-Clause for BIP-340, MIT for Bech32/Bech32m).

If you're building a production system, consider using maintained libraries like:
- `python-bitcoinlib` for general Bitcoin operations
- Electrum's built-in cryptography modules
- Or depend directly on the upstream reference implementations

## Updates

These are reference implementations and should remain stable. If updates are needed:
1. Check the upstream sources linked above
2. Verify the license hasn't changed
3. Update the vendored copy and preserve all attribution
4. Test thoroughly to ensure compatibility
