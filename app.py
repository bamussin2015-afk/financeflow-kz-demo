from io import BytesIO
import hashlib
from pathlib import Path
import pandas as pd
import streamlit as st
from core import compute_cashflow, validate_transactions

st.set_page_config(page_title='FinanceFlow KZ 2.0', page_icon='📊', layout='wide')
st.title('FinanceFlow KZ 2.1 — сценарный Cash Flow')
st.caption('Демо на синтетических данных · KZT · редактор плана · сравнение сценариев')
st.warning('Публичное демо: не загружайте реальные банковские выписки или конфиденциальную информацию. Нет авторизации и долговременного хранения данных.')
BASE = Path(__file__).resolve().parent

def read_file(upload, fallback):
    if upload is None:
        frame = pd.read_csv(BASE / fallback, encoding='utf-8-sig')
    else:
        if upload.size > 5_000_000:
            raise ValueError('Файл превышает 5 МБ')
        if upload.name.lower().endswith('.csv'):
            frame = pd.read_csv(upload, sep=None, engine='python', encoding='utf-8-sig')
        elif upload.name.lower().endswith('.xlsx'):
            frame = pd.read_excel(upload)
        else:
            raise ValueError('Используйте CSV или XLSX')
    frame.columns = frame.columns.astype(str).str.replace('\ufeff', '', regex=False).str.strip()
    return frame

def money(value):
    return f'{value:,.0f}'.replace(',', ' ') + ' ₸'

def summary(daily, date):
    outlook=daily[daily['Дата'] > pd.Timestamp(date)]
    if outlook.empty:
        raise ValueError('Нет прогнозных дней')
    minimum=float(outlook['Остаток на конец'].min())
    negative=outlook[outlook['Остаток на конец'] < 0]
    return minimum, max(0,-minimum), (negative['Дата'].iloc[0] if not negative.empty else None)

with st.sidebar:
    st.header('Параметры')
    as_of=st.date_input('Отчетная дата',value=pd.Timestamp('2026-10-14').date())
    opening=st.number_input('Начальный остаток, ₸',min_value=0,value=1200000,step=100000)
    minimum=st.number_input('Контрольный остаток, ₸',min_value=0,value=250000,step=50000)
    horizon=st.slider('Прогноз, дней',7,90,30)

st.subheader('1. Исходные файлы')
c1,c2=st.columns(2)
with c1:
    actual_upload=st.file_uploader('Факт (CSV/XLSX)', type=['csv','xlsx'],key='actual')
    st.download_button('Скачать пример факта',(BASE/'demo_actual.csv').read_bytes(),'demo_actual.csv','text/csv')
with c2:
    plan_upload=st.file_uploader('План (CSV/XLSX)',type=['csv','xlsx'],key='planned')
    st.download_button('Скачать пример плана',(BASE/'demo_plan.csv').read_bytes(),'demo_plan.csv','text/csv')
try:
    actual=read_file(actual_upload,'demo_actual.csv')
    original_plan=read_file(plan_upload,'demo_plan.csv')
    original_plan=validate_transactions(original_plan,planned=True)
    actual=validate_transactions(actual,planned=False)
    original_plan=original_plan.copy(deep=True)
    baseline=compute_cashflow(actual,original_plan.copy(deep=True),opening,as_of,horizon,minimum)
except (ValueError,KeyError,TypeError,pd.errors.ParserError) as exc:
    st.error(f'Не удалось прочитать исходные данные: {exc}')
    st.stop()
except Exception:
    st.error('Не удалось обработать файлы. Используйте тестовые шаблоны CSV/XLSX.')
    st.stop()

st.subheader('2. Редактирование платежного календаря')
st.info('**Базовый сценарий** всегда рассчитывается из загруженного CSV/XLSX, а не из таблицы ниже. Для начала теста загрузите оригинальный `demo_plan.csv` из архива.')
reference_date=pd.Timestamp('2026-10-29')
def payment_on(df,date):
    return float(df.loc[(df['Дата'].eq(date)) & (df['Тип'].eq('Выплата')), 'Сумма'].sum())
st.write('**Исходная выплата 29.10.2026 (из файла, до редактирования):**',money(payment_on(original_plan,reference_date)))
if payment_on(original_plan,reference_date) != 5600000:
    st.warning('Исходная выплата за 29.10.2026 отличается от 5 600 000 ₸. Убедитесь, что не загружен ранее измененный CSV.')
source_key=(plan_upload.getvalue() if plan_upload is not None else (BASE/'demo_plan.csv').read_bytes())
source_id=hashlib.sha256(source_key).hexdigest()[:12]
if st.session_state.get('active_source') != source_id:
    st.session_state['active_source']=source_id
    st.session_state['editor_generation']=st.session_state.get('editor_generation',0)+1
if st.button('↩️ Сбросить изменения: вернуться к исходному плану'):
    st.session_state['editor_generation']=st.session_state.get('editor_generation',0)+1
    st.rerun()
editor_key='plan_editor_'+source_id+'_'+str(st.session_state.get('editor_generation',0))

st.caption('Изменяйте дату, сумму, тип и описание операции, добавляйте или удаляйте строки. Сценарий изменяется только в этом сеансе; исходный CSV не перезаписывается.')
editable=original_plan[['Дата','Описание','Тип','Сумма']].copy()
editable['Дата']=editable['Дата'].dt.date
edited=st.data_editor(
    editable,hide_index=True,num_rows='dynamic',use_container_width=True,
    column_config={
        'Дата':st.column_config.DateColumn('Дата',required=True,format='DD.MM.YYYY'),
        'Описание':st.column_config.TextColumn('Описание',required=True),
        'Тип':st.column_config.SelectboxColumn('Тип',options=['Поступление','Выплата'],required=True),
        'Сумма':st.column_config.NumberColumn('Сумма, ₸',min_value=0.01,required=True,format='%.0f'),
    },key=editor_key
)
try:
    if edited.empty:
        raise ValueError('Платежный календарь не может быть пустым')
    edited['Дата']=pd.to_datetime(edited['Дата'],errors='coerce')
    edited['Сумма']=pd.to_numeric(edited['Сумма'],errors='coerce')
    scenario_plan=validate_transactions(edited,planned=True)
    scenario=compute_cashflow(actual,scenario_plan.copy(deep=True),opening,as_of,horizon,minimum)
except (ValueError, KeyError,TypeError) as exc:
    st.error(f'Ошибка в измененном плане: {exc}. Исправьте значения в таблице.')
    st.stop()

st.write('**Выплата 29.10.2026 в измененном плане:**',money(payment_on(scenario_plan,reference_date)))
st.caption('Для сравнения: исходные и измененные платежи должны отличаться. Если они одинаковы, разница в прогнозе будет равна нулю.')
st.subheader('3. Сравнение сценариев')
as_of_ts=pd.Timestamp(as_of)
fact=baseline[baseline['Дата']<=as_of_ts]
current=float(fact['Остаток на конец'].iloc[-1])
base_min,base_short,base_first=summary(baseline,as_of)
scenario_min,scenario_short,scenario_first=summary(scenario,as_of)
a,b,c,d=st.columns(4)
a.metric('Фактический остаток',money(current))
b.metric('Минимум: исходный план',money(base_min))
c.metric('Минимум: измененный план',money(scenario_min),delta=money(scenario_min-base_min))
d.metric('Дефицит: измененный план',money(scenario_short),delta=money(base_short-scenario_short),delta_color='normal')
if scenario_first is not None:
    st.error(f'Кассовый разрыв по сценарию: {scenario_first:%d.%m.%Y}; максимальный дефицит {money(scenario_short)}.')
elif scenario_min < minimum:
    st.warning('Отрицательного остатка нет, но прогноз опускается ниже контрольного уровня.')
else:
    st.success('Отрицательных остатков и нарушений контрольного уровня в горизонте не выявлено.')

comparison=pd.DataFrame({
    'Дата':baseline['Дата'],
    'Исходный план':baseline['Остаток на конец'],
    'Измененный план':scenario['Остаток на конец'],
})
comparison['Разница']=comparison['Измененный план']-comparison['Исходный план']
st.line_chart(comparison.set_index('Дата')[['Исходный план','Измененный план']])
st.caption('График включает фактический период и прогноз. Изменение платежей за пределами выбранного горизонта не влияет на расчет.')

if abs(base_min-scenario_min)<0.01:
    st.info('Минимумы одинаковы. Если вы еще не редактировали план, это нормально. Измените именно выплату «Крупная партия товара» и проверьте, что выше появились разные исходная и измененная суммы.')
st.subheader('4. Детализация и выгрузка')
tab1,tab2,tab3,tab4=st.tabs(['Сравнение по дням','Денежные потоки: сценарий','Измененный план','Исходный план'])
with tab1:
    st.dataframe(comparison,hide_index=True,use_container_width=True)
with tab2:
    st.dataframe(scenario,hide_index=True,use_container_width=True)
with tab3:
    st.dataframe(scenario_plan,hide_index=True,use_container_width=True)
with tab4:
    st.dataframe(original_plan,hide_index=True,use_container_width=True)

out=BytesIO()
with pd.ExcelWriter(out,engine='xlsxwriter',datetime_format='dd.mm.yyyy') as writer:
    comparison.to_excel(writer,sheet_name='Сравнение',index=False)
    baseline.to_excel(writer,sheet_name='Базовый CashFlow',index=False)
    scenario.to_excel(writer,sheet_name='Сценарный CashFlow',index=False)
    actual.to_excel(writer,sheet_name='Факт',index=False)
    original_plan.to_excel(writer,sheet_name='Исходный план',index=False)
    scenario_plan.to_excel(writer,sheet_name='Измененный план',index=False)
st.download_button('📥 Скачать сравнение и оба сценария в Excel',out.getvalue(),'FinanceFlow_KZ_Scenarios.xlsx',mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',type='primary')
st.caption('Расчет основан на загруженном платежном календаре. Это не статистический прогноз будущих поступлений.')
