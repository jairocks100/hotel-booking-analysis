"""Open-Meteo enrichment: run from any directory; --self-test never calls network."""
import argparse,json,time
from pathlib import Path
import numpy as np
import pandas as pd
import requests
ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
OUT=HERE/'output'; CACHE=HERE/'cache'
URL='https://archive-api.open-meteo.com/v1/archive'
COORDS={'Goa':(15.4909,73.8278),'Manali':(32.2432,77.1892)}
COLS=['property_city','weather_date','precipitation_sum','temperature_2m_max']

def fetch_city(city,start,end,cache_only=False):
    lat,lon=COORDS[city]
    path=CACHE/f'{city}_{start}_{end}.json'
    params={'latitude':lat,'longitude':lon,'start_date':start,'end_date':end,'daily':'precipitation_sum,temperature_2m_max','timezone':'Asia/Kolkata'}
    payload=None; errors=[]; origin='cache'
    if path.exists():
        try:payload=json.loads(path.read_text())
        except (OSError,ValueError) as e:errors.append('Invalid cache: '+str(e))
    if payload is None and not cache_only:
        origin='live'
        for attempt in range(3):
            try:
                response=requests.get(URL,params=params,timeout=(10,60))
                response.raise_for_status();payload=response.json()
                if payload.get('error'):raise ValueError(payload.get('reason','API error'))
                if 'daily' not in payload:raise ValueError('Missing daily response')
                CACHE.mkdir(exist_ok=True);path.write_text(json.dumps(payload));break
            except (requests.RequestException,ValueError,OSError) as e:
                errors.append(str(e));payload=None
                if attempt<2:time.sleep(2**attempt)
    if payload is None:
        return pd.DataFrame(columns=COLS),{'city':city,'status':'failed','origin':origin,'params':params,'errors':errors or ['No usable cache; live call disabled']}
    try:
        daily=payload['daily']
        z=pd.DataFrame({'weather_date':daily['time'],'precipitation_sum':daily['precipitation_sum'],'temperature_2m_max':daily['temperature_2m_max']})
        z['weather_date']=pd.to_datetime(z.weather_date,errors='raise').dt.normalize()
        z['property_city']=city
        for c in ['precipitation_sum','temperature_2m_max']:z[c]=pd.to_numeric(z[c],errors='coerce')
        if z.weather_date.duplicated().any():raise ValueError('Duplicate weather dates')
        if z.precipitation_sum.lt(0).any():raise ValueError('Negative precipitation')
        return z[COLS],{'city':city,'status':'ok','origin':origin,'days':len(z),'params':params,'errors':errors}
    except (KeyError,TypeError,ValueError) as e:
        return pd.DataFrame(columns=COLS),{'city':city,'status':'failed','origin':origin,'params':params,'errors':errors+[str(e)]}

def merge_weather(bookings,weather):
    b=bookings.copy();b['weather_date']=pd.to_datetime(b.checkin_date).dt.normalize()
    w=weather.copy();w['weather_date']=pd.to_datetime(w.weather_date).dt.normalize()
    m=b.merge(w,on=['property_city','weather_date'],how='left',validate='many_to_one',indicator='weather_match')
    assert len(m)==len(b),'Join changed booking count'
    m['cancelled']=m.booking_status.eq('Cancelled').astype(int)
    m['no_show']=m.booking_status.eq('No-Show').astype(int)
    m['adverse']=(m.cancelled+m.no_show).astype(int)
    for label,column,test in [('heavy_rain','precipitation_sum',lambda s:s.ge(20)),('hot','temperature_2m_max',lambda s:s.ge(35)),('cold','temperature_2m_max',lambda s:s.le(5))]:
        m[label]=test(m[column]).astype('boolean').mask(m[column].isna(),pd.NA)
    m['weather_available']=m[['precipitation_sum','temperature_2m_max']].notna().all(axis=1)
    m['any_exposure']=(m.heavy_rain|m.hot|m.cold).mask(~m.weather_available,pd.NA)
    m['month']=m.weather_date.dt.month
    return m

def self_test():
    b=pd.DataFrame({'booking_id':[1,2,3,4],'property_city':['Goa','Goa','Manali','Manali'],'checkin_date':['2024-07-01']*4,'booking_status':['Cancelled','Completed','No-Show','Completed']})
    w=pd.DataFrame({'property_city':['Goa','Manali'],'weather_date':['2024-07-01']*2,'precipitation_sum':[25,None],'temperature_2m_max':[30,None]})
    m=merge_weather(b,w)
    assert len(m)==4 and m.booking_id.is_unique
    assert m.loc[m.property_city.eq('Goa'),'heavy_rain'].all()
    assert m.loc[m.property_city.eq('Manali'),'any_exposure'].isna().all()
    assert m.adverse.sum()==2
    try:merge_weather(b,pd.concat([w,w.iloc[[0]]],ignore_index=True))
    except pd.errors.MergeError:pass
    else:raise AssertionError('Duplicate weather key was not rejected')
    print('PASS: merge count, city+date keys, exposure, missingness, adverse outcome, duplicate-key rejection. Synthetic fixtures only.')

def main(cache_only=False):
    OUT.mkdir(exist_ok=True)
    source=ROOT/'results/clean_bookings.csv'
    if not source.exists():
        status={'status':'blocked','reason':'Run python code/analysis.py first.'}
        (OUT/'status.json').write_text(json.dumps(status,indent=2));print(status);return
    b=pd.read_csv(source,keep_default_na=False)
    b['checkin_date']=pd.to_datetime(b.checkin_date,errors='coerce')
    b=b[b.property_city.isin(COORDS)&b.checkin_date.dt.year.eq(2024)].copy()
    frames=[];calls=[]
    for city,g in b.groupby('property_city'):
        start=g.checkin_date.min().strftime('%Y-%m-%d');end=g.checkin_date.max().strftime('%Y-%m-%d')
        frame,call=fetch_city(city,start,end,cache_only);frames.append(frame);calls.append(call)
    w=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame(columns=COLS)
    w.to_csv(OUT/'city_date_weather.csv',index=False)
    m=merge_weather(b,w);m.to_csv(OUT/'weather_enriched_bookings.csv',index=False)
    records=[]
    for exposure in ['heavy_rain','hot','cold','any_exposure']:
        eligible=m[m[exposure].notna()]
        for city,g in [('All',eligible)]+list(eligible.groupby('property_city')):
            for exposed,h in g.groupby(exposure):
                records.append({'exposure':exposure,'city':city,'exposed':bool(exposed),'bookings':len(h),'adverse_count':int(h.adverse.sum()),'adverse_rate':h.adverse.mean(),'cancel_count':int(h.cancelled.sum()),'cancel_rate':h.cancelled.mean(),'no_show_count':int(h.no_show.sum()),'no_show_rate':h.no_show.mean()})
    groups=pd.DataFrame(records,columns=['exposure','city','exposed','bookings','adverse_count','adverse_rate','cancel_count','cancel_rate','no_show_count','no_show_rate'])
    groups.to_csv(OUT/'weather_groups.csv',index=False)
    strata=[]
    for (city,month),g in m[m.any_exposure.notna()].groupby(['property_city','month']):
        e=g[g.any_exposure.eq(True)];u=g[g.any_exposure.eq(False)]
        if len(e) and len(u):strata.append({'city':city,'month':int(month),'weight':len(g),'exposed_n':len(e),'unexposed_n':len(u),'risk_difference':float(e.adverse.mean()-u.adverse.mean())})
    pd.DataFrame(strata,columns=['city','month','weight','exposed_n','unexposed_n','risk_difference']).to_csv(OUT/'city_month_contrasts.csv',index=False)
    n=int(m.weather_available.sum())
    status={'status':'complete' if n==len(m) and n>0 else 'partial' if n>0 else 'failed','sample_bookings':len(m),'complete_weather_bookings':n,'calls':calls,'successful_live_calls':sum(c['status']=='ok' and c['origin']=='live' for c in calls),'limitation':'Observed check-in weather is not necessarily known at cancellation; association is not causation.'}
    (OUT/'status.json').write_text(json.dumps(status,indent=2))
    e=m[m.any_exposure.eq(True).fillna(False)];u=m[m.any_exposure.eq(False).fillna(False)]
    if len(e) and len(u):
        diff=100*(e.adverse.mean()-u.adverse.mean())
        adjusted=sum(s['weight']*s['risk_difference'] for s in strata)/sum(s['weight'] for s in strata)*100 if strata else None
        sentence=f'Within {len(strata)} city-month strata containing both exposed and unexposed bookings, the booking-weighted within-stratum difference is {adjusted:.2f} percentage points.' if adjusted is not None else 'No city-month stratum has both groups, so a within-season comparison cannot be estimated.'
        insight=(f'Weather availability covers {n}/{len(m)} sampled bookings; on heavy-rain (>=20 mm), hot (>=35 C) or cold (<=5 C) days, {int(e.adverse.sum())}/{len(e)} bookings cancelled or no-showed ({e.adverse.mean():.2%}), versus {int(u.adverse.sum())}/{len(u)} ({u.adverse.mean():.2%}) on other observed-weather days. '
                 f'The unadjusted difference is {diff:.2f} percentage points. '+sentence+' Actual check-in weather, city-grid coordinates and unknown cancellation timing prevent causal interpretation; missing weather is excluded rather than classified as benign.')
    else:
        insight=f'No defensible exposed-versus-unexposed weather insight can be estimated: complete weather covers {n}/{len(m)} bookings, exposed n={len(e)}, unexposed n={len(u)}. No missing values have been treated as dry or normal-temperature days. Consult status.json for retrieval diagnostics. A successful live API run with both exposure groups is required before submitting this section.'
    (OUT/'insight.md').write_text('# Weather insight\n\n'+insight+'\n')
    print(json.dumps(status,indent=2));print(insight)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--self-test',action='store_true');parser.add_argument('--cache-only',action='store_true');args=parser.parse_args()
    if args.self_test:self_test()
    else:main(args.cache_only)
