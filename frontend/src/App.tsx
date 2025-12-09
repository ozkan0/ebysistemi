import React, { useEffect, useState } from 'react';
import axios from 'axios';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  ArcElement
} from 'chart.js';
import { Line, Doughnut, Bar } from 'react-chartjs-2';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  ArcElement
);

const API = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';

// --- Interfaces ---
interface Dam {
  name: string;
  occupancy_pct: number;
  capacity_m3: number;
  volume_m3: number;
  status: 'CRITICAL' | 'WARNING' | 'CAUTION' | 'SAFE';
  connected_districts_count: number;
  days_to_crisis: number;
}

interface DistrictSummary {
  name: string;
  status: 'CRITICAL' | 'WARNING' | 'CAUTION' | 'SAFE';
  days_supply: number;
  daily_cons: number;
  primary_driver: string;
  source_dams: {name: string, status: string}[];
}

interface ConsumptionData {
  district_name: string;
  avg_daily_m3: number;
  primary_driver: string;
}

interface Recommendation {
  action: string;
  priority: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW';
  reason: string;
  details: {
    duration: string;
    scope: string;
    days_gained: number;
    retention_30d: number;
    vol_saved_m3: number;
  }
}

interface DamDetail {
  dam: string;
  occupancy_pct: number;
  capacity_m3: number;
  volume_m3: number;
  status: 'CRITICAL' | 'WARNING' | 'CAUTION' | 'SAFE';
  days_to_crisis: number;
  connected_districts: any[];
  connected_districts_count: number;
  recommendations: Recommendation[];
}

interface OccupancyForecast {
  dates: string[];
  dams: { [key: string]: number[] };
}

interface ModelMetrics {
  model_type: string;
  training_date: string;
  cross_validation: { val_r2: number; val_mae: number; val_rmse: number; };
  top_features?: { feature: string; importance: number; }[];
}

// --- CONSTANTS & HELPERS ---
const statusColors = {
  CRITICAL: { bg: 'bg-red-600', border: 'border-red-600', text: 'text-red-500', light: 'bg-red-500/10', darkBg: 'bg-red-950/30' },
  WARNING:  { bg: 'bg-orange-600', border: 'border-orange-600', text: 'text-orange-500', light: 'bg-orange-500/10', darkBg: 'bg-orange-950/30' },
  CAUTION:  { bg: 'bg-yellow-500', border: 'border-yellow-500', text: 'text-yellow-500', light: 'bg-yellow-500/10', darkBg: 'bg-yellow-950/30' },
  SAFE:     { bg: 'bg-emerald-500', border: 'border-emerald-500', text: 'text-emerald-500', light: 'bg-emerald-500/10', darkBg: 'bg-emerald-950/30' },
};

const DAM_COLORS: {[key: string]: string} = {
  'Omerli': '#60a5fa', 'Darlik': '#818cf8', 'Elmali': '#a78bfa', 'Terkos': '#34d399', 'Alibey': '#fbbf24',
  'Buyukcekmece': '#f87171', 'Sazlidere': '#f472b6', 'Kazandere': '#94a3b8', 'Pabucdere': '#cbd5e1', 'Istrancalar': '#475569'
};

const formatVolume = (m3: number) => {
  if (m3 >= 1000000000) return `${(m3 / 1000000000).toFixed(2)}B m³`;
  if (m3 >= 1000000) return `${(m3 / 1000000).toFixed(1)}M m³`;
  if (m3 >= 1000) return `${(m3 / 1000).toFixed(0)}k m³`;
  return `${m3.toFixed(0)} m³`;
};

// --- TRANSLATION DICTIONARY ---
const dictionary = {
  en: {
    sidebar: { title: "EBYS", subtitle: "DECISION SUPPORT SYSTEM", dash: "Dashboard", pred: "Predictions", dist: "Regional Analysis", docs: "Documentation", crit: "System Critical" },
    header: { system_avg: "System Average", sub_title: "Effective Dam Management System" },
    dashboard: { 
      monitored: "Monitored Reservoirs", 
      analytics: "System Analytics", 
      cap_dist: "Reservoir Capacity Distribution", 
      total: "Total", 
      dist_cons: "District Consumption (m³/day)",
      connected: "connected",
      days_safe: "days safe"
    },
    predictions: {
      forecast_title: "30-Day Dam Depletion Forecast",
      forecast_sub: "Physics-based projection assuming current consumption rates.",
      model_perf: "Model Performance",
      drivers: "Drivers of Consumption",
      r2: "R² Score (Accuracy)",
      mae: "Mean Error (MAE)",
      rmse: "RMSE",
      algo: "Algorithm",
      loading: "Loading Model..."
    },
    districts: {
      name: "District Name",
      risk: "Risk Status",
      daily: "Daily Cons. (m³)",
      supply: "Est. Supply",
      source: "Water Sources",
      driver: "Driver"
    },
    docs: {
      physics_title: "Physics Engine & Dead Volume",
      physics_desc: "The system calculates 'Days to Crisis' based on the usable water column. Water below the intake pipes is considered Dead Volume.",
      glossary_title: "Model Feature Glossary"
    },
    modal: {
      alert_active: "ALERT ACTIVE",
      sys_crit: "System Critical",
      warn: "Warning",
      scenario: "Scenario Analysis",
      projected: "Projected Outcome (30 Days)",
      baseline: "Baseline",
      with_action: "With Action",
      net_retention: "Net Retention",
      conn_dist: "Connected Districts",
      life_ext: "Life Extended By",
      duration: "Duration",
      saved: "Saved",
      full: "FULL",
      reservoir: "Reservoir",
      days: "Days"
    }
  },
  tr: {
    sidebar: { title: "EBYS", subtitle: "KARAR DESTEK SİSTEMİ", dash: "Denetim Paneli", pred: "Tahminler", dist: "Bölgesel Analiz", docs: "Kılavuz", crit: "Sistem Kritik" },
    header: { system_avg: "Sistem Ortalaması", sub_title: "Etkili Baraj Yönetim Sistemi" },
    dashboard: { 
      monitored: "İzlenen Barajlar", 
      analytics: "Sistem Analizi", 
      cap_dist: "Baraj Doluluk Dağılımı", 
      total: "Toplam", 
      dist_cons: "İlçe Tüketimi (m³/gün)",
      connected: "bağlı ilçe",
      days_safe: "gün güvenli"
    },
    predictions: {
      forecast_title: "30 Günlük Baraj Çekilme Tahmini",
      forecast_sub: "Mevcut tüketim oranlarına dayalı fizik tabanlı projeksiyon.",
      model_perf: "Model Performansı",
      drivers: "Tüketim Etkenleri",
      r2: "R² Skoru (Doğruluk)",
      mae: "Ortalama Hata (MAE)",
      rmse: "RMSE",
      algo: "Algoritma",
      loading: "Model Yükleniyor..."
    },
    districts: {
      name: "İlçe Adı",
      risk: "Risk Durumu",
      daily: "Günlük Tük. (m³)",
      supply: "Tahmini Arz",
      source: "Su Kaynakları",
      driver: "Kullanım Türü"
    },
    docs: {
      physics_title: "Fizik Motoru & Ölü Hacim",
      physics_desc: "Sistem, 'Krize Kalan Gün' sayısını kullanılabilir su kolonuna göre hesaplar. Giriş borularının altındaki su Ölü Hacim olarak kabul edilir.",
      glossary_title: "Model Özellik Sözlüğü"
    },
    modal: {
      alert_active: "ALARM AKTİF",
      sys_crit: "Sistem Kritik",
      warn: "Uyarı",
      scenario: "Senaryo Analizi",
      projected: "Öngörülen Sonuç (30 Gün)",
      baseline: "Mevcut Durum",
      with_action: "Eylem İle",
      net_retention: "Net Kazanç",
      conn_dist: "Bağlı İlçeler",
      life_ext: "Kazanılan Süre",
      duration: "Süre",
      saved: "Korundu",
      full: "DOLU",
      reservoir: "Rezervuarı",
      days: "Gün"
    }
  }
};

const translateBackendText = (text: string, lang: 'tr' | 'en') => {
  if (lang === 'en') return text;
  
  const map: {[key: string]: string} = {
    "CUT WATER 20%": "SU KESİNTİSİ %20",
    "INDUSTRIAL CUTOFF": "SANAYİ KESİNTİSİ",
    "24H PRESSURE THROTTLING": "24S BASINÇ DÜŞÜRME",
    "NIGHTLY PRESSURE DROP": "GECE BASINÇ DÜŞÜRME",
    "ACTIVATE BACKUP WELLS": "YEDEK KUYULARI AÇ",
    "ROTATIONAL ZONING": "DÖNÜŞÜMLÜ KESİNTİ",
    "72H SYSTEM CUTOFF": "72S SİSTEM KAPATMA",
    "PRESSURE REDUCTION": "BASINÇ AZALTMA",
    
    "Next 30 Days": "Gelecek 30 Gün",
    "Indefinite": "Süresiz",
    "Continuous": "Sürekli",
    "Residential": "Konutlar",
    "Industrial Zones": "Sanayi Bölgeleri",
    "Infrastructure": "Altyapı",
    "Daily": "Günlük",
    "General Rationing": "Genel Kısıtlama",
    "Target High-Volume Zones": "Yüksek Hacimli Bölgeler",
    "Minimize Pipe Flow": "Boru Akışını Minimize Et",
    "Leak Minimization": "Kaçak Önleme",
    "Supplement Supply": "Arz Takviyesi",
    "Supply Extension": "Arz Uzatma",
    "Emergency Halt": "Acil Durdurma",
    "Total Stoppage": "Tam Durdurma",
    "1 Day/Week Cutoff": "Haftada 1 Gün Kesinti",
    "District Rotation": "İlçe Dönüşümü",
    "4 Days / Month": "Ayda 4 Gün",
    "Daily Operation": "Günlük Operasyon",
    "Groundwater": "Yeraltı Suyu"
  };

  return map[text] || text;
};

export default function App() {
  const [dams, setDams] = useState<Dam[]>([]);
  const [districts, setDistricts] = useState<DistrictSummary[]>([]);
  const [topConsumption, setTopConsumption] = useState<ConsumptionData[]>([]);
  const [damDetail, setDamDetail] = useState<DamDetail | null>(null);
  const [generalOccupancy, setGeneralOccupancy] = useState(0);
  const [occupancyForecast, setOccupancyForecast] = useState<OccupancyForecast | null>(null);
  const [modelStats, setModelStats] = useState<ModelMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState<'dashboard' | 'predictions' | 'districts' | 'docs'>('dashboard');
  
  const [lang, setLang] = useState<'tr' | 'en'>('tr'); 
  
  const [selectedRecommendation, setSelectedRecommendation] = useState<Recommendation | null>(null);
  const [projectedOccupancy, setProjectedOccupancy] = useState<number | null>(null);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const handleEsc = (event: KeyboardEvent) => { if (event.key === 'Escape') closeDamDetail(); };
    window.addEventListener('keydown', handleEsc);
    return () => window.removeEventListener('keydown', handleEsc);
  }, []);

  const fetchData = async () => {
    try {
      const damRes = await axios.get(`${API}/dams`);
      setDams(damRes.data.dams);
      setGeneralOccupancy(damRes.data.general_occupancy_pct);
      const distRes = await axios.get(`${API}/districts`);
      setDistricts(distRes.data.districts);
      const forecastRes = await axios.get(`${API}/predictions/occupancy`);
      setOccupancyForecast(forecastRes.data);
      const statsRes = await axios.get(`${API}/predictions/stats`);
      setModelStats(statsRes.data);
      const consRes = await axios.get(`${API}/consumption/districts`);
      setTopConsumption(consRes.data);
      setLoading(false);
    } catch (error) { console.error(error); setLoading(false); }
  };

  const openDamDetail = async (damName: string) => {
    try {
      const response = await axios.get(`${API}/dam/${damName}`);
      setDamDetail(response.data);
      const rec = response.data.recommendations[0];
      if (rec) {
         setSelectedRecommendation(rec);
         const projected = Math.min(response.data.occupancy_pct + rec.details.retention_30d, 100);
         setProjectedOccupancy(projected);
      } else {
         setSelectedRecommendation(null);
         setProjectedOccupancy(null);
      }
    } catch (error) { console.error(error); }
  };

  const closeDamDetail = () => {
    setDamDetail(null);
    setSelectedRecommendation(null);
    setProjectedOccupancy(null);
  };

  const calculateProjectedEffect = (recommendation: Recommendation) => {
    if (!damDetail) return;
    setProjectedOccupancy(Math.min(damDetail.occupancy_pct + recommendation.details.retention_30d, 100));
    setSelectedRecommendation(recommendation);
  };

  // --- CHARTS ---
  const getForecastChartData = () => {
    if (!occupancyForecast) return { labels: [], datasets: [] };
    const datasets = Object.keys(occupancyForecast.dams).map((damName) => {
      const color = DAM_COLORS[damName] || '#cbd5e1';
      return {
        label: damName,
        data: occupancyForecast.dams[damName],
        borderColor: color,
        backgroundColor: 'transparent',
        tension: 0.4,
        pointRadius: 0,
        borderWidth: 2
      };
    });
    return { labels: occupancyForecast.dates, datasets: datasets };
  };

  const lineChartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'right' as const, labels: { color: '#cbd5e1', font: { size: 14, weight: 'bold' as const }, boxWidth: 20, padding: 15 } },
      title: { display: false },
      tooltip: { mode: 'index' as const, intersect: false, backgroundColor: 'rgba(15, 23, 42, 0.9)' }
    },
    scales: {
      y: { grid: { color: '#1e293b' }, ticks: { color: '#94a3b8' }, min: 0, max: 100 },
      x: { grid: { color: '#1e293b' }, ticks: { color: '#94a3b8', maxTicksLimit: 6 } }
    }
  };

  const getCapacityChartData = () => {
    return {
      labels: dams.map(d => d.name),
      datasets: [{
        data: dams.map(d => d.capacity_m3 || 0),
        backgroundColor: dams.map(d => DAM_COLORS[d.name] || '#cbd5e1'),
        borderWidth: 0,
        hoverOffset: 15
      }]
    };
  };

  const doughnutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    layout: { padding: 0 },
    plugins: {
      legend: { display: false },
      tooltip: { backgroundColor: 'rgba(15, 23, 42, 0.9)' }
    },
    cutout: '40%'
  };

  const getConsumptionChartData = () => {
    if (!topConsumption.length) return { labels: [], datasets: [] };
    return {
      labels: topConsumption.map(d => d.district_name),
      datasets: [{
        label: dictionary[lang].dashboard.dist_cons,
        data: topConsumption.map(d => d.avg_daily_m3),
        backgroundColor: '#3b82f6',
        borderRadius: 4,
        barThickness: 20
      }]
    };
  };

  const consumptionOptions = {
    indexAxis: 'y' as const,
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { color: '#1e293b' }, ticks: { color: '#94a3b8' } },
      y: { grid: { display: false }, ticks: { color: '#cbd5e1', font: { size: 11 } } }
    }
  };

  const getFeatureChartData = () => {
    if (!modelStats?.top_features) return { labels: [], datasets: [] };
    const features = modelStats.top_features.slice(0, 5);
    return {
      labels: features.map(f => f.feature.replace(/_/g, ' ')),
      datasets: [{
        label: 'Impact Score',
        data: features.map(f => f.importance),
        backgroundColor: '#3b82f6',
        borderRadius: 4,
        barThickness: 20
      }]
    };
  };

  const barOptions = {
    indexAxis: 'y' as const,
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { grid: { color: '#1e293b' }, ticks: { color: '#94a3b8' } },
      y: { grid: { display: false }, ticks: { color: '#cbd5e1', font: { size: 11 } } }
    }
  };

  const totalSystemCapacity = dams.reduce((acc, d) => acc + (d.capacity_m3 || 0), 0);
  const criticalCount = dams.filter(d => d.status === 'CRITICAL').length;
  const t = dictionary[lang];

  if (loading) return <div className="min-h-screen bg-slate-950 flex items-center justify-center text-blue-400 font-mono tracking-widest text-xl">{t.predictions.loading}</div>;

  return (
    <div className="min-h-screen bg-slate-950 flex font-sans text-slate-200">
      <aside className="w-64 bg-slate-950 border-r border-slate-800 flex flex-col fixed h-full z-20">
        <div className="p-6 border-b border-slate-800 flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-500 to-cyan-400 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <span className="text-white font-bold text-2xl font-mono">E</span>
          </div>
          <div>
            <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-blue-400 to-cyan-300 font-mono tracking-tighter">{t.sidebar.title}</h1>
            <p className="text-[9px] text-slate-500 font-bold tracking-widest">{t.sidebar.subtitle}</p>
          </div>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          {[{ id: 'dashboard', label: t.sidebar.dash, icon: '📊' }, { id: 'predictions', label: t.sidebar.pred, icon: '📈' }, { id: 'districts', label: t.sidebar.dist, icon: '🌍' }, { id: 'docs', label: t.sidebar.docs, icon: '📘' }].map((item) => (
            <button key={item.id} onClick={() => setCurrentPage(item.id as any)} className={`w-full text-left px-4 py-3 rounded-lg transition-all flex items-center gap-3 ${currentPage === item.id ? 'bg-blue-600 text-white shadow-lg shadow-blue-900/20' : 'hover:bg-slate-800 text-slate-400'}`}>
              <span>{item.icon}</span><span className="font-semibold">{item.label}</span>
            </button>
          ))}
        </nav>
        <div className="p-6 border-t border-slate-800 bg-slate-900/50">
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs font-bold text-red-500 uppercase">{t.sidebar.crit}</span>
            <span className="bg-red-500/10 text-red-400 text-xs px-2 py-1 rounded-full font-mono">{criticalCount}</span>
          </div>
          <div className="w-full bg-slate-800 h-1.5 rounded-full overflow-hidden"><div className="bg-red-500 h-full" style={{width: `${(criticalCount/dams.length)*100}%`}}></div></div>
        </div>
      </aside>

      <main className="flex-1 ml-64 p-8 h-screen overflow-y-auto bg-slate-950">
        
        {/* TOP BAR */}
        <div className="flex justify-between items-start mb-10">
           <div>
             <h2 className="text-4xl font-extrabold text-white tracking-tight mb-2">
               {currentPage === 'dashboard' ? t.sidebar.dash : 
                currentPage === 'predictions' ? t.sidebar.pred :
                currentPage === 'districts' ? t.sidebar.dist : t.sidebar.docs}
             </h2>
             <p className="text-slate-400 text-base font-light">{t.header.sub_title}</p>
           </div>
           
           <div className="flex items-center gap-6">
              <div className="flex items-center gap-3 bg-slate-900/50 border border-slate-700/50 px-5 py-2.5 rounded-full backdrop-blur-md">
                 <span className="text-slate-400 text-xs uppercase tracking-wide font-semibold">{t.header.system_avg}</span>
                 <span className={`text-xl font-bold font-mono ${generalOccupancy < 20 ? 'text-red-400' : 'text-blue-400'}`}>
                   {generalOccupancy.toFixed(1)}%
                 </span>
              </div>
              <div className="flex bg-slate-900 border border-slate-700 rounded-lg p-1">
                 <button onClick={() => setLang('tr')} className={`px-3 py-1 rounded text-xs font-bold transition-all ${lang === 'tr' ? 'bg-blue-600 text-white' : 'text-slate-500 hover:text-white'}`}>TR</button>
                 <button onClick={() => setLang('en')} className={`px-3 py-1 rounded text-xs font-bold transition-all ${lang === 'en' ? 'bg-blue-600 text-white' : 'text-slate-500 hover:text-white'}`}>EN</button>
              </div>
           </div>
        </div>

        {currentPage === 'dashboard' && (
          <div className="space-y-8">
             <div className="grid grid-cols-4 gap-4">
               {dams.map(dam => (
                 <button key={dam.name} onClick={() => openDamDetail(dam.name)} className={`p-5 rounded-xl border transition-all hover:scale-[1.02] text-left relative overflow-hidden group ${dam.status === 'CRITICAL' ? 'bg-red-950/10 border-red-900/30 hover:border-red-600' : dam.status === 'WARNING' ? 'bg-orange-950/10 border-orange-900/30 hover:border-orange-600' : dam.status === 'CAUTION' ? 'bg-yellow-950/10 border-yellow-900/30 hover:border-yellow-600' : 'bg-slate-900 border-slate-800 hover:border-blue-500'}`}>
                   <div className="flex justify-between items-center mb-2 relative z-10">
                     <h3 className="font-bold text-slate-100 text-lg">{dam.name}</h3>
                     <div className="relative flex h-3 w-3">
                       <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${statusColors[dam.status].bg} opacity-75`}></span>
                       <span className={`relative inline-flex rounded-full h-3 w-3 ${statusColors[dam.status].bg}`}></span>
                     </div>
                   </div>
                   <div className="relative z-10">
                      <p className={`text-3xl font-bold font-mono ${statusColors[dam.status].text}`}>{dam.occupancy_pct.toFixed(0)}%</p>
                      <p className="text-xs text-slate-400 mt-1 flex justify-between">
                        <span>{dam.connected_districts_count} {t.dashboard.connected}</span>
                      </p>
                   </div>
                   <div className={`absolute bottom-0 left-0 h-1 ${statusColors[dam.status].bg}`} style={{width: `${dam.occupancy_pct}%`}}></div>
                 </button>
               ))}
             </div>
             <div>
                <h3 className="text-xl font-bold text-white mb-4 uppercase tracking-wider border-b border-slate-800 pb-2">{t.dashboard.analytics}</h3>
                <div className="grid grid-cols-2 gap-6">
                   <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 h-[400px]">
                      <h4 className="text-sm font-bold text-slate-400 mb-6 uppercase">{t.dashboard.cap_dist}</h4>
                      <div className="flex items-center h-[280px]">
                         <div className="w-1/2 h-full relative">
                            <Doughnut data={getCapacityChartData()} options={doughnutOptions} />
                            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                               <div className="text-center">
                                  <p className="text-[10px] text-slate-500 uppercase tracking-widest">{t.dashboard.total}</p>
                                  <p className="text-lg font-bold text-white">{(totalSystemCapacity/1e9).toFixed(2)}B m³</p>
                               </div>
                            </div>
                         </div>
                         <div className="w-1/2 pl-6 pr-4 overflow-y-auto h-full custom-scrollbar">
                            <div className="space-y-2">
                               {dams.sort((a,b) => b.capacity_m3 - a.capacity_m3).map(d => (
                                  <div key={d.name} className="flex justify-between items-center text-sm py-2 border-b border-slate-800/50">
                                     <div className="flex items-center gap-3">
                                        <div className="w-3 h-3 rounded-full" style={{backgroundColor: DAM_COLORS[d.name]}}></div>
                                        <span className="text-slate-300 font-medium">{d.name}</span>
                                     </div>
                                     <span className="text-slate-500 font-mono">{(d.capacity_m3/1e6).toFixed(0)}M</span>
                                  </div>
                               ))}
                            </div>
                         </div>
                      </div>
                   </div>
                   <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 h-[400px] flex flex-col">
                      <h4 className="text-sm font-bold text-slate-400 mb-4 uppercase">{t.dashboard.dist_cons}</h4>
                      <div className="flex-1 overflow-y-auto custom-scrollbar pr-2">
                         <div className="h-[1200px]"><Bar data={getConsumptionChartData()} options={consumptionOptions} /></div>
                      </div>
                   </div>
                </div>
             </div>
          </div>
        )}

        {currentPage === 'predictions' && (
          <div className="space-y-6">
             <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 h-[500px] flex flex-col">
               <h3 className="text-xl font-bold text-slate-200 mb-2">{t.predictions.forecast_title}</h3>
               <p className="text-sm text-slate-500 mb-4">{t.predictions.forecast_sub}</p>
               <div className="flex-1 w-full relative">
                 {occupancyForecast ? <Line data={getForecastChartData()} options={lineChartOptions} /> : <div className="text-center text-slate-500 mt-20">{t.predictions.loading}</div>}
               </div>
             </div>
             <div className="grid grid-cols-2 gap-6">
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                    <div className="flex justify-between items-center mb-6">
                        <h3 className="text-sm font-bold text-slate-400 uppercase">{t.predictions.model_perf}</h3>
                    </div>
                    {modelStats ? (
                       <div className="grid grid-cols-2 gap-4">
                          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800"><p className="text-xs text-slate-500 mb-1">{t.predictions.r2}</p><p className="text-3xl font-bold text-green-400 font-mono">{modelStats.cross_validation.val_r2.toFixed(3)}</p></div>
                          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800"><p className="text-xs text-slate-500 mb-1">{t.predictions.mae}</p><p className="text-3xl font-bold text-amber-400 font-mono">{(modelStats.cross_validation.val_mae/1000).toFixed(1)}k <span className="text-sm text-slate-600">m³</span></p></div>
                          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800"><p className="text-xs text-slate-500 mb-1">{t.predictions.rmse}</p><p className="text-3xl font-bold text-blue-400 font-mono">{(modelStats.cross_validation.val_rmse/1000).toFixed(1)}k</p></div>
                          <div className="bg-slate-950 p-4 rounded-lg border border-slate-800"><p className="text-xs text-slate-500 mb-1">{t.predictions.algo}</p><p className="text-lg font-bold text-slate-300">Random Forest</p></div>
                       </div>
                    ) : <p className="text-slate-500">Loading metrics...</p>}
                </div>
                <div className="bg-slate-900 border border-slate-800 rounded-xl p-6">
                   <h3 className="text-sm font-bold text-slate-400 uppercase mb-4">{t.predictions.drivers}</h3>
                   <div className="h-[200px] w-full">{modelStats?.top_features ? <Bar data={getFeatureChartData()} options={barOptions} /> : <div className="text-slate-500">Loading features...</div>}</div>
                </div>
             </div>
          </div>
        )}

        {currentPage === 'districts' && (
          <div className="space-y-6">
             <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
                <table className="w-full text-left">
                   <thead className="bg-slate-950 text-slate-400 text-xs uppercase font-bold">
                      <tr><th className="p-4">{t.districts.name}</th><th className="p-4">{t.districts.risk}</th><th className="p-4">{t.districts.daily}</th><th className="p-4">{t.districts.supply}</th><th className="p-4">{t.districts.source}</th><th className="p-4 text-right">{t.districts.driver}</th></tr>
                   </thead>
                   <tbody className="divide-y divide-slate-800">
                      {districts.map(dist => (
                         <tr key={dist.name} className="hover:bg-slate-800/50 transition-colors">
                            <td className="p-4 font-medium text-slate-200">{dist.name}</td>
                            <td className="p-4"><span className={`px-2 py-1 rounded text-xs font-bold ${statusColors[dist.status].light} ${statusColors[dist.status].text}`}>{dist.status}</span></td>
                            <td className="p-4 text-sm text-slate-400 font-mono">{dist.daily_cons.toLocaleString()}</td>
                            <td className="p-4 text-sm text-slate-400 font-mono">~{dist.days_supply} {t.modal.days}</td>
                            <td className="p-4 text-[10px] text-slate-600 max-w-xs leading-tight font-mono">{dist.source_dams.map(d => d.name).join(', ')}</td>
                            <td className="p-4 text-right text-xs text-slate-500 uppercase tracking-wide">{translateBackendText(dist.primary_driver, lang)}</td>
                         </tr>
                      ))}
                   </tbody>
                </table>
             </div>
          </div>
        )}

        {currentPage === 'docs' && (
           <div className="space-y-8 max-w-4xl mx-auto pb-10">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-8">
                 <h3 className="text-2xl font-bold text-white mb-4">{t.docs.physics_title}</h3>
                 <p className="text-slate-400 mb-4">{t.docs.physics_desc}</p>
                 <div className="bg-slate-950 p-4 rounded-lg border border-slate-800 font-mono text-sm text-blue-300">IF Current_Level &lt; Dead_Volume_Limit THEN Days_Left = 0</div>
              </div>
              
              {/* Detailed Metrics Documentation Table */}
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-8">
                 <h3 className="text-2xl font-bold text-white mb-6">{t.docs.glossary_title}</h3>
                 <div className="grid grid-cols-1 gap-4">
                    {[
                       {code: 'consumption_roll_3m', en: 'Rolling Average (3 Months)', tr: 'Hareketli Ortalama (3 Ay)', desc: 'Used to smooth out short-term fluctuations and identify seasonal trends.'},
                       {code: 'consumption_lag_1m', en: 'Lag Feature (1 Month)', tr: 'Gecikmeli Veri (1 Ay)', desc: 'The exact consumption from the previous month; highly predictive for the next month.'},
                       {code: 'monthly_calls', en: 'ISKI Breakdown Calls', tr: 'ISKI Arıza Çağrıları', desc: 'Indicates infrastructure stress. Higher calls correlate with higher water loss due to leaks.'},
                       {code: 'R² Score', en: 'Statistical Accuracy', tr: 'İstatistiksel Doğruluk', desc: '0.92 means the model explains 92% of the variance in the data. Higher is better.'},
                       {code: 'RMSE', en: 'Root Mean Square Error', tr: 'Kök Ortalama Kare Hata', desc: 'The average magnitude of the prediction error in cubic meters (m³). Lower is better.'}
                    ].map(item => (
                       <div key={item.code} className="bg-slate-950 p-5 rounded-lg border border-slate-800 flex justify-between items-start">
                          <div>
                             <h4 className="text-blue-400 font-bold font-mono text-lg">{item.code}</h4>
                             <p className="text-slate-500 text-xs mt-1">{item.en} / {item.tr}</p>
                          </div>
                          <p className="text-slate-400 text-sm max-w-lg text-right">{item.desc}</p>
                       </div>
                    ))}
                 </div>
              </div>
           </div>
        )}
      </main>

      {damDetail && (
        <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4" onClick={closeDamDetail}>
           <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-6xl shadow-2xl flex flex-col max-h-[90vh]" onClick={(e) => e.stopPropagation()}>
              
              {/* STATUS BANNER */}
              {damDetail.status !== 'SAFE' && (
                 <div className={`px-8 py-3 flex items-center gap-4 ${damDetail.status === 'CRITICAL' ? 'bg-red-900/80 border-b border-red-700' : 'bg-orange-900/80 border-b border-orange-700'} text-white rounded-t-2xl`}>
                    <span className="text-2xl">⚠️</span>
                    <div className="flex-1 flex justify-between items-center">
                       <span className="text-base font-bold">{damDetail.status === 'CRITICAL' ? t.modal.sys_crit : t.modal.warn} - {t.modal.alert_active}</span>
                       <span className="text-sm opacity-90">{damDetail.status === 'CRITICAL' ? `Only ${damDetail.days_to_crisis} days remaining.` : `Check levels.`}</span>
                    </div>
                 </div>
              )}

              {/* HEADER */}
              <div className="px-8 py-6 border-b border-slate-800 bg-slate-900 grid grid-cols-3 gap-8 items-center shrink-0">
                 <div className="col-span-2"><h2 className="text-4xl font-bold text-white tracking-tight">{damDetail.dam} {t.modal.reservoir}</h2></div>
                 <div className="relative flex items-center justify-center">
                    <div className="relative group flex items-center justify-center">
                       <svg className="w-20 h-20 transform -rotate-90 drop-shadow-2xl">
                          <circle cx="40" cy="40" r="36" stroke="#1e293b" strokeWidth="6" fill="transparent" />
                          <circle cx="40" cy="40" r="36" stroke={damDetail.status === 'CRITICAL' ? '#ef4444' : damDetail.status === 'WARNING' ? '#f97316' : '#3b82f6'} strokeWidth="6" fill="transparent" strokeDasharray={2 * Math.PI * 36} strokeDashoffset={2 * Math.PI * 36 * (1 - damDetail.occupancy_pct / 100)} strokeLinecap="round" className="transition-all duration-1000 ease-out" style={{ filter: `drop-shadow(0 0 6px ${damDetail.status === 'CRITICAL' ? '#ef4444' : '#3b82f6'})` }} />
                       </svg>
                       <div className="absolute inset-0 flex items-center justify-center"><span className={`text-2xl font-bold font-mono tracking-tighter ${damDetail.status === 'CRITICAL' ? 'text-red-400' : damDetail.status === 'WARNING' ? 'text-orange-400' : 'text-blue-100'}`}>{damDetail.occupancy_pct.toFixed(0)}%</span></div>
                    </div>
                    <button onClick={closeDamDetail} className="absolute right-0 text-slate-500 hover:text-white text-4xl leading-none transition-colors">&times;</button>
                 </div>
              </div>

              {/* BODY CONTENT */}
              <div className="p-8 overflow-y-auto">
                 <div className="grid grid-cols-3 gap-8">
                    
                    {/* LEFT COLUMN: SCENARIOS */}
                    <div className="col-span-2 flex flex-col gap-6">
                       <h3 className="text-sm font-bold text-slate-400 uppercase tracking-widest">{t.modal.scenario}</h3>
                       
                       {/* Scenarios Grid */}
                       <div className="grid grid-cols-2 gap-4">
                          {damDetail.recommendations.map((rec, i) => (
                             <button key={i} onClick={() => calculateProjectedEffect(rec)} className={`text-left p-5 rounded-xl border transition-all hover:scale-[1.01] flex flex-col justify-between min-h-[120px] ${selectedRecommendation?.action === rec.action ? 'bg-blue-600 border-blue-500 ring-2 ring-blue-400/50' : 'bg-slate-800 border-slate-700 hover:border-blue-500'}`}>
                                <div className="flex justify-between items-start">
                                   <span className="font-bold text-white text-sm">{translateBackendText(rec.action, lang)}</span>
                                   <span className={`text-[10px] font-bold px-2 py-0.5 rounded ${rec.priority === 'CRITICAL' ? 'bg-red-900/50 text-red-400' : 'bg-blue-900/50 text-blue-400'}`}>{rec.priority}</span>
                                </div>
                                <div className="space-y-1.5 mt-2">
                                   <div className="flex justify-between text-xs text-slate-300"><span className="opacity-70">{t.modal.life_ext}:</span> <span className="text-green-400 font-bold">+{rec.details.days_gained} {t.modal.days}</span></div>
                                   <div className="flex justify-between text-xs text-slate-300"><span className="opacity-70">{t.modal.duration}:</span> <span>{translateBackendText(rec.details.duration, lang)}</span></div>
                                </div>
                             </button>
                          ))}
                       </div>

                       {/* Outcome Box */}
                       <div className="bg-slate-950 border border-slate-800 p-6 rounded-xl mt-auto">
                          <h4 className="text-xs font-bold text-slate-500 uppercase mb-4 tracking-wider">{t.modal.projected}</h4>
                          <div className="grid grid-cols-3 gap-4 items-center divide-x divide-slate-800/50">
                             <div className="text-center px-2">
                                <p className="text-slate-500 text-xs uppercase mb-1">{t.modal.baseline}</p>
                                <p className={`text-3xl font-bold font-mono ${statusColors[damDetail.status].text}`}>{damDetail.occupancy_pct.toFixed(1)}%</p>
                                <p className="text-xs text-slate-500 mt-1 font-mono">{formatVolume(damDetail.volume_m3)}</p>
                             </div>
                             <div className="text-center px-2 relative">
                                <p className="text-slate-500 text-xs uppercase mb-1">{t.modal.with_action}</p>
                                {projectedOccupancy ? (
                                   <>
                                      <p className="text-3xl font-bold text-green-400 font-mono">{projectedOccupancy.toFixed(1)}%</p>
                                      <p className="text-xs text-slate-500 mt-1 font-mono">{formatVolume(damDetail.capacity_m3 * (projectedOccupancy/100))}</p>
                                   </>
                                ) : <p className="text-3xl font-bold text-slate-700">--.-%</p>}
                                <div className="absolute -left-3 top-1/2 -translate-y-1/2 text-slate-700 text-xl">➔</div>
                             </div>
                             <div className="text-center px-2">
                                <p className="text-slate-500 text-xs uppercase mb-1">{t.modal.net_retention}</p>
                                {projectedOccupancy ? (
                                   <>
                                      <span className="text-green-400 font-bold text-2xl block font-mono">+{selectedRecommendation?.details.retention_30d.toFixed(1)}%</span>
                                      <span className="text-xs text-slate-500 block font-mono">+{formatVolume(selectedRecommendation?.details.vol_saved_m3 || 0)}</span>
                                   </>
                                ) : <span className="text-slate-700 font-bold text-2xl block">---</span>}
                             </div>
                          </div>
                       </div>
                    </div>

                    {/* RIGHT COLUMN: CONNECTED DISTRICTS */}
                    <div className="relative col-span-1 min-h-[400px]"> 
                       <div className="absolute inset-0 flex flex-col bg-slate-900/50 rounded-xl border border-slate-800/50 p-5">
                          <h3 className="text-sm font-bold text-slate-400 uppercase mb-4 shrink-0 tracking-widest">{t.modal.conn_dist}</h3>
                          <div className="flex-1 overflow-y-auto pr-2 custom-scrollbar space-y-3">
                             {damDetail.connected_districts.map(dist => (
                                <div key={dist.name} className="flex justify-between items-center p-3 rounded bg-slate-800 border border-slate-700 hover:border-slate-500 transition-colors">
                                   <span className="text-sm text-slate-200 font-medium">{dist.name}</span>
                                </div>
                             ))}
                          </div>
                       </div>
                    </div>

                 </div>
              </div>
           </div>
        </div>
      )}
    </div>
  );
}