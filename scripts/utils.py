# Utility functions
import re
import json
import gspread
import pandas as pd 
import streamlit as st
from io import BytesIO
from google.oauth2 import service_account
from dotenv import load_dotenv
import os

# ✅ Carrega variáveis locais do .env (sem efeito no Streamlit Cloud)

# 🔐 Autenticação com Google Sheets (funciona no Cloud e local)
def get_google_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    # ☁️ STREAMLIT CLOUD – tenta primeiro
    try:
        creds = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=scopes
        )
        sheet_url = st.secrets["SHEET_URL"]
        client = gspread.authorize(creds)
        return client.open_by_url(sheet_url)
    except Exception as cloud_error:
        print("⚠️ Falha ao carregar via st.secrets:", cloud_error)

    # 💻 LOCAL – tenta se o JSON realmente existir
    load_dotenv(dotenv_path=os.path.join("config", ".env"))
    json_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if json_path and os.path.exists(json_path):
        sheet_url = os.getenv("GOOGLE_SHEET_URL")
        creds = service_account.Credentials.from_service_account_file(
            json_path, scopes=scopes
        )
        client = gspread.authorize(creds)
        return client.open_by_url(sheet_url)

    # 🚨 Falhou em tudo
    st.error("❌ Nenhuma credencial válida encontrada.")
    st.stop()

# 📞 Formatação de telefone
def clean_phone_number(phone):
    if not phone:
        return None
    phone = re.sub(r'\D', '', str(phone))
    if len(phone) == 11 and phone[2] == '9':
        return f"+55{phone}"
    if len(phone) == 10:
        return f"+55{phone[:2]}9{phone[2:]}"
    if len(phone) == 11 and phone[2] != '9':
        return f"+55{phone[:2]}9{phone[2:]}"
    return None

# 💬 Mensagens sugeridas por segmento RFV
def suggested_message(segment):
    messages = {
        'Campeões': 'Agradecimento e oferta VIP',
        'Leais': 'Agradecimento e benefício',
        'Potenciais Leais': 'Incentivar 3ª compra',
        'Recentes': 'Agradecer e acompanhar',
        'Promissores': 'Incentivar 2ª compra',
        'Precisam Atenção': 'Lembrete para voltar',
        'Não pode perdê-los': 'Recuperar cliente',
        'Em risco': 'Recuperar cliente',
        'Prestes a dormir': 'Incentivar 2ª compra',
        'Hibernando': 'Recuperar cliente',
        'Perdidos': 'Oferecer algo especial ou reativar'
    }
    return messages.get(segment, '')

# 📥 Exporta DataFrame como Excel
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='RFV')
    return output.getvalue()

# 📊 Carrega nomes das vendedoras do Google Sheet
def get_seller_names():
    sheet = get_google_sheet()
    try:
        sellers_df = pd.DataFrame(sheet.worksheet("Vendedoras").get_all_records())
        sellers_df.columns = sellers_df.columns.str.lower()
        active = sorted(sellers_df[sellers_df["status"].str.lower() == "ativo"]["seller_name"].dropna().unique())
        inactive = sorted(sellers_df[sellers_df["status"].str.lower() != "ativo"]["seller_name"].dropna().unique())
        return active, inactive
    except Exception as e:
        print(f"⚠️ Erro ao carregar 'Vendedoras': {e}")
        return [], []

# 📆 Data relativa (dias, meses, anos)
def relative_date(date):
    today = pd.Timestamp.today()

    if pd.isna(date):
        return ""

    delta = today - date
    total_days = delta.days

    if total_days <= 31:
        unit = "dia" if total_days == 1 else "dias"
        return f"{total_days} {unit}"
    elif total_days <= 365:
        months = round(total_days / 30)
        unit = "mês" if months == 1 else "meses"
        return f"{months} {unit}"
    else:
        years = total_days // 365
        remaining_days = total_days % 365
        months = round(remaining_days / 30)

        year_unit = "ano" if years == 1 else "a"
        month_unit = "mês" if months == 1 else "m"

        if months == 0:
            return f"{years} {year_unit}"
        return f"{years} {year_unit} {months} {month_unit}"
