# EMG Recording Inspector

Double-click `run_inspector.bat` to open the local browser app. Alternatively:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address 127.0.0.1
```

First-time setup on another computer:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Choose a recording, gesture, trial, channels, and time window. Zoom and hover over plots. Large windows use min/max envelopes to retain peaks; CSV exports preserve full samples. Review quality checks and channel statistics, inspect trial sample counts, or scan every recording from Recording summary.

The signal viewer marks recorded gesture intervals with consistent colored bands on every selected channel. The legend identifies gestures; hovering over signals shows the gesture and trial. Windows containing up to 24 intervals also show gesture names inside each channel plot. Toggle **Mark gesture intervals** to hide the bands. Ch1–Ch8 are EMG and Ch9–Ch11 are IMU; all eleven channels are selected initially. IMU axes and physical units are not assumed.

For samples, click **Prepare selected samples CSV**, then **Save selected samples CSV**. Quality reports have a **Save quality report CSV** link. These browser-local links avoid the Streamlit download widget's server-connection error. If an old error remains visible after updating, refresh the browser with Ctrl+F5. Keep the launcher terminal open while using the app.

The app reads existing CSVs and metadata without modifying them. It checks invalid/missing values, infinity, constant channels, non-increasing timestamps, gaps within the same trial and label, unknown labels, and metadata sample-count mismatches. Review flags require human interpretation: pauses may be intentional, constant auxiliary sensors may be normal, and small count deviations may come from capture timing. No ADC clipping threshold or channel sensor type is assumed because the metadata does not define these. No filtering is applied; optional DC removal only changes the plot.
