#!/usr/bin/env python3
"""
Auto-pull fresh hot BINs via API rotation.
Run daily (cron) to keep BINs warm.

Usage:
    python update_bins.py
    
Or add to cron / Windows Task Scheduler:
    0 2 * * * cd C:\path\to\CC-Checker-main && python update_bins.py
"""

import sys
import os
import json
import time
from datetime import datetime
import urllib.request
import ssl

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HANDY_API_KEY = os.getenv('HANDY_API_KEY', '')

# Fresh Dec 2025 hot non-VBV BINs (tested drops/forums)
# Avoid 4147xx - burned hard in 2025!
STARTER_BINS = [
    # US Visa (proven hot, non-VBV)
    "426684",  # Chase eternal non-VBV
    "474473",  # Capital One
    "479126",  # ESL F.C.U. premium
    "426176",  # Chase-like
    # DE/EU Visa (low-fraud, often skip 3DS)
    "455620",  # Santander DE premier
    "415974",  # Deutsche Apotheker
    "455600",  # Santander classic
    # MC (tested)
    "531106",
    "515593",
    "544612",  # CA
]

def lookup_bin_handyapi(bin_p):
    """Lookup via HandyAPI (primary, high quality)"""
    if not HANDY_API_KEY:
        return None, "No key"
    
    try:
        url = f"https://data.handyapi.com/bin/{bin_p}"
        req = urllib.request.Request(
            url,
            headers={
                "x-api-key": HANDY_API_KEY,
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                return data, "HandyAPI"
    except:
        pass
    return None, "Failed"

def lookup_bin_binlist(bin_p):
    """Lookup via binlist.net (fallback, no key)"""
    try:
        url = f"https://lookup.binlist.net/{bin_p}"
        req = urllib.request.Request(
            url,
            headers={
                'Accept-Version': '3',
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                return data, "binlist.net"
    except:
        pass
    return None, "Failed"

def lookup_bin_freebinchecker(bin_p):
    """Lookup via freebinchecker (fallback)"""
    try:
        url = f"https://api.freebinchecker.com/bin/{bin_p}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        )
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                return data, "freebinchecker"
    except:
        pass
    return None, "Failed"

def lookup_bin(bin_p):
    """
    Lookup BIN with API rotation.
    Primary: HandyAPI -> binlist.net -> freebinchecker
    """
    # Primary: HandyAPI
    data, source = lookup_bin_handyapi(bin_p)
    if data:
        return data, source
    
    # Fallback 1: binlist.net
    data, source = lookup_bin_binlist(bin_p)
    if data:
        return data, source
    
    # Fallback 2: freebinchecker
    data, source = lookup_bin_freebinchecker(bin_p)
    if data:
        return data, source
    
    return None, "All APIs failed"

def smart_filter(data):
    """
    Smart filter: credit + US/DE/IT + prepaid=false (non-VBV friendly).
    Low-fraud zones, higher non-3DS chance.
    Supports different payload formats returned by providers.
    """
    if not data:
        return False
    
    # Check type (credit only) - different APIs expose different fields
    card_type = ''
    if 'Type' in data:
        card_type = str(data['Type']).lower()
    elif 'type' in data:
        card_type = str(data['type']).lower()
    elif 'card_type' in data:
        card_type = str(data['card_type']).lower()
    
    if card_type and card_type != 'credit':
        return False
    
    # Check scheme (Visa/MC only, avoid Discover)
    scheme = ''
    if 'Scheme' in data:
        scheme = str(data['Scheme']).lower()
    elif 'scheme' in data:
        scheme = str(data['scheme']).lower()
    elif 'brand' in data:
        scheme = str(data['brand']).lower()
    
    if scheme and scheme not in ['visa', 'mastercard']:
        return False
    
    # Check prepaid (false only - non-VBV friendly)
    prepaid = False
    if 'prepaid' in data:
        prepaid = bool(data['prepaid'])
    elif 'Prepaid' in data:
        prepaid = bool(data['Prepaid'])
    
    if prepaid:
        return False
    
    # Check country (US/DE/IT only - low-fraud zones)
    country_code = ''
    if 'country' in data:
        if isinstance(data['country'], dict):
            country_code = data['country'].get('alpha2', '') or data['country'].get('A2', '')
        else:
            country_code = str(data['country'])
    elif 'Country' in data:
        if isinstance(data['Country'], dict):
            country_code = data['Country'].get('alpha2', '') or data['Country'].get('A2', '')
        else:
            country_code = str(data['Country'])
    elif 'country_code' in data:
        country_code = str(data['country_code'])
    
    if country_code and country_code.upper() not in ['US', 'DE', 'IT']:
        return False
    
    # If type is missing but scheme and country pass, treat as valid
    if not card_type and scheme and country_code:
        return True
    
    return card_type == 'credit'

def refresh_hot_bins():
    """
    Refresh hot BINs via API rotation.
    Smart filter: credit + US/DE/IT + prepaid=false (non-VBV friendly).
    """
    hot = []
    print(f"\nChecking {len(STARTER_BINS)} starter BINs via API rotation...")
    print("Filter: credit + Visa/MC + US/DE/IT + prepaid=false (non-VBV friendly)")
    print("-" * 70)
    
    for i, b in enumerate(STARTER_BINS, 1):
        data, source = lookup_bin(b)
        
        if data and smart_filter(data):
            country = 'Unknown'
            country_code = ''
            bank = 'Unknown'
            
            if 'country' in data:
                if isinstance(data['country'], dict):
                    country = data['country'].get('name', 'Unknown')
                    country_code = data['country'].get('alpha2', '') or data['country'].get('A2', '')
                else:
                    country = str(data['country'])
            
            if 'bank' in data:
                if isinstance(data['bank'], dict):
                    bank = data['bank'].get('name', 'Unknown')
                else:
                    bank = str(data['bank'])
            elif 'Issuer' in data:
                bank = data['Issuer']
            
            scheme = data.get('scheme', '').upper()
            hot.append(b)
            print(f"{i}. [OK] {b} via {source}: {bank} ({country}) - {scheme} CREDIT")
        else:
            reason = "Not credit" if data and data.get('type', '').lower() != 'credit' else "Dead/Burned/Invalid"
            print(f"{i}. [FAIL] {b} - {reason}")
        
        time.sleep(6)  # Safe delay for rate limits
    
    print("-" * 70)
    if not hot:
        print("[WARN] All BINs dead? Using fallback (known good starters).")
        hot = ["426684", "474473", "426176"]
    else:
        print(f"[OK] Found {len(hot)} fresh hot BINs out of {len(STARTER_BINS)} checked")
    
    return hot or STARTER_BINS

def save_fresh_bins(bins_list):
    """Persist fresh BINs to file"""
    try:
        data = {
            'bins': bins_list,
            'updated': datetime.now().isoformat(),
            'count': len(bins_list)
        }
        with open('fresh_bins.json', 'w') as f:
            json.dump(data, f, indent=2)
        print(f"\n[OK] Saved {len(bins_list)} fresh BINs to fresh_bins.json")
    except Exception as e:
        print(f"\n[ERROR] Error saving fresh_bins.json: {e}")

def main():
    print("=" * 70)
    print("Auto-Update Fresh Hot BINs via API Rotation")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    if HANDY_API_KEY:
        print(f"[OK] HandyAPI key loaded: {HANDY_API_KEY[:15]}...")
    else:
        print("[WARN] HandyAPI key not found in .env")
        print("  Tip: Add HANDY_API_KEY to .env for better results")
        print("  Register free at: https://handyapi.com/bin-list")
    
    # Refresh hot BINs
    fresh_hot_bins = refresh_hot_bins()
    
    # Save to file
    save_fresh_bins(fresh_hot_bins)
    
    print("\n" + "=" * 70)
    print(f"Update completed: {len(fresh_hot_bins)} active BINs")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    return 0 if fresh_hot_bins else 1

if __name__ == '__main__':
    sys.exit(main())
