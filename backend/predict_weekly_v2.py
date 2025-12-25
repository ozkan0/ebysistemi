#!/usr/bin/env python3
"""
Effective Dam Management System - ML Inference Engine
"""

import json
import pickle
import numpy as np
from datetime import datetime
from pathlib import Path

class RealPredictionEngine:
    def __init__(self, models_dir: str = 'models'):
        self.models_dir = Path(models_dir)
        
        self.data_dir = self.models_dir.parent / 'data'
        
        self.load_artifacts()
        self.load_historical_baselines()
        
    def load_artifacts(self):
        try:
            with open(self.models_dir / 'rf_consumption_model.pkl', 'rb') as f:
                self.model = pickle.load(f)
            with open(self.models_dir / 'scaler.pkl', 'rb') as f:
                self.scaler = pickle.load(f)
            with open(self.models_dir / 'feature_names.json', 'r') as f:
                self.feature_names = json.load(f)
            with open(self.models_dir / 'district_mapping.json', 'r') as f:
                self.district_mapping = json.load(f)
            with open(self.models_dir / 'district_to_dams.json', 'r') as f:
                self.district_to_dams = json.load(f)
            with open(self.models_dir / 'dam_stats.json', 'r') as f:
                data = json.load(f)
                self.dam_stats = data.get('today_stats', {})
        except FileNotFoundError as e:
            print(f"❌ Critical ML Artifact missing: {e}")
            raise

    def load_historical_baselines(self):
        self.district_baselines = {}
        try:
            file_path = self.data_dir / 'ilce_bazinda_tuketim.json'
            if not file_path.exists():
                print(f"⚠️ Historical data not found at {file_path}. Using fallbacks.")
                return

            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            fields = {item['id']: idx for idx, item in enumerate(data['fields'])}
            totals = {}
            counts = {}
            
            for row in data['records']:
                for district_name, idx in fields.items():
                    if idx < 2: continue 
                    val = row[idx] if row[idx] is not None else 0
                    totals[district_name] = totals.get(district_name, 0) + val
                    counts[district_name] = counts.get(district_name, 0) + 1
            
            for dist, total in totals.items():
                years = max(1, counts[dist])
                self.district_baselines[dist] = (total / years) / 12.0
                
            print(f"✅ Loaded historical baselines for {len(self.district_baselines)} districts.")
        except Exception as e:
            print(f"⚠️ Error calculating baselines: {e}")

    def _get_seasonal_weather_averages(self, month):
        weather_lookup = {
            1:  {'temp_avg': 5.8,  'temp_max': 8.5,  'temp_min': 3.2, 'humidity_avg': 78, 'windspeed_avg': 18},
            2:  {'temp_avg': 6.2,  'temp_max': 9.1,  'temp_min': 3.5, 'humidity_avg': 75, 'windspeed_avg': 19},
            3:  {'temp_avg': 8.5,  'temp_max': 12.0, 'temp_min': 5.1, 'humidity_avg': 72, 'windspeed_avg': 17},
            4:  {'temp_avg': 13.2, 'temp_max': 17.5, 'temp_min': 9.2, 'humidity_avg': 68, 'windspeed_avg': 15},
            5:  {'temp_avg': 18.5, 'temp_max': 23.0, 'temp_min': 14.1,'humidity_avg': 65, 'windspeed_avg': 14},
            6:  {'temp_avg': 23.5, 'temp_max': 28.1, 'temp_min': 18.5,'humidity_avg': 62, 'windspeed_avg': 16},
            7:  {'temp_avg': 26.2, 'temp_max': 30.5, 'temp_min': 21.2,'humidity_avg': 60, 'windspeed_avg': 19},
            8:  {'temp_avg': 26.5, 'temp_max': 30.8, 'temp_min': 21.5,'humidity_avg': 63, 'windspeed_avg': 18},
            9:  {'temp_avg': 22.1, 'temp_max': 26.5, 'temp_min': 17.8,'humidity_avg': 66, 'windspeed_avg': 16},
            10: {'temp_avg': 17.5, 'temp_max': 21.5, 'temp_min': 13.5,'humidity_avg': 72, 'windspeed_avg': 15},
            11: {'temp_avg': 12.5, 'temp_max': 16.2, 'temp_min': 9.1, 'humidity_avg': 76, 'windspeed_avg': 16},
            12: {'temp_avg': 8.1,  'temp_max': 11.2, 'temp_min': 5.2, 'humidity_avg': 79, 'windspeed_avg': 18},
        }
        return weather_lookup.get(month, weather_lookup[1])

    def predict_district_monthly_consumption(self, district_name, current_occ_pct):
        if district_name not in self.district_mapping: return 150000.0
        today = datetime.now()
        month = today.month
        weather = self._get_seasonal_weather_averages(month)
        
        if month in [12, 1, 2]: season = 1
        elif month in [3, 4, 5]: season = 2
        elif month in [6, 7, 8]: season = 3
        else: season = 4

        historical_avg = self.district_baselines.get(district_name, 250000.0)

        features = {}
        features['temp_max'] = weather['temp_max']
        features['temp_min'] = weather['temp_min']
        features['temp_avg'] = weather['temp_avg']
        features['humidity_avg'] = weather['humidity_avg']
        features['windspeed_avg'] = weather['windspeed_avg']
        features['district_code'] = self.district_mapping[district_name]
        features['season'] = season
        features['consumption_lag_1m'] = historical_avg 
        features['consumption_roll_3m'] = historical_avg
        features['monthly_calls'] = 50 
        features[f'{district_name}_dam_occ_weighted'] = current_occ_pct
        features[f'{district_name}_dam_occ_avg'] = current_occ_pct

        ordered_values = []
        for col_name in self.feature_names:
            if col_name in features: val = features[col_name]
            elif '_occ_monthly' in col_name:
                dam_name = col_name.replace('_occ_monthly', '')
                val = self.dam_stats.get(dam_name, {}).get('occupancy_pct', 0)
            elif '_precip_monthly' in col_name: val = 40.0 
            else: val = features.get(col_name, 0.0)
            ordered_values.append(val)

        input_array = np.array([ordered_values])
        X_scaled = self.scaler.transform(input_array)
        prediction_m3 = self.model.predict(X_scaled)[0]
        return max(10000, prediction_m3)

    def get_dam_daily_outflow(self, dam_name):
        total_daily_outflow = 0
        connected_districts = []
        for dist, dams in self.district_to_dams.items():
            if dam_name in dams: connected_districts.append(dist)
        for dist in connected_districts:
            monthly_pred = self.predict_district_monthly_consumption(dist, 50.0)
            daily_pred = monthly_pred / 30.0
            num_sources = len(self.district_to_dams[dist])
            total_daily_outflow += (daily_pred / max(1, num_sources))
        return total_daily_outflow