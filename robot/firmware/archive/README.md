# Archived firmware experiments

Sources here are **not** built by any PlatformIO env. Kept for reference only.

| File | Archived | Reason |
|------|----------|--------|
| `face240_espi_test.cpp` | 2026-06-23 | TFT_eSPI sprite experiment; product path uses `face240_9expr_merged` |

To restore: copy back to `src/`, add a dedicated `[env:*]` in `platformio.ini`, verify with `pio run -e <env>`.
