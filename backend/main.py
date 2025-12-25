from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
import json
import uvicorn
from datetime import datetime, timedelta

# Import the Real Engine
from predict_weekly_v2 import RealPredictionEngine
from action_rules_v1 import ActionRulesEngine

# --- CONFIGURATION ---
ALERT_THRESHOLD = 40.0
CRITICAL_THRESHOLD = 18.0

# --- GLOBAL SINGLETONS ---
ml_engine = None
rules_engine = None
district_drivers = {}
ROOT_DIR = Path(__file__).parent.parent

# --- LIFESPAN HANDLER ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global ml_engine, rules_engine, district_drivers
    try:
        print("🔄 Initializing ML Engine...")
        ml_engine = RealPredictionEngine(models_dir=str(ROOT_DIR / 'models'))
        rules_engine = ActionRulesEngine(
            district_to_dams=ml_engine.district_to_dams,
            dam_stats=ml_engine.dam_stats
        )
        print("✅ ML Engine & Rules Engine Loaded Successfully")

        # --- LOAD DRIVERS FROM JSON ---
        try:
            drivers_path = ROOT_DIR / 'data' / 'ilceler_kullanimlar.json'
            if drivers_path.exists():
                with open(drivers_path, 'r', encoding='utf-8') as f:
                    raw_drivers = json.load(f)
                    for item in raw_drivers:
                        d_name = item.get('district_name')
                        d_driver = item.get('primary_driver')
                        if d_name and d_driver:
                            district_drivers[d_name] = d_driver
                print(f"✅ Loaded drivers for {len(district_drivers)} districts")
            else:
                print(f"⚠️ Drivers file not found at: {drivers_path}")
        except Exception as e:
            print(f"⚠️ Error loading drivers json: {e}")

    except Exception as e:
        print(f"❌ Failed to load ML models: {e}")
    yield
    print("🛑 Shutting down ML Engine...")

# Initialize App
app = FastAPI(title="Istanbul Water Management API", version="13.0 (Drivers Fixed)", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- LOGIC HELPERS ---
def get_dam_status(occupancy):
    if occupancy < CRITICAL_THRESHOLD: return "CRITICAL"
    elif occupancy < ALERT_THRESHOLD: return "WARNING"
    elif occupancy < 60: return "CAUTION"
    else: return "SAFE"

def calculate_depletion(dam_name, current_occupancy_pct, capacity_m3):
    if not ml_engine: return 0, 0, 0
    daily_outflow_m3 = ml_engine.get_dam_daily_outflow(dam_name)
    current_volume = capacity_m3 * (current_occupancy_pct / 100.0)
    dead_volume = capacity_m3 * 0.03
    usable_volume = max(0, current_volume - dead_volume)
    
    if daily_outflow_m3 <= 0: days_to_crisis = 999
    else: days_to_crisis = usable_volume / daily_outflow_m3
        
    return daily_outflow_m3, usable_volume, days_to_crisis

# --- ENDPOINTS ---
@app.get("/api/dams")
async def get_all_dams():
    if not ml_engine: return {"dams": [], "general_occupancy_pct": 0}
    dams_list = []
    total_sys_vol = 0
    total_sys_cap = 0
    for name, stats in ml_engine.dam_stats.items():
        occ = stats['occupancy_pct']
        cap = stats['capacity_m3']
        daily_out, usable, days = calculate_depletion(name, occ, cap)
        
        conn_count = 0
        for d_list in ml_engine.district_to_dams.values():
            if name in d_list: conn_count += 1
            
        dams_list.append({
            "name": name, "occupancy_pct": occ, "capacity_m3": cap,
            "volume_m3": cap * (occ/100), "status": get_dam_status(occ),
            "connected_districts_count": conn_count, "days_to_crisis": round(days)
        })
        total_sys_vol += (cap * (occ/100))
        total_sys_cap += cap
    gen_occ = (total_sys_vol / total_sys_cap * 100) if total_sys_cap > 0 else 0
    return {"dams": dams_list, "general_occupancy_pct": round(gen_occ, 2)}

@app.get("/api/dam/{dam_name}")
async def get_dam_detail(dam_name: str):
    if not ml_engine or dam_name not in ml_engine.dam_stats:
        raise HTTPException(status_code=404, detail="Dam not found")
    
    stats = ml_engine.dam_stats[dam_name]
    occ = stats['occupancy_pct']
    cap = stats['capacity_m3']
    status = get_dam_status(occ)
    
    daily_out_base, usable, days_base = calculate_depletion(dam_name, occ, cap)
    
    recs = []

    # Common Action
    daily_supplement = cap * 0.0005 
    daily_net_loss_gw = max(1, daily_out_base - daily_supplement)
    days_gw = usable / daily_net_loss_gw
    days_gained_gw = days_gw - days_base
    recs.append({
        "action": "GROUNDWATER_SUPPLEMENT",
        "title": "YERALTI SUYU TAKVİYESİ",
        "sub_title": "Arz Takviyesi",
        "priority": "CRITICAL" if status == "CRITICAL" else "HIGH",
        "details": {
            "duration": "Sürekli (7/24)",
            "days_gained": round(days_gained_gw, 1),
            "retention_30d": round((daily_supplement * 30 / cap) * 100, 2),
            "vol_saved_m3": round(daily_supplement * 30),
            "support_label": f"+{(daily_supplement/1000):.0f}-{(daily_supplement*1.2/1000):.0f}k m³"
        }
    })

    if status == "CRITICAL":
        savings_pct_cut = 0.35 
        daily_out_cut = daily_out_base * (1 - savings_pct_cut)
        days_cut = usable / daily_out_cut
        vol_saved_cut = (daily_out_base - daily_out_cut) * 30
        recs.append({
            "action": "PLANNED_CUTS_12H",
            "title": "ZORUNLU SU KESİNTİSİ",
            "sub_title": "Kritik Seviye Önlemi",
            "priority": "CRITICAL",
            "details": {
                "duration": "Her Gün (12 Saat)",
                "days_gained": round(days_cut - days_base, 1),
                "retention_30d": round((vol_saved_cut / cap) * 100, 2),
                "vol_saved_m3": round(vol_saved_cut),
                "risk_label": "⚠️ Çok Yüksek Tepki Riski"
            }
        })

        savings_pct_pr = 0.12
        daily_out_pr = daily_out_base * (1 - savings_pct_pr)
        days_pr = usable / daily_out_pr
        vol_saved_pr = (daily_out_base - daily_out_pr) * 30
        recs.append({
            "action": "PRESSURE_REDUCTION_HIGH",
            "title": "YÜKSEK BASINÇ KISITLAMASI",
            "sub_title": "Fiziksel Kısıtlama (-1.0 Bar)",
            "priority": "CRITICAL",
            "details": {
                "duration": "Sürekli",
                "days_gained": round(days_pr - days_base, 1),
                "retention_30d": round((vol_saved_pr / cap) * 100, 2),
                "vol_saved_m3": round(vol_saved_pr),
                "risk_label": "⚠️ Yüksek İrtifa Riski"
            }
        })

    elif status == "WARNING":
        savings_pct_cut_8 = 0.20 
        daily_out_cut_8 = daily_out_base * (1 - savings_pct_cut_8)
        days_cut_8 = usable / daily_out_cut_8
        vol_saved_cut_8 = (daily_out_base - daily_out_cut_8) * 30
        recs.append({
            "action": "PLANNED_CUTS_8H",
            "title": "KISMI SU KESİNTİSİ",
            "sub_title": "Uyarı Seviyesi Önlemi",
            "priority": "HIGH",
            "details": {
                "duration": "Her Gün (8 Saat)",
                "days_gained": round(days_cut_8 - days_base, 1),
                "retention_30d": round((vol_saved_cut_8 / cap) * 100, 2),
                "vol_saved_m3": round(vol_saved_cut_8),
                "risk_label": "⚠️ Orta Tepki Riski"
            }
        })

        savings_pct_pr_low = 0.06
        daily_out_pr_low = daily_out_base * (1 - savings_pct_pr_low)
        days_pr_low = usable / daily_out_pr_low
        vol_saved_pr_low = (daily_out_base - daily_out_pr_low) * 30
        recs.append({
            "action": "PRESSURE_REDUCTION_LOW",
            "title": "HAFİF BASINÇ KISITLAMASI",
            "sub_title": "Fiziksel Kısıtlama (-0.5 Bar)",
            "priority": "HIGH",
            "details": {
                "duration": "Gece (00:00 - 06:00)",
                "days_gained": round(days_pr_low - days_base, 1),
                "retention_30d": round((vol_saved_pr_low / cap) * 100, 2),
                "vol_saved_m3": round(vol_saved_pr_low),
            }
        })

    connected = []
    for dist, dams in ml_engine.district_to_dams.items():
        if dam_name in dams: connected.append({"name": dist, "status": "SAFE"})

    return { 
        "dam": dam_name, 
        "occupancy_pct": occ, 
        "capacity_m3": cap, 
        "volume_m3": cap * (occ/100), 
        "status": status, 
        "days_to_crisis": round(days_base, 1), 
        "recommendations": recs, 
        "connected_districts": connected, 
        "connected_districts_count": len(connected) 
    }

@app.get("/api/districts")
async def get_districts():
    if not ml_engine: return {"districts": []}
    dist_summary = []
    for dist in ml_engine.district_mapping.keys():
        monthly_cons = ml_engine.predict_district_monthly_consumption(dist, 50.0)
        daily_cons = monthly_cons / 30.0
        sources = ml_engine.district_to_dams.get(dist, [])
        source_details = []
        total_supply_m3 = 0
        for dam in sources:
            if dam in ml_engine.dam_stats:
                d_stats = ml_engine.dam_stats[dam]
                usable = (d_stats['capacity_m3'] * (d_stats['occupancy_pct']/100)) * 0.95
                total_supply_m3 += usable
                source_details.append({"name": dam, "status": get_dam_status(d_stats['occupancy_pct'])})
        effective_supply = total_supply_m3 / max(1, len(sources) * 2) 
        days_supply = effective_supply / daily_cons if daily_cons > 0 else 0
        status = "SAFE"
        if days_supply < 30: status = "CRITICAL"
        elif days_supply < 90: status = "WARNING"
        elif days_supply < 180: status = "CAUTION"
        
        # USE REAL DRIVER FROM JSON
        driver = district_drivers.get(dist, "Residential (Est)")
        
        dist_summary.append({ "name": dist, "status": status, "days_supply": round(days_supply), "daily_cons": round(daily_cons), "primary_driver": driver, "source_dams": source_details })
    return {"districts": sorted(dist_summary, key=lambda x: x['days_supply'])}

@app.get("/api/predictions/occupancy")
async def get_occupancy_forecast():
    if not ml_engine: return {}
    forecasts = {}
    today = datetime.now()
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(30)]
    for dam, stats in ml_engine.dam_stats.items():
        cap = stats['capacity_m3']
        current_vol = cap * (stats['occupancy_pct'] / 100.0)
        daily_loss_m3 = ml_engine.get_dam_daily_outflow(dam)
        trend = []
        sim_vol = current_vol
        for _ in range(30):
            sim_vol -= daily_loss_m3
            sim_vol = max(0, sim_vol)
            pct = (sim_vol / cap) * 100
            trend.append(round(pct, 2))
        forecasts[dam] = trend
    return {"dates": dates, "dams": forecasts}

@app.get("/api/consumption/districts")
async def get_consumption_rankings():
    if not ml_engine: return []
    data = []
    for dist in ml_engine.district_mapping.keys():
        monthly = ml_engine.predict_district_monthly_consumption(dist, 50.0)
        data.append({ "district_name": dist, "avg_daily_m3": round(monthly / 30), "primary_driver": "Model Forecast" })
    return sorted(data, key=lambda x: x['avg_daily_m3'], reverse=True)

@app.get("/api/predictions/stats")
async def get_stats():
    try:
        with open(ROOT_DIR / 'models' / 'training_metrics.json', 'r') as f: return json.load(f)
    except: return {"error": "Metrics not found"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)