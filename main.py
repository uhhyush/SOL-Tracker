import discord
import requests
import json

# Set up intents for the bot
intents = discord.Intents.default()
intents.message_content = True

# RPC URL for Solana blockchain
RPC_URL = "https://api.mainnet-beta.solana.com"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=usd"
DEXSCREENER_API_URL = "https://api.dexscreener.io/latest/dex/tokens/"

# Discord bot setup
TOKEN = "ENTER TOKEN HERE"
CHANNEL_ID = "ENTER CHANNEL ID HERE AS AN INTEGER NOT STRING"

client = discord.Client(intents=intents)

# Dictionary to keep track of wallets
tracked_wallets = {}

# Fetch Solana price from CoinGecko
def get_solana_price():
    response = requests.get(COINGECKO_API_URL)
    if response.status_code == 200:
        data = response.json()
        return data["solana"]["usd"]
    else:
        return None

# Fetch SOL balance from Solana RPC
def get_sol_balance(wallet_address):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBalance",
        "params": [wallet_address]
    }
    response = requests.post(RPC_URL, json=payload)
    if response.status_code == 200:
        result = response.json()
        sol_balance = result['result']['value'] / 10 ** 9  # Convert lamports to SOL
        return sol_balance
    else:
        print(f"Error fetching SOL balance: {response.status_code}, {response.text}")
        return None

# Fetch wallet token data from Solana RPC
def get_wallet_tokens(wallet_address):
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getTokenAccountsByOwner",
        "params": [
            wallet_address,
            {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
            {"encoding": "jsonParsed"}
        ]
    }

    response = requests.post(RPC_URL, json=payload)

    if response.status_code == 200:
        return response.json()
    else:
        print(f"Solana RPC Error: {response.status_code}, {response.text}")
        return None

# Fetch token info from Dexscreener
def get_token_info(token_address):
    url = DEXSCREENER_API_URL + token_address
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        try:
            price_usd = float(data['pairs'][0]['priceUsd'])
            market_cap = float(data['pairs'][0]['marketCap'])
            token_ticker = data['pairs'][0]['baseToken']['symbol']
            token_name = data['pairs'][0]['baseToken']['name']
            return {"price_usd": price_usd, "market_cap": market_cap, "ticker": token_ticker, "name": token_name}
        except (KeyError, ValueError, TypeError) as e:
            print(f"Error parsing token data: {e}")
            return None
    return None

# Handle commands
@client.event
async def on_message(message):
    # Ensure bot only responds in the correct channel
    if message.channel.id != CHANNEL_ID:
        return

    # Handle the !track command
    if message.content.startswith("!track"):
        wallet_address = message.content.split(" ", 1)[1]
        if wallet_address in tracked_wallets:
            await message.channel.send(f"Already tracking wallet {wallet_address}.")
            return

        tracked_wallets[wallet_address] = {"invested_amounts": {}, "sold_amounts": {}, "remaining_amounts": {}}

        solana_price = get_solana_price()
        if solana_price is None:
            await message.channel.send("Error fetching Solana price.")
            return

        # Fetch SOL balance
        sol_balance = get_sol_balance(wallet_address)
        if sol_balance is None:
            await message.channel.send("Error fetching SOL balance.")
            return

        # Fetch token data
        tokens = get_wallet_tokens(wallet_address)

        # Initialize totals
        total_tokens_value_usd = 0

        # Display tracking status
        await message.channel.send(f"Now tracking wallet {wallet_address}")
        await message.channel.send(f"Solana balance: {sol_balance:.2f} SOL (~${sol_balance * solana_price:.2f} USD)")

        if tokens and 'result' in tokens:
            token_accounts = tokens['result']['value']

            if token_accounts:
                for token_account in token_accounts:
                    token_amount = token_account['account']['data']['parsed']['info']['tokenAmount']['uiAmount']
                    token_address = token_account['account']['data']['parsed']['info']['mint']

                    # Skip tokens with a balance of 0
                    if token_amount == 0:
                        continue

                    # Fetch token info from Dexscreener
                    token_info = get_token_info(token_address)
                    if token_info:
                        token_price_usd = token_info['price_usd']
                        token_value_usd = token_price_usd * token_amount
                        total_tokens_value_usd += token_value_usd

                        # Track investments and amounts
                        if token_address not in tracked_wallets[wallet_address]['invested_amounts']:
                            tracked_wallets[wallet_address]['invested_amounts'][token_address] = token_value_usd
                            tracked_wallets[wallet_address]['remaining_amounts'][token_address] = token_value_usd
                        else:
                            tracked_wallets[wallet_address]['remaining_amounts'][token_address] = token_value_usd

        # Calculate and display the total USD balance
        await message.channel.send(f"Total Token Value: ~${total_tokens_value_usd:.2f} USD")
        await message.channel.send(f"Total Wallet Balance: ~${total_tokens_value_usd + (sol_balance * solana_price):.2f} USD")

    # Handle the !show_positions command
    elif message.content.startswith("!show_positions"):
        wallet_address = list(tracked_wallets.keys())[0]  # Show positions for the first tracked wallet
        if wallet_address is None:
            await message.channel.send("No wallet is currently being tracked.")
            return

        solana_price = get_solana_price()
        if solana_price is None:
            await message.channel.send("Error fetching Solana price.")
            return

        # Fetch token data
        tokens = get_wallet_tokens(wallet_address)

        if tokens and 'result' in tokens:
            token_accounts = tokens['result']['value']

            if token_accounts:
                for token_account in token_accounts:
                    token_amount = token_account['account']['data']['parsed']['info']['tokenAmount']['uiAmount']
                    token_address = token_account['account']['data']['parsed']['info']['mint']

                    # Skip tokens with a balance of 0
                    if token_amount == 0:
                        continue

                    # Fetch token info from Dexscreener
                    token_info = get_token_info(token_address)
                    if token_info:
                        token_price_usd = token_info['price_usd']
                        remaining_usd = token_price_usd * token_amount

                        # Update remaining amounts
                        tracked_wallets[wallet_address]['remaining_amounts'][token_address] = remaining_usd

                        # Generate Dexscreener link and display token info
                        dexscreener_link = f"https://dexscreener.com/solana/{token_address}"
                        token_ticker = token_info['ticker']
                        token_name = token_info['name']

                        # Create the formatted output message
                        message_content = (
                            f"Ticker: {token_ticker}\n"
                            f"Name: {token_name}\n"
                            f"Token Address: {token_address}\n"
                            f"Market Cap: ${token_info['market_cap']:.2f} USD\n"
                            f"Value: ${remaining_usd:.2f} USD\n"
                            f"Dexscreener Link: {dexscreener_link}\n"
                            "______________________________________________"
                        )

                        # Send the formatted message
                        await message.channel.send(message_content)
                else:
                    await message.channel.send("No token positions found for this wallet.")
            else:
                await message.channel.send("Error fetching wallet token data.")

    # Handle the bot start message
    elif message.content == "!help":
        help_message = (
            "Bot Commands:\n"
            "!track (wallet address) - Start tracking a Solana wallet.\n"
            "!show_positions - Show the current positions of the tracked wallet.\n"
        )
        await message.channel.send(help_message)

@client.event
async def on_ready():
    print(f'Bot logged in as {client.user}')
    # Send help message to the channel when the bot starts
    channel = client.get_channel(CHANNEL_ID)
    await channel.send("Bot is online! Use `!help` to get a list of commands.")

# Start the bot
client.run(TOKEN)
