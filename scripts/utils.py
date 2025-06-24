# Utility functions
import re

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
