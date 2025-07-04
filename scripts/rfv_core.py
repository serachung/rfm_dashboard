import pandas as pd
from dotenv import load_dotenv
from datetime import timedelta

load_dotenv("config/.env")


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
    
    
def generate_rfv_snapshot(df, snapshot_date):
    df['createdAt'] = pd.to_datetime(df['createdAt'])
    df = df.sort_values(by='createdAt')

    # Current snapshot range
    # one_year_ago = snapshot_date - timedelta(days=365)
    current_df = df[df['createdAt'] <= snapshot_date]
    # current_df = current_df[current_df['createdAt'] >= one_year_ago]

    # Last month snapshot
    prev_snapshot_date = snapshot_date.replace(day=1) - timedelta(days=1)
    # one_year_before_prev = prev_snapshot_date - timedelta(days=365)
    previous_df = df[df['createdAt'] <= prev_snapshot_date]
    # previous_df = previous_df[previous_df['createdAt'] >= one_year_before_prev]

    # Group current
    current_group = current_df.groupby(['customerId']).agg(
        seller_name=('seller', lambda x: x.dropna().iloc[-1] if not x.dropna().empty else None),
        recency=('createdAt', lambda x: (snapshot_date - x.max()).days),
        frequency=('createdAt', 'count'),
        value=('netValue', 'sum'),
        first_purchase_date=('createdAt', 'min'),
        last_purchase_date=('createdAt', 'max')
    ).reset_index()

    # current_group.columns = current_group.columns.str.lower()
    current_group['snapshot_day'] = snapshot_date.strftime('%Y-%m-%d')
    current_group['m0_rfm'] = current_group.apply(segment, axis=1)

    # Group previous
    previous_group = previous_df.groupby(['customerId']).agg(
        recency=('createdAt', lambda x: (prev_snapshot_date - x.max()).days),
        frequency=('createdAt', 'count'),
        value=('netValue', 'sum')
    ).reset_index()

    previous_group.columns = ['customerId', 'prev_recency', 'prev_frequency', 'prev_value']
    previous_group['m1_rfm'] = previous_group.apply(lambda row: segment({
        'recency': row['prev_recency'], 'frequency': row['prev_frequency']
    }), axis=1)

    # Merge previous into current
    merged = pd.merge(current_group, previous_group, on=['customerId'], how='left')

    merged['m1_rfm'] = merged['m1_rfm'].fillna('Sem histórico')
    merged['rfm_change'] = merged['m0_rfm'] != merged['m1_rfm']
    merged['change_value'] = merged.apply(
        lambda row: row['prev_value'] - row['value']  if row['rfm_change'] and not pd.isna(row['prev_value']) else 0.0,
        axis=1
    )
    merged['message_sent'] = False
    merged['message_timestamp'] = ''
    merged['message_by'] = ''

    return merged


