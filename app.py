from pathlib import Path
import base64
import html
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative
from plotly.subplots import make_subplots
import streamlit as st
from analysis import load_recording, inspect_recording


def csv_download_link(data, filename, label):
    """Browser-local download: avoids Streamlit's server-URI download widget."""
    encoded = base64.b64encode(data.encode('utf-8-sig')).decode('ascii')
    st.markdown(
        f'<a download="{html.escape(filename, quote=True)}" '
        f'href="data:text/csv;base64,{encoded}">{html.escape(label)}</a>',
        unsafe_allow_html=True,
    )

st.set_page_config(page_title='EMG Recording Inspector', page_icon='📈', layout='wide')
st.title('EMG Recording Inspector')
st.caption('Browse recordings, compare channels, and review acquisition issues.')

@st.cache_data(max_entries=12)
def read(path, modified):
    return load_recording(path)

root = st.sidebar.text_input('Data folder', str(Path(__file__).parent / 'EMG_DataSet_Fall26'))
folder = Path(root)
if not folder.is_dir():
    st.info('Enter an existing data folder in the sidebar.')
    st.stop()
files = sorted(folder.rglob('emg_data*.csv'))
if not files:
    st.info('No emg_data*.csv recordings found.')
    st.stop()
file = st.sidebar.selectbox('Recording', files, format_func=lambda p: p.parent.name)
if st.sidebar.button('Refresh data'):
    st.cache_data.clear()
try:
    df, meta, channels = read(str(file), file.stat().st_mtime_ns)
except Exception as exc:
    st.error(f'Cannot read {file.name}: {exc}')
    st.stop()
if df.empty:
    st.warning('This recording has no samples.')
    st.stop()
issues = inspect_recording(df, meta, channels)
a, b, c, d = st.columns(4)
a.metric('Samples', f'{len(df):,}')
b.metric('Channels', len(channels))
c.metric('Trials', df.Trial_ID.nunique() if 'Trial_ID' in df else '—')
d.metric('Checks to review', len(issues))
signal_tab, quality_tab, summary_tab = st.tabs(['Signal viewer', 'Quality checks', 'Recording summary'])
with signal_tab:
    if 'Timestamp_ms' not in df or not channels:
        st.error('Signal viewing requires timestamps and channel columns. See Quality checks.')
    else:
        left, right = st.columns([1, 3])
        with left:
            labels = ['All gestures', *sorted(df.Label.dropna().astype(str).unique())] if 'Label' in df else ['All gestures']
            label = st.selectbox('Gesture', labels)
            subset = df if label == 'All gestures' else df[df.Label.astype(str).eq(label)]
            trials = subset.Trial_ID.dropna().unique().tolist() if 'Trial_ID' in subset else []
            trial = st.selectbox('Trial', ['Full recording', *trials])
            if trial != 'Full recording':
                subset = subset[subset.Trial_ID.eq(trial)]
            selected = st.multiselect('Channels', channels, default=channels,
                                      format_func=lambda ch: f'{ch} · IMU' if ch in ['Ch9', 'Ch10', 'Ch11'] else f'{ch} · EMG')
            centered = st.checkbox('Remove DC offset for viewing', value=False)
            mark_gestures = st.checkbox('Mark gesture intervals', value=True)
            st.caption('Ch1–Ch8: EMG. Ch9–Ch11: IMU. Each channel keeps its own scale; IMU axes and units have not been specified.')
        with right:
            valid = subset.Timestamp_ms.dropna()
            if valid.empty:
                st.warning('No valid timestamps in this selection.')
            else:
                origin = df.Timestamp_ms.dropna().iloc[0]
                times = (subset.Timestamp_ms - origin) / 1000
                lo, hi = float(times.min()), float(times.max())
                window = st.slider('Time window (seconds from recording start)', lo, hi, (lo, hi)) if hi > lo else (lo, hi)
                view = subset.loc[times.between(*window)].copy()
                st.caption(f'{len(view):,} samples in window. Plots use min/max envelopes for large windows; quality checks use all samples.')
                if selected and not view.empty:
                    titles = [f'{ch} · {"IMU" if ch in ["Ch9", "Ch10", "Ch11"] else "EMG"}' for ch in selected]
                    fig = make_subplots(rows=len(selected), cols=1, shared_xaxes=True, subplot_titles=titles, vertical_spacing=0.025)
                    # Break traces across filtered-out rows and acquisition pauses.
                    segments = (view.index.to_series().diff().ne(1) | view.Timestamp_ms.diff().gt(100)).cumsum()
                    bucket_size = max(1, int(np.ceil(len(view) / 2500)))
                    gesture_names = sorted(df.Label.dropna().astype(str).unique()) if 'Label' in df else []
                    palette = {name: ('#94a3b8' if name == 'Rest' else qualitative.Dark24[i % len(qualitative.Dark24)]) for i, name in enumerate(gesture_names)}
                    intervals = []
                    if mark_gestures and 'Label' in view:
                        boundaries = segments.ne(segments.shift()) | view.Label.ne(view.Label.shift())
                        if 'Trial_ID' in view:
                            boundaries |= view.Trial_ID.ne(view.Trial_ID.shift())
                        for _, segment in view.groupby(boundaries.cumsum()):
                            valid_times = (segment.Timestamp_ms.dropna() - origin) / 1000
                            if not valid_times.empty:
                                intervals.append((float(valid_times.min()), float(valid_times.max()), str(segment.Label.iloc[0])))
                        for name in gesture_names:
                            if any(label == name for _, _, label in intervals):
                                fig.add_trace(go.Scatter(x=[None], y=[None], mode='markers', name=name.replace('_', ' '), marker=dict(color=palette[name], size=10), showlegend=True, hoverinfo='skip'), row=1, col=1)
                        st.caption('Colored bands mark recorded gestures on every channel. Hover over a signal to see its gesture and trial. Shorter windows show gesture names inside the bands.')
                    shapes = []
                    for row, ch in enumerate(selected, 1):
                        x, y, hover = [], [], []
                        offset = view[ch].mean() if centered else 0
                        for _, seg in view.groupby(segments):
                            if bucket_size > 1 and len(seg) > 2 * bucket_size:
                                buckets = np.arange(len(seg)) // bucket_size
                                values = seg[ch].replace([np.inf, -np.inf], np.nan)
                                grouped = values.groupby(buckets)
                                usable = grouped.count().gt(0)
                                clean = values.loc[np.isin(buckets, usable[usable].index)]
                                clean_buckets = buckets[np.isin(buckets, usable[usable].index)]
                                if not clean.empty:
                                    grouped = clean.groupby(clean_buckets)
                                    indices = pd.concat([grouped.idxmin(), grouped.idxmax()]).dropna().unique()
                                    seg = seg.loc[sorted(indices)]
                                else:
                                    seg = seg.iloc[:0]
                            x.extend(((seg.Timestamp_ms-origin)/1000).tolist() + [None])
                            y.extend((seg[ch]-offset).tolist() + [None])
                            hover.extend([[str(label), str(trial)] for label, trial in zip(seg.get('Label', pd.Series('Unknown', index=seg.index)), seg.get('Trial_ID', pd.Series('Unknown', index=seg.index)))] + [[None, None]])
                        fig.add_trace(go.Scattergl(x=x, y=y, customdata=hover, mode='lines', name=ch, showlegend=False,
                                                 line=dict(width=1, color='#2563eb' if ch not in ['Ch9', 'Ch10', 'Ch11'] else '#9333ea'),
                                                 hovertemplate='Time: %{x:.3f} s<br>Value: %{y:.3f}<br>Gesture: %{customdata[0]}<br>Trial: %{customdata[1]}<extra>' + ch + '</extra>'), row=row, col=1)
                        suffix = '' if row == 1 else str(row)
                        for start, end, gesture in intervals:
                            shapes.append(dict(type='rect', xref=f'x{suffix}', yref=f'y{suffix} domain', x0=start, x1=end, y0=0, y1=1,
                                               fillcolor=palette.get(gesture, '#94a3b8'), opacity=0.15, line_width=0, layer='below'))
                            if len(intervals) <= 24:
                                fig.add_annotation(x=(start+end)/2, y=0.98, xref=f'x{suffix}', yref=f'y{suffix} domain',
                                                   text=gesture.replace('_', ' '), showarrow=False, yanchor='top', font=dict(size=9), textangle=-90)
                    fig.update_layout(shapes=shapes, height=max(350, len(selected)*180), showlegend=bool(intervals),
                                      legend=dict(orientation='h', y=1.05, x=0), margin=dict(t=100 if intervals else 35, b=35))
                    fig.update_xaxes(title_text='Time (s)', row=len(selected), col=1)
                    st.plotly_chart(fig, width='stretch')
                else:
                    st.info('Select at least one channel and a window containing samples.')
                with st.expander('Raw samples in selected window'):
                    st.dataframe(view.head(2000), width='stretch')
                    if st.button('Prepare selected samples CSV'):
                        csv_download_link(view.to_csv(index=False), 'selected_samples.csv', 'Save selected samples CSV')
with quality_tab:
    st.caption('Review flags indicate possible acquisition problems, not a clinical assessment. Intentional segment pauses are excluded from gap checks; repeated packet numbers are allowed.')
    if issues.empty:
        st.success('No issues found by the implemented checks.')
    else:
        st.dataframe(issues, hide_index=True, width='stretch')
    csv_download_link(issues.to_csv(index=False), f'{file.stem}_quality.csv', 'Save quality report CSV')
    if channels:
        st.subheader('Channel statistics')
        st.dataframe(df[channels].describe().T, width='stretch')
    if 'Timestamp_ms' in df:
        delta = df.Timestamp_ms.diff()
        bad = delta.le(0)
        with st.expander('Rows with duplicate or backward timestamps'):
            st.dataframe(df.loc[bad].head(1000), width='stretch')
with summary_tab:
    st.subheader(file.parent.name)
    if all(c in df for c in ['Trial_ID', 'Label']):
        summary = df.groupby(['Trial_ID', 'Label'], dropna=False).size().reset_index(name='Samples')
        st.dataframe(summary, hide_index=True, width='stretch')
        counts = df.groupby('Label', dropna=False).size()
        st.bar_chart(counts)
    with st.expander('Acquisition metadata', expanded=True):
        st.json(meta)
    if st.button('Scan all recordings'):
        rows = []
        progress = st.progress(0)
        for i, p in enumerate(files):
            try:
                data, metadata, ch = read(str(p), p.stat().st_mtime_ns)
                report = inspect_recording(data, metadata, ch)
                rows.append({'Recording': p.parent.name, 'Samples': len(data), 'Channels': len(ch), 'Review checks': len(report), 'Errors': int(report.Severity.eq('Error').sum())})
            except Exception as exc:
                rows.append({'Recording': p.parent.name, 'Read error': str(exc)})
            progress.progress((i+1)/len(files))
        st.dataframe(pd.DataFrame(rows), hide_index=True, width='stretch')
