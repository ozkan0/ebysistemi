#!/usr/bin/env python3
"""
Istanbul Water Management Decision Support System
Enhanced Model Trainer v2.0

Predicts monthly district-level water consumption
Generates weekly 7-day sufficiency assessments
Integrates occupancy + precipitation + demand trends
Time-series aware with RandomForest
"""

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os
import pickle
import warnings
warnings.filterwarnings('ignore')

from sklearn.model_selection import TimeSeriesSplit, cross_validate
from sklearn.preprocessing import StandardScaler
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score, mean_absolute_percentage_error

print("╔════════════════════════════════════════════════════════════════════╗")
print("║  ISTANBUL WATER MANAGEMENT - ENHANCED MODEL TRAINER v2.0           ║")
print("║  Monthly Consumption + Weekly 7-Day Sufficiency Predictions        ║")
print("║  Features: Occupancy + Precipitation + Demand Trends              ║")
print("╚════════════════════════════════════════════════════════════════════╝")

# ============================================================================
# TODAY'S DAM STATS (December 8, 2025 - CRITICAL LEVELS)
# ============================================================================

TODAY_DATE = "2025-12-08"
TODAY_DAM_STATS = {
    'Omerli': {'capacity_m3': 244540000, 'occupancy_pct': 13.11},
    'Darlik': {'capacity_m3': 102463000, 'occupancy_pct': 27.65},
    'Elmali': {'capacity_m3': 9600000, 'occupancy_pct': 50.68},
    'Terkos': {'capacity_m3': 195974000, 'occupancy_pct': 19.23},
    'Alibey': {'capacity_m3': 34143000, 'occupancy_pct': 10.1},
    'Buyukcekmece': {'capacity_m3': 129892000, 'occupancy_pct': 18.46},
    'Sazlidere': {'capacity_m3': 88730000, 'occupancy_pct': 16.87},
    'Istrancalar': {'capacity_m3': 6231000, 'occupancy_pct': 30.84},
    'Kazandere': {'capacity_m3': 21096000, 'occupancy_pct': 2.3},
    'Pabucdere': {'capacity_m3': 35222000, 'occupancy_pct': 2.41}
}

GENERAL_OCCUPANCY = 17.12

print(f"\n🚨 TODAY'S DAM STATUS: {TODAY_DATE}")
print(f"   General Occupancy: {GENERAL_OCCUPANCY}% (CRITICAL)")
print(f"   Total Capacity: {sum(d['capacity_m3'] for d in TODAY_DAM_STATS.values())/1e9:.2f}B m³")

# ============================================================================
# 1. LOAD & PARSE DATA
# ============================================================================

print("\n📂 Loading datasets...")

def load_json(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

try:
    weather_data = load_json('data/hava_durumu_istanbul_2015_2021.json')
    precipitation_data = load_json('data/gunluk_yagis_verileri_2015_2021.json')
    dam_occupancy_data = load_json('data/baraj_doluluk_2015_2021.json')
    consumption_data = load_json('data/ilce_bazinda_tuketim.json')
    calls_2019 = load_json('data/2019_su_kesintisi_cagrilari.json')
    calls_2020 = load_json('data/2020_su_kesintisi_cagrilari.json')
    calls_2021 = load_json('data/2021_su_kesintisi_cagrilari.json')
    district_dams = load_json('data/ilceler_bagli_barajlar.json')
except Exception as e:
    print(f" ❌ Error loading files: {e}")
    sys.exit(1)

print(f" ✅ Weather: {len(weather_data['records'])} days")
print(f" ✅ Precipitation: {len(precipitation_data['records'])} days")
print(f" ✅ Dam occupancy: {len(dam_occupancy_data['records'])} days")
print(f" ✅ Consumption: {len(consumption_data['records'])} years")
print(f" ✅ Complaint calls: 2019-2021")
print(f" ✅ District-Dam mapping: {len(district_dams)} districts")

# ============================================================================
# 2. BUILD DISTRICT-DAM MAPPING
# ============================================================================

print("\n🗺️  Building district-dam relationships...")

district_to_dams = {}
for entry in district_dams:
    district = entry['district'].strip()
    dams = [d.strip() for d in entry['connected_dams'].split(',')]
    district_to_dams[district] = dams

print(f" ✅ {len(district_to_dams)} districts mapped to dams")

# ============================================================================
# 3. PREPARE CONSUMPTION DATA (ANNUAL → MONTHLY)
# ============================================================================

print("\n💧 Preparing monthly consumption targets...")

consumption_records = []
fields = consumption_data['fields']
district_names = [f['id'] for f in fields[2:]]

for record in consumption_data['records']:
    year = int(record[1])
    for i, district in enumerate(district_names):
        annual_consumption = record[i + 2]
        monthly_consumption = annual_consumption / 12  # Simple division for now
        
        for month in range(1, 13):
            consumption_records.append({
                'year': year,
                'month': month,
                'district': district,
                'monthly_consumption': monthly_consumption
            })

df_consumption = pd.DataFrame(consumption_records)
df_consumption['date'] = pd.to_datetime(
    df_consumption.apply(
        lambda r: f"{r['year']}-{r['month']:02d}-01", axis=1
    )
)

print(f" ✅ {len(df_consumption)} monthly consumption records created")
print(f"   Years: {sorted(df_consumption['year'].unique())}")
print(f"   Districts: {df_consumption['district'].nunique()}")

# ============================================================================
# 4. PREPARE MONTHLY WEATHER FEATURES
# ============================================================================

print("\n🌤️  Preparing monthly weather features...")

weather_records = []
for record in weather_data['records']:
    weather_records.append({
        'date': pd.to_datetime(record[1]),
        'temp_max': float(record[2]),
        'temp_min': float(record[3]),
        'temp_avg': float(record[4]),
        'humidity_avg': float(record[8]),
        'windspeed_avg': float(record[10])
    })

df_weather_daily = pd.DataFrame(weather_records)
df_weather_daily['year'] = df_weather_daily['date'].dt.year
df_weather_daily['month'] = df_weather_daily['date'].dt.month

df_weather_monthly = df_weather_daily.groupby(['year', 'month']).agg({
    'temp_max': 'mean',
    'temp_min': 'mean',
    'temp_avg': 'mean',
    'humidity_avg': 'mean',
    'windspeed_avg': 'mean'
}).reset_index()

print(f" ✅ {len(df_weather_monthly)} monthly weather records")

# ============================================================================
# 5. PREPARE MONTHLY PRECIPITATION (DAM-SPECIFIC)
# ============================================================================

print("\n☔ Preparing monthly precipitation by dam...")

precipitation_records = []
dam_names_precip = ['Omerli', 'Darlik', 'Elmali', 'Terkos', 'Buyukcekmece', 
                    'Sazlidere', 'Alibey', 'Kazandere', 'Pabucdere', 'Istrancalar']

for record in precipitation_data['records']:
    date = pd.to_datetime(record[1])
    precip_dict = {'date': date}
    for i, dam in enumerate(dam_names_precip):
        precip_dict[dam] = float(record[i + 2]) if record[i + 2] else 0.0
    precipitation_records.append(precip_dict)

df_precip_daily = pd.DataFrame(precipitation_records)
df_precip_daily['year'] = df_precip_daily['date'].dt.year
df_precip_daily['month'] = df_precip_daily['date'].dt.month

# Aggregate to monthly
precip_monthly = {'year': [], 'month': []}
for dam in dam_names_precip:
    precip_monthly[f'{dam}_precip_monthly'] = []

for year in sorted(df_precip_daily['year'].unique()):
    for month in range(1, 13):
        year_month_data = df_precip_daily[(df_precip_daily['year'] == year) & 
                                           (df_precip_daily['month'] == month)]
        
        if len(year_month_data) > 0:
            precip_monthly['year'].append(year)
            precip_monthly['month'].append(month)
            
            for dam in dam_names_precip:
                precip_monthly[f'{dam}_precip_monthly'].append(
                    year_month_data[dam].sum()
                )

df_precip_monthly = pd.DataFrame(precip_monthly)

print(f" ✅ {len(df_precip_monthly)} monthly precipitation records")

# ============================================================================
# 6. PREPARE MONTHLY DAM OCCUPANCY
# ============================================================================

print("\n🏞️  Preparing monthly dam occupancy...")

occupancy_records = []
dam_names_occ = ['Omerli', 'Darlik', 'Elmali', 'Terkos', 'Buyukcekmece', 
                 'Sazlidere', 'Alibey', 'Kazandere', 'Pabucdere', 'Istrancalar']

for record in dam_occupancy_data['records']:
    date = pd.to_datetime(record[1])
    occ_dict = {'date': date}
    for i, dam in enumerate(dam_names_occ):
        try:
            occ_dict[dam] = float(record[i + 2]) if record[i + 2] else 0.0
        except:
            occ_dict[dam] = 0.0
    occupancy_records.append(occ_dict)

df_occ_daily = pd.DataFrame(occupancy_records)
df_occ_daily['year'] = df_occ_daily['date'].dt.year
df_occ_daily['month'] = df_occ_daily['date'].dt.month

# Aggregate to monthly
occ_monthly = {'year': [], 'month': []}
for dam in dam_names_occ:
    occ_monthly[f'{dam}_occ_monthly'] = []

for year in sorted(df_occ_daily['year'].unique()):
    for month in range(1, 13):
        year_month_data = df_occ_daily[(df_occ_daily['year'] == year) & 
                                        (df_occ_daily['month'] == month)]
        
        if len(year_month_data) > 0:
            occ_monthly['year'].append(year)
            occ_monthly['month'].append(month)
            
            for dam in dam_names_occ:
                occ_monthly[f'{dam}_occ_monthly'].append(
                    year_month_data[dam].mean()
                )

df_occ_monthly = pd.DataFrame(occ_monthly)

print(f" ✅ {len(df_occ_monthly)} monthly occupancy records")

# ============================================================================
# 7. PREPARE COMPLAINT CALLS (AGGREGATED TO MONTHLY)
# ============================================================================

print("\n📞 Preparing monthly complaint calls...")

all_calls = []
for record in calls_2019['records']:
    all_calls.append({'year': record[1], 'district': record[2], 'calls': record[3]})
for record in calls_2020['records']:
    all_calls.append({'year': record[1], 'district': record[2], 'calls': record[3]})
for record in calls_2021['records']:
    all_calls.append({'year': record[1], 'district': record[2], 'calls': record[3]})

# Distribute annual calls evenly to months (improvement: use seasonal patterns)
call_records = []
for entry in all_calls:
    year = int(entry['year'])
    district = entry['district'].strip()
    annual_calls = entry['calls']
    monthly_calls = annual_calls / 12
    
    for month in range(1, 13):
        call_records.append({
            'year': year,
            'month': month,
            'district': district,
            'monthly_calls': monthly_calls
        })

df_calls = pd.DataFrame(call_records)

print(f" ✅ {len(df_calls)} monthly call records")

# ============================================================================
# 8. MERGE ALL DATASETS
# ============================================================================

print("\n🔗 Merging datasets by year+month+district...")

df_model = df_consumption.copy()
print(f"   Start: {len(df_model)} rows")

# Merge weather
df_model = df_model.merge(df_weather_monthly, on=['year', 'month'], how='left')
print(f"   After weather: {len(df_model)} rows")

# Merge precipitation
df_model = df_model.merge(df_precip_monthly, on=['year', 'month'], how='left')
print(f"   After precipitation: {len(df_model)} rows")

# Merge occupancy
df_model = df_model.merge(df_occ_monthly, on=['year', 'month'], how='left')
print(f"   After occupancy: {len(df_model)} rows")

# Merge calls
df_model = df_model.merge(df_calls[['year', 'month', 'district', 'monthly_calls']], 
                         on=['year', 'month', 'district'], how='left')
print(f"   After calls: {len(df_model)} rows")

# Fill missing calls with 0
df_model['monthly_calls'] = df_model['monthly_calls'].fillna(0)

# Check for NAs
na_cols = [col for col in df_model.columns if df_model[col].isna().sum() > 0]
if na_cols:
    print(f"\n   ⚠️  Columns with NAs: {na_cols}")
    df_model = df_model.dropna()
    print(f"   After dropna(): {len(df_model)} rows")
else:
    print(f"\n   ✅ No missing values!")

if len(df_model) == 0:
    print("   ❌ NO DATA AFTER MERGE! Exit.")
    sys.exit(1)

# ============================================================================
# 9. FEATURE ENGINEERING
# ============================================================================

print("\n🔧 Engineering features...")

# District encoding
district_mapping = {dist: i for i, dist in enumerate(sorted(df_model['district'].unique()))}
df_model['district_code'] = df_model['district'].map(district_mapping)

# Season encoding
df_model['season'] = df_model['month'].map({
    12: 1, 1: 1, 2: 1,      # Winter
    3: 2, 4: 2, 5: 2,       # Spring
    6: 3, 7: 3, 8: 3,       # Summer (high consumption)
    9: 4, 10: 4, 11: 4      # Fall
})

# District-specific dam occupancy (capacity-weighted average)
dam_capacities = TODAY_DAM_STATS
total_capacity = sum(d['capacity_m3'] for d in dam_capacities.values())

for district in df_model['district'].unique():
    if district in district_to_dams:
        connected_dams = district_to_dams[district]
        
        # Create weighted occupancy feature
        occ_cols = [f'{dam}_occ_monthly' for dam in connected_dams 
                   if f'{dam}_occ_monthly' in df_model.columns]
        
        if occ_cols:
            # Capacity-weighted average
            weights = [dam_capacities[dam]['capacity_m3'] / total_capacity 
                      for dam in connected_dams]
            weight_sum = sum(weights)
            weights = [w / weight_sum for w in weights]  # Normalize
            
            df_model[f'{district}_dam_occ_weighted'] = df_model[occ_cols].values @ weights
        
        # Also add simple average
        df_model[f'{district}_dam_occ_avg'] = df_model[occ_cols].mean(axis=1)

# Lag features (previous month consumption)
df_model = df_model.sort_values(['district', 'year', 'month'])
df_model['consumption_lag_1m'] = df_model.groupby('district')['monthly_consumption'].shift(1)

# Rolling average (3-month)
df_model['consumption_roll_3m'] = df_model.groupby('district')['monthly_consumption'].rolling(3).mean().reset_index(0, drop=True)

print(f" ✅ {df_model.shape[1]} features engineered")

# ============================================================================
# 10. PREPARE TRAINING DATA
# ============================================================================

print("\n📊 Preparing training dataset...")

# Drop rows with NaN from lag/rolling features
df_model = df_model.dropna()

feature_cols = [col for col in df_model.columns if col not in 
                ['year', 'month', 'date', 'district', 'monthly_consumption', 'district_code']]

X = df_model[feature_cols].values
y = df_model['monthly_consumption'].values

print(f" ✅ Features: {len(feature_cols)}")
print(f" ✅ Samples: {len(X)}")
print(f" ✅ Target range: {y.min():,.0f} - {y.max():,.0f} m³")

# Scale features
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# ============================================================================
# 11. TIME-SERIES CROSS-VALIDATION & TRAINING
# ============================================================================

print("\n⏰ Time-series cross-validation (5 folds)...")

tscv = TimeSeriesSplit(n_splits=5)

rf_model = RandomForestRegressor(
    n_estimators=100,
    max_depth=12,
    min_samples_split=3,
    min_samples_leaf=1,
    max_features='sqrt',
    random_state=42,
    n_jobs=-1,
    verbose=0
)

cv_results = cross_validate(
    rf_model, X_scaled, y,
    cv=tscv,
    scoring=['neg_mean_absolute_error', 'neg_mean_squared_error', 'r2', 'neg_mean_absolute_percentage_error'],
    return_train_score=True,
    verbose=0
)

# Train on full dataset
rf_model.fit(X_scaled, y)

# Extract metrics
train_mae = -cv_results['train_neg_mean_absolute_error'].mean()
val_mae = -cv_results['test_neg_mean_absolute_error'].mean()
train_rmse = np.sqrt(-cv_results['train_neg_mean_squared_error'].mean())
val_rmse = np.sqrt(-cv_results['test_neg_mean_squared_error'].mean())
train_r2 = cv_results['train_r2'].mean()
val_r2 = cv_results['test_r2'].mean()
val_mape = -cv_results['test_neg_mean_absolute_percentage_error'].mean()

print(f"\n ✅ RandomForest trained")
print(f"\n 📈 Cross-Validation Results (5-fold time-series):")
print(f"    Train MAE:  {train_mae:>12,.0f} m³/month")
print(f"    Val MAE:    {val_mae:>12,.0f} m³/month")
print(f"    Train RMSE: {train_rmse:>12,.0f} m³/month")
print(f"    Val RMSE:   {val_rmse:>12,.0f} m³/month")
print(f"    Train R²:   {train_r2:>12.4f}")
print(f"    Val R²:     {val_r2:>12.4f}")
print(f"    Val MAPE:   {val_mape:>12.2f}%")

# ============================================================================
# 12. FEATURE IMPORTANCE
# ============================================================================

print("\n🎯 Top 15 Important Features:")

feature_importance = pd.DataFrame({
    'feature': feature_cols,
    'importance': rf_model.feature_importances_
}).sort_values('importance', ascending=False)

for idx, (_, row) in enumerate(feature_importance.head(15).iterrows(), 1):
    print(f"    {idx:2d}. {row['feature']:40s} {row['importance']:.4f}")

# ============================================================================
# 13. SAVE ARTIFACTS
# ============================================================================

print("\n💾 Saving model artifacts...")

os.makedirs('models', exist_ok=True)

# Model
with open('models/rf_consumption_model.pkl', 'wb') as f:
    pickle.dump(rf_model, f)

# Scaler
with open('models/scaler.pkl', 'wb') as f:
    pickle.dump(scaler, f)

# Feature names
with open('models/feature_names.json', 'w') as f:
    json.dump(feature_cols, f, indent=2)

# District mapping
with open('models/district_mapping.json', 'w') as f:
    json.dump(district_mapping, f, indent=2)

# District-dam mapping
with open('models/district_to_dams.json', 'w') as f:
    json.dump(district_to_dams, f, indent=2)

# Dam capacities & stats
with open('models/dam_stats.json', 'w') as f:
    json.dump({
        'today_date': TODAY_DATE,
        'today_stats': TODAY_DAM_STATS,
        'general_occupancy': GENERAL_OCCUPANCY
    }, f, indent=2)

# Training metrics
metrics = {
    'model_type': 'RandomForestRegressor',
    'training_date': datetime.now().isoformat(),
    'data_points': int(len(df_model)),
    'features_count': int(len(feature_cols)),
    'districts': int(df_model['district'].nunique()),
    'years': [int(y) for y in sorted(df_model['year'].unique())],
    'cross_validation': {
        'splits': 5,
        'type': 'TimeSeriesSplit',
        'train_mae': float(train_mae),
        'val_mae': float(val_mae),
        'train_rmse': float(train_rmse),
        'val_rmse': float(val_rmse),
        'train_r2': float(train_r2),
        'val_r2': float(val_r2),
        'val_mape': float(val_mape),
    },
    'top_features': feature_importance.head(10).to_dict('records')
}

with open('models/training_metrics.json', 'w') as f:
    json.dump(metrics, f, indent=2)

print(f" ✅ Model saved: models/rf_consumption_model.pkl")
print(f" ✅ Scaler saved: models/scaler.pkl")
print(f" ✅ Features saved: models/feature_names.json")
print(f" ✅ District mapping saved: models/district_mapping.json")
print(f" ✅ Dam stats saved: models/dam_stats.json")
print(f" ✅ Metrics saved: models/training_metrics.json")

# ============================================================================
# 14. SUMMARY
# ============================================================================

print(f"\n{'='*75}")
print(f"✅ MODEL TRAINING COMPLETE - PRODUCTION READY")
print(f"{'='*75}")
print(f"\n📊 Model Summary:")
print(f"   Type: RandomForest (100 trees, depth=12)")
print(f"   Target: Monthly consumption per district (m³/month)")
print(f"   Validation R²: {val_r2:.4f}")
print(f"   Validation MAE: {val_mae:,.0f} m³/month")
print(f"   Validation MAPE: {val_mape:.2f}%")

print(f"\n🗺️  Istanbul System:")
print(f"   Districts: {df_model['district'].nunique()}")
print(f"   Dams: {len(dam_capacities)}")
print(f"   Total Capacity: {total_capacity/1e9:.2f}B m³")
print(f"   Current Occupancy: {GENERAL_OCCUPANCY:.2f}%")

print(f"\n🚨 Ready for decision-support predictions!")
print(f"   Use: predict_consumption.py for weekly 7-day forecasts")
