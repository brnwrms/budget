#!/usr/bin/env python3
"""
Budget Display Generator for Kindle - DEBUG VERSION
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont
import requests

try:
    import plaid
    from plaid.api import plaid_api
    from plaid.model.transactions_get_request import TransactionsGetRequest
    from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
    PLAID_AVAILABLE = True
except ImportError:
    PLAID_AVAILABLE = False

WIDTH = 1072
HEIGHT = 1448
BG_COLOR = (232, 232, 232)
TIMEZONE = ZoneInfo('America/Los_Angeles')

EXCLUDED_CATEGORIES = [
    'Transfer', 'Deposit', 'Payment', 
    'Bank Fees', 'Interest', 'Tax'
]

EXCLUDED_TRANSACTION_TYPES = ['special', 'unresolved']


def get_plaid_client():
    env = os.getenv('PLAID_ENV', 'sandbox')
    
    if env == 'sandbox':
        host = plaid.Environment.Sandbox
    elif env == 'development':
        host = plaid.Environment.Development
    else:
        host = plaid.Environment.Production
    
    configuration = plaid.Configuration(
        host=host,
        api_key={
            'clientId': os.getenv('PLAID_CLIENT_ID'),
            'secret': os.getenv('PLAID_SECRET'),
        }
    )
    
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)


def fetch_transactions(client, access_token, days=35):
    end_date = datetime.now(TIMEZONE).date()
    start_date = end_date - timedelta(days=days)
    
    request = TransactionsGetRequest(
        access_token=access_token,
        start_date=start_date,
        end_date=end_date,
        options=TransactionsGetRequestOptions(count=500)
    )
    
    response = client.transactions_get(request)
    return response['transactions']


def calculate_spending(transactions):
    today = datetime.now(TIMEZONE).date()
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)
    month_start = today.replace(day=1)
    
    day_total = 0.0
    week_total = 0.0
    month_total = 0.0
    
    print("\n" + "="*80)
    print("ALL TRANSACTIONS THIS MONTH:")
    print("="*80)
    
    for txn in transactions:
        txn_date = txn['date']
        if isinstance(txn_date, str):
            txn_date = datetime.strptime(txn_date, '%Y-%m-%d').date()
        
        # Only show this month's transactions
        if txn_date < month_start:
            continue
            
        amount = txn['amount']
        name = txn.get('name', 'Unknown')[:40]
        category = txn.get('category') or []
        cat_str = ' > '.join(category) if category else 'No category'
        
        # Check if excluded
        excluded = False
        exclude_reason = ""
        
        if any(exc in cat for cat in category for exc in EXCLUDED_CATEGORIES):
            excluded = True
            exclude_reason = "EXCLUDED (category)"
        elif txn.get('transaction_type') in EXCLUDED_TRANSACTION_TYPES:
            excluded = True
            exclude_reason = "EXCLUDED (txn type)"
        elif amount <= 0:
            excluded = True
            exclude_reason = "EXCLUDED (income/refund)"
        
        status = exclude_reason if excluded else "COUNTED"
        print(f"{txn_date} | ${amount:>8.2f} | {status:<25} | {cat_str:<30} | {name}")
        
        if not excluded:
            if txn_date == today:
                day_total += amount
            if txn_date >= week_start:
                week_total += amount
            if txn_date >= month_start:
                month_total += amount
    
    print("="*80)
    print(f"TOTALS: Day=${day_total:.2f}, Week=${week_total:.2f}, Month=${month_total:.2f}")
    print("="*80 + "\n")
    
    return {
        'day': day_total,
        'week': week_total,
        'month': month_total
    }


def format_amount(amount):
    if amount >= 1000:
        return f"${amount:,.0f}"
    elif amount >= 100:
        return f"${amount:.0f}"
    else:
        return f"${amount:.0f}"


def download_font(url, path):
    if not path.exists():
        print(f"Downloading font to {path}...")
        try:
            response = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
            print(f"Successfully downloaded {path.name}")
            return True
        except Exception as e:
            print(f"Could not download font: {e}")
            return False
    return True


def generate_image(spending, output_path='display.png'):
    font_dir = Path(__file__).parent / 'fonts'
    font_dir.mkdir(exist_ok=True)
    
    font_path = font_dir / 'CormorantGaramond-Regular.ttf'
    font_medium_path = font_dir / 'CormorantGaramond-Medium.ttf'
    font_semibold_path = font_dir / 'CormorantGaramond-SemiBold.ttf'
    
    base_url = "https://raw.githubusercontent.com/google/fonts/main/ofl/cormorantgaramond"
    download_font(f"{base_url}/CormorantGaramond-Regular.ttf", font_path)
    download_font(f"{base_url}/CormorantGaramond-Medium.ttf", font_medium_path)
    download_font(f"{base_url}/CormorantGaramond-SemiBold.ttf", font_semibold_path)
    
    LABEL_SIZE = 36
    SMALL_SIZE = 80
    MEDIUM_SIZE = 115
    LARGE_SIZE = 200
    
    font_label = None
    font_small = None
    font_medium = None
    font_large = None
    
    try:
        if font_path.exists():
            font_label = ImageFont.truetype(str(font_path), LABEL_SIZE)
            font_small = ImageFont.truetype(str(font_path), SMALL_SIZE)
        if font_medium_path.exists():
            font_medium = ImageFont.truetype(str(font_medium_path), MEDIUM_SIZE)
        if font_semibold_path.exists():
            font_large = ImageFont.truetype(str(font_semibold_path), LARGE_SIZE)
        print("Loaded Cormorant Garamond fonts")
    except Exception as e:
        print(f"Cormorant loading error: {e}")
    
    if font_label is None:
        try:
            serif_paths = [
                '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
                '/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
            ]
            for font_name in serif_paths:
                if Path(font_name).exists():
                    print(f"Using system font: {font_name}")
                    font_label = ImageFont.truetype(font_name, LABEL_SIZE)
                    font_small = ImageFont.truetype(font_name, SMALL_SIZE)
                    font_medium = ImageFont.truetype(font_name, MEDIUM_SIZE)
                    font_large = ImageFont.truetype(font_name, LARGE_SIZE)
                    break
        except Exception as e:
            print(f"System font loading failed: {e}")
    
    if font_label is None:
        print("WARNING: Using default font!")
        font_label = ImageFont.load_default()
        font_small = font_label
        font_medium = font_label
        font_large = font_label
    
    if font_small is None:
        font_small = font_label
    if font_medium is None:
        font_medium = font_small
    if font_large is None:
        font_large = font_medium
    
    img = Image.new('L', (WIDTH, HEIGHT), color=232)
    draw = ImageDraw.Draw(img)
    
    LABEL_COLOR = 150
    SMALL_COLOR = 100
    MEDIUM_COLOR = 60
    LARGE_COLOR = 0
    
    center_x = WIDTH // 2
    start_y = 340
    
    day_label = "DAY"
    day_amount = format_amount(spending['day'])
    
    bbox = draw.textbbox((0, 0), day_label, font=font_label)
    label_width = bbox[2] - bbox[0]
    draw.text((center_x - label_width // 2, start_y), day_label, font=font_label, fill=LABEL_COLOR)
    
    bbox = draw.textbbox((0, 0), day_amount, font=font_small)
    amount_width = bbox[2] - bbox[0]
    draw.text((center_x - amount_width // 2, start_y + 45), day_amount, font=font_small, fill=SMALL_COLOR)
    
    week_y = start_y + 170
    week_label = "WEEK"
    week_amount = format_amount(spending['week'])
    
    bbox = draw.textbbox((0, 0), week_label, font=font_label)
    label_width = bbox[2] - bbox[0]
    draw.text((center_x - label_width // 2, week_y), week_label, font=font_label, fill=LABEL_COLOR)
    
    bbox = draw.textbbox((0, 0), week_amount, font=font_medium)
    amount_width = bbox[2] - bbox[0]
    draw.text((center_x - amount_width // 2, week_y + 45), week_amount, font=font_medium, fill=MEDIUM_COLOR)
    
    month_y = start_y + 380
    month_label = "MONTH"
    month_amount = format_amount(spending['month'])
    
    bbox = draw.textbbox((0, 0), month_label, font=font_label)
    label_width = bbox[2] - bbox[0]
    draw.text((center_x - label_width // 2, month_y), month_label, font=font_label, fill=LABEL_COLOR)
    
    bbox = draw.textbbox((0, 0), month_amount, font=font_large)
    amount_width = bbox[2] - bbox[0]
    draw.text((center_x - amount_width // 2, month_y + 50), month_amount, font=font_large, fill=LARGE_COLOR)
    
    char_path = Path(__file__).parent / 'assets' / 'character.png'
    if char_path.exists():
        try:
            char_img = Image.open(char_path).convert('RGBA')
            char_height = 350
            aspect = char_img.width / char_img.height
            char_width = int(char_height * aspect)
            char_img = char_img.resize((char_width, char_height), Image.Resampling.LANCZOS)
            
            char_gray = char_img.convert('L')
            char_alpha = char_img.split()[3]
            char_alpha = char_alpha.point(lambda x: int(x * 0.25))
            
            char_x = (WIDTH - char_width) // 2
            char_y = HEIGHT - char_height + 32
            
            temp = Image.new('RGBA', (WIDTH, HEIGHT), (232, 232, 232, 255))
            char_rgba = Image.merge('RGBA', (char_gray, char_gray, char_gray, char_alpha))
            temp.paste(char_rgba, (char_x, char_y), char_rgba)
            
            img = Image.alpha_composite(
                Image.merge('RGBA', (img, img, img, Image.new('L', img.size, 255))),
                temp
            ).convert('L')
            
            draw = ImageDraw.Draw(img)
            
            bbox = draw.textbbox((0, 0), day_label, font=font_label)
            label_width = bbox[2] - bbox[0]
            draw.text((center_x - label_width // 2, start_y), day_label, font=font_label, fill=LABEL_COLOR)
            
            bbox = draw.textbbox((0, 0), day_amount, font=font_small)
            amount_width = bbox[2] - bbox[0]
            draw.text((center_x - amount_width // 2, start_y + 45), day_amount, font=font_small, fill=SMALL_COLOR)
            
            bbox = draw.textbbox((0, 0), week_label, font=font_label)
            label_width = bbox[2] - bbox[0]
            draw.text((center_x - label_width // 2, week_y), week_label, font=font_label, fill=LABEL_COLOR)
            
            bbox = draw.textbbox((0, 0), week_amount, font=font_medium)
            amount_width = bbox[2] - bbox[0]
            draw.text((center_x - amount_width // 2, week_y + 45), week_amount, font=font_medium, fill=MEDIUM_COLOR)
            
            bbox = draw.textbbox((0, 0), month_label, font=font_label)
            label_width = bbox[2] - bbox[0]
            draw.text((center_x - label_width // 2, month_y), month_label, font=font_label, fill=LABEL_COLOR)
            
            bbox = draw.textbbox((0, 0), month_amount, font=font_large)
            amount_width = bbox[2] - bbox[0]
            draw.text((center_x - amount_width // 2, month_y + 50), month_amount, font=font_large, fill=LARGE_COLOR)
            
        except Exception as e:
            print(f"Could not load character image: {e}")
    
    img.save(output_path, 'PNG')
    print(f"Generated {output_path}")
    return output_path


def main():
    required_vars = ['PLAID_CLIENT_ID', 'PLAID_SECRET', 'PLAID_ACCESS_TOKEN']
    missing = [v for v in required_vars if not os.getenv(v)]
    
    if missing or not PLAID_AVAILABLE:
        if not PLAID_AVAILABLE:
            print("Plaid library not installed.")
        else:
            print(f"Missing environment variables: {', '.join(missing)}")
        print("Generating demo image with sample data...")
        spending = {'day': 42, 'week': 412, 'month': 2847}
    else:
        client = get_plaid_client()
        access_token = os.getenv('PLAID_ACCESS_TOKEN')
        
        print("Fetching transactions from Plaid...")
        transactions = fetch_transactions(client, access_token)
        print(f"Found {len(transactions)} transactions")
        
        spending = calculate_spending(transactions)
    
    output_path = Path(__file__).parent / 'display.png'
    generate_image(spending, output_path)


if __name__ == '__main__':
    main()
