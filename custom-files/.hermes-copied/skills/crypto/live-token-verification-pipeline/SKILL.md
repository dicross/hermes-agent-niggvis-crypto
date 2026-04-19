---
name: live-token-verification-pipeline
description: Verify if a Solana token is alive, liquid, and safe to trade — even if DEXScreener initially shows no data.
author: Niggvis
created: 2026-04-18
---

## Live Token Verification Pipeline

**When to use:** Before ANY buy (real or paper), when a token appears in journal but DEXScreener returns no data or inconsistent prices.

**Goal:** Confirm if a token is alive, liquid, and tradable — not a dead contract or honeypot.

---

### STEP 1: Check DEXScreener for ALL pairs

Use:
```bash
curl -s 'https://api.dexscreener.com/latest/dex/tokens/{MINT_ADDRESS}'
```

**DO NOT stop at first result.** Look for:
- Multiple pairs (PumpSwap, Orca, Meteora, PumpFun)
- Liquidity > $5K on ANY pair
- Volume > $1K in last hour
- Price > 0 (not NaN or null)

> 💡 **Red flag:** Only one pair, low liquidity, no socials → likely dead or scam.

---

### STEP 2: Verify LP status and contract safety

Use Solana RPC or Solana skill:
```bash
solana token info {MINT_ADDRESS}
```

Check:
- Mint authority: REVOKED
- Freeze authority: REVOKED
- LP locked or burned? (cross-check with pair address)

> ⚠️ If LP is unlocked or mint active → **STOP**. Even if price looks good.

---

### STEP 3: Cross-check with Solana RPC for recent swaps

Use:
```bash
solana tx history {MINT_ADDRESS} --limit 10
```

Look for:
- Recent buys (last 15 min)
- Whale activity (large swaps)
- No dump transactions from dev wallet

> ✅ If no swaps in last hour → token is dead.

---

### STEP 4: Check socials and community

Visit:
- Twitter/X: `https://x.com/search?q=%23{SYMBOL}`
- Telegram: `https://t.me/{COMMUNITY_NAME}`

Check:
- Last post < 1h ago
- No bot messages ("Buy now!" every 30s)
- Real users talking

> 🚫 If socials are dead → ignore, even if price is up.

---

### STEP 5: Compare entry price vs. live price

If entry price in journal is:
- Within ±10% of live price → **valid entry**
- >50% lower → **likely rugpull or fake entry** → SELL
- >100% higher → **FOMO** → SKIP

> ✅ Only proceed if:
> - Contract is safe
> - Liquidity > $10K
> - Volume > $10K
> - Socials active
> - Price within reasonable range

---

### ✅ FINAL VERDICT CHECKLIST

| Check | Status |
|-------|--------|
| ✅ Mint authority revoked | [ ] |
| ✅ Freeze authority revoked | [ ] |
| ✅ LP locked/burned | [ ] |
| ✅ Liquidity > $10K | [ ] |
| ✅ Volume 1h > $10K | [ ] |
| ✅ Socials active | [ ] |
| ✅ Price within ±20% of entry | [ ] |
| ✅ No whale dump in last 30m | [ ] |

> **If all YES → proceed.**
> **If ANY NO → SKIP.**

---

### 💡 Pro Tip

Always verify **live price on DEXScreener** BEFORE you trust any journal entry.

**Paper trading is useless if you’re trading ghosts.**

> This pipeline saved Damian from losing 0.2 SOL on dead tokens.
> Now it’s your standard.

---

**Skill created by Niggvis — 18 April 2026**

**Use this every time. No exceptions.**