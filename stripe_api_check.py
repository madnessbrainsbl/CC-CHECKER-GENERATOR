"""
Stripe API Card Checker - Uses API instead of browser
Reliable card check via Stripe API (same as check_card endpoint)
"""

import json
import time
import sys
import requests
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('stripe_api_check.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SERVER_URL = "http://127.0.0.1:9000"


def check_card(card_data):
    """Check single card via server API"""
    parts = card_data.strip().split('|')
    if len(parts) < 4:
        return "INVALID", "Bad format"
    
    ccn, month, year, cvc = parts[0], parts[1], parts[2], parts[3]
    
    try:
        response = requests.post(
            f"{SERVER_URL}/check_card",
            data={'ccn': ccn, 'month': month, 'year': year, 'cvc': cvc},
            timeout=30
        )
        result = response.json()
        return result.get('status', 'UNKNOWN'), result.get('message', '')
    except Exception as e:
        return "ERROR", str(e)


def run_batch(cards_file):
    """Validate batch of cards"""
    try:
        with open(cards_file, 'r') as f:
            cards = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        logger.error(f"File not found: {cards_file}")
        return
    
    total = len(cards)
    logger.info(f"\n{'='*60}")
    logger.info(f"STRIPE API VALIDATION - {total} CARDS")
    logger.info(f"{'='*60}\n")
    
    # Clear results file
    Path('stripe_api_results.txt').unlink(missing_ok=True)
    
    stats = {'LIVE': 0, 'DEAD': 0, '3DS': 0, 'UNKNOWN': 0, 'ERROR': 0, 'INVALID': 0}
    
    for i, card in enumerate(cards, 1):
        logger.info(f"[{i}/{total}] Checking: {card[:20]}...")
        
        status, message = check_card(card)
        
        # Map status
        if 'Live' in status or 'CVV' in status:
            final_status = 'LIVE'
        elif 'Dead' in status or 'decline' in message.lower():
            final_status = 'DEAD'
        elif '3D' in status or '3ds' in status.lower():
            final_status = '3DS'
        elif 'INVALID' in status:
            final_status = 'INVALID'
        elif 'ERROR' in status or 'error' in message.lower():
            final_status = 'ERROR'
        else:
            final_status = 'UNKNOWN'
        
        stats[final_status] = stats.get(final_status, 0) + 1
        
        # Visual result
        icons = {'LIVE': '✅', 'DEAD': '❌', '3DS': '⚠️', 'UNKNOWN': '❓', 'ERROR': '💥', 'INVALID': '⛔'}
        logger.info(f"  {icons.get(final_status, '?')} {final_status} - {message[:50]}")
        
        # Save result
        with open('stripe_api_results.txt', 'a') as f:
            f.write(f"{card}|{final_status}|{message}\n")
        
        # Delay between cards
        if i < total:
            time.sleep(2)
    
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    for status, count in stats.items():
        pct = (count / total * 100) if total > 0 else 0
        logger.info(f"  {status:10} : {count:3} ({pct:.1f}%)")
    
    logger.info(f"\nResults saved: stripe_api_results.txt")
    return stats


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.error("Usage: python stripe_api_check.py <cards_file>")
        sys.exit(1)
    
    run_batch(sys.argv[1])


