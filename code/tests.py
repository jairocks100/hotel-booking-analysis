"""Run from root: python code/tests.py. No internet required."""
import json,runpy,sqlite3
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
m=json.loads((ROOT/'results/metrics.json').read_text())
x=pd.read_csv(ROOT/'results/clean_bookings.csv',keep_default_na=False)
assert len(x)==m['valid_rows']==11460
assert x.booking_id.is_unique
assert x.customer_loyalty_tier.eq('None').any()
assert not x.coupon_code.eq('NONE').any()
assert pd.to_datetime(x.checkout_date).gt(pd.to_datetime(x.checkin_date)).all()
assert pd.to_datetime(x.booking_date).ge(pd.to_datetime(x.customer_signup_date)).all()
assert x.num_rooms.gt(0).all()
assert m['flags']['invalid_stay']==120 and m['flags']['price_mismatch']==35
assert x.booking_status.eq('Cancelled').sum()==m['platform_cancellations']==2267
assert abs(m['scenario2_prevented']/len(x)*100-m['scenario2_pp'])<1e-10
assert m['combined_model_pp']<m['scenario1_pp']+m['scenario2_pp']<5
assert round(x.loc[x.booking_status.eq('Completed')&x.property_type.eq('Luxury'),'total_amount'].sum(),2)==56060653.54
q=pd.read_csv(ROOT/'results/sql_AQ1.csv')
g=x[x.booking_status.eq('Completed')].groupby(['property_city','property_id','property_name'],as_index=False).total_amount.sum().rename(columns={'total_amount':'revenue'})
best=g[g.revenue.eq(g.groupby('property_city').revenue.transform('max'))].sort_values(['property_city','property_id'])
assert list(q.property_id)==list(best.property_id)
assert ((q.revenue.values-best.revenue.round(2).values)**2).sum()<1e-8
z=x[x.booking_status.eq('Completed')].copy();z['checkin_date']=pd.to_datetime(z.checkin_date);z=z.sort_values(['customer_id','checkin_date','booking_id']);z['gap']=z.groupby('customer_id').checkin_date.diff().dt.days
assert int(z.groupby('customer_id').gap.mean().lt(30).sum())==m['SQL_AQ2']==247
assert len((ROOT/'project/README.md').read_text().splitlines())==6
for f in ROOT.rglob('*.py'):compile(f.read_text(),str(f),'exec')
runpy.run_path(str(ROOT/'project/weather_analyzer.py'),run_name='offline_test')['self_test']()
assert (ROOT/'Answer_Report.pdf').stat().st_size>1000
print('PASS: cohort, identity, parsing, cleaning, pricing flags, impact math, revenue, both SQL outputs, six-line README, Python compilation, offline weather tests, PDF presence.')
