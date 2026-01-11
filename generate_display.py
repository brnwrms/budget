#!/usr/bin/env python3
"""
Budget Display Generator for Kindle
Fetches transactions from Plaid and generates a grayscale PNG for e-ink display.
"""

import os
import json
from datetime import datetime, timedelta
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import requests

# Plaid imports are optional for demo mode
try:
    import plaid
    from plaid.api import plaid_api
    from plaid.model.transactions_get_request import TransactionsGetRequest
    from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions
    PLAID_AVAILABLE = True
except ImportError:
    PLAID_AVAILABLE = False

# Kindle Paperwhite 7th gen resolution
WIDTH = 1072
HEIGHT = 1448

# E-ink paper gray background
BG_COLOR = (232, 232, 232)

# Categories to exclude (transfers, income, etc.)
EXCLUDED_CATEGORIES = [
    'Transfer', 'Credit Card', 'Deposit', 'Payment', 
    'Bank Fees', 'Interest', 'Tax'
]

EXCLUDED_TRANSACTION_TYPES = ['special', 'unresolved']


def get_plaid_client():
    """Initialize Plaid client from environment variables."""
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
    """Fetch transactions from Plaid for the specified number of days."""
    end_date = datetime.now().date()
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
    """Calculate spending totals for day, week, and month."""
    today = datetime.now().date()
    
    # Week starts on Monday
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)
    
    # Month start
    month_start = today.replace(day=1)
    
    day_total = 0.0
    week_total = 0.0
    month_total = 0.0
    
    for txn in transactions:
        # Skip excluded categories
        category = txn.get('category') or []
        if any(exc in cat for cat in category for exc in EXCLUDED_CATEGORIES):
            continue
        
        # Skip non-spending transaction types
        if txn.get('transaction_type') in EXCLUDED_TRANSACTION_TYPES:
            continue
        
        # Only count money going out (positive amounts in Plaid = money spent)
        amount = txn['amount']
        if amount <= 0:
            continue
        
        txn_date = txn['date']
        if isinstance(txn_date, str):
            txn_date = datetime.strptime(txn_date, '%Y-%m-%d').date()
        
        # Add to appropriate totals
        if txn_date == today:
            day_total += amount
        
        if txn_date >= week_start:
            week_total += amount
        
        if txn_date >= month_start:
            month_total += amount
    
    return {
        'day': day_total,
        'week': week_total,
        'month': month_total
    }


def format_amount(amount):
    """Format amount as currency string."""
    if amount >= 1000:
        return f"${amount:,.0f}"
    elif amount >= 100:
        return f"${amount:.0f}"
    else:
        return f"${amount:.0f}"


def download_font(url, path):
    """Download a font file if it doesn't exist."""
    if not path.exists():
        print(f"Downloading font to {path}...")
        try:
            response = requests.get(url, timeout=30)
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
    """Generate the Kindle display image."""
    
    # Font setup - using EB Garamond from Google Fonts CDN
    font_dir = Path(__file__).parent / 'fonts'
    font_dir.mkdir(exist_ok=True)
    
    font_path = font_dir / 'EBGaramond-Regular.ttf'
    font_medium_path = font_dir / 'EBGaramond-Medium.ttf'
    font_semibold_path = font_dir / 'EBGaramond-SemiBold.ttf'
    
    # More reliable Google Fonts CDN URLs
    font_urls = {
        'regular': "https://fonts.gstatic.com/s/ebgaramond/v27/SlGDmQSNjdsmc35JDF1K5E55YMjF_7DPuGi-6_RkC49_S6w.ttf",
        'medium': "https://fonts.gstatic.com/s/ebgaramond/v27/SlGDmQSNjdsmc35JDF1K5E55YMjF_7DPuGi-2fRkC49_S6w.ttf",
        'semibold': "https://fonts.gstatic.com/s/ebgaramond/v27/SlGDmQSNjdsmc35JDF1K5E55YMjF_7DPuGi-NfNkC49_S6w.ttf",
    }
    
    # Try downloading fonts
    download_font(font_urls['regular'], font_path)
    download_font(font_urls['medium'], font_medium_path)
    download_font(font_urls['semibold'], font_semibold_path)
    
    # Load fonts at different sizes - BIGGER SIZES
    font_label = None
    font_small = None
    font_medium = None
    font_large = None
    
    try:
        if font_path.exists():
            font_label = ImageFont.truetype(str(font_path), 48)
            font_small = ImageFont.truetype(str(font_path), 120)
        if font_medium_path.exists():
            font_medium = ImageFont.truetype(str(font_medium_path), 160)
        if font_semibold_path.exists():
            font_large = ImageFont.truetype(str(font_semibold_path), 280)
    except Exception as e:
        print(f"Font loading error: {e}")
    
    # Fallback to DejaVu Sans (pre-installed on Ubuntu)
    if font_label is None:
        try:
            # Try system fonts on Ubuntu
            for font_name in ['/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', 
                              '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf']:
                if Path(font_name).exists():
                    print(f"Using system font: {font_name}")
                    font_label = ImageFont.truetype(font_name, 48)
                    font_small = ImageFont.truetype(font_name, 120)
                    font_medium = ImageFont.truetype(font_name, 160)
                    font_large = ImageFont.truetype(font_name, 280)
                    break
        except Exception as e:
            print(f"System font loading failed: {e}")
    
    # Final fallback - use default but warn
    if font_label is None:
        print("WARNING: Using default font - text will be small!")
        font_label = ImageFont.load_default()
        font_small = font_label
        font_medium = font_label
        font_large = font_label
    
    # Fill in any missing fonts
    if font_small is None:
        font_small = font_label
    if font_medium is None:
        font_medium = font_small
    if font_large is None:
        font_large = font_medium
    
    # Create base image
    img = Image.new('L', (WIDTH, HEIGHT), color=232)  # Grayscale, e-ink gray
    draw = ImageDraw.Draw(img)
    
    # Colors (grayscale values)
    LABEL_COLOR = 140  # Light gray for labels
    SMALL_COLOR = 80   # Day amount
    MEDIUM_COLOR = 50  # Week amount
    LARGE_COLOR = 0    # Month amount (black)
    
    # Layout - centered, vertical stack
    center_x = WIDTH // 2
    
    # Calculate vertical positions
    start_y = 280
    
    # Day
    day_label = "DAY"
    day_amount = format_amount(spending['day'])
    
    bbox = draw.textbbox((0, 0), day_label, font=font_label)
    label_width = bbox[2] - bbox[0]
    draw.text((center_x - label_width // 2, start_y), day_label, font=font_label, fill=LABEL_COLOR)
    
    bbox = draw.textbbox((0, 0), day_amount, font=font_small)
    amount_width = bbox[2] - bbox[0]
    draw.text((center_x - amount_width // 2, start_y + 55), day_amount, font=font_small, fill=SMALL_COLOR)
    
    # Week
    week_y = start_y + 220
    week_label = "WEEK"
    week_amount = format_amount(spending['week'])
    
    bbox = draw.textbbox((0, 0), week_label, font=font_label)
    label_width = bbox[2] - bbox[0]
    draw.text((center_x - label_width // 2, week_y), week_label, font=font_label, fill=LABEL_COLOR)
    
    bbox = draw.textbbox((0, 0), week_amount, font=font_medium)
    amount_width = bbox[2] - bbox[0]
    draw.text((center_x - amount_width // 2, week_y + 55), week_amount, font=font_medium, fill=MEDIUM_COLOR)
    
    # Month
    month_y = start_y + 480
    month_label = "MONTH"
    month_amount = format_amount(spending['month'])
    
    bbox = draw.textbbox((0, 0), month_label, font=font_label)
    label_width = bbox[2] - bbox[0]
    draw.text((center_x - label_width // 2, month_y), month_label, font=font_label, fill=LABEL_COLOR)
    
    bbox = draw.textbbox((0, 0), month_amount, font=font_large)
    amount_width = bbox[2] - bbox[0]
    draw.text((center_x - amount_width // 2, month_y + 60), month_amount, font=font_large, fill=LARGE_COLOR)
    
    # Add character image at bottom center
    char_path = Path(__file__).parent / 'assets' / 'character.png'
    if char_path.exists():
        try:
            char_img = Image.open(char_path).convert('RGBA')
            
            # Resize character (scale to ~400px height)
            char_height = 400
            aspect = char_img.width / char_img.height
            char_width = int(char_height * aspect)
            char_img = char_img.resize((char_width, char_height), Image.Resampling.LANCZOS)
            
            # Convert to grayscale and apply 25% opacity
            char_gray = char_img.convert('L')
            char_alpha = char_img.split()[3]  # Get alpha channel
            
            # Reduce alpha to 25%
            char_alpha = char_alpha.point(lambda x: int(x * 0.25))
            
            # Position at bottom center, flush with bottom edge
            char_x = (WIDTH - char_width) // 2
            char_y = HEIGHT - char_height + 40
            
            # Create a temporary RGBA image to composite
            temp = Image.new('RGBA', (WIDTH, HEIGHT), (232, 232, 232, 255))
            char_rgba = Image.merge('RGBA', (char_gray, char_gray, char_gray, char_alpha))
            temp.paste(char_rgba, (char_x, char_y), char_rgba)
            
            # Composite onto main image
            img = Image.alpha_composite(
                Image.merge('RGBA', (img, img, img, Image.new('L', img.size, 255))),
                temp
            ).convert('L')
            
            # Redraw text on top (recreate draw object)
            draw = ImageDraw.Draw(img)
            
            # Redraw all text
            bbox = draw.textbbox((0, 0), day_label, font=font_label)
            label_width = bbox[2] - bbox[0]
            draw.text((center_x - label_width // 2, start_y), day_label, font=font_label, fill=LABEL_COLOR)
            
            bbox = draw.textbbox((0, 0), day_amount, font=font_small)
            amount_width = bbox[2] - bbox[0]
            draw.text((center_x - amount_width // 2, start_y + 55), day_amount, font=font_small, fill=SMALL_COLOR)
            
            bbox = draw.textbbox((0, 0), week_label, font=font_label)
            label_width = bbox[2] - bbox[0]
            draw.text((center_x - label_width // 2, week_y), week_label, font=font_label, fill=LABEL_COLOR)
            
            bbox = draw.textbbox((0, 0), week_amount, font=font_medium)
            amount_width = bbox[2] - bbox[0]
            draw.text((center_x - amount_width // 2, week_y + 55), week_amount, font=font_medium, fill=MEDIUM_COLOR)
            
            bbox = draw.textbbox((0, 0), month_label, font=font_label)
            label_width = bbox[2] - bbox[0]
            draw.text((center_x - label_width // 2, month_y), month_label, font=font_label, fill=LABEL_COLOR)
            
            bbox = draw.textbbox((0, 0), month_amount, font=font_large)
            amount_width = bbox[2] - bbox[0]
            draw.text((center_x - amount_width // 2, month_y + 60), month_amount, font=font_large, fill=LARGE_COLOR)
            
        except Exception as e:
            print(f"Could not load character image: {e}")
    
    # Save
    img.save(output_path, 'PNG')
    print(f"Generated {output_path}")
    return output_path


def main():
    """Main entry point."""
    # Check for required environment variables
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
        # Fetch real data
        client = get_plaid_client()
        access_token = os.getenv('PLAID_ACCESS_TOKEN')
        
        print("Fetching transactions from Plaid...")
        transactions = fetch_transactions(client, access_token)
        print(f"Found {len(transactions)} transactions")
        
        spending = calculate_spending(transactions)
        print(f"Spending: Day=${spending['day']:.2f}, Week=${spending['week']:.2f}, Month=${spending['month']:.2f}")
    
    # Generate image
    output_path = Path(__file__).parent / 'display.png'
    generate_image(spending, output_path)


if __name__ == '__main__':
    main()
