import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import os
import gspread
import json
from google.oauth2 import service_account
from pathlib import Path
from scripts.utils import clean_phone_number, suggested_message

# ✅ Load environment
load_dotenv(dotenv_path=Path("config/.env"))

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

if os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE").endswith(".json"):
    creds = service_account.Credentials.from_service_account_file(
        os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"),
        scopes=SCOPES
    )
else:
    creds = service_account.Credentials.from_service_account_info(
        json.loads(os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")),
        scopes=SCOPES
    )

gc = gspread.authorize(creds)

sheet = gc.open_by_url(os.getenv("GOOGLE_SHEET_URL"))

def run_rfv():
    print("🚀 Running RFV check...")

    today = pd.Timestamp.today().strftime('%Y-%m-%d')

    try:
        rfm_ws = sheet.worksheet("RFM")
        rfm_data = rfm_ws.get_all_records()
        rfm_df = pd.DataFrame(rfm_data)

        if not rfm_df.empty and 'snapshot_date' in rfm_df.columns:
            latest_snapshot = rfm_df['snapshot_date'].max()
            if latest_snapshot == today:
                print(f"🛑 RFV snapshot for {today} already exists. Skipping.")
                return
    except:
        print("ℹ️ 'RFM' worksheet does not exist. It will be created.")
        rfm_ws = sheet.add_worksheet(title="RFM", rows=1000, cols=20)

    pedidos = pd.DataFrame(sheet.worksheet("Pedidos").get_all_records())
    pedidos = pedidos[pedidos['loja'].str.upper() != 'ECOMMERCE']

    clientes = pd.DataFrame(sheet.worksheet("Clientes").get_all_records())

    if pedidos.empty:
        raise Exception("❌ 'Pedidos' is empty. Run data update first.")

    pedidos.columns = [c.lower().strip() for c in pedidos.columns]
    clientes.columns = [c.lower().strip() for c in clientes.columns]

    pedidos['data_pedido'] = pd.to_datetime(pedidos['data_pedido'], errors='coerce')

    if 'seller' not in pedidos.columns:
        raise Exception("❌ Missing 'seller' column in 'Pedidos'.")

    rfm = pedidos.groupby(['customer_cnpj', 'seller']).agg({
        'data_pedido': lambda x: (pd.Timestamp.today() - x.max()).days,
        'order_id': 'count',
        'total_value': 'sum'
    }).reset_index()

    rfm.columns = ['cnpj', 'seller', 'recency', 'frequency', 'value']

    clientes['whatsapp'] = clientes.apply(
        lambda x: clean_phone_number(x.get('mobile') or x.get('telefone')), axis=1
    )

    clientes_subset = clientes[['cnpj', 'cliente', 'whatsapp']]

    final = rfm.merge(clientes_subset, on='cnpj', how='left')

    def segment(row):
        r = row['recency']
        f = row['frequency']
        if r <= 30 and f >= 10:
            return 'Campeões'
        elif 30 < r <= 120 and f >= 10:
            return 'Leais'
        elif r <= 60 and 2 <= f <= 9:
            return 'Potenciais Leais'
        elif r <= 30 and f == 1:
            return 'Recentes'
        elif 30 < r <= 60 and f == 1:
            return 'Promissores'
        elif 60 < r <= 120 and 2 <= f <= 9:
            return 'Precisam Atenção'
        elif 120 < r <= 360 and f >= 10:
            return 'Não pode perdê-los'
        elif 120 < r <= 180 and 2 <= f <= 9:
            return 'Em risco'
        elif 60 < r <= 180 and f == 1:
            return 'Prestes a dormir'
        elif 180 < r <= 360 and 1 <= f <= 9:
            return 'Hibernando'
        elif r > 360:
            return 'Perdidos'
        else:
            return 'Outros'

    final['rfv_segment'] = final.apply(segment, axis=1)
    final['mensagem'] = final['rfv_segment'].apply(suggested_message)
    final['snapshot_date'] = today

    # ✅ Create WhatsApp link
    final['whatsapp_link'] = final['whatsapp'].apply(
        lambda x: f"https://wa.me/55{x}" if pd.notnull(x) and x != "" else ""
    )

    final.columns = [c.lower().strip() for c in final.columns]

    output = final[[
        'snapshot_date', 'seller', 'cnpj', 'cliente', 'whatsapp', 'whatsapp_link',
        'recency', 'frequency', 'value', 'rfv_segment', 'mensagem'
    ]]

    print("📝 Writing RFM snapshot to Google Sheets...")
    data_to_write = [output.columns.tolist()] + output.astype(str).values.tolist()

    rfm_ws.clear()
    rfm_ws.update('A1', data_to_write)

    print(f"✅ RFV snapshot for {today} saved successfully!")

