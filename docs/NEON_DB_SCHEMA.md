# Neon Production Database Schema Analysis

## Database Connection

**Connection String:**
```
postgresql://neondb_owner:npg_KwgtR7LI1qUA@ep-shy-king-a1mismh7-pooler.ap-southeast-1.aws.neon.tech/india_cadastral_production?sslmode=require
```

**Database:** `india_cadastral_production`  
**Host:** Neon PostgreSQL (AWS ap-southeast-1)

---

## Table Structure

### Table: `cadastrals`

**Total Rows:** 1,452,025 parcels

**Schema:**

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `gid` | integer | NOT NULL | Primary key (auto-increment) |
| `Survey_Number` | varchar(255) | NULL | Survey number of the parcel |
| `Village_Name` | varchar(255) | NULL | Village name |
| `Mandal_Name` | varchar(255) | NULL | Mandal/Tehsil name |
| `District_Name` | varchar(255) | NULL | District name |
| `State_Name` | varchar(255) | NULL | State name |
| `State_Code` | varchar(10) | NULL | State code (e.g., "ka") |
| `District_Code` | varchar(10) | NULL | District code (e.g., "526") |
| `geom` | geometry(MultiPolygon, 32643) | NULL | Parcel boundary geometry |
| `Updated_On` | timestamp | NULL | Last update timestamp (default: CURRENT_TIMESTAMP) |

**Note:** Column names are **case-sensitive** (PascalCase) - must use quoted identifiers in queries.

---

## Key Differences from Local Database

### 1. **Table Structure**
- **Neon DB:** Single table `cadastrals` (non-partitioned)
- **Local DB:** Partitioned tables `parcels_master` and `parcels_simplified`

### 2. **Primary Key**
- **Neon DB:** `gid` (integer, auto-increment)
- **Local DB:** `parcel_uuid` (UUID, auto-generated)

### 3. **Column Naming**
- **Neon DB:** PascalCase (`Survey_Number`, `Village_Name`, etc.)
- **Local DB:** snake_case (`survey_num`, `village_name`, etc.)

### 4. **Geometry CRS**
- **Neon DB:** EPSG:32643 (UTM Zone 43N) - **MUST TRANSFORM TO 4326**
- **Local DB:** EPSG:4326 (WGS84) - already in lat/lon

### 5. **Additional Fields**
- **Neon DB:** Has `Mandal_Name` (equivalent to `sub_district_name`/`tehsil`)
- **Neon DB:** Has `Updated_On` timestamp
- **Local DB:** Has `label_point` (pre-computed) - **MISSING in Neon DB**

### 6. **Missing in Neon DB**
- No `label_point` column (needs to be computed)
- No partitioning (single table)
- No `parcel_uuid` (uses `gid` instead)

---

## Data Distribution

### States
- **1 state:** Karnataka
- **State Code:** "ka"

### Districts (8 total)
| District Name | Parcels | Percentage |
|---------------|---------|------------|
| Tumakuru | 432,056 | 29.8% |
| Chikkaballapura | 323,438 | 22.3% |
| Kolara | 248,593 | 17.1% |
| Ramanagara | 157,202 | 10.8% |
| Bengaluru (Rural) | 150,804 | 10.4% |
| Bengaluru (Urban) | 139,923 | 9.6% |
| Mandya | 8 | <0.1% |
| Chitradurga | 1 | <0.1% |

### Administrative Units
- **Districts:** 8
- **Villages:** 6,998
- **Total Parcels:** 1,452,025

### Geographic Extent (WGS84)
- **Bounding Box:** 
  - Longitude: 76.35°E to 78.59°E
  - Latitude: 12.24°N to 14.34°N
- **Approximate Center:** ~77.5°E, 13.3°N (Karnataka region)

---

## Indexes

1. **Primary Key:** `parcels_pkey` on `gid` (btree)
2. **Spatial Index:** `parcels_geom_idx` on `geom` (GIST)
3. **District Code:** `parcels_district_code_idx` on `District_Code` (btree)
4. **District Name:** `parcels_district_name_idx` on `District_Name` (btree)
5. **State Code:** `parcels_state_code_idx` on `State_Code` (btree)

---

## Field Mapping (Neon → Local)

| Neon DB Column | Local DB Column | Notes |
|----------------|-----------------|-------|
| `gid` | `parcel_uuid` | Different type (int vs UUID) |
| `Survey_Number` | `survey_num` | Same data |
| `Village_Name` | `village_name` | Same data |
| `Mandal_Name` | `sub_district_name` | Same concept |
| `District_Name` | `district_name` | Same data |
| `State_Name` | `state` | Same data |
| `State_Code` | `state_code` | Same data |
| `District_Code` | `district_code` | Same data |
| `geom` | `geom` | **Different CRS** (32643 vs 4326) |
| `Updated_On` | `created_at` | Different purpose |
| - | `label_point` | **Missing** - needs computation |

---

## Important Considerations

### 1. **CRS Transformation Required**
All geometry queries must transform from EPSG:32643 to EPSG:4326:
```sql
ST_Transform(geom, 4326)
```

### 2. **Case-Sensitive Column Names**
Always use quoted identifiers:
```sql
SELECT "Survey_Number", "Village_Name" FROM cadastrals;
```

### 3. **No Label Points**
The `label_point` column doesn't exist. It needs to be computed:
```sql
ST_PointOnSurface(ST_Transform(geom, 4326)) AS label_point
```

### 4. **No Partitioning**
Single table structure - may need partitioning for performance with 1.4M+ rows.

### 5. **Different Primary Key**
Uses integer `gid` instead of UUID `parcel_uuid`.

---

## Sample Data

```sql
gid: 1
Survey_Number: "78"
Village_Name: "Devarahosahalli"
Mandal_Name: "Nelamangala"
District_Name: "Bengaluru (Rural)"
State_Name: "Karnataka"
State_Code: "ka"
District_Code: "526"
geom: MultiPolygon (EPSG:32643)
Updated_On: 2025-12-11 09:16:14.699914
```

---

## Recommendations for Integration

1. **Create adapter layer** to handle:
   - CRS transformation (32643 → 4326)
   - Column name mapping (PascalCase → snake_case)
   - Label point computation
   - UUID generation (if needed)

2. **Consider partitioning** for better performance:
   - Partition by `State_Code` → `District_Code`
   - Similar to local database structure

3. **Add label_point column** (computed):
   ```sql
   ALTER TABLE cadastrals 
   ADD COLUMN label_point geometry(Point, 4326);
   
   UPDATE cadastrals 
   SET label_point = ST_PointOnSurface(ST_Transform(geom, 4326));
   ```

4. **Update queries** to:
   - Always transform geometry to 4326
   - Use quoted column names
   - Handle case sensitivity

---

## Query Examples

### Get parcels in bounding box (WGS84)
```sql
SELECT gid, "Survey_Number", "Village_Name", 
       ST_Transform(geom, 4326) as geom_wgs84
FROM cadastrals
WHERE ST_Transform(geom, 4326) && ST_MakeEnvelope(77.0, 13.0, 78.0, 14.0, 4326);
```

### Compute label point on-the-fly
```sql
SELECT gid, "Survey_Number",
       ST_PointOnSurface(ST_Transform(geom, 4326)) as label_point
FROM cadastrals
WHERE gid = 1;
```

### Get district statistics
```sql
SELECT "District_Name", COUNT(*) as parcels,
       ST_Extent(ST_Transform(geom, 4326)) as bbox
FROM cadastrals
GROUP BY "District_Name";
```

