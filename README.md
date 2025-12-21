# CC-CHECKER-GENERATOR

Full-stack credit card generation and validation suite. It auto-refreshes hot non-VBV BINs via rotating APIs, forges realistic card sets with configurable BIN patterns, and runs server-side checks with fallback BIN intelligence. Includes proxy-ready Python backend, responsive frontend, and daily BIN updater for consistent live-rate performance.

## 💳 Credit Card Checker

### Running locally

```rb
  - Install XAMPP or Python 3.x
  - Extract files into the project folder
  - Install dependencies: pip install python-dotenv
  - Configure API keys: Copy .env.example to .env and fill in your API keys
  - Run: python server.py
  - Goto http://127.0.0.1:9000
```

**Note** ~ Use high quality SOCKS/SSL proxies

### API Keys Configuration

API keys are stored in `.env` file (not in git for security):

- `HANDY_API_KEY` - Handy API key (optional, paid/enterprise)
- `BINTABLE_API_KEY` - Bintable.com key (optional, free signup)
- `BINCODES_API_KEY` - Bincodes.com key (optional, free registration)

The system uses multiple free APIs with automatic fallback:

1. binlist.net (primary, no key required)
2. Handy API (if key provided)
3. freebinchecker.com (free unlimited)
4. bincheck.io (free unlimited)
5. bintable.com (if key provided)
6. bincodes.com (if key provided)

### Auto-Update Fresh BINs

Run `update_bins.py` daily to get fresh hot BINs via API rotation:

```bash
python update_bins.py
```

Or add to Windows Task Scheduler (daily at 2 AM):

- Program: `python`
- Arguments: `update_bins.py`
- Start in: `C:\path\to\CC-Checker-main`

The script will:

- Check starter BINs via API rotation (HandyAPI -> binlist.net -> freebinchecker)
- Smart filter: credit + Visa/MC + US/DE/IT + prepaid=false (non-VBV friendly)
- Save fresh BINs to `fresh_bins.json` (auto-loaded by card_generator.py)

> **Warning**
> All the information provided here is intended solely for educational and testing purposes. I do not endorse any illegal activities or unfair usage of this program.

### 📄 License

Copyright © 2025 [MadnessBrains](https://madnessbrains.tilda.ws/)

Licensed under the Apache License, Version 2.0
