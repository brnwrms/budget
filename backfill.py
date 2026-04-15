#!/usr/bin/env python3
"""
One-time backfill of credit card transactions from April statement.
Run once, then remove from workflow and repo.
"""

import json
from datetime import datetime
from pathlib import Path

TRANSACTIONS_FILE = 'transactions.json'

# April CC transactions from statement (transaction date used)
# Payment excluded, only purchases
BACKFILL = [
    {'date': '2026-03-30', 'amount': 20.00, 'merchant': 'PANGRAM AI DETECTION', 'source': 'cc_backfill'},
    {'date': '2026-03-31', 'amount': 92.43, 'merchant': 'TST* POSTINO - PARK PL', 'source': 'cc_backfill'},
    {'date': '2026-03-31', 'amount': 9.99, 'merchant': 'PAYPAL *CRUNCHYROLL', 'source': 'cc_backfill'},
    {'date': '2026-04-01', 'amount': 5.00, 'merchant': 'PAYPAL *PATREON MEMBE', 'source': 'cc_backfill'},
    {'date': '2026-04-01', 'amount': 8.82, 'merchant': 'POSITIV ENERGY', 'source': 'cc_backfill'},
    {'date': '2026-04-01', 'amount': 50.58, 'merchant': 'POSITIV ENERGY', 'source': 'cc_backfill'},
    {'date': '2026-04-02', 'amount': 22.00, 'merchant': 'IN-N-OUT REDONDO BEACH', 'source': 'cc_backfill'},
    {'date': '2026-04-02', 'amount': 35.88, 'merchant': 'PAYPAL *PROTON', 'source': 'cc_backfill'},
    {'date': '2026-04-02', 'amount': 5.00, 'merchant': 'PAYPAL *PATREON MEMBE', 'source': 'cc_backfill'},
    {'date': '2026-04-03', 'amount': 31.57, 'merchant': 'TOKYO CENTRAL COSTA MESA', 'source': 'cc_backfill'},
    {'date': '2026-04-03', 'amount': 25.00, 'merchant': 'UP IN SMOKE SMOKE SHOP', 'source': 'cc_backfill'},
    {'date': '2026-04-03', 'amount': 53.17, 'merchant': 'PAYPAL *SPOTHERO', 'source': 'cc_backfill'},
    {'date': '2026-04-04', 'amount': 112.02, 'merchant': 'WAL-MART #5644', 'source': 'cc_backfill'},
    {'date': '2026-04-04', 'amount': 15.00, 'merchant': 'UNIFIED VALET PARKING', 'source': 'cc_backfill'},
    {'date': '2026-04-04', 'amount': 26.93, 'merchant': 'AMAZON MARK*', 'source': 'cc_backfill'},
    {'date': '2026-04-05', 'amount': 32.29, 'merchant': 'AMAZON RETA*', 'source': 'cc_backfill'},
    {'date': '2026-04-04', 'amount': 3.78, 'merchant': 'ALBERTSONS #0597', 'source': 'cc_backfill'},
    {'date': '2026-04-06', 'amount': 54.00, 'merchant': 'TICKETS', 'source': 'cc_backfill'},
    {'date': '2026-04-06', 'amount': 29.70, 'merchant': 'ARMSTRONG 765 CARLSBAD', 'source': 'cc_backfill'},
    {'date': '2026-04-07', 'amount': 29.25, 'merchant': 'AMAZON MARK*', 'source': 'cc_backfill'},
    {'date': '2026-04-07', 'amount': 4.09, 'merchant': 'SQ *CATALLAC, INC', 'source': 'cc_backfill'},
    {'date': '2026-04-07', 'amount': 10.76, 'merchant': 'AMAZON MARK*', 'source': 'cc_backfill'},
    {'date': '2026-04-08', 'amount': 192.00, 'merchant': 'SQSP* WEBSIT', 'source': 'cc_backfill'},
    {'date': '2026-04-07', 'amount': 22.81, 'merchant': 'ALBERTSONS #0597', 'source': 'cc_backfill'},
    {'date': '2026-04-10', 'amount': 33.29, 'merchant': 'SHELL OIL', 'source': 'cc_backfill'},
    {'date': '2026-04-10', 'amount': 6.18, 'merchant': '99 RANCH MARKET #121', 'source': 'cc_backfill'},
    {'date': '2026-04-10', 'amount': 27.37, 'merchant': 'GROCERY OUTLET', 'source': 'cc_backfill'},
    {'date': '2026-04-11', 'amount': 24.24, 'merchant': 'SQ *SOUTH LA CAFE', 'source': 'cc_backfill'},
    {'date': '2026-04-11', 'amount': 36.00, 'merchant': 'AT *NATHISTMUSEUMLAC', 'source': 'cc_backfill'},
    {'date': '2026-04-11', 'amount': 3.69, 'merchant': 'ARCO 907050', 'source': 'cc_backfill'},
    {'date': '2026-04-11', 'amount': 85.51, 'merchant': 'WAL-MART #5644', 'source': 'cc_backfill'},
    {'date': '2026-04-11', 'amount': 20.00, 'merchant': 'MASJID UMAR IBNALKHATT', 'source': 'cc_backfill'},
    {'date': '2026-04-11', 'amount': 130.00, 'merchant': 'ONOTRIA WINE COUNTRY', 'source': 'cc_backfill'},
    {'date': '2026-04-12', 'amount': 8.07, 'merchant': 'AMAZON PRIME*', 'source': 'cc_backfill'},
    {'date': '2026-04-12', 'amount': 49.55, 'merchant': 'AMAZON MARK*', 'source': 'cc_backfill'},
]


def main():
    path = Path(TRANSACTIONS_FILE)

    if path.exists():
        data = json.loads(path.read_text())
    else:
        data = {'last_fetch': None, 'transactions': []}

    # Check what's already backfilled to avoid duplicates
    existing_backfill = {
        (t['date'], t['amount'], t['merchant'])
        for t in data['transactions']
        if t.get('source') == 'cc_backfill'
    }

    added = 0
    for txn in BACKFILL:
        key = (txn['date'], txn['amount'], txn['merchant'])
        if key not in existing_backfill:
            # Generate a stable email_id for dedup
            txn['email_id'] = f"backfill-{txn['date']}-{txn['amount']}-{hash(txn['merchant']) & 0xFFFFFF:06x}"
            txn['alert_type'] = 'manual_backfill'
            txn['time'] = None
            data['transactions'].append(txn)
            existing_backfill.add(key)
            added += 1
            print(f"  Added: {txn['date']} ${txn['amount']:.2f} {txn['merchant']}")

    data['transactions'].sort(key=lambda t: t['date'], reverse=True)
    path.write_text(json.dumps(data, indent=2))
    print(f"\nBackfilled {added} transactions ({len(data['transactions'])} total)")


if __name__ == '__main__':
    main()
