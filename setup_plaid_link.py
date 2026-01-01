#!/usr/bin/env python3
"""
One-time setup script to connect your bank account via Plaid Link.
Run this locally, connect your bank, then save the access token as a GitHub secret.
"""

import os
from flask import Flask, render_template_string, request, jsonify
import plaid
from plaid.api import plaid_api
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.products import Products
from plaid.model.country_code import CountryCode

app = Flask(__name__)

# Get credentials from environment
PLAID_CLIENT_ID = os.getenv('PLAID_CLIENT_ID')
PLAID_SECRET = os.getenv('PLAID_SECRET')
PLAID_ENV = os.getenv('PLAID_ENV', 'development')

if PLAID_ENV == 'sandbox':
    host = plaid.Environment.Sandbox
elif PLAID_ENV == 'development':
    host = plaid.Environment.Development
else:
    host = plaid.Environment.Production

configuration = plaid.Configuration(
    host=host,
    api_key={
        'clientId': PLAID_CLIENT_ID,
        'secret': PLAID_SECRET,
    }
)

api_client = plaid.ApiClient(configuration)
client = plaid_api.PlaidApi(api_client)

HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Connect Your Bank - Budget Display Setup</title>
    <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            max-width: 600px;
            margin: 0 auto;
            padding: 40px 20px;
            background: #111;
            color: #fff;
            min-height: 100vh;
        }
        h1 { color: #a3e635; margin-bottom: 10px; }
        p { color: #888; line-height: 1.6; }
        button {
            background: #a3e635;
            color: #000;
            border: none;
            padding: 16px 32px;
            font-size: 18px;
            font-weight: 600;
            border-radius: 8px;
            cursor: pointer;
            margin-top: 20px;
        }
        button:hover { background: #84cc16; }
        button:disabled { background: #444; color: #888; cursor: not-allowed; }
        .success {
            background: #1a3d1a;
            border: 1px solid #22c55e;
            padding: 20px;
            border-radius: 8px;
            margin-top: 20px;
        }
        .success h2 { color: #22c55e; margin-top: 0; }
        code {
            background: #222;
            padding: 12px 16px;
            display: block;
            border-radius: 4px;
            word-break: break-all;
            margin: 10px 0;
            font-size: 14px;
            color: #a3e635;
        }
        .steps { margin-top: 20px; }
        .steps li { margin-bottom: 10px; color: #ccc; }
    </style>
</head>
<body>
    <h1>Connect Your Bank</h1>
    <p>Click the button below to securely connect your bank account via Plaid. 
       This is a one-time setup - your connection will be saved for automatic updates.</p>
    
    <button id="connect-btn" onclick="openPlaidLink()">Connect Bank Account</button>
    
    <div id="result"></div>
    
    <script>
        let linkHandler = null;
        
        async function initPlaid() {
            const response = await fetch('/create_link_token');
            const data = await response.json();
            
            linkHandler = Plaid.create({
                token: data.link_token,
                onSuccess: async (public_token, metadata) => {
                    document.getElementById('connect-btn').disabled = true;
                    document.getElementById('connect-btn').textContent = 'Processing...';
                    
                    const exchangeResponse = await fetch('/exchange_token', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ public_token })
                    });
                    const exchangeData = await exchangeResponse.json();
                    
                    document.getElementById('result').innerHTML = `
                        <div class="success">
                            <h2>✓ Bank Connected!</h2>
                            <p>Save this access token as a GitHub secret named <strong>PLAID_ACCESS_TOKEN</strong>:</p>
                            <code>${exchangeData.access_token}</code>
                            <div class="steps">
                                <p><strong>Next steps:</strong></p>
                                <ol>
                                    <li>Go to your GitHub repo → Settings → Secrets and variables → Actions</li>
                                    <li>Click "New repository secret"</li>
                                    <li>Name: <code style="display:inline;padding:2px 6px;">PLAID_ACCESS_TOKEN</code></li>
                                    <li>Value: Copy the token above</li>
                                    <li>Click "Add secret"</li>
                                </ol>
                            </div>
                        </div>
                    `;
                },
                onExit: (err, metadata) => {
                    if (err) console.error(err);
                }
            });
        }
        
        function openPlaidLink() {
            if (linkHandler) linkHandler.open();
        }
        
        initPlaid();
    </script>
</body>
</html>
'''

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/create_link_token')
def create_link_token():
    request = LinkTokenCreateRequest(
        products=[Products("transactions")],
        client_name="Budget Display",
        country_codes=[CountryCode('US')],
        language='en',
        user=LinkTokenCreateRequestUser(client_user_id='user-1')
    )
    response = client.link_token_create(request)
    return jsonify({'link_token': response['link_token']})

@app.route('/exchange_token', methods=['POST'])
def exchange_token():
    public_token = request.json['public_token']
    exchange_request = ItemPublicTokenExchangeRequest(public_token=public_token)
    response = client.item_public_token_exchange(exchange_request)
    return jsonify({'access_token': response['access_token']})

if __name__ == '__main__':
    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        print("Error: Set PLAID_CLIENT_ID and PLAID_SECRET environment variables")
        print("")
        print("  export PLAID_CLIENT_ID='your_client_id'")
        print("  export PLAID_SECRET='your_secret'")
        print("  python setup_plaid_link.py")
        exit(1)
    
    print("")
    print("  ╔═══════════════════════════════════════════════════╗")
    print("  ║  Open http://localhost:5000 in your browser       ║")
    print("  ║  to connect your bank account                     ║")
    print("  ╚═══════════════════════════════════════════════════╝")
    print("")
    
    app.run(port=5000, debug=False)
