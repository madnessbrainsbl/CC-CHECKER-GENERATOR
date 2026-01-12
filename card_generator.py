import random
from datetime import datetime
import urllib.request
import json
import ssl
import time
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Игнорируем SSL ошибки
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# Hot Dec 2025 non-VBV BINs (avoid Discover - они часто не проходят)
# Hot Dec 2025 non-VBV BINs (avoid Discover - they often fail)
# Strict selection: only proven hot BINs for high live rate
BASE_BINS = [
    # US Visa BINs (high success rate)
    "426684", "474473", "426176", "479126", "415974",
    # US MC BINs
    "531106", "515593", "520082", "544612",
    # DE/IT non-VBV (часто skip 3DS на low amount trials)
    "455620", "415974",
]

# Strict matrix middle patterns (only real patterns from dumps)
# Vary ONLY last 6-8 digits, fix middle for maximum realism
MIDDLE_PATTERNS = [
    '',  # No middle (40% chance - more variety in tail)
    # Real patterns from known dumps (proven)
    '10', '20',  # Common increments
    '1234', '5678',  # Sequential 4-digit (most common in real dumps)
]

# Load configuration for API keys
CONFIG = {}
CONFIG_FILE = 'config.json'
if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE, 'r') as f:
            CONFIG = json.load(f)
    except:
        pass

# API ключи из .env (приоритет) или config.json (fallback)
HANDY_API_KEY = os.getenv('HANDY_API_KEY', CONFIG.get('api_keys', {}).get('handy_api_key', ''))
BINLIST_API_KEY = os.getenv('BINLIST_API_KEY', CONFIG.get('api_keys', {}).get('binlist_api_key', ''))
BINTABLE_API_KEY = os.getenv('BINTABLE_API_KEY', CONFIG.get('api_keys', {}).get('bintable_api_key', ''))
BINCODES_API_KEY = os.getenv('BINCODES_API_KEY', CONFIG.get('api_keys', {}).get('bincodes_api_key', ''))

# Кэш для валидных BIN'ов
BIN_CACHE = {}
CACHE_EXPIRY = 3600  # 1 час
CACHE_FILE = 'bin_cache.json'

# Загружаем кэш из файла
if os.path.exists(CACHE_FILE):
    try:
        with open(CACHE_FILE, 'r') as f:
            cached_data = json.load(f)
            current_time = time.time()
            for key, value in cached_data.items():
                if current_time - value.get('timestamp', 0) < CACHE_EXPIRY:
                    BIN_CACHE[key] = value
    except:
        pass

def save_cache():
    """Сохранить кэш в файл"""
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump(BIN_CACHE, f)
    except:
        pass

def luhn_checksum(number_str):
    """Calculate Luhn check digit for a partial card number string."""
    digits = [int(d) for d in number_str]
    for i in range(len(digits) - 2, -1, -2):
        doubled = digits[i] * 2
        digits[i] = doubled - 9 if doubled > 9 else doubled
    total = sum(digits)
    return (10 - (total % 10)) % 10

def validate_luhn(card_number):
    """Validate card number using Luhn algorithm"""
    digits = [int(d) for d in str(card_number)]
    checksum = digits[-1]
    digits = digits[:-1]
    
    for i in range(len(digits) - 1, -1, -2):
        doubled = digits[i] * 2
        digits[i] = doubled - 9 if doubled > 9 else doubled
    
    total = sum(digits) + checksum
    return total % 10 == 0

def lookup_bin_handyapi(bin_prefix, api_key=None):
    """
    Lookup BIN via Handy API (handyapi.com/bin-list).
    Free tier: 900k+ records, updated weekly/daily.
    Returns (is_valid, bank_name, country, country_code, scheme, type) tuple.
    """
    bin_number = str(bin_prefix)[:6]
    cache_key = f"handy_{bin_number}"
    
    # Проверяем кэш
    if cache_key in BIN_CACHE:
        cached_data = BIN_CACHE[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_EXPIRY:
            return cached_data['result']
    
    url = f"https://data.handyapi.com/bin/{bin_number}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    if api_key:
        headers["x-api-key"] = api_key
    
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                bank_name = data.get('Issuer', 'Unknown')
                country = data.get('Country', {}).get('Name', 'Unknown')
                country_code = data.get('Country', {}).get('A2', '')
                scheme = data.get('Scheme', '').lower()
                card_type = data.get('Type', '').lower()
                
                result = (True, bank_name, country, country_code, scheme, card_type)
                BIN_CACHE[cache_key] = {'result': result, 'timestamp': time.time()}
                save_cache()
                return result
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(6)
        return (False, f"HTTP {e.code}", "", "", "", "")
    except:
        pass
    
    return (False, "API error", "", "", "", "")

def lookup_bin_binlist(bin_prefix):
    """
    Lookup BIN via binlist.net (free, no key required, eternal classic).
    Primary API - open-source data, GitHub updates.
    Limits: ~10 req/min, потом 429 — sleep 6s.
    """
    bin_number = str(bin_prefix)[:6]
    cache_key = f"binlist_{bin_number}"
    
    if cache_key in BIN_CACHE:
        cached_data = BIN_CACHE[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_EXPIRY:
            return cached_data['result']
    
    url = f"https://lookup.binlist.net/{bin_number}"
    
    try:
        req = urllib.request.Request(
            url,
            headers={
                "Accept-Version": "3",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                bank_name = data.get('bank', {}).get('name', 'Unknown')
                country = data.get('country', {}).get('name', 'Unknown')
                country_code = data.get('country', {}).get('alpha2', '')
                scheme = data.get('scheme', '').lower()
                card_type = data.get('type', '').lower()
                
                result = (True, bank_name, country, country_code, scheme, card_type)
                BIN_CACHE[cache_key] = {'result': result, 'timestamp': time.time()}
                save_cache()
                return result
            elif response.status == 404:
                result = (False, "Not found", "", "", "", "")
                BIN_CACHE[cache_key] = {'result': result, 'timestamp': time.time()}
                save_cache()
                return result
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(6)
        return (False, f"HTTP {e.code}", "", "", "", "")
    except:
        pass
    
    return (False, "API error", "", "", "", "")

def lookup_bin_bincheckio(bin_prefix):
    """
    Lookup BIN via bincheck.io (free web lookup, 365k+ BINs database).
    Free unlimited lookup.
    """
    bin_number = str(bin_prefix)[:6]
    cache_key = f"bincheckio_{bin_number}"
    
    if cache_key in BIN_CACHE:
        cached_data = BIN_CACHE[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_EXPIRY:
            return cached_data['result']
    
    url = f"https://bincheck.io/api/v1/{bin_number}"
    
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                if data.get('success') or data.get('valid'):
                    bank_name = data.get('bank', {}).get('name', 'Unknown')
                    country = data.get('country', {}).get('name', 'Unknown')
                    country_code = data.get('country', {}).get('code', data.get('country', {}).get('alpha2', ''))
                    scheme = data.get('scheme', data.get('brand', '')).lower()
                    card_type = data.get('type', data.get('card_type', '')).lower()
                    
                    result = (True, bank_name, country, country_code, scheme, card_type)
                    BIN_CACHE[cache_key] = {'result': result, 'timestamp': time.time()}
                    save_cache()
                    return result
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(6)
    except:
        pass
    
    return (False, "API error", "", "", "", "")

def lookup_bin_freebinchecker(bin_prefix):
    """
    Lookup BIN via freebinchecker.com (public RESTful API, community updated frequently).
    Free unlimited lookup, но premium для bulk.
    """
    bin_number = str(bin_prefix)[:6]
    cache_key = f"freebinchecker_{bin_number}"
    
    if cache_key in BIN_CACHE:
        cached_data = BIN_CACHE[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_EXPIRY:
            return cached_data['result']
    
    url = f"https://api.freebinchecker.com/bin/{bin_number}"
    
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                if data.get('valid') or data.get('success'):
                    bank_name = data.get('bank', data.get('issuer', 'Unknown'))
                    country = data.get('country', data.get('country_name', 'Unknown'))
                    country_code = data.get('country_code', data.get('country_alpha2', ''))
                    scheme = data.get('brand', data.get('scheme', '')).lower()
                    card_type = data.get('type', data.get('card_type', '')).lower()
                    
                    result = (True, bank_name, country, country_code, scheme, card_type)
                    BIN_CACHE[cache_key] = {'result': result, 'timestamp': time.time()}
                    save_cache()
                    return result
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(6)
    except:
        pass
    
    return (False, "API error", "", "", "", "")

def lookup_bin_bintable(bin_prefix, api_key=None):
    """
    Lookup BIN via bintable.com (free signup, 100 lookups/month).
    Accurate, easy. Requires API key.
    """
    if not api_key and not BINTABLE_API_KEY:
        return (False, "No API key", "", "", "", "")
    
    bin_number = str(bin_prefix)[:6]
    cache_key = f"bintable_{bin_number}"
    
    if cache_key in BIN_CACHE:
        cached_data = BIN_CACHE[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_EXPIRY:
            return cached_data['result']
    
    url = f"https://api.bintable.com/v1/{bin_number}?api_key={api_key or BINTABLE_API_KEY}"
    
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                if data.get('valid') or data.get('success'):
                    bank_name = data.get('bank', data.get('issuer', {}).get('name', 'Unknown'))
                    country = data.get('country', data.get('country_name', 'Unknown'))
                    country_code = data.get('country_code', data.get('country_alpha2', ''))
                    scheme = data.get('scheme', data.get('brand', '')).lower()
                    card_type = data.get('type', data.get('card_type', '')).lower()
                    
                    result = (True, bank_name, country, country_code, scheme, card_type)
                    BIN_CACHE[cache_key] = {'result': result, 'timestamp': time.time()}
                    save_cache()
                    return result
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(6)
    except:
        pass
    
    return (False, "API error", "", "", "", "")

def lookup_bin_bincodes(bin_prefix, api_key=None):
    """
    Lookup BIN via bincodes.com (free tools + API, register для key).
    """
    if not api_key and not BINCODES_API_KEY:
        return (False, "No API key", "", "", "", "")
    
    bin_number = str(bin_prefix)[:6]
    cache_key = f"bincodes_{bin_number}"
    
    if cache_key in BIN_CACHE:
        cached_data = BIN_CACHE[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_EXPIRY:
            return cached_data['result']
    
    url = f"https://api.bincodes.com/bin/json/{BINCODES_API_KEY or api_key}/{bin_number}"
    
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                if data.get('valid') or data.get('status') == 'success':
                    bank_name = data.get('bank', data.get('issuer', 'Unknown'))
                    country = data.get('country', data.get('country_name', 'Unknown'))
                    country_code = data.get('country_code', data.get('country_alpha2', ''))
                    scheme = data.get('scheme', data.get('brand', '')).lower()
                    card_type = data.get('type', data.get('card_type', '')).lower()
                    
                    result = (True, bank_name, country, country_code, scheme, card_type)
                    BIN_CACHE[cache_key] = {'result': result, 'timestamp': time.time()}
                    save_cache()
                    return result
    except urllib.error.HTTPError as e:
        if e.code == 429:
            time.sleep(6)
    except:
        pass
    
    return (False, "API error", "", "", "", "")

def lookup_bin(bin_prefix, api_key=None):
    """
    Lookup BIN with multiple API rotation and fallback.
    Primary: binlist.net (eternal classic, no key) -> Handy API -> freebinchecker -> bincheck.io -> bintable -> bincodes
    Smart rotate при 429/errors, всегда fresh data.
    """
    # Primary: binlist.net (no key, eternal classic, ideal fallback)
    result = lookup_bin_binlist(bin_prefix)
    if result[0]:
        return result
    
    # Fallback 1: Handy API (if key provided, paid/enterprise, high quality)
    if api_key or HANDY_API_KEY:
        result = lookup_bin_handyapi(bin_prefix, api_key or HANDY_API_KEY)
        if result[0]:
            return result
    
    # Fallback 2: freebinchecker.com (public RESTful, community updated)
    result = lookup_bin_freebinchecker(bin_prefix)
    if result[0]:
        return result
    
    # Fallback 3: bincheck.io (free unlimited, 365k+ BINs)
    result = lookup_bin_bincheckio(bin_prefix)
    if result[0]:
        return result
    
    # Fallback 4: bintable.com (free signup, 100/month, accurate)
    if BINTABLE_API_KEY:
        result = lookup_bin_bintable(bin_prefix)
        if result[0]:
            return result
    
    # Fallback 5: bincodes.com (free tools + API, register для key)
    if BINCODES_API_KEY:
        result = lookup_bin_bincodes(bin_prefix)
        if result[0]:
            return result
    
    return (False, "All APIs failed", "", "", "", "")

def is_active_bin(bin_prefix, check_credit=True):
    """
    Quick check if BIN is active via API (optional pre-filter).
    Returns True if active and (optionally) credit type, or if API check fails (fallback).
    """
    bin_number = str(bin_prefix)[:6]
    cache_key = f"active_check_{bin_number}"
    
    # Проверяем кэш
    if cache_key in BIN_CACHE:
        cached_data = BIN_CACHE[cache_key]
        if time.time() - cached_data['timestamp'] < CACHE_EXPIRY:
            return cached_data['result']
    
    # Quick check via binlist.net (fast, no key required)
    try:
        url = f"https://lookup.binlist.net/{bin_number}"
        req = urllib.request.Request(
            url,
            headers={"Accept-Version": "3", "User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                # Проверяем что это credit (если требуется)
                if check_credit:
                    card_type = data.get('type', '').lower()
                    result = card_type == 'credit'
                else:
                    result = True
            elif response.status == 404:
                result = False
            else:
                result = True  # Fallback: assume active if unknown
        BIN_CACHE[cache_key] = {'result': result, 'timestamp': time.time()}
        save_cache()
        return result
    except:
        # Fallback: assume active if API check fails
        return True

def get_fresh_bins(bins_list, filter_credit=True, filter_countries=None, check_all=False, api_key=None):
    """
    Auto-update: check validity of BINs via multiple APIs, filter active ones.
    
    Args:
        bins_list: List of BIN prefixes to check
        filter_credit: Only include credit cards (default: True)
        filter_countries: List of country codes to include
        check_all: Check all BINs or use cache (default: False)
        api_key: Handy API key (optional)
    """
    if filter_countries is None:
        filter_countries = ['US', 'DE', 'GB', 'CA', 'FR', 'AU', 'NL']
    
    fresh = []
    print(f"Checking {len(bins_list)} BINs via multiple APIs...")
    print("APIs: binlist.net (primary) -> freebinchecker -> bincheck.io -> bintable -> bincodes -> Handy API")
    print(f"Filtering: credit={filter_credit}, countries={', '.join(filter_countries)}")
    print("-" * 70)
    
    for i, bin_p in enumerate(bins_list, 1):
        # Проверяем кэш если не check_all
        if not check_all:
            for api_name in ['handy', 'binlist', 'bincheckio', 'freebinchecker', 'bintable', 'bincodes']:
                cache_key = f"{api_name}_{bin_p[:6]}"
                if cache_key in BIN_CACHE:
                    cached_data = BIN_CACHE[cache_key]
                    if time.time() - cached_data['timestamp'] < CACHE_EXPIRY:
                        result = cached_data['result']
                        if result[0]:
                            country_code = result[3]
                            card_type = result[5]
                            
                            if filter_credit and card_type != 'credit':
                                continue
                            if country_code not in filter_countries:
                                continue
                            
                            fresh.append(bin_p)
                            print(f"{i}. ✓ {bin_p} - {result[1]} ({result[2]}) - CACHED")
                            break
            else:
                # Not in cache, check via API
                valid, bank, country, country_code, scheme, card_type = lookup_bin(bin_p, api_key)
                
                if valid:
                    if filter_credit and card_type != 'credit':
                        print(f"{i}. ✗ {bin_p} - {bank} ({country}) - Not credit")
                        time.sleep(6)
                        continue
                    
                    if country_code not in filter_countries:
                        print(f"{i}. ✗ {bin_p} - {bank} ({country}) - Wrong country")
                        time.sleep(6)
                        continue
                    
                    fresh.append(bin_p)
                    print(f"{i}. ✓ {bin_p} - {bank} ({country}) - {scheme.upper()} {card_type.upper()}")
                else:
                    print(f"{i}. ✗ {bin_p} - {bank} - Dead/Burned/Invalid")
                
                time.sleep(6)  # Безопасная задержка для binlist.net (лимит 10 req/min)
        else:
            # Всегда проверяем через API
            valid, bank, country, country_code, scheme, card_type = lookup_bin(bin_p, api_key)
            
            if valid:
                if filter_credit and card_type != 'credit':
                    print(f"{i}. ✗ {bin_p} - {bank} ({country}) - Not credit")
                    time.sleep(6)
                    continue
                
                if country_code not in filter_countries:
                    print(f"{i}. ✗ {bin_p} - {bank} ({country}) - Wrong country")
                    time.sleep(6)
                    continue
                
                fresh.append(bin_p)
                print(f"{i}. ✓ {bin_p} - {bank} ({country}) - {scheme.upper()} {card_type.upper()}")
            else:
                print(f"{i}. ✗ {bin_p} - {bank} - Dead/Burned/Invalid")
            
            time.sleep(6)  # Safe delay for binlist.net (10 req/min limit)
    
    print("-" * 70)
    if not fresh:
        print("⚠ All BINs dead? Using fallback (known good starters).")
        fresh = ["426684", "474473", "426176"]
    else:
        print(f"✓ Found {len(fresh)} active BINs out of {len(bins_list)} checked")
    
    return fresh

def generate_cc_matrix(bin_prefix, middle_pattern='', length=16):
    """
    Strict matrix generation - vary ONLY last 6-8 digits, fix middle from real patterns.
    This makes the number maximally "real-like" for issuer pre-check.
    """
    if bin_prefix.startswith('3'):
        length = 15  # Amex
    elif bin_prefix.startswith('4') or bin_prefix.startswith('5') or bin_prefix.startswith('6'):
        length = 16
    
    prefix = str(bin_prefix) + str(middle_pattern)
    # Tail length: vary ONLY last 6-8 digits (strict matrix)
    tail_length = length - len(prefix) - 1  # -1 for check digit
    
    if tail_length < 0:
        # If middle is too long, use only BIN
        prefix = str(bin_prefix)
        tail_length = length - len(prefix) - 1
    
    # Ensure tail is 6-8 digits for strict matrix
    if tail_length < 6:
        # If tail is too short, reduce middle
        prefix = str(bin_prefix)
        tail_length = length - len(prefix) - 1
    
    # Generate tail (last 6-8 digits vary - strict matrix)
    tail = ''.join(str(random.randint(0, 9)) for _ in range(tail_length))
    partial = prefix + tail
    check_digit = luhn_checksum(partial)
    return partial + str(check_digit)

# Backward compatibility
def generate_cc(bin_prefix, middle_pattern='', length=16):
    """Alias for generate_cc_matrix"""
    return generate_cc_matrix(bin_prefix, middle_pattern, length)

def generate_expiry():
    """
    Generate valid expiration date (only future dates).
    Super far (4-8 years) for maximum AVS soft flags bypass and premium feel.
    """
    current_year = datetime.now().year
    # Super far: 4-8 years (not 3-7, for maximum bypass)
    year_offset = random.randint(4, 8)
    year = current_year + year_offset
    month = random.randint(1, 12)
    month_str = f"{month:02d}"
    year_str_4 = str(year)
    year_str_2 = str(year % 100)
    return month_str, year_str_4, year_str_2

def generate_cvv(card_type='visa'):
    """Generate CVV"""
    if card_type == 'amex':
        return f"{random.randint(1000, 9999):04d}"
    else:
        return f"{random.randint(100, 999):03d}"

# BIN-to-country/ZIP mapping для perfect match (match BIN country/ZIP)
# Perfect match для bypass AVS flags
BIN_COUNTRY_MAP = {
    # US Visa BINs (high success rate)
    "426684": ("US", "NY", "10001"),  # Chase - NY ZIP
    "474473": ("US", "CA", "90210"),  # CA ZIP
    "426176": ("US", "CA", "94102"),  # CA ZIP
    "479126": ("US", "TX", "77001"),  # TX ZIP
    "415974": ("US", "CA", "90001"),  # CA ZIP (может быть DE, но используем US для consistency)
    # US MC BINs
    "531106": ("US", "CA", "90210"),  # CA ZIP
    "515593": ("US", "NY", "10001"),  # NY ZIP
    "520082": ("US", "TX", "75001"),  # TX ZIP
    "544612": ("US", "CA", "94102"),  # CA ZIP
    # DE/IT non-VBV (часто skip 3DS)
    "455620": ("DE", "DE", "10115"),  # Berlin ZIP
}

# Issuer-to-ZIP mapping для realism (match issuer location)
# Chase → NY ZIP как 10001, Bank of America → CA/NY, etc.
ISSUER_ZIP_MAP = {
    # Chase (часто NY/CA)
    "chase": {"states": ["NY", "CA", "TX", "FL"], "zips": {"NY": ["10001", "10002", "10003", "10004", "10005"], "CA": ["90001", "90210", "94102"], "TX": ["75001", "77001"], "FL": ["33101", "33102"]}},
    # Bank of America (широко распространен)
    "bofa": {"states": ["CA", "NY", "NC", "TX"], "zips": {"CA": ["90001", "90002", "94102"], "NY": ["10001", "10002"], "NC": ["28201", "28202"], "TX": ["75001", "77001"]}},
    # Wells Fargo (CA/TX)
    "wells": {"states": ["CA", "TX", "NY"], "zips": {"CA": ["90001", "90210", "94102"], "TX": ["75001", "77001"], "NY": ["10001", "10002"]}},
    # Citi (NY)
    "citi": {"states": ["NY", "CA", "FL"], "zips": {"NY": ["10001", "10002", "10003", "10004"], "CA": ["90001", "90210"], "FL": ["33101", "33102"]}},
    # Amex (NY/CA)
    "amex": {"states": ["NY", "CA", "TX"], "zips": {"NY": ["10001", "10002", "10003"], "CA": ["90001", "90210", "94102"], "TX": ["75001", "77001"]}},
    # Default (common US locations)
    "default": {"states": ["NY", "CA", "TX", "FL", "IL", "PA"], "zips": {"NY": ["10001", "10002", "10003"], "CA": ["90001", "90210", "94102"], "TX": ["75001", "77001"], "FL": ["33101", "33102"], "IL": ["60601", "60602"], "PA": ["19101", "19102"]}}
}

# Common US names (realistic)
US_FIRST_NAMES = ["John", "Michael", "David", "James", "Robert", "William", "Richard", "Joseph", "Thomas", "Christopher", "Daniel", "Matthew", "Anthony", "Mark", "Donald", "Steven", "Paul", "Andrew", "Joshua", "Kenneth", "Kevin", "Brian", "George", "Timothy", "Ronald", "Jason", "Edward", "Jeffrey", "Ryan", "Jacob", "Gary", "Nicholas", "Eric", "Jonathan", "Stephen", "Larry", "Justin", "Scott", "Brandon", "Benjamin", "Samuel", "Frank", "Gregory", "Raymond", "Alexander", "Patrick", "Jack", "Dennis", "Jerry", "Tyler", "Aaron", "Jose", "Henry", "Adam", "Douglas", "Nathan", "Zachary", "Kyle", "Noah", "Ethan", "Jeremy", "Walter", "Christian", "Keith", "Roger", "Terry", "Austin", "Sean", "Gerald", "Carl", "Harold", "Dylan", "Roy", "Ralph", "Lawrence", "Joe", "Juan", "Wayne", "Alan", "Randy", "Willie", "Gabriel", "Louis", "Russell", "Ralph", "Philip", "Bobby", "Johnny", "Eugene"]

US_LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez", "Hernandez", "Lopez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin", "Lee", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson", "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores", "Green", "Adams", "Nelson", "Baker", "Hall", "Rivera", "Campbell", "Mitchell", "Carter", "Roberts"]

def generate_address_by_bin(bin_prefix):
    """
    Generate address matching BIN country/ZIP для realism.
    Generate address matching BIN country/ZIP for realism.
    CN BINs -> CN ZIP, DE BINs -> DE ZIP, US BINs -> US ZIP.
    Returns: (name, state, zip_code, country)
    """
    bin_str = str(bin_prefix)[:6]
    country_info = BIN_COUNTRY_MAP.get(bin_str)
    
    if country_info:
        country, state, zip_code = country_info
        # Generate name depending on country
        if country == "CN":
            # Chinese names
            first_names = ["Wei", "Ming", "Li", "Zhang", "Wang", "Liu", "Chen", "Yang", "Huang", "Zhao"]
            last_names = ["Wang", "Li", "Zhang", "Liu", "Chen", "Yang", "Huang", "Zhao", "Wu", "Zhou"]
            name = f"{random.choice(first_names)} {random.choice(last_names)}"
        elif country == "DE":
            # German names
            first_names = ["Hans", "Peter", "Klaus", "Michael", "Thomas", "Andreas", "Stefan", "Martin", "Christian", "Daniel"]
            last_names = ["Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann"]
            name = f"{random.choice(first_names)} {random.choice(last_names)}"
        else:
            # US names (default)
            first_name = random.choice(US_FIRST_NAMES)
            last_name = random.choice(US_LAST_NAMES)
            name = f"{first_name} {last_name}"
        
        return (name, state, zip_code, country)
    else:
        # Fallback to US
        name, state, zip_code = generate_us_address()
        return (name, state, zip_code, "US")

def generate_us_address(issuer_hint=None):
    """
    Generate random US address for billing.
    Match ZIP with issuer location for realism (Chase -> NY ZIP as 10001).
    """
    # Define issuer by hint or use default
    issuer_key = "default"
    if issuer_hint:
        hint_lower = issuer_hint.lower()
        if "chase" in hint_lower:
            issuer_key = "chase"
        elif "bank of america" in hint_lower or "bofa" in hint_lower:
            issuer_key = "bofa"
        elif "wells" in hint_lower or "fargo" in hint_lower:
            issuer_key = "wells"
        elif "citi" in hint_lower or "citibank" in hint_lower:
            issuer_key = "citi"
        elif "amex" in hint_lower or "american express" in hint_lower:
            issuer_key = "amex"
    
    issuer_data = ISSUER_ZIP_MAP.get(issuer_key, ISSUER_ZIP_MAP["default"])
    states = issuer_data["states"]
    zips_map = issuer_data["zips"]
    
    state = random.choice(states)
    zip_code = random.choice(zips_map.get(state, ["10001"]))
    
    first_name = random.choice(US_FIRST_NAMES)
    last_name = random.choice(US_LAST_NAMES)
    name = f"{first_name} {last_name}"
    
    return name, state, zip_code

# Глобальная переменная для свежих BIN'ов
FRESH_BINS = BASE_BINS.copy()

def update_fresh_bins(filter_credit=True, filter_countries=None, check_all=True, api_key=None):
    """Обновить список свежих BIN'ов через API"""
    global FRESH_BINS
    FRESH_BINS = get_fresh_bins(
        BASE_BINS,
        filter_credit=filter_credit,
        filter_countries=filter_countries,
        check_all=check_all,
        api_key=api_key
    )
    # Сохраняем в файл
    try:
        with open('fresh_bins.json', 'w') as f:
            json.dump({'bins': FRESH_BINS, 'updated': datetime.now().isoformat()}, f)
    except:
        pass
    return FRESH_BINS

# Загружаем сохраненные свежие BIN'ы
if os.path.exists('fresh_bins.json'):
    try:
        with open('fresh_bins.json', 'r') as f:
            saved_data = json.load(f)
            # Проверяем что не старше 7 дней
            updated = datetime.fromisoformat(saved_data.get('updated', '2000-01-01'))
            if (datetime.now() - updated).days < 7:
                FRESH_BINS = saved_data.get('bins', BASE_BINS)
    except:
        pass

def generate_card(bin_prefix=None, use_top_bins=True, use_matrix=True, fresh_bins_list=None, issuer_hint=None, pre_check_bin=False):
    """
    Generate full card with valid data.
    Доработанный алгоритм: matrix + fresh BINs + realism max.
    - Matrix middle patterns (4-6 digits из patterns dumps)
    - Super future expiry (3-7 years)
    - Match ZIP/country с BIN
    - Optional API pre-check для BIN validation
    """
    bins_to_use = fresh_bins_list if fresh_bins_list else FRESH_BINS
    
    if bin_prefix:
        selected_bin = str(bin_prefix)
    elif use_top_bins:
        # Optional: pre-validate BINs via API
        if pre_check_bin and bins_to_use:
            active_bins = [b for b in bins_to_use if is_active_bin(b, check_credit=True)]
            selected_bin = random.choice(active_bins) if active_bins else random.choice(bins_to_use)
        else:
            selected_bin = random.choice(bins_to_use) if bins_to_use else random.choice(BASE_BINS)
    else:
        selected_bin = random.choice(bins_to_use) if bins_to_use else random.choice(BASE_BINS)
    
    if selected_bin.startswith('3'):
        card_type = 'amex'
    elif selected_bin.startswith('4'):
        card_type = 'visa'
    elif selected_bin.startswith('5'):
        card_type = 'mastercard'
    else:
        card_type = 'visa'
    
    # Matrix generation: 70% chance использовать middle pattern
    if use_matrix:
        if random.random() < 0.7:
            middle = random.choice(MIDDLE_PATTERNS)
            card_number = generate_cc_matrix(selected_bin, middle)
        else:
            card_number = generate_cc_matrix(selected_bin, '')
    else:
        card_number = generate_cc_matrix(selected_bin, '')
    
    # Validate Luhn (должно быть валидно, но проверяем на всякий случай)
    if not validate_luhn(card_number):
        # Retry без middle pattern
        card_number = generate_cc_matrix(selected_bin, '')
    
    # Super far expiry (4-8 years) для максимального bypass AVS
    month, year_4, year_2 = generate_expiry()
    cvv = generate_cvv(card_type)
    
    # Match name/ZIP/country с BIN для realism (CN BIN → CN ZIP, DE BIN → DE ZIP)
    name, state, zip_code, country = generate_address_by_bin(selected_bin)
    
    return f"{card_number}|{month}|{year_4}|{cvv}|{name}|{state}|{zip_code}"

def generate_batch(quantity=10, bin_prefix=None, use_top_bins=True, use_matrix=True, fresh_bins_list=None, issuer_hint=None, pre_check_bin=False):
    """
    Generate batch of cards with improved matrix algorithm.
    Доработанный алгоритм: matrix + fresh BINs + realism max.
    """
    cards = []
    for _ in range(quantity):
        card = generate_card(bin_prefix, use_top_bins, use_matrix, fresh_bins_list, issuer_hint, pre_check_bin)
        card_number = card.split('|')[0]
        # Validate Luhn (должно быть валидно, но проверяем)
        if validate_luhn(card_number):
            cards.append(card)
        else:
            # Retry если не валидно
            card = generate_card(bin_prefix, use_top_bins, use_matrix, fresh_bins_list, issuer_hint, pre_check_bin)
            cards.append(card)
    return cards

if __name__ == '__main__':
    print("=== Auto-Updated Card Generator (Multi-API BIN Validation) ===\n")
    
    print("Quick generation (using cached/known BINs):")
    print("-" * 70)
    test_card = generate_card(use_matrix=True)
    parts = test_card.split('|')
    print(f"Generated: {parts[0][:4]} {parts[0][4:8]} {parts[0][8:12]} {parts[0][12:]}")
    print(f"Exp: {parts[1]}/{parts[2]} | CVV: {parts[3]} | Luhn: {validate_luhn(parts[0])}\n")
    
    print("Full BIN validation via multiple APIs:")
    print("=" * 70)
    print("APIs: Handy API (if key in config.json) -> binlist.net -> bincheck.io -> freebinchecker")
    print("(Takes ~5-6 seconds per BIN due to rate limits)\n")
    
    user_input = input("Update BINs via API? (y/n, default=n): ").strip().lower()
    
    if user_input == 'y':
        api_key = HANDY_API_KEY if HANDY_API_KEY else None
        if not api_key:
            print("\n💡 Tip: Add 'handy_api_key' to config.json for better results")
            print("   Register free at: https://handyapi.com/bin-list\n")
        
        update_fresh_bins(
            filter_credit=True,
            filter_countries=['US', 'DE', 'GB', 'CA', 'FR'],
            check_all=True,
            api_key=api_key
        )
        print(f"\nUsing {len(FRESH_BINS)} validated fresh BINs\n")
    
    print("Batch generation (20 cards):")
    print("-" * 70)
    cards = generate_batch(20, use_top_bins=True, use_matrix=True, fresh_bins_list=FRESH_BINS)
    
    for i, card in enumerate(cards, 1):
        parts = card.split('|')
        card_num = parts[0]
        month = parts[1]
        year = parts[2]
        cvv = parts[3]
        
        is_valid = validate_luhn(card_num)
        status = "OK" if is_valid else "FAIL"
        bin_prefix = card_num[:6]
        card_type = "Visa" if bin_prefix.startswith('4') else ("MC" if bin_prefix.startswith('5') else "Amex")
        
        print(f"{i:2d}. {card_num[:4]} {card_num[4:8]} {card_num[8:12]} {card_num[12:]} | {month}/{year} | {cvv} | {card_type} {status}")
