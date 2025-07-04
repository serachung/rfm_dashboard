
import pandas as pd
import gspread
import requests
import json
import os
from google.oauth2 import service_account
from dotenv import load_dotenv
from datetime import datetime, timedelta
from scripts.rfv_core import generate_rfv_snapshot
from scripts.utils import get_google_sheet, clean_phone_number
from requests.auth import HTTPBasicAuth
import streamlit as st


load_dotenv("config/.env")

# 🔐 Authenticate to Google Sheets
def get_google_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    if os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE").endswith(".json"):
        creds = service_account.Credentials.from_service_account_file(
            os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"), scopes=scopes)
    else:
        creds = service_account.Credentials.from_service_account_info(
            json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")), scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_url(os.getenv("GOOGLE_SHEET_URL"))
    return sheet

# 📅 Get last order date from "Pedidos" sheet
def get_last_order_date():
    sheet = get_google_sheet()
    try:
        orders = pd.DataFrame(sheet.worksheet("Pedidos").get_all_records())
        orders["createdAt"] = pd.to_datetime(orders["createdAt"], errors="coerce") # dayfirst=True,
        print("DATA MAXIMA", orders["createdAt"].max())
        
        return orders["createdAt"].max()
    except Exception as e:
        print("⚠️ Could not read 'Pedidos':", e)
        return None

# 🔁 Fetch missing orders day-by-day



def fetch_orders_from_api(start_date, end_date):
    url = "https://mire.omnni.com.br/api/orders"
    username = os.getenv("API_USERNAME")
    password = os.getenv("API_PASSWORD")
    seller_id = os.getenv("API_SELLER_ID")

    all_orders = []

    current_date = start_date
    while current_date <= end_date:
        params = {
            "data": current_date.strftime("%Y-%m-%d"),
            "sellerid": seller_id
        }

        headers = {"Accept": "application/json"}
        print(f"📡 Fetching orders for {current_date.strftime('%Y-%m-%d')}")
        response = requests.get(url,headers=headers, params=params, auth=HTTPBasicAuth(username, password))

        
        print(response.status_code)
        print(response.headers.get("Content-Type"))
        print(response.text[:500])  # first 500 chars of response

        if response.status_code == 200:
            daily_data = response.json()
            print('daily_data: ', daily_data)
            all_orders.extend(daily_data)
        else:
            print(f"❌ Failed for {current_date.strftime('%Y-%m-%d')}: {response.status_code}")

        current_date += timedelta(days=1)

    return pd.DataFrame(all_orders)

# 🧩 Safely backfill orders into Google Sheets
def backfill_orders_if_needed():
    sheet = get_google_sheet()
    today = datetime.today()
    
    try:
        orders_ws = sheet.worksheet("Pedidos")
        existing = pd.DataFrame(orders_ws.get_all_records())
        existing.columns = existing.columns.str.strip()
        last_date = pd.to_datetime(existing["createdAt"]).max()

    except Exception as e:
        print(f"⚠️ Could not read 'Pedidos': {e}")
        return

    if pd.isna(last_date):
        start_date = today - timedelta(days=365)
        print(f"🔄 No valid last date found. Backfilling from {start_date.date()} to {today.date()}")
    
    elif (today - last_date).days < 1:
        print("✅ Orders are up-to-date.")
        return
    else:
        start_date = last_date + timedelta(days=1)
        print(f"🔄 Backfilling from {start_date.date()} to {today.date()}")

    # Fetch new orders
    new_orders = fetch_orders_from_api(start_date, today)

    if not new_orders.empty:
        # Use existing sheet structure if available
        expected_columns = existing.columns.tolist() if not existing.empty else new_orders.columns.tolist()

        # Ensure all expected columns exist in new data
        for col in expected_columns:
            if col not in new_orders.columns:
                new_orders[col] = None
        # print(new_orders.columns)
        
        # Order columns to match
        new_orders = new_orders[expected_columns]
        new_orders = new_orders[new_orders.status != "ESPERA"]

        # Format date
        if "createdAt" in new_orders.columns:
            # print(new_orders.createdAt.dtype)
            new_orders["createdAt"] = pd.to_datetime(new_orders["createdAt"], errors="coerce").dt.strftime("%Y-%m-%d")

        # Combine and format
        updated = pd.concat([existing, new_orders], ignore_index=True)

        # Remove duplicates by 'orderId' (keep the latest entry)
        if "orderId" in updated.columns:
            updated = updated.drop_duplicates(subset="orderId", keep="last")

        # Format all values
        updated = updated.fillna("").astype(str)

        # Push to sheet
        orders_ws.update([updated.columns.tolist()] + updated.values.tolist())
        print("✅ Orders updated.")
    else:
        print("ℹ️ No new orders.")



# 🧍 Check and backfill missing clients
def fetch_clients_by_cnpj(customer_ids):
    url_base = "https://mire.omnni.com.br/api/customers"
    username = os.getenv("API_USERNAME")
    password = os.getenv("API_PASSWORD")
    seller_id = os.getenv("API_SELLER_ID")

    sheet = get_google_sheet()
    orders_df = pd.DataFrame(sheet.worksheet("Pedidos").get_all_records())

    clients_data = []
    for customer_id in customer_ids:
        if pd.isna(customer_id) or customer_id in ("#N/A", "nan", ""):
            continue

        url = f"{url_base}/{customer_id}"
        params = {"sellerid": seller_id}

        try:
            response = requests.get(url, params=params, auth=HTTPBasicAuth(username, password))
            if response.status_code == 200:
                client_info = response.json()
                if isinstance(client_info, dict):
                    # 🛠️ If seller is missing, fill from Pedidos
                    if not client_info.get("seller"):
                        matching_seller = (
                            orders_df[orders_df["customerId"] == customer_id]
                            .sort_values(by="createdAt")
                            .seller.dropna()
                        )
                        if not matching_seller.empty:
                            client_info["seller"] = matching_seller.iloc[-1]  # Most recent

                    clients_data.append(client_info)
                else:
                    print(f"⚠️ Unexpected client format for {customer_id}")
            else:
                print(f"❌ Failed to fetch client {customer_id}: {response.status_code}")
        except Exception as e:
            print(f"🚨 Error fetching client {customer_id}: {e}")

    return pd.DataFrame(clients_data)


def backfill_missing_clients():
    sheet = get_google_sheet()
    orders = pd.DataFrame(sheet.worksheet("Pedidos").get_all_records())
    clients = pd.DataFrame(sheet.worksheet("Clientes").get_all_records())

    missing_cnpjs = set(orders["customerId"]) - set(clients["document"])
    missing_cnpjs = [c for c in missing_cnpjs if pd.notna(c) and c != "#N/A"]

    if missing_cnpjs:
        print(f"🔍 Found {len(missing_cnpjs)} missing clients. Fetching from API...")
        new_clients = fetch_clients_by_cnpj(list(missing_cnpjs))
        if not new_clients.empty:
            # Coalesce phone columns into 'whatsapp'
            def get_best_phone(row):
                for col in ['whatsapp', 'telefone', 'mobile']:
                    if col in row and pd.notna(row[col]) and row[col]:
                        return clean_phone_number(row[col])
                return None

            new_clients['whatsapp'] = new_clients.apply(get_best_phone, axis=1)
            updated = pd.concat([clients, new_clients], ignore_index=True)
            ws = sheet.worksheet("Clientes")
            ws.update([updated.columns.tolist()] + updated.astype(str).values.tolist())
            print("✅ Clients updated.")
    else:
        print("✅ No missing clients.")



def generate_and_save_snapshot():
    sheet = get_google_sheet()

    # 🔄 Load orders
    try:
        orders = pd.DataFrame(sheet.worksheet("Pedidos").get_all_records())
        orders.columns = orders.columns.str.strip()
        orders["createdAt"] = pd.to_datetime(orders["createdAt"], errors="coerce")
    except Exception as e:
        print(f"❌ Could not load Pedidos: {e}")
        return pd.DataFrame()

    # 📆 Filter last 12 months
    # one_year_ago = datetime.today() - timedelta(days=365)
    # df_recent = orders[orders["createdAt"] >= one_year_ago]

    # 📌 Snapshot cutoff: last day of previous month
    snapshot_date = datetime.today().replace(day=1) - timedelta(days=1)
    snapshot_df = generate_rfv_snapshot(orders, snapshot_date)

    # 📥 Load client names from "Clientes"
    try:
        clientes_df = pd.DataFrame(sheet.worksheet("Clientes").get_all_records())
        if "document" in clientes_df.columns and "name" in clientes_df.columns:
            clientes_df = clientes_df.rename(columns={"document": "customerId"})
            snapshot_df = pd.merge(snapshot_df, clientes_df[["customerId", "name"]], on="customerId", how="left")
        else:
            snapshot_df["name"] = ""

    except Exception as e:
        print(f"⚠️ Could not load Clientes: {e}")
        snapshot_df["name"] = "Erro ao buscar nome"

    # 📊 Save snapshot to new worksheet
    sheet_title = f"rfm_snapshot_{snapshot_date.strftime('%Y_%m_%d')}"
    try:
        ws = sheet.worksheet(sheet_title)
        sheet.del_worksheet(ws)
    except:
        pass
    ws = sheet.add_worksheet(title=sheet_title, rows="1000", cols="30")
    snapshot_df = snapshot_df.rename(columns={"customerId": "cnpj"})
    snapshot_df = snapshot_df[["name","cnpj","seller_name","recency","frequency","value","first_purchase_date","last_purchase_date","snapshot_day","m0_rfm","prev_recency","prev_frequency","prev_value","m1_rfm","rfm_change","change_value","message_sent"]]
    ws.update([snapshot_df.columns.tolist()] + snapshot_df.astype(str).values.tolist())

    print(f"✅ Snapshot saved to sheet: {sheet_title}")
    return snapshot_df




def update_data():
    print("🔄 Verificando pedidos e clientes manualmente...")
    backfill_orders_if_needed()
    backfill_missing_clients()
    print("✅ Sincronização manual concluída.")