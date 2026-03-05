#!/usr/bin/env python3
"""
Gmail Transaction Fetcher for Budget Dashboard

Connects to a dedicated Gmail account via IMAP, parses SchoolsFirst FCU
alert emails, and maintains a local transactions.json file.

Required environment variables:
  GMAIL_ADDRESS       - e.g. sambudgetbot@gmail.com
  GMAIL_APP_PASSWORD  - 16-char app password from Google
"""

import email
import imaplib
import json
import os
import re
from datetime import datetime, timedelta
from email.header import decode_header
from pathlib import Path
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo('America/Los_Angeles')
TRANSACTIONS_FILE = 'transactions.json'

# SchoolsFirst alert sender
ALERT_SENDER = 'alerts@schoolsfirstfcu.org'

# ---------------------------------------------------------------------------
# Email parsing
# ---------------------------------------------------------------------------

# Debit/POS card transaction pattern
# "A Debit/POS Card transaction for Share xxxx43-70 in the amount of $10.76
#  at AMAZON.COM*BE9CN was made at 11:34 AM on 03/04/2026."
DEBIT_PATTERN = re.compile(
    r'(?:A\s+)?Debit/POS\s+Card\s+transaction\s+for\s+Share\s+\S+\s+'
    r'in\s+the\s+amount\s+of\s+\$([0-9,]+\.\d{2})\s+'
    r'at\s+(.+?)\s+was\s+made\s+at\s+'
    r'(\d{1,2}:\d{2}\s*[AP]M)\s+on\s+(\d{2}/\d{2}/\d{4})',
    re.IGNORECASE | re.DOTALL
)

# Automatic withdrawal pattern (estimated — update once we see a real one)
# "An Automatic Withdrawal ... in the amount of $XX.XX ... on MM/DD/YYYY"
AUTO_WITHDRAWAL_PATTERN = re.compile(
    r'Automatic\s+Withdrawal\s+.*?'
    r'in\s+the\s+amount\s+of\s+\$([0-9,]+\.\d{2})\s+'
    r'.*?on\s+(\d{2}/\d{2}/\d{4})',
    re.IGNORECASE | re.DOTALL
)

# Credit card transaction pattern (placeholder — update once we see the email)
CC_PATTERN = re.compile(
    r'credit\s+card\s+.*?transaction\s+.*?'
    r'\$([0-9,]+\.\d{2})\s+'
    r'.*?at\s+(.+?)\s+.*?on\s+(\d{2}/\d{2}/\d{4})',
    re.IGNORECASE | re.DOTALL
)


def get_email_text(msg):
    """Extract plain text body from email message."""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain':
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    return payload.decode(charset, errors='replace')
            elif content_type == 'text/html':
                # Fall back to HTML if no plain text
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or 'utf-8'
                    text = payload.decode(charset, errors='replace')
                    # Strip HTML tags for parsing
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = re.sub(r'\s+', ' ', text)
                    return text
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or 'utf-8'
            text = payload.decode(charset, errors='replace')
            if msg.get_content_type() == 'text/html':
                text = re.sub(r'<[^>]+>', ' ', text)
                text = re.sub(r'\s+', ' ', text)
            return text
    return ''


def parse_debit_transaction(body, subject):
    """Parse a Debit/POS Card transaction alert."""
    match = DEBIT_PATTERN.search(body)
    if not match:
        return None
    
    amount_str, merchant, time_str, date_str = match.groups()
    amount = float(amount_str.replace(',', ''))
    merchant = merchant.strip()
    
    # Parse date: MM/DD/YYYY
    try:
        txn_date = datetime.strptime(date_str, '%m/%d/%Y').date()
    except ValueError:
        return None
    
    return {
        'date': txn_date.isoformat(),
        'amount': amount,
        'merchant': merchant,
        'source': 'debit_card',
        'time': time_str.strip(),
    }


def parse_auto_withdrawal(body, subject):
    """Parse an Automatic Withdrawal alert."""
    match = AUTO_WITHDRAWAL_PATTERN.search(body)
    if not match:
        return None
    
    amount_str, date_str = match.groups()
    amount = float(amount_str.replace(',', ''))
    
    try:
        txn_date = datetime.strptime(date_str, '%m/%d/%Y').date()
    except ValueError:
        return None
    
    return {
        'date': txn_date.isoformat(),
        'amount': amount,
        'merchant': 'Automatic Withdrawal',
        'source': 'auto_withdrawal',
        'time': None,
    }


def parse_cc_transaction(body, subject):
    """Parse a credit card transaction alert. Placeholder — needs real sample."""
    match = CC_PATTERN.search(body)
    if not match:
        return None
    
    groups = match.groups()
    amount_str = groups[0]
    amount = float(amount_str.replace(',', ''))
    merchant = groups[1].strip() if len(groups) > 1 else 'Credit Card Purchase'
    date_str = groups[-1]
    
    try:
        txn_date = datetime.strptime(date_str, '%m/%d/%Y').date()
    except ValueError:
        return None
    
    return {
        'date': txn_date.isoformat(),
        'amount': amount,
        'merchant': merchant,
        'source': 'credit_card',
        'time': None,
    }


def parse_alert_email(msg):
    """Parse a SchoolsFirst alert email into a transaction dict."""
    subject = ''
    raw_subject = msg.get('Subject', '')
    decoded_parts = decode_header(raw_subject)
    for part, encoding in decoded_parts:
        if isinstance(part, bytes):
            subject += part.decode(encoding or 'utf-8', errors='replace')
        else:
            subject += part
    
    body = get_email_text(msg)
    
    subject_lower = subject.lower()
    
    # Try parsers in order of specificity
    if 'debit' in subject_lower or 'debit/pos' in body.lower():
        txn = parse_debit_transaction(body, subject)
        if txn:
            txn['alert_type'] = subject.strip()
            return txn
    
    if 'automatic withdrawal' in subject_lower:
        txn = parse_auto_withdrawal(body, subject)
        if txn:
            txn['alert_type'] = subject.strip()
            return txn
    
    if 'credit card' in subject_lower:
        txn = parse_cc_transaction(body, subject)
        if txn:
            txn['alert_type'] = subject.strip()
            return txn
    
    # Unknown alert type — log it
    print(f"  UNKNOWN ALERT TYPE: {subject}")
    print(f"  Body preview: {body[:200]}")
    return None


# ---------------------------------------------------------------------------
# Gmail IMAP connection
# ---------------------------------------------------------------------------

def connect_gmail(address, app_password):
    """Connect to Gmail via IMAP."""
    mail = imaplib.IMAP4_SSL('imap.gmail.com')
    mail.login(address, app_password)
    return mail


def fetch_alert_emails(mail, since_date=None, processed_ids=None):
    """Fetch SchoolsFirst alert emails from Gmail."""
    if processed_ids is None:
        processed_ids = set()
    
    mail.select('INBOX')
    
    # Build search criteria
    criteria = [f'FROM "{ALERT_SENDER}"']
    if since_date:
        # IMAP date format: DD-Mon-YYYY
        date_str = since_date.strftime('%d-%b-%Y')
        criteria.append(f'SINCE {date_str}')
    
    search_query = '(' + ' '.join(criteria) + ')'
    print(f"IMAP search: {search_query}")
    
    status, message_ids = mail.search(None, search_query)
    if status != 'OK':
        print(f"IMAP search failed: {status}")
        return []
    
    ids = message_ids[0].split()
    print(f"Found {len(ids)} alert emails")
    
    transactions = []
    
    for msg_id in ids:
        # Use message ID for deduplication
        status, msg_data = mail.fetch(msg_id, '(RFC822 BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])')
        if status != 'OK':
            continue
        
        # Extract Message-ID header for deduplication
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        message_id = msg.get('Message-ID', '').strip()
        
        if message_id in processed_ids:
            print(f"  Skipping already processed: {message_id}")
            continue
        
        txn = parse_alert_email(msg)
        if txn:
            txn['email_id'] = message_id
            transactions.append(txn)
            print(f"  Parsed: {txn['date']} ${txn['amount']:.2f} {txn['merchant']} [{txn['source']}]")
        else:
            print(f"  Could not parse email: {msg.get('Subject', 'no subject')}")
    
    return transactions


# ---------------------------------------------------------------------------
# Transaction storage
# ---------------------------------------------------------------------------

def load_transactions(path):
    """Load existing transactions from JSON file."""
    try:
        if path.exists():
            data = json.loads(path.read_text())
            return data
    except Exception as e:
        print(f"Error loading transactions: {e}")
    
    return {
        'last_fetch': None,
        'transactions': []
    }


def save_transactions(path, data):
    """Save transactions to JSON file."""
    data['last_fetch'] = datetime.now(TIMEZONE).isoformat()
    path.write_text(json.dumps(data, indent=2))
    print(f"Saved {len(data['transactions'])} transactions to {path}")


def merge_transactions(existing_data, new_transactions):
    """Merge new transactions, deduplicating by email_id."""
    existing_ids = {t.get('email_id') for t in existing_data['transactions'] if t.get('email_id')}
    
    added = 0
    for txn in new_transactions:
        if txn.get('email_id') not in existing_ids:
            existing_data['transactions'].append(txn)
            existing_ids.add(txn.get('email_id'))
            added += 1
    
    # Sort by date descending
    existing_data['transactions'].sort(key=lambda t: t['date'], reverse=True)
    
    print(f"Added {added} new transactions ({len(existing_data['transactions'])} total)")
    return existing_data


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    gmail_address = os.getenv('GMAIL_ADDRESS')
    gmail_password = os.getenv('GMAIL_APP_PASSWORD')
    
    if not gmail_address or not gmail_password:
        print("ERROR: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be set")
        print("Skipping Gmail fetch.")
        return
    
    script_dir = Path(__file__).parent
    txn_path = script_dir / TRANSACTIONS_FILE
    
    # Load existing transactions
    existing = load_transactions(txn_path)
    processed_ids = {t.get('email_id') for t in existing['transactions'] if t.get('email_id')}
    
    # Look back 35 days to catch any we might have missed
    since_date = datetime.now(TIMEZONE).date() - timedelta(days=35)
    
    print(f"Connecting to Gmail as {gmail_address}...")
    try:
        mail = connect_gmail(gmail_address, gmail_password)
        new_txns = fetch_alert_emails(mail, since_date=since_date, processed_ids=processed_ids)
        mail.logout()
    except Exception as e:
        print(f"Gmail error: {e}")
        return
    
    # Merge and save
    updated = merge_transactions(existing, new_txns)
    save_transactions(txn_path, updated)


if __name__ == '__main__':
    main()
