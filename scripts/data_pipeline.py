import pandas as pd
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os
import gspread
from google.oauth2.service_account import Credentials
from pathlib import Path

# ✅ Load environment variables
load_dotenv(dotenv_path=Path("config/.env"))

# ✅ Google Sheets auth
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file(
    os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"), scopes=SCOPES
)
gc = gspread.authorize(creds)

# ✅ Open the Google Sheet
sheet = gc.open_by_url(os.getenv("GOOGLE_SHEET_URL"))

# ✅ API Info
BASE_URL = os.getenv("MIRE_API_BASE_URL")
SELLER_ID = os.getenv("MIRE_API_SELLER_ID")

def update_data():
    print("🚀 Updating Pedidos and Clientes...")

    pedidos_ws = sheet.worksheet("Pedidos")
    clientes_ws = sheet.worksheet("Clientes")

    pedidos_data = pedidos_ws.get_all_records()
    pedidos_df = pd.DataFrame(pedidos_data)

    # ✅ Check last date in Pedidos
    if pedidos_df.empty:
        max_date = pd.to_datetime("2024-01-01")
    else:
        pedidos_df['data_pedido'] = pd.to_datetime(pedidos_df['data_pedido'], errors='coerce')
        max_date = pedidos_df['data_pedido'].max()

    yesterday = pd.Timestamp.today() - pd.Timedelta(days=1)
    date_range = pd.date_range(max_date + timedelta(days=1), yesterday)

    # ✅ Add headers if empty
    if len(pedidos_data) == 0:
        pedidos_ws.append_row([
            'Loja', 'data_pedido', 'order_id', 'Cliente', 'customer_cnpj',
            'Quantidade', 'Valor', 'Desconto', 'Devolução', 'total_value',
            'Pagamento', 'seller', 'Observação', 'Motivo', 'Status'
        ])

    if len(clientes_ws.get_all_values()) == 0:
        clientes_ws.append_row([
            'Loja', 'cnpj', 'Cliente', 'Tickets', 'Qtde', 'Total', 'DDD',
            'telefone', 'mobile', 'Email', 'Cadastro', 'Ult.Compra',
            'Cidade', 'UF', 'Grupo', 'seller'
        ])

    for date in date_range:
        date_str = date.strftime('%Y-%m-%d')
        print(f"🔄 Fetching orders for {date_str}...")

        # ✅ Fetch Orders
        order_url = f"{BASE_URL}/orders?data={date_str}&sellerid={SELLER_ID}"
        res = requests.get(order_url)

        if res.status_code == 200:
            orders = res.json()

            for order in orders:
                pedidos_ws.append_row([
                    order.get('Loja'),
                    date_str,
                    order.get('order_id'),
                    order.get('customer_name'),
                    order.get('customer_cnpj'),
                    order.get('Quantidade'),
                    order.get('Valor'),
                    order.get('Desconto'),
                    order.get('Devolucao'),
                    order.get('total_value'),
                    order.get('Pagamento'),
                    order.get('seller'),
                    order.get('Observacao'),
                    order.get('Motivo'),
                    order.get('Status')
                ])

                # ✅ Upsert Clientes
                try:
                    cust_cell = clientes_ws.find(order.get('customer_cnpj'))
                    clientes_ws.update_cell(cust_cell.row, 12, date_str)  # Update Ult.Compra
                except:
                    # ✅ Fetch Customer details
                    cust_url = f"{BASE_URL}/customers/{order.get('customer_cnpj')}?sellerid={SELLER_ID}"
                    cust_res = requests.get(cust_url)

                    if cust_res.status_code == 200:
                        c = cust_res.json()
                        clientes_ws.append_row([
                            c.get('Loja'),
                            c.get('cnpj'),
                            c.get('name'),
                            c.get('Tickets'),
                            c.get('Qtde'),
                            c.get('Total'),
                            c.get('DDD'),
                            c.get('telefone'),
                            c.get('mobile'),
                            c.get('Email'),
                            c.get('Cadastro'),
                            date_str,  # Ult.Compra
                            c.get('Cidade'),
                            c.get('UF'),
                            c.get('Grupo'),
                            c.get('seller')
                        ])

        else:
            print(f"❌ Failed to fetch orders for {date_str}. Status: {res.status_code}")

    print("✅ Pedidos and Clientes updated.")
