# Butterfly Tester – Setup

## 1. Install Python

You need **Python 3.8 or newer** on your machine.

- **Option A:** [python.org/downloads](https://www.python.org/downloads/) — during setup, check **“Add python.exe to PATH”**.
- **Option B:** Install from Microsoft Store (search “Python 3.12”).

## 2. Create virtual environment and install dependencies

In PowerShell, from the project folder:

```powershell
.\setup_venv.ps1
```

This will:

- Create a `venv` folder (virtual environment).
- Install: **PyQt5**, **pyserial**, **PyVISA**, **pythonnet**.

## 3. Run the app

Activate the venv and start the app:

```powershell
.\venv\Scripts\Activate.ps1
python main.py
```

If you see “Python was not found”, install Python as in step 1 and run `.\setup_venv.ps1` again.
