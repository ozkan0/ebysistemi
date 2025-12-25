# EBYS - Efektif Baraj Yönetim Sistemi / Effective Dam Management System

**Hibrit Yapay Zeka (Random Forest + Fizik Motoru) destekli Karar Destek Sistemi.**
**---Çeviriler hatalı olabilir. Ayrıca gerçek hayatta, ilgili yönetim sistemine tam entegre edilmesi için yeterince hazır değildir.---**
**A Decision Support System powered by Hybrid Machine Learning (Random Forest + Physics Engine).**
**---Translations may be inaccurate. Furthermore, in real life, it is not sufficiently prepared for full integration into the relevant management system.---**

---

## 🌐 Live Demo / Canlı Demo 
👉 **[https://ebysistemi.vercel.app/](https://ebysistemi.vercel.app/)**

---


## 🇹🇷 Hızlı Başlangıç Kılavuzu (Türkçe)

### 1. Gereksinimler
*   **Node.js** & **npm** (Arayüz için)
*   **Python 3.8+** (Sunucu ve Yapay Zeka için)

### 2. Yerel Kurulum (Localhost)

#### Adım A: Backend Kurulumu (Python/FastAPI)
Backend, yapay zeka modelini çalıştırır ve API hizmeti verir.

1.  Terminali açın ve backend klasörüne gidin:
    ```bash
    cd backend
    ```
2.  (Opsiyonel) Sanal ortam oluşturun (Olası VSCode hatalarını için önerilir):
    ```bash
    python -m venv .venv
    # Windows için:
    .venv\Scripts\activate
    # Mac/Linux için:
    source .venv/bin/activate
    ```
3.  Kütüphaneleri yükleyin:
    ```bash
    pip install -r requirements.txt
    ```
4.  Sunucuyu başlatın:
    ```bash
    python main.py
    ```
    *API `http://localhost:8000` adresinde çalışmaya başlayacaktır.*

#### Adım B: Frontend Kurulumu (React)
Frontend, verileri ve senaryoları görselleştirir.

1.  **Yeni** bir terminal penceresi açın ve frontend klasörüne gidin:
    ```bash
    cd frontend
    ```
2.  Paketleri yükleyin:
    ```bash
    npm install
    ```
3.  Uygulamayı başlatın:
    ```bash
    npm start
    ```
    *Uygulama `http://localhost:3000` adresinde açılacaktır.*

---

## 🇬🇧 Quick Start Guide (English)

### 1. Prerequisites
*   **Node.js** & **npm** (for Frontend)
*   **Python 3.8+** (for Backend)

### 2. Local Setup

#### Step A: Backend Setup (Python/FastAPI)
The backend runs the ML models and serves the API.

1.  Open a terminal and navigate to the backend folder:
    ```bash
    cd backend
    ```
2.  (Optional) Create a virtual environment (Suggested for possible VSCode errors):
    ```bash
    python -m venv .venv
    # Windows:
    .venv\Scripts\activate
    # Mac/Linux:
    source .venv/bin/activate
    ```
3.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```
4.  Start the server:
    ```bash
    python main.py
    ```
    *The API will start at `http://localhost:8000`*

#### Step B: Frontend Setup (React)
The frontend visualizes the data and scenarios.

1.  Open a **new** terminal window and navigate to the frontend folder:
    ```bash
    cd frontend
    ```
2.  Install dependencies:
    ```bash
    npm install
    ```
3.  Start the application:
    ```bash
    npm start
    ```
    *The App will open at `http://localhost:3000`*
