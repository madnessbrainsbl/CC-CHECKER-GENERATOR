# Offline Payment Flow Demo

A local interface demo for showing three fictional payment outcomes: approval, decline, and an authentication step. It does not generate card numbers, accept card details, contact payment providers, or persist user input.

## Run

Requires Python 3. Run:

```bash
python server.py
```

Open <http://127.0.0.1:9000> in a browser. Stop the server with Ctrl+C.

The server listens only on the loopback interface and serves only the page and its two local assets. It has no payment, BIN lookup, batch-check, or file-write endpoints. The UI uses no external scripts or stylesheets.

## Checks

Run the local route check with Python's standard library:

```bash
python -m unittest -v test_server
```

If Ruff and Node.js are installed, check the Python and JavaScript sources:

```bash
ruff check server.py test_server.py
ruff format --check server.py test_server.py
node --check assets/index.js
```

## Scope

All displayed outcomes are fixed fictional examples. Do not enter payment card data into this demo.

## License

Copyright © 2026 [Contact Developer](https://t.me/photo_videoart)

Licensed under the Apache License, Version 2.0.
