# ⚠️ DISCLAIMER ⚠️

## SIGNET-PRODUCTION Quality Proof of Concept

This CHECKLOCKTIMEVERIFY plugin is a **SIGNET-PRODUCTION** level quality proof of concept.

### This is kind of a meme and a joke! 😄

**DO NOT USE ON MAINNET WITH REAL BITCOIN!**

## What This Means

✅ **Safe for:**
- Bitcoin Signet (worthless test coins)
- Bitcoin Testnet (worthless test coins)
- Educational purposes
- Learning about BIP-65 and Bitcoin Script
- Hackathon demonstrations
- Code study and review

❌ **NOT Safe for:**
- Bitcoin Mainnet
- Real funds
- Production use
- Financial transactions
- Anything involving actual value

## Mainnet Protection

The plugin includes **hardcoded protection** against mainnet usage:

```python
# 🚨 MAINNET PROTECTION 🚨
if constants.net.TESTNET == False and constants.net.REGTEST == False:
    raise RuntimeError("CLTV Plugin cannot run on mainnet")
```

**If you try to run this on mainnet, it will:**
1. Show an error message
2. Refuse to open the dialog
3. Log warnings to the console
4. Prevent you from generating addresses

## Why This Disclaimer?

This plugin was built as:
- An **educational tool** to demonstrate BIP-65
- A **learning resource** for understanding Bitcoin timelocks
- A **hackathon project** to showcase Electrum plugin development
- A **fun demonstration** of Bitcoin Script capabilities

It has **NOT** been:
- ❌ Audited by security professionals
- ❌ Tested extensively with real funds
- ❌ Reviewed for production readiness
- ❌ Verified against all edge cases
- ❌ Hardened against attack vectors

## Sponsorship

**Developed with sponsorship from:**

### Vibes Capital Management 🚀

![Vibes Capital Management](vibes_logo.jpg)

This project was made possible by the generous support of Vibes Capital Management.

## Use At Your Own Risk

Even on testnet/signet, this software is provided "AS IS" without warranty of any kind.

By using this plugin, you acknowledge:
- ✅ You understand this is experimental software
- ✅ You will only use it on testnet/signet
- ✅ You accept full responsibility for any outcomes
- ✅ You've read and understood this disclaimer
- ✅ You think Bitcoin is cool and want to learn 🎓

## Questions?

**Q: Can I use this on mainnet if I really want to?**
A: No. The code literally prevents it. That's the joke! 😄

**Q: What if I modify the code to bypass the check?**
A: Then you're on your own, friend. This is your sign to NOT do that.

**Q: Is this plugin malicious?**
A: No! It's educational. All code is open source for review.

**Q: Can I fork this and make it production-ready?**
A: Sure! MIT license. But please audit it thoroughly first.

**Q: Why "SIGNET-PRODUCTION"?**
A: It's production-quality... for signet. Get it? 😏

## Final Word

**Bitcoin is serious business.**

This plugin is **not serious business**.

It's a learning tool, a demonstration, and yes, kind of a meme.

If you want to use CHECKLOCKTIMEVERIFY on mainnet:
- Use battle-tested wallets
- Get professional security audits
- Test exhaustively on testnet first
- Understand the risks completely
- Maybe don't use a plugin made for a hackathon 😉

---

**Stay safe, have fun learning, and thanks to Vibes Capital Management for making this possible! 🚀**

*"Not your keys, not your coins. Not production-ready, not on mainnet!" - Ancient Bitcoin Proverb*
