#!/usr/bin/env python3
"""
Budget Display Generator for Kindle
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont, ImageOps
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
TIMEZONE = ZoneInfo('America/Los_Angeles')

# Irvine, CA coordinates
IRVINE_LAT = 33.6846
IRVINE_LON = -117.8265

EXCLUDED_CATEGORIES = [
    'Transfer', 'Deposit', 'Payment', 
    'Bank Fees', 'Interest', 'Tax'
]

EXCLUDED_TRANSACTION_TYPES = []

# Weather code to icon mapping
# Icons are white-on-transparent, will be inverted to black
WEATHER_ICONS = {
    # Clear
    (0, True): 'sunny.png',
    (0, False): 'clear-night.png',
    # Mainly clear / Partly cloudy
    (1, True): 'partly-cloudy.png',
    (1, False): 'partly-cloudy-night.png',
    (2, True): 'partly-cloudy.png',
    (2, False): 'partly-cloudy-night.png',
    # Overcast
    (3, True): 'cloudy.png',
    (3, False): 'cloudy.png',
    # Fog
    (45, True): 'humidity.png',
    (45, False): 'humidity.png',
    (48, True): 'humidity.png',
    (48, False): 'humidity.png',
    # Drizzle
    (51, True): 'rain.png',
    (51, False): 'rain.png',
    (53, True): 'rain.png',
    (53, False): 'rain.png',
    (55, True): 'rain.png',
    (55, False): 'rain.png',
    # Rain
    (61, True): 'rain.png',
    (61, False): 'rain.png',
    (63, True): 'rain.png',
    (63, False): 'rain.png',
    # Heavy rain
    (65, True): 'heavy_rain.png',
    (65, False): 'heavy_rain.png',
    (80, True): 'heavy_rain.png',
    (80, False): 'heavy_rain.png',
    (81, True): 'heavy_rain.png',
    (81, False): 'heavy_rain.png',
    (82, True): 'heavy_rain.png',
    (82, False): 'heavy_rain.png',
    # Snow
    (71, True): 'snow.png',
    (71, False): 'snow.png',
    (73, True): 'snow.png',
    (73, False): 'snow.png',
    (75, True): 'snow.png',
    (75, False): 'snow.png',
    (77, True): 'snow.png',
    (77, False): 'snow.png',
    (85, True): 'snow.png',
    (85, False): 'snow.png',
    (86, True): 'snow.png',
    (86, False): 'snow.png',
    # Thunderstorm
    (95, True): 'severe_thunderstorm.png',
    (95, False): 'severe_thunderstorm.png',
    (96, True): 'severe_thunderstorm.png',
    (96, False): 'severe_thunderstorm.png',
    (99, True): 'severe_thunderstorm.png',
    (99, False): 'severe_thunderstorm.png',
}


def get_weather():
    """Fetch current weather from Open-Meteo (free, no API key)"""
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={IRVINE_LAT}&longitude={IRVINE_LON}"
            f"&current=temperature_2m,weather_code,is_day"
            f"&temperature_unit=fahrenheit"
            f"&timezone=America/Los_Angeles"
        )
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        current = data['current']
        return {
            'temp': round(current['temperature_2m']),
            'code': current['weather_code'],
            'is_day': bool(current['is_day'])
        }
    except Exception as e:
        print(f"Could not fetch weather: {e}")
        return None


def get_weather_icon(weather_code, is_day, assets_dir):
    """Get the appropriate weather icon"""
    icon_name = WEATHER_ICONS.get((weather_code, is_day))
    
    # Fallback for unknown codes
    if not icon_name:
        icon_name = 'sunny.png' if is_day else 'clear-night.png'
    
    icon_path = assets_dir / 'weather' / icon_name
    if icon_path.exists():
        return icon_path
    return None


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
    
    for txn in transactions:
        txn_date = txn['date']
        if isinstance(txn_date, str):
            txn_date = datetime.strptime(txn_date, '%Y-%m-%d').date()
        
        if txn_date < month_start:
            continue
            
        amount = txn['amount']
        category = txn.get('category') or []
        
        excluded = False
        
        if any(exc in cat for cat in category for exc in EXCLUDED_CATEGORIES):
            excluded = True
        elif txn.get('transaction_type') in EXCLUDED_TRANSACTION_TYPES:
            excluded = True
        elif amount <= 0:
            excluded = True
        
        if not excluded:
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
    if amount >= 1000:
        return f"${amount:,.0f}"
    else:
        return f"${amount:.0f}"


def download_font(url, path):
    if not path.exists():
        try:
            response = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
            return True
        except Exception as e:
            print(f"Could not download font: {e}")
            return False
    return True


def generate_image(spending, weather=None, output_path='display.png'):
    script_dir = Path(__file__).parent
    font_dir = script_dir / 'fonts'
    font_dir.mkdir(exist_ok=True)
    assets_dir = script_dir / 'assets'
    
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
    WEATHER_SIZE = 42
    
    font_label = None
    font_small = None
    font_medium = None
    font_large = None
    font_weather = None
    
    try:
        if font_path.exists():
            font_label = ImageFont.truetype(str(font_path), LABEL_SIZE)
            font_small = ImageFont.truetype(str(font_path), SMALL_SIZE)
            font_weather = ImageFont.truetype(str(font_path), WEATHER_SIZE)
        if font_medium_path.exists():
            font_medium = ImageFont.truetype(str(font_medium_path), MEDIUM_SIZE)
        if font_semibold_path.exists():
            font_large = ImageFont.truetype(str(font_semibold_path), LARGE_SIZE)
    except Exception as e:
        print(f"Font loading error: {e}")
    
    if font_label is None:
        try:
            serif_paths = [
                '/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf',
                '/usr/share/fonts/truetype/liberation2/LiberationSerif-Regular.ttf',
                '/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf',
            ]
            for font_name in serif_paths:
                if Path(font_name).exists():
                    font_label = ImageFont.truetype(font_name, LABEL_SIZE)
                    font_small = ImageFont.truetype(font_name, SMALL_SIZE)
                    font_medium = ImageFont.truetype(font_name, MEDIUM_SIZE)
                    font_large = ImageFont.truetype(font_name, LARGE_SIZE)
                    font_weather = ImageFont.truetype(font_name, WEATHER_SIZE)
                    break
        except Exception as e:
            print(f"System font loading failed: {e}")
    
    if font_label is None:
        font_label = ImageFont.load_default()
        font_small = font_label
        font_medium = font_label
        font_large = font_label
        font_weather = font_label
    
    if font_small is None:
        font_small = font_label
    if font_medium is None:
        font_medium = font_small
    if font_large is None:
        font_large = font_medium
    if font_weather is None:
        font_weather = font_label
    
    img = Image.new('L', (WIDTH, HEIGHT), color=232)
    draw = ImageDraw.Draw(img)
    
    LABEL_COLOR = 150
    SMALL_COLOR = 100
    MEDIUM_COLOR = 60
    LARGE_COLOR = 0
    
    # Draw weather in top right
    icon_x = 0
    icon_size = 48
    if weather:
        temp_str = f"{weather['temp']}°"
        bbox = draw.textbbox((0, 0), temp_str, font=font_weather)
        temp_width = bbox[2] - bbox[0]
        
        padding = 40
        temp_x = WIDTH - padding - temp_width
        icon_x = temp_x - icon_size - 12
        icon_y = 38
        
        # Load and display weather icon
        icon_path = get_weather_icon(weather['code'], weather['is_day'], assets_dir)
        if icon_path and icon_path.exists():
            icon = Image.open(icon_path).convert('RGBA')
            # Invert RGB (white->black) keeping alpha
            r, g, b, a = icon.split()
            r = ImageOps.invert(r)
            g = ImageOps.invert(g)
            b = ImageOps.invert(b)
            icon = Image.merge('RGBA', (r, g, b, a))
            icon = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            
            img_rgba = Image.merge('RGBA', (img, img, img, Image.new('L', img.size, 255)))
            img_rgba.paste(icon, (icon_x, icon_y), icon)
            img = img_rgba.convert('L')
            draw = ImageDraw.Draw(img)
        
        draw.text((temp_x, 40), temp_str, font=font_weather, fill=100)
    
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
    
    char_path = assets_dir / 'character.png'
    if char_path.exists():
        try:
            char_img = Image.open(char_path).convert('RGBA')
            char_height = 350
            aspect = char_img.width / char_img.height
            char_width = int(char_height * aspect)
            char_img = char_img.resize((char_width, char_height), Image.Resampling.LANCZOS)
            
            char_gray = char_img.convert('L')
            char_alpha = char_img.split()[3]
            # 70% opacity
            char_alpha = char_alpha.point(lambda x: int(x * 0.70))
            
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
            
            # Redraw weather
            if weather:
                icon_path = get_weather_icon(weather['code'], weather['is_day'], assets_dir)
                if icon_path and icon_path.exists():
                    icon = Image.open(icon_path).convert('RGBA')
                    r, g, b, a = icon.split()
                    r = ImageOps.invert(r)
                    g = ImageOps.invert(g)
                    b = ImageOps.invert(b)
                    icon = Image.merge('RGBA', (r, g, b, a))
                    icon = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
                    
                    img_rgba = Image.merge('RGBA', (img, img, img, Image.new('L', img.size, 255)))
                    img_rgba.paste(icon, (icon_x, icon_y), icon)
                    img = img_rgba.convert('L')
                    draw = ImageDraw.Draw(img)
                
                draw.text((temp_x, 40), temp_str, font=font_weather, fill=100)
            
            # Redraw budget text
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
    # Fetch weather
    weather = get_weather()
    if weather:
        print(f"Weather: {weather['temp']}F, code {weather['code']}")
    
    required_vars = ['PLAID_CLIENT_ID', 'PLAID_SECRET', 'PLAID_ACCESS_TOKEN']
    missing = [v for v in required_vars if not os.getenv(v)]
    
    if missing or not PLAID_AVAILABLE:
        print("Generating demo image with sample data...")
        spending = {'day': 42, 'week': 412, 'month': 2847}
    else:
        client = get_plaid_client()
        access_token = os.getenv('PLAID_ACCESS_TOKEN')
        
        transactions = fetch_transactions(client, access_token)
        spending = calculate_spending(transactions)
        print(f"Day: ${spending['day']:.0f}, Week: ${spending['week']:.0f}, Month: ${spending['month']:.0f}")
    
    output_path = Path(__file__).parent / 'display.png'
    generate_image(spending, weather, output_path)


if __name__ == '__main__':
    main()
