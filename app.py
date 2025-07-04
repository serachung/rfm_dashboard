import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st
import plotly.express as px

from dotenv import load_dotenv
from pathlib import Path
from datetime import datetime
from gspread_dataframe import set_with_dataframe
from scripts.data_pipeline import generate_and_save_snapshot, update_data, get_google_sheet
from scripts.utils import get_seller_names, to_excel,relative_date

# Page config
st.set_page_config(page_title="RFV WhatsApp", layout="wide")
st.title("📦 RFV Snapshot - Incentive")


# ✅ Load environment
load_dotenv(dotenv_path=Path("config/.env"))

# ✅ Login
st.title("🔐 Login")
password = st.text_input("Senha", type="password")
if password != st.secrets["APP_PASSWORD"]:
    st.error("❌ Acesso negado - insira a senha")
    st.stop()
st.success("✅ Acesso liberado!")

# ✅ Session state setup
if "snapshot_df" not in st.session_state:
    st.session_state.snapshot_df = pd.DataFrame()

if "pagination" not in st.session_state:
    st.session_state.pagination = {}

PAGE_SIZE = 10

today = datetime.today()
snapshot_day = (datetime.today().replace(day=1) - pd.Timedelta(days=1)).date()
snapshot_title = f"rfm_snapshot_{snapshot_day:%Y_%m_%d}"

if st.session_state.snapshot_df.empty:
    try:
        sheet = get_google_sheet()  
        ws = sheet.worksheet(snapshot_title)
        df = pd.DataFrame(ws.get_all_records())
        st.session_state.snapshot_df = df
        st.success(f"✅ RFM DO DIA {snapshot_day:%d-%m-%Y} CARREGADA COM SUCESSO")

    except Exception as e:
        st.warning(f"⚠️ Snapshot do mês ainda não existe. Gere manualmente. Erro: {e}")

        with st.expander("⚙️ Operações Manuais", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Atualizar pedidos e clientes"):
                    with st.spinner("🔄 Atualizando dados..."):
                        update_data()
                    st.success("✅ Dados atualizados com sucesso.")
            with col2:
                if st.button("📊 Gerar snapshot manual"):
                    with st.spinner("📊 Gerando snapshot mensal..."):
                        df = generate_and_save_snapshot()
                        st.session_state.snapshot_df = df
                    st.success("✅ Snapshot gerado com sucesso.")
        st.stop()
else:
    df = st.session_state.snapshot_df
    # 🚫 Excluir NUVEMSHOP e CNPJ = 1
    df = df[(df["seller_name"] != "NUVEMSHOP") & (df["cnpj"] != 1)]

active_sellers, inactive_sellers = get_seller_names()
seller_options = ["Todas"] + active_sellers + (["Sem vendedora"] if inactive_sellers else ["Sem vendedora"])
selected_seller = st.selectbox("Filtrar por vendedora:", seller_options)

if selected_seller == "Sem vendedora":
    df = df[~df["seller_name"].isin(active_sellers)]
elif selected_seller != "Todas":
    df = df[df["seller_name"] == selected_seller]

df = df[df["cnpj"].notna()]
df = df[df["value"] > 0]

st.subheader("📨 Marcação de mensagens por segmento")
rfv_groups = {
    "🏆 Campeões de vendas": ["Campeões", "Leais"],
    "🔄 Potenciais vendas": ["Potenciais Leais", "Recentes", "Promissores", "Precisam Atenção", "Não pode perdê-los"],
    "⚠️ Atenção": ["Em risco", "Prestes a dormir", "Hibernando"],
    "❄️ Perdidos": ["Perdidos"]
}

updated_rows = []

for title, segments in rfv_groups.items():
    group_df = df[df["m0_rfm"].isin(segments)].copy()
    group_df["original_index"] = group_df.index
    group_df = group_df.sort_values(by="last_purchase_date", ascending=False)
    total_rows = len(group_df)
    max_page = (total_rows - 1) // PAGE_SIZE
    page_key = f"page_{title}"
    if page_key not in st.session_state.pagination:
        st.session_state.pagination[page_key] = 0

    with st.expander(f"{title}", expanded=True):
        st.markdown(f"({total_rows} clientes)")

        current_page = st.session_state.pagination[page_key]
        start = current_page * PAGE_SIZE
        end = start + PAGE_SIZE
        paginated_df = group_df.iloc[start:end]

        edited_df = paginated_df.copy() # Paginate
        edited_df["Enviado?"] = edited_df["message_sent"]  # Default unchecked

        # Format value to "1.250" instead of "1,250.00"
        edited_df["Valor (R$)"] = edited_df["value"].apply(lambda v: f"R$ {int(round(v)):,}".replace(",", "."))

        # Convert to datetime if not already
        edited_df["first_purchase_date"] = pd.to_datetime(edited_df["first_purchase_date"], errors="coerce")
        edited_df["last_purchase_date"] = pd.to_datetime(edited_df["last_purchase_date"], errors="coerce")
        edited_df["1ª compra"] = edited_df["first_purchase_date"].apply(relative_date)
        edited_df["Última compra"] = edited_df["last_purchase_date"].apply(relative_date)

        # Check all toggle
        check_all = st.checkbox("✔️ Selecionar todos os 10", key=f"check_all_{title}")
        if check_all:
            edited_df["message_sent"] = True

        # Change display name
        edited_df_display = edited_df[[
            "name", "cnpj", "seller_name", "recency", "frequency", "Valor (R$)",
            "1ª compra", "Última compra", "m0_rfm", "m1_rfm", "Enviado?"
        ]].rename(columns={
            "name": "Cliente", "cnpj": "CNPJ", "seller_name": "Vendedora",
            "recency": "Recência", "frequency": "Frequência",
            "m0_rfm": "RFM atual", "m1_rfm": "RFM (M-1)","message_sent":"Enviado?"
        })

        # COLUMNS TO SHOW
        edited_df_display = st.data_editor(
            edited_df_display,
            key=f"editor_{title}",
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic",
            column_order=[
                "Cliente", "CNPJ", "Vendedora", "Recência", "Frequência", "Valor (R$)",
                "1ª compra", "Última compra", "Snapshot", "RFM Mês 0", "RFM Mês 1", "Enviado?"
            ]
        )
        edited_with_cnpj = edited_df_display.merge(
            paginated_df[["cnpj", "original_index"]],
            how="left",
            left_on="CNPJ",
            right_on="cnpj"
        )

        for _, row in edited_with_cnpj.iterrows():
            if row["Enviado?"]:
                updated_rows.append((row["original_index"], True))

        col1, col2 = st.columns([1, 6])
        with col1:
            if current_page > 0:
                if st.button("⬅️ Anterior", key=f"prev_{title}"):
                    st.session_state.pagination[page_key] -= 1
        with col2:
            if current_page < max_page:
                if st.button("Próximo ➡️", key=f"next_{title}"):
                    st.session_state.pagination[page_key] += 1


# SAVE CHECKS TO GOOGLE SHEETS
if updated_rows:
    if st.button("📅 Salvar marcações de mensagem"):
        for idx, is_checked in updated_rows:
            df.at[idx, "message_sent"] = is_checked

        try:
            sheet = get_google_sheet()
            ws = sheet.worksheet(snapshot_title)
            set_with_dataframe(ws, df)
            st.success("✅ Marcações salvas e sincronizadas com o Google Sheet!")
        except Exception as e:
            st.error(f"❌ Erro ao salvar no Google Sheet: {e}")

rfm_order = [
    "Campeões", "Leais", "Potenciais Leais", "Recentes", "Promissores",
    "Precisam Atenção", "Não pode perdê-los", "Em risco", 
    "Prestes a dormir", "Hibernando", "Perdidos"
]
segment_counts = df['m0_rfm'].value_counts().reindex(rfm_order).fillna(0).astype(int)
df_plot = pd.DataFrame({
    "Segmento": segment_counts.index,
    "Clientes": segment_counts.values
})
df_plot["% do total"] = (df_plot["Clientes"] / df_plot["Clientes"].sum() * 100).round(0)

fig = px.bar(
    df_plot,
    x="Segmento",
    y="Clientes",
    color="Segmento",
    text="% do total",
    color_discrete_sequence=px.colors.qualitative.Safe,
    labels={"Clientes": "Nº de Clientes"},
    title="📊 Nº de Clientes por Segmento RFM"
)
fig.update_traces(texttemplate='%{text}%', textposition='outside')
fig.update_layout(
    xaxis_tickangle=-45,
    yaxis=dict(showgrid=True, gridcolor="lightgrey"),
    plot_bgcolor='white',
    showlegend=False
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("⬇️ Exportar")
st.download_button(
    label="📥 Baixar CSV",
    data=df.to_csv(index=False),
    file_name="rfv_clientes.csv",
    mime="text/csv",
    key="csv_download_button"
)

st.download_button(
    label="📥 Baixar Excel",
    data=to_excel(df),
    file_name="rfv_clientes.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    key="excel_download_button"
)



# 🔗 Link to open the Google Sheet (styled like a button)
try:
    sheet = get_google_sheet()
    sheet_url = sheet.url

    st.markdown(
        f"""
        <a href="{sheet_url}" target="_blank">
            <button style="
                background-color: #4CAF50;
                color: white;
                padding: 0.5em 1.5em;
                border: none;
                border-radius: 4px;
                font-size: 16px;
                cursor: pointer;
                margin-top: 1em;
            ">
                📄 Abrir no Google Sheets
            </button>
        </a>
        """,
        unsafe_allow_html=True
    )

except Exception as e:
    st.warning(f"⚠️ Não foi possível gerar o link do Google Sheet: {e}")











