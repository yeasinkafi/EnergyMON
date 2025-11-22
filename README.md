

# 📘 **README.md – EnergyMon**

# ⚡ EnergyMon – IoT-Based Real-Time Energy Monitoring Dashboard

EnergyMon is a Python + Flask–based IoT energy monitoring system that connects to a **Tuya Smart Plug (20A)** and provides **real-time power, voltage, and current readings**, historical data analysis, and CSV export capability — all through a modern, responsive dashboard.

The system is ideal for monitoring appliances such as **TV, Laptop, Desktop PC, Monitor, and AC**.



## 🚀 Features

### 🔌 Real-Time Monitoring

* Power (W), Voltage (V), Current (A) updated every second
* Live second-by-second chart
* Device ON/OFF state indicator

### 📊 Aggregated Energy Analytics

* Minute, Hourly, Daily, and Weekly trends
* Average Power + Energy (kWh)
* Server-side bucketing for smooth charts

### 🗓 Historical View

* View any chosen day’s consumption
* 10-minute interval graph
* Ideal for long-term analysis

### 🎛 Smart Plug Control

* Turn device **ON/OFF** from dashboard
* Auto-detects `switch_1` / `switch` datapoints

### 🗄 Local Database (SQLite)

* Stores timestamps, voltage, current, power
* Auto-created `power.db`
* Efficient time-series storage

### 📥 CSV Export (ZIP)

* One-click “Download CSV”
* Includes readable 12-hour timestamps
* Works perfectly in Excel



## 📁 Project Structure

```
.
├── PCmonitoringAPP.py        # Flask backend
├── dashboard.html            # Dashboard UI
├── power.db                  # Local SQLite database
├── requirements.txt          # Dependencies
└── README.md                 # User Manual
```



## 🛠 Installation

### 1. Install Python (3.9+ recommended)

[https://www.python.org/downloads/](https://www.python.org/downloads/)

Ensure `pip` is installed.



### 2. Install dependencies

```
pip install -r requirements.txt
```

---

### 3. Configure Tuya API

Create a Tuya Cloud project:

1. Log in at [https://iot.tuya.com](https://iot.tuya.com)
2. Create a Cloud Project
3. Link your Smart Life App account
4. Copy these values:

```
ACCESS_ID
ACCESS_SECRET
DEVICE_ID
```

Update them inside **PCmonitoringAPP.py** if needed:

```python
ACCESS_ID     = 'your_access_id'
ACCESS_SECRET = 'your_access_secret'
DEVICE_ID     = 'your_device_id'
```



## ▶️ Running the Application

Start the backend:

```
python PCmonitoringAPP.py
```

Then open the dashboard in your browser:

```
http://localhost:5000
```

A background thread will automatically start logging energy readings every 15 seconds.



## 🖥 Dashboard Usage

### Real-Time Monitoring

* Power, Voltage, and Current update live
* Live seconds chart automatically scrolls

### Aggregated Monitoring

Tabs include:

* Minutes
* Hourly
* Daily
* Weekly

Each view shows:

* Avg Power (W)
* Energy (kWh)

### Historical View

Select a date → View that day's energy pattern in 10-min bins.

### ON/OFF Control

Click the button to toggle the plug.
Supports both `switch` and `switch_1`.



## 📥 CSV Export

You can download all logged data via:

```
⬇️ Download CSV
```

The export includes:

* UNIX timestamp (`ts`)
* Voltage
* Current
* Power
* `readable_time` (12-hour **AM/PM**)

Export is delivered as:

```
energy_data_csv.zip
```

With one CSV per database table.



## 🔒 Data Privacy

* All data stored **locally** in `power.db`
* No personal info is collected
* API secrets remain on your machine



## 🧪 Tested Appliances

EnergyMon was tested with:

* Television
* Laptop
* Desktop Monitor
* Desktop PC
* Air Conditioner




## 🌱 Future Improvements

* Multiple-device monitoring
* Predictive energy usage (AI/ML)
* Mobile app integration
* True real-time push updates (WebSockets)
* Energy billing predictions



## 👨‍💻 Credits

Developed for:
**CSE407 – Green Computing**
Midterm Project
East West University

