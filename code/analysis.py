"""Reproducible Set A analysis. Run from package root: python code/analysis.py."""
import json, sqlite3, calendar
from pathlib import Path
import pandas as pd
import numpy as np
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, Preformatted
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.enums import TA_LEFT
from reportlab.graphics.shapes import Drawing, Rect, String
from xml.sax.saxutils import escape
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results'; OUT.mkdir(exist_ok=True)
d=pd.read_excel(ROOT/'data/hotel_bookings.xlsx',keep_default_na=False)
assert d.shape==(12000,28)
for col in ['booking_date','checkin_date','checkout_date','customer_signup_date','review_date']:
    d[col]=pd.to_datetime(d[col],errors='coerce')
for col in ['adr','discount_amount','total_amount','review_rating','num_rooms','nights']:
    d[col]=pd.to_numeric(d[col],errors='coerce')
f=pd.DataFrame(index=d.index)
f['invalid_stay']=d.checkout_date.le(d.checkin_date)
f['before_signup']=d.booking_date.lt(d.customer_signup_date)
f['zero_rooms']=d.num_rooms.le(0)
f['negative_lead']=d.checkin_date.lt(d.booking_date)
f['price_mismatch']=(d.total_amount-(d.adr*d.nights*d.num_rooms-d.discount_amount)).abs().gt(.011)
f['nights_mismatch']=d.nights.ne((d.checkout_date-d.checkin_date).dt.days)
f['cancelled_review']=d.booking_status.eq('Cancelled') & d.review_rating.notna()
base_errors=f[['invalid_stay','before_signup','zero_rooms','negative_lead']].any(axis=1)
x=d.loc[~base_errors].copy()
x['lead_days']=(x.checkin_date-x.booking_date).dt.days
x['month']=x.checkin_date.dt.month
x['cancelled']=x.booking_status.eq('Cancelled').astype(int)
x['adverse']=x.booking_status.isin(['Cancelled','No-Show']).astype(int)
x['coupon_code']=x.coupon_code.replace({'':'','NONE':''})
x['normalized_review']=x.review_rating/np.where(x.customer_segment.eq('Corporate'),2,1)
x.loc[x.booking_status.ne('Completed'),'normalized_review']=np.nan
N=len(x); C=int(x.cancelled.sum()); R=C/N
land=x.groupby(['property_city','month']).agg(bookings=('booking_id','size'),cancellations=('cancelled','sum'))
land['rate']=land.cancellations/land.bookings
land=land.reset_index()
by_rate=land.sort_values(['rate','bookings','property_city','month'],ascending=[False,False,True,True])
by_count=land.sort_values(['cancellations','rate','property_city','month'],ascending=[False,False,True,True])
w=by_rate.iloc[0]; city=w.property_city; month=int(w.month)
wm=x.property_city.eq(city)&x.month.eq(month); a=x[wm]; rest=x[~wm]
L=x.lead_days.gt(30); nL=int(L.sum()); CL=int(x.loc[L,'cancelled'].sum()); nS=int((~L).sum()); CS=int(x.loc[~L,'cancelled'].sum())
rL=CL/nL; rS=CS/nS
p1=len(a)*(a.cancelled.mean()-R); p2=nL*(rL-rS)
pp1=100*p1/N; pp2=100*p2/N
reviews=d.groupby('customer_segment').review_rating.agg(['min','max','mean','count']).reset_index()
lux=x.property_type.eq('Luxury')&x.booking_status.eq('Completed')
lux_reported=round(x.loc[lux,'total_amount'].sum(),2)
lux_reconciled=round((x.loc[lux,'adr']*x.loc[lux,'nights']*x.loc[lux,'num_rooms']-x.loc[lux,'discount_amount']).sum(),2)
lux_quarantine=round(x.loc[lux&~f.price_mismatch.reindex(x.index),'total_amount'].sum(),2)
channels=pd.DataFrame({'slice_share':a.booking_channel.value_counts(normalize=True),'rest_share':rest.booking_channel.value_counts(normalize=True),'slice_cancel_rate':a.groupby('booking_channel').cancelled.mean(),'rest_cancel_rate':rest.groupby('booking_channel').cancelled.mean()}).fillna(0).reset_index().rename(columns={'index':'booking_channel'})
lead_expected=sum(a.lead_days.gt(30).value_counts(normalize=True).get(k,0)*rest.loc[rest.lead_days.gt(30).eq(k),'cancelled'].mean() for k in [True,False])
channel_expected=sum(a.booking_channel.value_counts(normalize=True)*rest.groupby('booking_channel').cancelled.mean())
other_city='Manali' if city!='Manali' else 'Goa'
season=x[x.property_city.eq(city)&x.month.ne(month)]
comparison=x[x.property_city.eq(other_city)&x.month.eq(month)]
# Variation measured by booking-weighted between-group variance in cancellation probabilities.
variance=[]
for dims in [['property_city'],['month'],['booking_channel'],['lead_days'],['property_city','month']]:
    g=x.groupby(dims).cancelled.agg(['size','mean'])
    variance.append({'dimension':' x '.join(dims),'weighted_between_variance':float((g['size']*(g['mean']-R)**2).sum()/N),'max_minus_min_pp':float((g['mean'].max()-g['mean'].min())*100)})
variance=pd.DataFrame(variance)
audit=pd.concat([d,f.add_prefix('flag_')],axis=1)
audit.to_csv(OUT/'row_audit.csv',index=False)
x.to_csv(OUT/'clean_bookings.csv',index=False)
land.to_csv(OUT/'city_month_landscape.csv',index=False)
channels.to_csv(OUT/'channel_diagnosis.csv',index=False)
reviews.to_csv(OUT/'segment_raw_reviews.csv',index=False)
variance.to_csv(OUT/'dimension_variance.csv',index=False)
# Verify customer/property denormalization is consistent before dimension extraction.
customer_cols=['customer_id','customer_name','customer_segment','customer_signup_date','customer_home_city','customer_loyalty_tier']
property_cols=['property_id','property_name','property_city','property_star_rating','property_type','property_total_rooms']
for cols in [customer_cols,property_cols]:
    assert not d[cols].drop_duplicates().duplicated(cols[0]).any(), 'Conflicting dimension attributes require resolution.'
con=sqlite3.connect(':memory:'); con.executescript((ROOT/'code/schema.sql').read_text())
def load(table,frame):
    z=frame.copy()
    for c in z.columns:
        if pd.api.types.is_datetime64_any_dtype(z[c]):z[c]=z[c].dt.strftime('%Y-%m-%d')
    z=z.astype(object).where(z.notna(),None)
    con.executemany('INSERT INTO '+table+' ('+','.join(z.columns)+') VALUES ('+','.join('?'*len(z.columns))+')',z.itertuples(index=False,name=None))
load('customers',d[customer_cols].drop_duplicates())
load('properties',d[property_cols].drop_duplicates())
booking_cols=['booking_id','customer_id','property_id','booking_date','checkin_date','checkout_date','room_type','num_rooms','nights','booking_channel','adr','discount_amount','coupon_code','total_amount','payment_method','booking_status']
b=x[booking_cols].copy(); b['coupon_code']=b.coupon_code.replace('',None);load('bookings',b)
v=x[x.normalized_review.notna()][['booking_id','normalized_review','review_date']].rename(columns={'normalized_review':'review_rating'});load('reviews',v)
sql=(ROOT/'code/queries.sql').read_text(); statements=[s.strip() for s in '\n'.join(line.split('--')[0] for line in sql.splitlines()).split(';') if s.strip()]
q1=pd.read_sql_query(statements[0],con);q2=pd.read_sql_query(statements[1],con)
q1.to_csv(OUT/'sql_AQ1.csv',index=False);q2.to_csv(OUT/'sql_AQ2.csv',index=False)
# Independently cross-check A-Q2 with pandas.
z=x[x.booking_status.eq('Completed')].sort_values(['customer_id','checkin_date','booking_id']).copy()
z['gap']=z.groupby('customer_id').checkin_date.diff().dt.days
pandas_q2=int(z.groupby('customer_id').gap.mean().lt(30).sum())
assert pandas_q2==int(q2.iloc[0,0])
# Combined scenario: apply short-lead reference first, then only residual excess in worst slice.
long_in_slice=int(a.lead_days.gt(30).sum())
combined_remaining_excess=max(0,p1-long_in_slice*(rL-rS))
combined=p2+combined_remaining_excess
metrics={'raw_rows':len(d),'valid_rows':N,'excluded_union':int(base_errors.sum()),'flags':{k:int(v) for k,v in f.sum().items()},'platform_cancellations':C,'platform_rate':R,'luxury_realized_reported':lux_reported,'luxury_formula_sensitivity':lux_reconciled,'luxury_quarantine_sensitivity':lux_quarantine,'worst_city':city,'worst_month':month,'worst_n':len(a),'worst_cancel':int(a.cancelled.sum()),'scenario1_prevented':p1,'scenario1_pp':pp1,'scenario2_prevented':p2,'scenario2_pp':pp2,'combined_model_prevented':combined,'combined_model_pp':100*combined/N,'SQL_AQ2':pandas_q2,'weather_status':'UNVERIFIED: live API calls failed in build environment; no weather effect estimated'}
(OUT/'metrics.json').write_text(json.dumps(metrics,indent=2))
styles=getSampleStyleSheet();styles['BodyText'].fontSize=9;styles['BodyText'].leading=13
styles['Heading1'].fontSize=17;styles['Heading2'].fontSize=12
story=[]
def p(t,style='BodyText'):story.append(Paragraph(escape(str(t)),styles[style]));story.append(Spacer(1,5))
def title(t):p(t,'Heading1')
def heading(t):p(t,'Heading2')
def table(headers,rows,widths=None):
    vals=[[Paragraph(escape(str(c)),styles['BodyText']) for c in headers]]+[[Paragraph(escape(str(c)),styles['BodyText']) for c in row] for row in rows]
    t=Table(vals,colWidths=widths,repeatRows=1,hAlign='LEFT');t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#dbeafe')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.35,colors.lightgrey),('BOTTOMPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),5)]));story.append(t);story.append(Spacer(1,8))
def newpage():story.append(PageBreak())
def rate(c):return f'{100*c:.2f}%'
def heatmap():
    dr=Drawing(510,265); cw=32;ch=20; cities=sorted(x.property_city.unique())
    for j in range(1,13):dr.add(String(108+(j-1)*cw,245,calendar.month_abbr[j],fontSize=8))
    for i,c in enumerate(cities):
        y=220-i*ch;dr.add(String(4,y+6,c,fontSize=9))
        for j in range(1,13):
            row=land[(land.property_city==c)&(land.month==j)].iloc[0];v=float(row.rate); intensity=min(v/.55,1)
            dr.add(Rect(102+(j-1)*cw,y,cw-1,ch-1,fillColor=colors.Color(1,1-.72*intensity,1-.78*intensity),strokeColor=None))
            dr.add(String(105+(j-1)*cw,y+6,f'{v*100:.1f}',fontSize=8))
    dr.add(String(4,6,'Cancellation rate (%) by check-in month; full n and counts in city_month_landscape.csv.',fontSize=8))
    return dr

def bars():
    vals=[('Goa July (20/38)',a.cancelled.mean()),('Rest of platform',rest.cancelled.mean()),('Goa other months',season.cancelled.mean()),('Manali July',comparison.cancelled.mean()),('Lead-mix expected',lead_expected),('Channel-mix expected',channel_expected)]
    dr=Drawing(510,190)
    for i,(label,v) in enumerate(vals):
        y=160-i*25;dr.add(String(0,y+4,label,fontSize=9));dr.add(Rect(155,y,v*540,15,fillColor=colors.HexColor('#2563eb'),strokeColor=None));dr.add(String(160+v*540,y+4,rate(v),fontSize=9))
    dr.add(String(0,2,'Expected = slice mix weighted by rest-of-platform category-specific cancellation rates.',fontSize=8))
    return dr

title('Business Analyst Assessment - Set A')
p('Rebuilt from BATaskA.pdf and hotel_bookings.xlsx | 21 October 2026')
p('Status: Sections 1-3 computed and SQL executed. Section 4 code supplied, but weather enrichment and insight remain unverified because live API retrieval failed. This package is not a fully complete submission.')
heading('Data contract, cleaning and denominators')
p(f'Raw data: {len(d):,} rows and 28 columns. Retain the literal loyalty value None using keep_default_na=False. Dates are parsed explicitly; blank reviews become missing numeric values. Invalid stays, booking-before-signup rows and zero-room rows are excluded jointly: {int(base_errors.sum()):,} distinct rows removed, leaving N={N:,}. Negative lead time is also screened; none occur. Flag counts overlap and must not be added.')
table(['Rule','Affected raw rows','Treatment'],[['Invalid stay',int(f.invalid_stay.sum()),'Exclude booking'],['Booking before signup',int(f.before_signup.sum()),'Exclude booking'],['Zero rooms',int(f.zero_rooms.sum()),'Exclude booking'],['Cancelled review',int(f.cancelled_review.sum()),'Null analytical rating, retain booking if otherwise valid'],['Formula mismatch',int(f.price_mismatch.sum()),'Flag and retain booked amount pending reconciliation']],[150,95,265])
p('Use property_id as property identity. Normalize blank and NONE coupons to one no-coupon category. Only Completed bookings contribute realized revenue. Corporate ratings are divided by two for a common 1-5 maximum scale; this is a declared proportional convention, not an assertion that the rating instruments are psychometrically equivalent. Raw segment statistics are shown before rating cleaning for DQ2.')
p('Cancellation denominator includes Completed, Cancelled and No-Show valid bookings; numerator is Cancelled only. Months refer to check-in month, not booking month. Pricing/review-only issues do not invalidate a cancellation status. All CS tables use the same N unless explicitly comparing a subset.')
heading('Section 1 - Data forensics')
p(f'DQ1. Invalid stays: {int(f.invalid_stay.sum())} bookings, counted on raw records before exclusions.')
table(['DQ2 segment','Min','Max','Mean','Reviews'],[[r.customer_segment,int(r['min']),int(r['max']),f'{r["mean"]:.6f}',int(r['count'])] for _,r in reviews.iterrows()],[140,65,65,110,130])
p('Implication: Corporate reviews use a 1-10 instrument while Individual and Group use 1-5; a pooled raw mean confounds scale with satisfaction. Observed Corporate minimum is 3, not the theoretical minimum 1.')
p(f'DQ3. Luxury realized revenue = Rs {lux_reported:,.2f}, summing recorded total_amount on Completed Luxury bookings after joint exclusion of invalid stays, bookings before signup and zero rooms. No imputation of dates or revenue; coupon recoding and rating cleaning do not change this amount.')
p(f'Pricing ambiguity is material: four valid Completed Luxury bookings have formula discrepancies. Primary answer preserves the recorded amount. Quarantining those rows gives Rs {lux_quarantine:,.2f}; recomputing their values from the stated formula gives Rs {lux_reconciled:,.2f}. These are reconciliation sensitivities, not silently substituted revenue.')
p(f'DQ4. Undocumented issue: {int(f.price_mismatch.sum())} records violate total_amount = adr x nights x num_rooms - discount_amount, beyond a Rs 0.011 rounding tolerance. Example booking 100016: recorded Rs 12,057.41 versus Rs 13,397.12 implied by 3349.28 x 4 x 1 - 0. Preserve raw values, flag discrepancies and reconcile against payment/discount ledger before financial reporting; do not assume the computed value is the true paid amount. row_audit.csv identifies every affected booking.')
newpage();title('Section 2 - Cancellation crisis')
heading('CS1. Cancellation landscape')
p(f'Raw cancellation rate is {rate(d.booking_status.eq("Cancelled").mean())}; cleaned rate is {C:,}/{N:,} = {rate(R)}. The 12% industry benchmark is supplied by the assessment, not independently validated.')
story.append(heatmap())
p('Figure 1. City x check-in month heatmap. Each cell is its cancellation percentage; counts are provided separately to avoid disguising small samples. No minimum-size filter was used: the smallest cell has '+str(int(land.bookings.min()))+' bookings. The worst-rate cell is selected over all 120 city-month cells, so winner selection inflates apparent extremeness.')
table(['Dimension','Weighted between-group variance','Rate range (pp)'],[[r.dimension,f'{r.weighted_between_variance:.6f}',f'{r.max_minus_min_pp:.2f}'] for _,r in variance.iterrows()],[185,190,135])
p('The city-month combination provides the strongest separation among the tested groupings (variance 0.002005 and a 42.63 pp range). Among single dimensions, exact lead time has the largest weighted variance (0.000557), followed by channel (0.000482); city alone is weakest (0.000098). The local worst-rate concentration is Goa in summer, even though its July cell is not long-lead or OTA-heavy.')
p('Variance is sum[n_g x (r_g - r_platform)^2] / N, in squared probability units. Exact lead_days is a categorical dimension here. Joint city-month variation is a descriptive landscape, not a causal decomposition; more granular groupings tend to explain more in-sample variation. Interpret the table with the diagnostic comparisons below, not as proof of a driver.')
heading('CS2. Rate versus volume: identical city-month slice definition')
table(['Ranking','Slice','Bookings','Cancels','Rate'],[['Top rate '+str(i+1),r.property_city+' '+calendar.month_name[int(r.month)],int(r.bookings),int(r.cancellations),rate(r.rate)] for i,(_,r) in enumerate(by_rate.head(3).iterrows())]+[['Top count '+str(i+1),r.property_city+' '+calendar.month_name[int(r.month)],int(r.bookings),int(r.cancellations),rate(r.rate)] for i,(_,r) in enumerate(by_count.head(3).iterrows())],[80,145,90,90,105])
p('The lists do not overlap. Goa summer cells have severe rates but low volumes; Kochi and Mumbai cells contain more cancellations. The board needs prevented cancellations divided by all platform bookings, so rate severity alone does not identify the largest lever.')
heading('CS3. Competing explanations')
story.append(bars())
p('Figure 2. Observed city-season comparisons versus mix-based expected rates. Both mix models use rates estimated outside the selected worst cell, reducing direct contamination from that cell.')
table(['Lead-time comparison','Goa July','Rest'],[['Mean days',f'{a.lead_days.mean():.2f}',f'{rest.lead_days.mean():.2f}'],['Median days',f'{a.lead_days.median():.0f}',f'{rest.lead_days.median():.0f}'],['25th / 75th percentile',f'{a.lead_days.quantile(.25):.0f} / {a.lead_days.quantile(.75):.0f}',f'{rest.lead_days.quantile(.25):.0f} / {rest.lead_days.quantile(.75):.0f}'],['Share over 30 days',rate(a.lead_days.gt(30).mean()),rate(rest.lead_days.gt(30).mean())]],[240,135,135])
p(f'Hypothesis 1, long-lead mix: not supported as an explanation for this cell. Its lead times are shorter, and weighting rest-of-platform <=30/>30-day rates by the cell mix predicts {rate(lead_expected)}, versus observed {rate(a.cancelled.mean())}. Long lead remains a separate platform-wide association.')
table(['Channel','Slice mix','Rest mix','Slice rate','Rest rate'],[[r.booking_channel,rate(r.slice_share),rate(r.rest_share),rate(r.slice_cancel_rate),rate(r.rest_cancel_rate)] for _,r in channels.iterrows()],[150,90,90,90,90])
p(f'Hypothesis 2, channel mix: not supported as the main explanation. The slice has less OTA exposure and more Direct Website exposure. Applying rest channel-specific rates to its channel mix predicts {rate(channel_expected)}, far below {rate(a.cancelled.mean())}. This comparison weakens a mix-only explanation; it does not prove all channel-related mechanisms absent.')
p(f'Hypothesis 3, city-season interaction: best descriptively supported. Goa July is {int(a.cancelled.sum())}/{len(a)}={rate(a.cancelled.mean())}, Goa other months is {int(season.cancelled.sum())}/{len(season)}={rate(season.cancelled.mean())}, and Manali July is {int(comparison.cancelled.sum())}/{len(comparison)}={rate(comparison.cancelled.mean())}. Goa June and August also rank highly. The data supports a Goa-summer concentration, not a proven weather mechanism; cancellation timestamps/reasons and a larger season sample are needed. These are stratified diagnostic comparisons rather than randomized causal tests.')
newpage();title('Section 2 - Impact and recommendation')
heading('CS4. Two fixed-denominator what-if scenarios')
p(f'(i) Worst cell to original platform average: 38 x (20/38 - {C}/{N}) = {p1:.4f} expected cancellations prevented. Platform reduction = {p1:.4f}/{N} x 100 = {pp1:.4f} percentage points. New rate = {100*R-pp1:.4f}%. Original platform average is the reference, not a recursively recomputed rate.')
p(f'(ii) Long-lead intervention: >30 days has {CL}/{nL} = {rate(rL)}; <=30 days has {CS}/{nS} = {rate(rS)}. Prevented = {nL} x ({CL}/{nL} - {CS}/{nS}) = {p2:.4f}; platform reduction = {p2:.4f}/{N} x 100 = {pp2:.4f} pp. New rate = {100*R-pp2:.4f}%. Long lead has the larger absolute effect because it covers {nL:,} bookings rather than 38. Fractional counts are expectations, not observed avoided events.')
heading('CS5. One targeted intervention, with explicitly assumed efficacy')
p(f'WHO: all valid bookings with lead_days >30, across every city, channel and customer segment. WHAT: pilot a 10% refundable-until-30-days-before-arrival deposit, with 50% deposit refund from 30 to 8 days and no deposit refund in the final 7 days, disclosed before purchase. Provide a narrowly defined documented-emergency exception. This is a proposed policy, not an existing data attribute.')
p(f'Assume the pilot closes 25%-60% of the observed long-versus-short cancellation gap. Expected prevented cancellations = {p2:.4f} x [0.25,0.60] = [{p2*.25:.2f},{p2*.60:.2f}]. Platform improvement = {pp2:.4f} x [0.25,0.60] = [{pp2*.25:.4f},{pp2*.60:.4f}] pp; resulting rate is [{100*R-pp2*.60:.4f}%,{100*R-pp2*.25:.4f}%]. This is an assumption-based planning range, not a confidence interval or a causal forecast. No policy-response data exists to estimate efficacy.')
p('Risk: conversion loss or a shift from cancellations to no-shows. Randomize eligible bookings into policy/control at customer level, track conversion, Cancelled+No-Show, realized net revenue and complaints, and compare intention-to-treat outcomes. The 10% deposit is a pilot design assumption, not an estimated optimum.')
heading('CS6. Can the board achieve five points?')
p(f'No: these supported benchmark scenarios do not establish a five-point opportunity. Five points requires {N} x 0.05 = {N*.05:.0f} prevented cancellations. The full long-lead scenario is only {pp2:.4f} pp. Even the optimistic additive bound {pp1:.4f}+{pp2:.4f}={pp1+pp2:.4f} pp is far below five and overlaps four worst-slice long-lead bookings.')
p(f'An explicit non-double-counted sequence first applies rL-rS to all long-lead bookings, then removes remaining worst-cell excess relative to the original R. Residual worst-cell excess = {p1:.4f} - {long_in_slice} x ({rL:.8f}-{rS:.8f}) = {combined_remaining_excess:.4f}. Total = {p2:.4f}+{combined_remaining_excess:.4f}={combined:.4f} prevented = {100*combined/N:.4f} pp. This is a scenario ceiling under these stipulated rate targets, not a proven achievable ceiling or a bound on every possible policy.')
p('The proposed policy range is more conservative than that full-gap scenario. Additional levers require cancellation timing/reason codes, refund and payment events, acquisition/conversion exposure, competing prices, inventory reliability and randomized policy-response data. Disjoint targets and incremental treatment effects must be estimated before combining initiatives; a larger reduction cannot be asserted from correlations alone.')
newpage();title('Section 3 - Normalized schema and SQL')
p('Dialect: SQLite 3.25+ with window functions. Tables: customers, properties, bookings and reviews. Monetary types declare DECIMAL precision; SQLite does not enforce fixed scale, so production financial storage should use integer paise or a strict DECIMAL engine. Outputs below use recorded total_amount, consistent with DQ3.')
p('Primary and foreign keys are explicit in DDL; all remaining columns are neither. NOT NULL flags are explicit. CHECK(checkout_date > checkin_date) addresses Footnote 1; CHECK(num_rooms > 0) addresses Footnote 3. Literal None is preserved as a valid tier. We deliberately do not impose uniqueness on property names. The indexed column is bookings.customer_id, supporting customer access/partitioning for A-Q2; it does not remove every date sort.')
for name in ['schema.sql','queries.sql']:
    heading(name)
    text=(ROOT/'code'/name).read_text()
    # Wrap comments/SQL without changing the actual source file.
    import textwrap
    display='\n'.join('\n'.join(textwrap.wrap(line,105,replace_whitespace=False,drop_whitespace=False)) if len(line)>105 else line for line in text.splitlines())
    story.append(Preformatted(display,styles['Code'],maxLineLength=110))
heading('Executed results and verification')
table(list(q1.columns),q1.values.tolist(),[100,65,200,145])
p(f'A-Q2 result: {pandas_q2} customers. Independently verified with pandas using Completed bookings ordered by customer_id, checkin_date, booking_id; customers with fewer than two such bookings have no average gap and are not counted. Gap is consecutive check-in to check-in days. Same-day check-ins contribute zero.')
newpage();title('Section 4 - Weather-Cancellation Analyzer')
p('Implementation is supplied in project/weather_analyzer.py. This build attempted live Open-Meteo historical requests for Goa and Manali over 2024, then shorter July retries; retrieval failed. No weather values were returned, so no live merge or weather-derived insight can be verified. This section therefore does not yet satisfy the assessment requirement for a successful real call and a quantified weather insight. No synthetic weather has been substituted.')
p('Implementation: use Goa (Panaji proxy: 15.4909, 73.8278) and Manali (32.2432, 77.1892); batch one annual date range per city, with timeout/retry handling and cache support. Coordinates are analyst-selected city proxies, not hotel geocodes. Merge on property_city and check-in calendar date, with many-to-one validation and row-count checks. Missing API values remain missing and are not classified as dry or normal-temperature days.')
p('Predeclared exposure definitions: heavy rain >=20 mm/day; hot day maximum >=35 C; cold day maximum <=5 C. Primary comparison is Cancelled+No-Show among valid bookings on exposed versus unexposed days with nonmissing data; report Cancelled and No-Show separately as well. These are operational cutoffs, not official warning thresholds. City-specific comparisons and city-month-standardized effects are generated to reduce seasonal mixing.')
p('Actual check-in weather is not necessarily information available when a cancellation was made. Without cancellation timestamps and forecasts, even a successful association would not show weather caused the cancellation. City-centre grid weather may not represent each property, especially in mountain terrain.')
p('Run python project/weather_analyzer.py from the package root on a machine with internet. It will write status.json, city_date_weather.csv, weather_enriched_bookings.csv, weather_groups.csv and insight.md under project/output. If retrieval fails, it writes a truthful status and partial/no-data insight rather than crashing or inventing evidence. Run --self-test for offline merge/classification tests; synthetic test rows are never used in the empirical insight.')
heading('Reproducibility and audit trail')
p('Inputs are bundled in data/. Run python code/analysis.py to regenerate the report and Section 1-3 tables. requirements.txt lists dependencies. Results include the raw-row flag audit, clean cohort, city-month table, hypothesis channel table, raw review statistics, weighted variation, SQL outputs and metrics.json. tests.py checks key counts, rate arithmetic and SQL agreement; the weather self-test validates date-key joins and missingness behavior without a network call.')
SimpleDocTemplate(str(ROOT/'Answer_Report.pdf'),pagesize=(595.28,841.89),rightMargin=42,leftMargin=42,topMargin=38,bottomMargin=38).build(story)
print(json.dumps(metrics,indent=2))
