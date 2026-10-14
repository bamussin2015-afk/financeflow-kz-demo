"""FinanceFlow KZ demo calculation engine. Amounts are positive and expressed in KZT."""
import pandas as pd

KINDS = {"Поступление", "Выплата"}

def validate_transactions(df, planned=False):
    required = ['Дата', 'Описание', 'Тип', 'Сумма']
    if not planned:
        required.append('ID')
    missing = [x for x in required if x not in df.columns]
    if missing:
        raise ValueError('Не найдены обязательные столбцы: ' + ', '.join(missing))
    df = df.copy()
    if df.empty:
        raise ValueError('Файл не содержит операций')
    if len(df) > 20000:
        raise ValueError('Демонстрационная версия поддерживает не более 20 000 строк')
    df['Дата'] = pd.to_datetime(df['Дата'], errors='coerce', format='mixed', dayfirst=False).dt.normalize()
    df['Сумма'] = pd.to_numeric(df['Сумма'], errors='coerce')
    if df['Дата'].isna().any() or df['Сумма'].isna().any():
        raise ValueError('Обнаружены неверные даты или суммы')
    if (~df['Тип'].isin(KINDS)).any():
        raise ValueError('Допустимые типы: Поступление, Выплата')
    if (~(df['Сумма'] > 0)).any():
        raise ValueError('Суммы операций должны быть строго положительными')
    if not planned:
        if df['ID'].isna().any() or df['ID'].astype(str).str.strip().eq('').any():
            raise ValueError('У каждой фактической операции должен быть ID')
        if df['ID'].astype(str).duplicated().any():
            raise ValueError('Найдены дублирующиеся ID операций')
    return df

def compute_cashflow(actual, planned, opening_balance, as_of, horizon=30, minimum_balance=250000):
    """Actual transactions on/before as_of; planned transactions strictly after as_of."""
    if opening_balance < 0 or minimum_balance < 0:
        raise ValueError('Начальный и минимальный контрольный остатки не могут быть отрицательными')
    if horizon < 1 or horizon > 365:
        raise ValueError('Горизонт должен быть от 1 до 365 дней')
    as_of = pd.Timestamp(as_of).normalize()
    actual = validate_transactions(actual, planned=False)
    planned = validate_transactions(planned, planned=True)
    if (actual['Дата'] > as_of).any():
        raise ValueError('Факт содержит операции после отчетной даты')
    if (planned['Дата'] <= as_of).any():
        raise ValueError('План содержит операции на отчетную дату или раньше')
    start = actual['Дата'].min()
    end = as_of + pd.Timedelta(days=horizon)
    daily = pd.DataFrame({'Дата': pd.date_range(start, end, freq='D')})
    daily['Режим'] = daily['Дата'].le(as_of).map({True:'Факт', False:'Прогноз'})
    both = pd.concat([actual, planned], ignore_index=True)
    sums = both.groupby(['Дата','Тип'])['Сумма'].sum().unstack(fill_value=0)
    daily['Поступления'] = daily['Дата'].map(sums['Поступление'] if 'Поступление' in sums else pd.Series(dtype=float)).fillna(0)
    daily['Выплаты'] = daily['Дата'].map(sums['Выплата'] if 'Выплата' in sums else pd.Series(dtype=float)).fillna(0)
    daily['Чистый поток'] = daily['Поступления']-daily['Выплаты']
    daily['Остаток на конец'] = float(opening_balance)+daily['Чистый поток'].cumsum()
    daily['Остаток на начало'] = daily['Остаток на конец']-daily['Чистый поток']
    daily['Сигнал'] = 'OK'
    daily.loc[daily['Остаток на конец']<minimum_balance,'Сигнал']='Низкий остаток'
    daily.loc[daily['Остаток на конец']<0,'Сигнал']='Кассовый разрыв'
    return daily
