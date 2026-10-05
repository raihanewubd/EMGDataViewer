"""Run with: python -m unittest test_uploads"""
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch
import json

from analysis import load_uploaded_recording, parse_metadata, inspect_recording
from streamlit.testing.v1 import AppTest


CSV = b'Timestamp_ms,Trial_ID,Ch1,Ch9,Ch10,Ch11,Label\n0,1,100,1,2,3,Left\n2,1,110,2,3,4,Left\n4,1,105,3,4,5,Rest\n'


class Upload:
    def __init__(self, name, data):
        self.name, self.data, self.file_id = name, data, name + str(hash(data))

    def getvalue(self):
        return self.data


class UploadTests(TestCase):
    def test_parser_with_and_without_metadata(self):
        meta = parse_metadata('\ufeffsample_rate_hz=500\nnum_samples=3\nlabels=Left,Rest')
        df, parsed, channels = load_uploaded_recording(CSV, meta)
        self.assertEqual(len(df), 3)
        self.assertEqual(channels, ['Ch1', 'Ch9', 'Ch10', 'Ch11'])
        self.assertEqual(parsed['sample_rate_hz'], '500')
        self.assertTrue(inspect_recording(df, parsed, channels).empty)
        self.assertEqual(load_uploaded_recording(CSV)[1], {})

    def test_upload_ui_and_batch_scan(self):
        csvs = [Upload('emg_data_demo.csv', CSV), Upload('emg_data_second.csv', CSV)]
        txts = [Upload('metadata_demo.txt', b'data_file=emg_data_demo.csv\nsample_rate_hz=500\nnum_samples=3')]
        def uploader(_, label, **kwargs):
            return csvs if label == 'Recording CSV files' else txts
        app_path = str(Path(__file__).with_name('app.py'))
        # Simulate cloud deployment, which has no default dataset folder.
        with patch('pathlib.Path.is_dir', return_value=False), patch('streamlit.delta_generator.DeltaGenerator.file_uploader', uploader):
            at = AppTest.from_file(app_path, default_timeout=60).run()
            self.assertFalse(at.exception)
            self.assertEqual(at.sidebar.radio[0].value, 'Upload recordings')
            spec = json.loads(at.get('plotly_chart')[0].proto.spec)
            self.assertEqual(len({s['yref'] for s in spec['layout']['shapes']}), 4)
            self.assertTrue(any(a['text'] == 'Ch9 · IMU' for a in spec['layout']['annotations']))
            self.assertTrue(any('500' in j.value for j in at.json))
            next(b for b in at.button if b.label == 'Scan all recordings').click().run()
            self.assertFalse(at.exception)
            table = at.dataframe[-1].value
            self.assertEqual(table['Recording'].tolist(), [c.name for c in csvs])
            at.sidebar.selectbox[0].set_value(csvs[1]).run()
            self.assertFalse(at.exception)
            self.assertTrue(any('No matching metadata' in c.value for c in at.caption))
            csvs[:] = [Upload('bad.csv', b'')]
            at = AppTest.from_file(app_path, default_timeout=60).run()
            self.assertFalse(at.exception)
            self.assertTrue(any('Cannot read bad.csv' in e.value for e in at.error))
            csvs.clear()
            at = AppTest.from_file(app_path, default_timeout=60).run()
            self.assertFalse(at.exception)
            self.assertTrue(any('Upload one or more' in i.value for i in at.info))


if __name__ == '__main__':
    main()
