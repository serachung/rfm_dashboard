import pandas as pd
from datetime import datetime, timedelta

def generate_rfv_snapshot(df, snapshot_date):
    df['created_at'] = pd.to_datetime(df['created_at'])
    df = df.sort_values(by='created_at')

    # Aggregate per client
    client_group = df.groupby(['client_name', 'cnpj']).agg(
        seller_name=('seller_name', lambda x: x.dropna().iloc[-1] if not x.dropna().empty else None),
        recency=('created_at', lambda x: (snapshot_date - x.max()).days),
        frequency=('created_at', 'count'),
        value=('value', 'sum'),
        first_purchase_date=('created_at', 'min'),
        last_purchase_date=('created_at', 'max')
    ).reset_index()

    # Lowercase columns
    client_group.columns = client_group.columns.str.lower()

    # Add snapshot columns
    client_group['snapshot_day'] = snapshot_date.strftime('%Y-%m-%d')
    client_group['m0_rfm'] = ''  # To be filled later
    client_group['m1_rfm'] = ''  # To be joined from previous snapshot
    client_group['rfm_change'] = False
    client_group['change_value'] = 0.0
    client_group['send_message'] = False
    client_group['message_timestamp'] = ''
    client_group['message_by'] = ''

    return client_group
