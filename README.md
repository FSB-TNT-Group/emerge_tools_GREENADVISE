# emerge_tools_GREENADVISE

# GREENADVISE V1.1 — Setup Guide

## Requirements

- **Windows 10 or 11** (64-bit)
- **Python 3.9 or newer**
  Download: [https://www.python.org/downloads/](https://www.python.org/downloads/)
  > During installation, check **"Add Python to PATH"**
- Internet connection (for package installation and weather data)

---

## Step 1 — Download the application files

Download or clone the repository and make sure your folder contains:

```
GREENADVISE\
GREENADVISE_installer.py
GREENADVISE_V1_Launcher.exe
```

---

## Step 2 — Create a Renewables.ninja account and get your API key

1. Go to [https://www.renewables.ninja/](https://www.renewables.ninja/)
2. Click **Register** and create a free account
3. After logging in, navigate to your **profile page**
4. Copy your **API token** and save it — you will need it in Step 5

---

## Step 3 — Run the installer (one time only)

Run the installer once before launching the app for the first time.

**Option A — Command Prompt:**

```bash
cd path\to\GREENADVISE
python GREENADVISE_installer.py
```

**Option B — IDE (PyCharm, VS Code, etc.):**

Open `GREENADVISE_installer.py` and run it with F5 or the Run button.

When prompted, press **ENTER** to confirm installation.

The installer will set up all required packages:

| Package | Version | Purpose |
|---|---|---|
| PyQt5 | 5.15.11 | GUI framework |
| PyQtWebEngine | 5.15.7 | Interactive map display |
| matplotlib | 3.10.9 | Charts and plots |
| numpy | 2.3.5 | Numerical computing |
| pandas | 2.3.3 | Data manipulation |
| pyomo | 6.9.5 | Optimization modeling |
| requests | 2.32.5 | Renewables.ninja API calls |
| openpyxl | 3.1.5 | Excel export |
| scipy | 1.17.0 | Scientific computing |
| torch | 2.7.0 | Neural network (CPU, ~250 MB) |

> Installation may take several minutes depending on your internet speed.
> If any package fails, install it manually: `pip install <package-name>`

---

## Step 4 — Launch the application

Double-click **`GREENADVISE_V1_Launcher.exe`**.

> **First launch note:** The application needs **15–20 seconds** to load all required files.
> If the window does not appear, wait up to 20 seconds. If it still doesn't respond,
> close it completely and relaunch — it will start normally on the second run.

---

## Step 5 — Enter your API key

1. Once the application is open, locate the **API key field**
2. Paste your Renewables.ninja API token from Step 2
3. The key is saved automatically — you only need to enter it once

---

## Troubleshooting

- Make sure Python 3.9+ is installed and added to PATH
- Re-run `GREENADVISE_installer.py` if any packages are missing
- Check your internet connection if weather data cannot be fetched
