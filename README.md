# CC-CHECKER-GENERATOR

Full-stack credit card generation and validation suite. It auto-refreshes hot non-VBV BINs via rotating APIs, forges realistic card sets with configurable BIN patterns, and runs server-side checks with fallback BIN intelligence. Includes proxy-ready Python backend, responsive frontend, and daily BIN updater for consistent live-rate performance.

## Features

- **Advanced Generator**: Creates realistic cards using matrix logic and strict expiration rules (2028-2033).
- **Top BINs Manager**:
  - Manage your own list of favorite BINs.
  - Automatically import detected "Live" BINs from your session.
  - Data persists locally in your browser.
- **Session Persistence**: Your input cards, results (Live/Dead/etc.), and counters are saved automatically. Reload safely without losing data.
- **Smart Validation**:
  - Checks expiration (month/year) before sending to server.
  - Simulates Android SDK for realistic token creation.
  - **Note**: Validation is simulated for educational purposes.
- **Localization**: Full English UI.
- **Proxy Support**: Backend supports rotation (configure in server).

## Running locally

1. **Install Python 3.x**
2. **Clone/Extract** the project.
3. **Install dependencies**:

    ```bash
    pip install requests python-dotenv
    ```

4. **Configure API keys** (Optional):
    - Copy `.env.example` to `.env`.
    - Add keys for HandyAPI, Bintable, etc. if you have them.
5. **Run the Server**:

    ```bash
    python server.py
    ```

6. **Open in Browser**:
    - Go to: `http://127.0.0.1:9000`

## Configuration

Settings are stored in `config.json`:

- `settings`: Control delays, timeouts, and retry logic.
- `api_keys`: Fallback keys if `.env` is missing.

## Auto-Update Fresh BINs

To keep your generator producing high-quality hits, run the updater daily:

```bash
python update_bins.py
```

This script fetches fresh BINs from multiple public sources and filters them for the best success rate (Credit, US/EU, Non-Prepaid).

---

> **Warning**
> All the information provided here is intended solely for educational and testing purposes. I do not endorse any illegal activities or unfair usage of this program.

## License

Copyright © 2026 [Contact Developer](https://t.me/photo_videoart)

Licensed under the Apache License, Version 2.0
