--------------------------------------------------------
INSTRUCTIONS FOR CREATING REQUIRED TABLES IN POSTGIS (for vellore data):
--------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS postgis;

1. parcels_raw table:
```sql
CREATE TABLE IF NOT EXISTS parcels_raw (
    parcel_uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    geom        geometry(MultiPolygon, 4326),
    kide        TEXT,
    kide_1      TEXT,
    kide_2      TEXT,
    survey_num  TEXT,
    gp_name     TEXT,
    v_name      TEXT,
    v_code      TEXT,
    district    TEXT,
    state       TEXT,
    tehsil      TEXT
);
```

Spatial Index:
```sql
CREATE INDEX IF NOT EXISTS idx_parcels_raw_geom
    ON parcels_raw
    USING GIST (geom);
```

2. parcels table:
```sql
CREATE TABLE IF NOT EXISTS parcels (
    parcel_uuid UUID PRIMARY KEY,
    geom        geometry(MultiPolygon, 4326),
    district    TEXT,
    tehsil      TEXT,
    v_name      TEXT,
    survey_num  TEXT
);
```

Spatial Index:
```sql
CREATE INDEX IF NOT EXISTS idx_parcels_geom
    ON parcels
    USING GIST (geom);
```

3. parcels_simplified table:
```sql
CREATE TABLE IF NOT EXISTS parcels_simplified (
    parcel_uuid UUID PRIMARY KEY,
    geom        geometry(MultiPolygon, 4326),
    survey_num  TEXT,
    v_code      TEXT
);
```

Spatial Index:
```sql
CREATE INDEX IF NOT EXISTS idx_parcels_simplified_geom
    ON parcels_simplified
    USING GIST (geom);
```  
--------------------------------------------------------
Instructions to run project -- Backend and Frontend:
--------------------------------------------------------
```bash
source venv/bin/activate
```
Backend: 
1.
 ```bash
   pip install -r requirements.txt
   ```
2. 
 ```bash
 sudo service postgresql start ## make sure postgres is running
```
3.
```bash
cd backend
```
4.
```bash
uvicorn main:app --reload
```
Frontend: 
1. ```bash
   cd frontend/map-app
   ```
2. ```bash
   python3 -m http.server 8080
   ```

--------------------------------------------------------
