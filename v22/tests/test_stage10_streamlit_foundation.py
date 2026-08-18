from pathlib import Path
import ast
import os

ROOT = Path(__file__).resolve().parents[2]


def test_app_exists_and_is_v22_read_only():
    app = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'V22 Brain' in app
    assert 'load_snapshot' in app
    assert 'COINGECKO' not in app
    assert 'yfinance' not in app
    ast.parse(app)


def test_streamlit_requires_psycopg():
    req = (ROOT / 'requirements.txt').read_text(encoding='utf-8')
    assert 'psycopg[binary]' in req


def test_reader_never_contains_a_database_secret():
    reader = (ROOT / 'v22' / 'ui' / 'neon_reader.py').read_text(encoding='utf-8')
    assert 'postgresql://' not in reader
    assert 'default_transaction_read_only = on' in reader
    ast.parse(reader)
