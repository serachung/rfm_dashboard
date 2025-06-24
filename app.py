import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from dotenv import load_dotenv
import gspread
from google.oauth2.service_account import Credentials
import os
from pathlib import Path
from io import BytesIO
from scripts.data_pipeline import update_data
from scripts.rfv import run_rfv
import re


# ✅ Load environment
load_dotenv(dotenv_path=Path("config/.env"))

st.set_page_config(page_title="RFV WhatsApp", layout="centered")

st.title("📱 RFV WhatsApp Dashboard")


# ✅ Google Sheets Authentication
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
creds = Credentials.from_service_account_file(
    os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"), scopes=SCOPES
)
gc = gspread.authorize(creds)
sheet = gc.open_by_url(os.getenv("GOOGLE_SHEET_URL"))


# ✅ Load RFM Data
@st.cache_data
def load_rfm_data():
    try:
        ws = sheet.worksheet("RFM")
    except:
        st.warning("❌ 'RFM' worksheet not found. Run RFV calculation first.")
        return pd.DataFrame()

    data = pd.DataFrame(ws.get_all_records())
    
    # ✅ Apply base business rule filters
    data = data[
        (data['cliente'].str.upper() != 'CONSUMIDOR') &
        (data['cnpj'].astype(str).str.strip() != '1')
    ]

    if not data.empty:
        data.columns = [c.lower().strip() for c in data.columns]
        data['recency'] = pd.to_numeric(data['recency'], errors='coerce')
        data['frequency'] = pd.to_numeric(data['frequency'], errors='coerce')
        data['value'] = pd.to_numeric(data['value'], errors='coerce')

    return data


# ✅ WhatsApp Validation Function
def is_valid_whatsapp(number):
    if pd.isna(number):
        return False
    number = str(number).strip()
    pattern = r'^55\d{2}9\d{8}$'
    return bool(re.match(pattern, number))


# ✅ Excel Export Function
def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='RFV')
    processed_data = output.getvalue()
    return processed_data


# ✅ Operations Buttons
st.subheader("⚙️ Operações")
col1, col2 = st.columns(2)

with col1:
    if st.button("🔄 Atualizar Dados"):
        update_data()
        st.success("✅ Dados atualizados com sucesso!")

with col2:
    if st.button("🚀 Calcular RFV"):
        run_rfv()
        st.success("✅ RFV calculado com sucesso!")


# ✅ Load data
data = load_rfm_data()

if data.empty:
    st.warning("⚠️ A aba 'RFM' está vazia. Rode 'Calcular RFV'.")
    st.stop()

if 'seller' not in data.columns:
    st.error("❌ A coluna 'seller' não existe na aba 'RFM'. Rode 'Calcular RFV'.")
    st.stop()


# ✅ Seller Filter
sellers = ["Todas"] + sorted(data["seller"].dropna().unique())
selected_seller = st.selectbox("Vendedora:", sellers)

if selected_seller != "Todas":
    data = data[data["seller"] == selected_seller]


# ✅ WhatsApp Toggle Filter
filter_whatsapp = st.checkbox(
    "❌ Ocultar clientes sem WhatsApp válido",
    value=False
)

if filter_whatsapp:
    data = data[data['whatsapp'].apply(is_valid_whatsapp)]
    data['whatsapp_link'] = data['whatsapp'].apply(lambda x: f"https://wa.me/{x}")
else:
    data['whatsapp_link'] = data['whatsapp'].apply(
        lambda x: f"https://wa.me/{x}" if pd.notna(x) and str(x).strip() != "" else ""
    )


# ✅ Show total count
if filter_whatsapp:
    st.markdown(f"**👥 Total de clientes com WhatsApp válido: {len(data)}**")
else:
    st.markdown(f"**👥 Total de clientes (todos): {len(data)}**")


# ✅ Display Table
st.subheader("📋 Lista de Clientes")
st.dataframe(data[[ 
    "cliente", "cnpj", "whatsapp_link", 
    "recency", "frequency", "value", 
    "rfv_segment", "mensagem"
]])


# ✅ Summary Table
st.subheader("📊 Resumo por Classificação RFV")
summary = data['rfv_segment'].value_counts().reset_index()
summary.columns = ["Classificação", "Quantidade"]
st.table(summary)


# ✅ RFM Heatmap
st.subheader("🔥 RFM Grid (Heatmap)")

def recency_bucket(r):
    if r <= 30:
        return '≤30 dias'
    elif r <= 60:
        return '31-60 dias'
    elif r <= 120:
        return '61-120 dias'
    elif r <= 180:
        return '121-180 dias'
    elif r <= 360:
        return '181-360 dias'
    else:
        return '>360 dias'

def frequency_bucket(f):
    if f == 1:
        return '1'
    elif 2 <= f <= 9:
        return '2-9'
    else:
        return '10+'


data['recency_group'] = data['recency'].apply(recency_bucket)
data['frequency_group'] = data['frequency'].apply(frequency_bucket)

rfm_grid = pd.pivot_table(
    data, index='recency_group', columns='frequency_group',
    values='cnpj', aggfunc='count', fill_value=0
).reindex(index=['≤30 dias', '31-60 dias', '61-120 dias', '121-180 dias', '181-360 dias', '>360 dias'])

st.dataframe(rfm_grid)

plt.figure(figsize=(8, 6))
sns.heatmap(
    rfm_grid.fillna(0).astype(int),
    annot=True, fmt='d', cmap="YlGnBu"
)
plt.title("RFM Grid Heatmap")
st.pyplot(plt.gcf())
plt.clf()


# ✅ Export buttons
st.subheader("⬇️ Exportar Dados")
st.download_button(
    label="📥 Baixar CSV",
    data=data.to_csv(index=False).encode('utf-8'),
    file_name='rfv_clientes.csv',
    mime='text/csv'
)

st.download_button(
    label="📥 Baixar Excel",
    data=to_excel(data),
    file_name='rfv_clientes.xlsx',
    mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
)


# ✅ Simple Styling for Mobile
st.markdown(
    """
    <style>
    table {
        font-size: 12px;
    }
    .stButton button {
        padding: 0.3rem 1rem;
    }
    .stDataFrame div {
        font-size: 12px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

# import streamlit as st
# import pandas as pd
# import numpy as np
# import matplotlib.pyplot as plt
# import seaborn as sns
# from scripts.data_pipeline import update_data
# from scripts.rfv import run_rfv
# from dotenv import load_dotenv
# import gspread
# from google.oauth2.service_account import Credentials
# import os
# from pathlib import Path

# load_dotenv(dotenv_path=Path("config/.env"))

# st.set_page_config(page_title="RFV WhatsApp Dashboard", layout="wide")
# st.title("📊 RFV WhatsApp Dashboard")

# SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
# creds = Credentials.from_service_account_file(
#     os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE"), scopes=SCOPES
# )
# gc = gspread.authorize(creds)
# sheet = gc.open_by_url(os.getenv("GOOGLE_SHEET_URL"))

# @st.cache_data
# def load_rfm_data():
#     try:
#         ws = sheet.worksheet("RFM")
#     except:
#         st.warning("❌ 'RFM' worksheet not found. Run RFV calculation first.")
#         return pd.DataFrame()

#     data = pd.DataFrame(ws.get_all_records())

#     if not data.empty:
#         data.columns = [c.lower().strip() for c in data.columns]
#         data['recency'] = pd.to_numeric(data['recency'], errors='coerce')
#         data['frequency'] = pd.to_numeric(data['frequency'], errors='coerce')
#         data['value'] = pd.to_numeric(data['value'], errors='coerce')

#     return data


# with st.sidebar:
#     st.header("⚙️ Operações")
#     if st.button("🔄 Atualizar Pedidos e Clientes"):
#         update_data()
#         st.success("✅ Dados atualizados com sucesso!")

#     if st.button("🚀 Calcular RFV"):
#         run_rfv()
#         st.success("✅ RFV calculado e salvo com sucesso!")

# data = load_rfm_data()

# if data.empty:
#     st.warning("⚠️ A aba 'RFM' está vazia. Rode 'Calcular RFV'.")
#     st.stop()

# if 'seller' not in data.columns:
#     st.error("❌ A coluna 'seller' não existe na aba 'RFM'. Rode 'Calcular RFV'.")
#     st.stop()

# sellers = ["Todas"] + sorted(data["seller"].dropna().unique())
# selected_seller = st.sidebar.selectbox("Filtrar por Vendedora:", sellers)

# if selected_seller != "Todas":
#     data = data[data["seller"] == selected_seller]

# # ✅ WhatsApp Clickable Link for UI
# data['whatsapp_click'] = data['whatsapp'].apply(
#     lambda x: f"[Abrir WhatsApp](https://wa.me/55{x})" if pd.notnull(x) and x != "" else ""
# )

# st.subheader("📋 Lista de Clientes com Classificação RFV e WhatsApp")
# st.markdown(
#     data[[
#         "seller", "cliente", "cnpj", "whatsapp", "whatsapp_click",
#         "recency", "frequency", "value",
#         "rfv_segment", "mensagem", "snapshot_date"
#     ]].to_markdown(index=False),
#     unsafe_allow_html=True
# )

# # ✅ RFV Summary
# st.subheader("🔢 Resumo por Classificação RFV")
# summary = data['rfv_segment'].value_counts().reset_index()
# summary.columns = ["Classificação", "Quantidade"]
# st.table(summary)

# # ✅ RFM Grid (Pivot Table)
# st.subheader("📊 RFM Grid (Tabela)")

# def recency_bucket(r):
#     if r <= 30:
#         return '≤30 dias'
#     elif r <= 60:
#         return '31-60 dias'
#     elif r <= 120:
#         return '61-120 dias'
#     elif r <= 180:
#         return '121-180 dias'
#     elif r <= 360:
#         return '181-360 dias'
#     else:
#         return '>360 dias'

# def frequency_bucket(f):
#     if f == 1:
#         return '1'
#     elif 2 <= f <= 9:
#         return '2-9'
#     else:
#         return '10+'

# data['recency_group'] = data['recency'].apply(recency_bucket)
# data['frequency_group'] = data['frequency'].apply(frequency_bucket)

# rfm_grid = pd.pivot_table(
#     data, index='recency_group', columns='frequency_group',
#     values='cnpj', aggfunc='count', fill_value=0
# ).reindex(index=['≤30 dias', '31-60 dias', '61-120 dias', '121-180 dias', '181-360 dias', '>360 dias'])

# st.dataframe(rfm_grid)

# # ✅ Heatmap
# st.subheader("🔥 RFM Grid (Heatmap)")

# plt.figure(figsize=(8, 6))
# sns.heatmap(
#     rfm_grid.fillna(0).astype(int),
#     annot=True, fmt='d', cmap="YlGnBu"
# )
# plt.title("RFM Grid Heatmap")
# st.pyplot(plt.gcf())
# plt.clf()
