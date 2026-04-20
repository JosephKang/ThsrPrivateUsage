# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CLI tool for automating Taiwan High Speed Rail (THSR) ticket booking. It scrapes/submits forms to the official THSR website faster than the manual web UI. Supports adult, child, disabled, elder, and college student tickets.

## Commands

```bash
# Run type checking (mypy), linting (flake8), and pylint analysis
make check

# Run unit tests with pytest
make test

# Run everything
make all

# Run the booking tool (fully interactive)
thsr-ticket                          # after pip install
.venv/bin/python -m thsr_ticket.main # from project root (recommended in WSL)

# Run with pre-filled arguments (skip selected prompts)
.venv/bin/python -m thsr_ticket.main -f 2 -t 12 -d 2026-05-14 -T 10 -a 1 \
  -i "A123456789" -m n -p 0912345678

# List available station IDs
.venv/bin/python -m thsr_ticket.main --list-station

# List available time slot IDs
.venv/bin/python -m thsr_ticket.main --list-time-table

# Auto-booking (no interactive prompts) — reads cfg/SOB.md or cfg/EOB.md
python scripts/book_auto.py --date 2026-04-21              # SOB, weekday auto-selects T
python scripts/book_auto.py --date 2026-04-21 --profile EOB
python scripts/book_auto.py --date 2026-04-21 --no-discount  # skip 8折/65折 filter

# Run a single test file
python -m pytest thsr_ticket/unittest/model/test_booking_form.py
python -m pytest thsr_ticket/unittest/model/test_confirm_ticket_flow.py
```

## CLI Arguments

| Flag | Description |
|---|---|
| `-f / --from-station` | Origin station ID (1–12) |
| `-t / --to-station` | Destination station ID (1–12) |
| `-d / --date` | Departure date (`YYYY-MM-DD` or `YYYY/MM/DD`) |
| `-T / --time` | Time slot ID (1-based index from `--list-time-table`) |
| `-a / --adult` | Number of adult tickets (0–10); if omitted and `-i` is given, inferred from ID count |
| `-i / --id` | Personal ID(s), `\|`-separated. Count = total passengers (infers adult ticket count). First ID = taker ID + membership number. Subsequent IDs = early-bird passengers 2, 3, … |
| `-m / --membership` | Use THSR membership: `y` or `n`; omit to prompt interactively |
| `-p / --phone` | Phone number (optional) |
| `--list-station` | Print station list and exit |
| `--list-time-table` | Print time table and exit |

Any omitted argument falls back to the original interactive prompt. The `|` separator in `-i` must be quoted in shell (`-i "A123456789|B987654321"`).

`-i` design rules:
- Number of IDs = total passengers = adult ticket count (overridden by explicit `-a`)
- First ID = taker's personal ID and THSR membership number (`memberShipNumber`)
- Subsequent IDs = early-bird passenger 2, 3, … (auto-filled; falls back to interactive if count is insufficient)

## Architecture

The booking process is a 3-stage sequential web form flow, orchestrated by `BookingFlow` in `controller/booking_flow.py`. A parsed `argparse.Namespace` (`args`) is threaded from `main()` → `BookingFlow` → `FirstPageFlow` / `ConfirmTrainFlow` / `ConfirmTicketFlow` and used to bypass interactive prompts when a value is provided.

1. **FirstPageFlow** — prompts (or reads from `args`) for origin/destination/date/time/tickets, auto-recognises CAPTCHA, submits to THSR booking page
2. **ConfirmTrainFlow** — parses available trains (including early-bird and student discount labels); in auto mode (`args.require_discount`) selects first 8折/65折 train automatically, otherwise user selects interactively
3. **ConfirmTicketFlow** — reads personal ID / phone / membership from `args` or prompts, handles early-bird passenger ID input (with `args` pre-fill support), submits final confirmation

After confirmation, `BookingFlow` parses the result and saves a `Record` to TinyDB (`model/db.py`) for history reuse.

### Layer responsibilities

| Layer | Location | Purpose |
|---|---|---|
| Controllers | `controller/*_flow.py` | Orchestrate each booking stage |
| Remote | `remote/http_request.py` | HTTP session with cookie management (JSESSIONID) |
| ViewModels | `view_model/` | Parse HTML (BeautifulSoup4) into structured data |
| Models | `model/web/` | Pydantic v1 models for form data with field aliases |
| Views | `view/web/` | CLI prompts and output display |
| Configs | `configs/` | Station enums, URL constants, time slot lists |

`remote/endpoint_client.py` is a REST API client (PTX API with HMAC-SHA1 auth) that is not used in the main booking flow.

`ml/` contains CAPTCHA image generation using sklearn polynomial warping — used only for testing/development, not in live booking.

### Key design notes

- Pydantic models use `Field(alias=...)` to map THSR HTML form field names to Python-friendly names.
- `configs/common.py` defines the 27-day booking window and the 43 available departure time slots.
- Station codes and ticket type enums live in `configs/rest/enums.py` and `configs/web/`.
- `pydantic<2.0` is required; do not upgrade to Pydantic v2 without refactoring all models.
- Extra membership and early-bird form fields are built as plain `dict` and merged into `dict_params` at call time — they are not part of the Pydantic schema because their shape is determined by HTML at runtime.

### CAPTCHA handling (`controller/first_page_flow.py`)

Auto-recognition pipeline: `_preprocess_captcha()` (median blur → Otsu binarisation → morphological opening → `remove_small_objects`) → `_ddddocr_recognize()`. In interactive mode, the predicted code is shown for confirmation; on failure the image is rendered as Unicode Braille in the terminal. When `args.auto_captcha=True` (used by `book_auto.py`), the OCR result is used directly with no confirmation prompt — `CaptchaError` is raised on empty result. In WSL environments the captcha image is also saved to Windows Downloads as `thsr_captcha.png` / `thsr_captcha_clean.png`. See `docs/captcha_spec.md` for details.

### Membership & early-bird handling (`controller/confirm_ticket_flow.py`)

`_select_member_radio(page, personal_id, args)` — uses `args.membership` (`y`/`n`) if provided, otherwise prompts interactively; reads `#memberSystemRadio1` (member) or `#memberSystemRadio3` (non-member) value from HTML; when membership is used adds `memberShipNumber` and `memberSystemShipCheckBox` fields to the POST payload.

`_process_early_bird(page, personal_id, args)` — detects `.superEarlyBird` elements (one per passenger); passenger 0 defaults to `args.id[0]` or `personal_id`; passengers 1+ are filled from `args.id[1], args.id[2], …` if provided, otherwise prompted interactively (non-empty required).

### Auto-booking script (`scripts/book_auto.py`)

Fully automated end-to-end booking with no interactive prompts. Reads defaults from `cfg/SOB.md` or `cfg/EOB.md`, sets `args.auto_captcha=True` and `args.require_discount=True`, and calls `BookingFlow(args=ns).run()`. For SOB profile the departure time slot is overridden by weekday (Mon–Thu → T=6/07:30, Fri → T=3/06:00). Exit codes: 0=success, 1=captcha fail, 2=no discount train. See `docs/book_auto.md` for full spec.

Exception types in `thsr_ticket/exceptions.py`:
- `CaptchaError` — raised by `_input_security_code()` when `auto_captcha=True` and OCR returns empty
- `NoDiscountError` — raised by `select_available_trains()` when `require_discount=True` and no 8折/65折 train is found
