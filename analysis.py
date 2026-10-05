"""Recording loading and conservative acquisition-quality checks."""
from pathlib import Path
from io import BytesIO
import numpy as np
import pandas as pd


def parse_metadata(text):
    meta = {}
    for line in text.lstrip('\ufeff').splitlines():
        if '=' in line:
            key, value = line.split('=', 1)
            meta[key.strip()] = value.strip()
    return meta


def normalize_recording(df, meta):
    channels = [c for c in df if c.startswith('Ch') and c[2:].isdigit()]
    for c in ['Timestamp_ms', *channels]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    return df, meta, channels


def load_recording(path):
    path = Path(path)
    meta = {}
    for file in path.parent.glob('metadata*.txt'):
        meta.update(parse_metadata(file.read_text(encoding='utf-8-sig')))
    return normalize_recording(pd.read_csv(path), meta)


def load_uploaded_recording(csv_bytes, metadata=None):
    """Read uploads in memory without writing recordings to disk."""
    return normalize_recording(pd.read_csv(BytesIO(csv_bytes)), metadata or {})


def inspect_recording(df, meta, channels):
    issues = []
    def add(severity, check, count, detail):
        issues.append(dict(Severity=severity, Check=check, Count=int(count), Detail=detail))
    for c in ['Timestamp_ms', 'Trial_ID', 'Label']:
        if c not in df:
            add('Error', 'Missing column', 1, c)
    if not channels:
        add('Error', 'Missing channels', 1, 'No Ch1, Ch2, ... columns found')
    for c in df:
        n = df[c].isna().sum()
        if n:
            add('Error', 'Missing / invalid values', n, c)
    for c in channels:
        n = np.isinf(df[c]).sum()
        if n:
            add('Error', 'Infinite signal values', n, c)
        if df[c].nunique() <= 1:
            add('Review', 'Constant channel', len(df), c)
    if 'Timestamp_ms' in df:
        delta = df.Timestamp_ms.diff()
        n = (delta <= 0).sum()
        if n:
            add('Error', 'Non-increasing timestamps', n, 'Duplicate or backward timestamp transitions')
        try:
            period = 1000 / float(meta['sample_rate_hz'])
        except (KeyError, ValueError, ZeroDivisionError):
            period = delta[delta > 0].median()
        # Intentional pauses between trials or gesture segments are excluded.
        same = pd.Series(True, index=df.index)
        for c in ['Trial_ID', 'Label']:
            if c in df:
                same &= df[c].eq(df[c].shift())
        n = ((delta > period * 1.5) & same).sum()
        if n:
            add('Review', 'Within-segment timestamp gaps', n, f'Gaps > {period * 1.5:.3f} ms; segment boundaries excluded')
    for key in ['num_samples', 'expected_num_samples']:
        try:
            expected = int(meta[key])
            if len(df) != expected:
                add('Review', key, abs(len(df)-expected), f'File: {len(df):,}; metadata: {expected:,}')
        except (KeyError, ValueError):
            pass
    if 'labels' in meta and 'Label' in df:
        unexpected = ~df.Label.isin(meta['labels'].split(',')) & df.Label.notna()
        if unexpected.any():
            add('Error', 'Unknown labels', unexpected.sum(), ', '.join(df.loc[unexpected, 'Label'].astype(str).unique()))
    return pd.DataFrame(issues, columns=['Severity', 'Check', 'Count', 'Detail'])
