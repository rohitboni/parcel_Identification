#!/usr/bin/env python3
"""Quick script to check available states and districts in the database."""

import sys
from pathlib import Path

# Add backend directory to path (scripts folder is one level up from backend)
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from config import DB_CONFIG
import psycopg2

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    # Get states
    cur.execute('''
        SELECT DISTINCT state_code, state, COUNT(*) as count
        FROM parcels_master
        WHERE state_code IS NOT NULL
        GROUP BY state_code, state
        ORDER BY state_code
    ''')
    states = cur.fetchall()
    
    print('=' * 70)
    print('AVAILABLE STATES IN DATABASE')
    print('=' * 70)
    for state_code, state_name, count in states:
        print(f'State Code: {state_code:<8} | State: {state_name:<30} | Parcels: {count:>12,}')
    
    print('\n' + '=' * 70)
    print('AVAILABLE DISTRICTS BY STATE')
    print('=' * 70)
    
    # Get districts for each state
    for state_code, state_name, _ in states:
        cur.execute('''
            SELECT district_code, district_name, COUNT(*) as count
            FROM parcels_master
            WHERE state_code = %s AND district_code IS NOT NULL
            GROUP BY district_code, district_name
            ORDER BY district_name
        ''', (state_code,))
        districts = cur.fetchall()
        
        print(f'\n{state_name} (State Code: {state_code}):')
        print('-' * 70)
        for dist_code, dist_name, count in districts:
            print(f'  District Code: {dist_code:<15} | {dist_name:<30} | {count:>12,} parcels')
    
    cur.close()
    conn.close()
    
    print('\n' + '=' * 70)
    print('SAMPLE COMMANDS')
    print('=' * 70)
    if states:
        state_code, state_name, _ = states[0]
        # Get sample districts (with most parcels)
        cur = conn.cursor()
        cur.execute('''
            SELECT district_code, district_name, COUNT(*) as count
            FROM parcels_master
            WHERE state_code = %s AND district_code IS NOT NULL
            GROUP BY district_code, district_name
            ORDER BY count DESC
            LIMIT 5
        ''', (state_code,))
        sample_districts = cur.fetchall()
        cur.close()
        
        print(f'\n# Interactive mode (recommended for first-time use):')
        print(f'python pregenerate_tiles.py')
        print(f'\n# CLI mode examples for {state_name} ({state_code}):')
        for dist_code, dist_name, count in sample_districts:
            print(f'python pregenerate_tiles.py --state-code {state_code} --district-code {dist_code}  # {dist_name} ({count:,} parcels)')
        print(f'\n# With custom zoom levels and workers:')
        if sample_districts:
            dist_code, dist_name, _ = sample_districts[0]
            print(f'python pregenerate_tiles.py --state-code {state_code} --district-code {dist_code} --zoom-levels 15,16,17,18 --workers 8')
            print(f'\n# Force regenerate (ignore cache):')
            print(f'python pregenerate_tiles.py --state-code {state_code} --district-code {dist_code} --force-regenerate')
    
except Exception as e:
    print(f'Error connecting to database: {e}')
    print(f'\nDatabase config: {DB_CONFIG}')
    print('\nMake sure:')
    print('1. Database is running')
    print('2. .env file is configured correctly')
    print('3. Virtual environment is activated (source venv/bin/activate)')
    sys.exit(1)

