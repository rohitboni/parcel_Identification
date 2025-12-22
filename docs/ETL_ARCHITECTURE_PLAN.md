# ETL Pipeline Architecture Plan

## Industry-Standard ETL Fundamentals

### Core Principles

1. **Separation of Concerns**: Extract, Transform, Load as distinct, testable modules
2. **Configuration-Driven**: Field mappings and rules in config files (not hardcoded)
3. **Idempotency**: Safe to re-run without creating duplicates
4. **Validation**: Schema checks, data quality validation, error handling
5. **Observability**: Logging, progress tracking, error reporting
6. **Modularity**: Reusable components that can be tested independently

### Common Patterns

**Exploration Phase** (Interactive):
- Jupyter notebooks for data discovery
- Visual inspection, statistics, sample data
- Schema analysis, data quality checks

**Production Pipeline** (Automated):
- Python modules/scripts for repeatability
- Configuration files for flexibility
- Command-line interface for execution

## Proposed Architecture

### Directory Structure

```
etl/
├── explore_data.ipynb          # Interactive data exploration notebook
├── config/
│   ├── vellore_mapping.yaml    # Field mapping config for Vellore
│   └── template_mapping.yaml    # Template for new datasets
├── modules/
│   ├── __init__.py
│   ├── extract.py              # Data extraction/inspection
│   ├── transform.py            # Data transformation
│   ├── load.py                 # Database loading
│   ├── validate.py             # Data validation
│   └── geometry_utils.py       # Geometry operations
├── pipeline.py                 # Main orchestrator
└── load_vellore.py             # Legacy script (deprecated)
```

### Component Design

#### 1. Exploration Notebook (`explore_data.ipynb`)

**Purpose**: Interactive data discovery

**Features**:
- Load shapefile/GeoPackage
- Display schema (columns, types)
- Show sample rows (first 5)
- Basic statistics
- Geometry validation checks
- Generate mapping config template

**Output**: Understanding of data structure → mapping config

#### 2. Configuration Files (`config/*.yaml`)

**Purpose**: Field mappings and transformation rules

**Structure**:
```yaml
dataset:
  name: "vellore_cad"
  source_path: "data/vellore/vellore_cad.shp"
  crs: "EPSG:4326"

field_mapping:
  # Source column -> Target column
  survey_n_4: survey_num
  District: district_name
  STATE: state
  TEHSIL: sub_district_name
  v_name: village_name
  v_code: district_code  # or custom transform
  
transforms:
  state_code:
    source: STATE
    transform: "uppercase"  # or custom function
  district_code:
    source: v_code
    transform: "string"
    
required_fields:
  - survey_num
  - state_code
  - district_code
  - district_name
  
geometry:
  simplify_tolerance: 0.00008
  target_crs: "EPSG:4326"
```

#### 3. Extract Module (`modules/extract.py`)

**Purpose**: Load and inspect data

**Functions**:
- `load_data(path)`: Load shapefile/GeoPackage
- `inspect_schema(gdf)`: Return column names, types
- `sample_data(gdf, n=5)`: Return sample rows
- `validate_source(gdf, required_fields)`: Check required columns exist

#### 4. Transform Module (`modules/transform.py`)

**Purpose**: Transform data to target format

**Functions**:
- `map_fields(gdf, mapping_config)`: Map source columns to target
- `apply_transforms(gdf, transform_config)`: Apply transformations
- `clean_geometry(gdf)`: Fix invalid geometries, normalize types
- `simplify_geometry(gdf, tolerance)`: Simplify for rendering
- `generate_label_points(gdf)`: Create point-on-surface for labels
- `validate_transformed(gdf, schema)`: Validate transformed data

#### 5. Load Module (`modules/load.py`)

**Purpose**: Load data into database

**Functions**:
- `connect_db(config)`: Database connection
- `load_master(conn, gdf)`: Insert into parcels_master
- `load_simplified(conn, gdf)`: Insert into parcels_simplified
- `batch_insert(conn, table, data, batch_size=1000)`: Efficient batch loading

**Features**:
- Batch inserts for performance
- UUID generation (let DB handle)
- Error handling and rollback
- Progress tracking

#### 6. Validate Module (`modules/validate.py`)

**Purpose**: Data quality checks

**Functions**:
- `validate_schema(gdf, expected_columns)`: Check columns exist
- `validate_geometries(gdf)`: Check geometry validity
- `validate_required_fields(gdf, required)`: Check non-null required fields
- `report_quality(gdf)`: Generate quality report

#### 7. Pipeline Orchestrator (`pipeline.py`)

**Purpose**: Coordinate ETL process

**Flow**:
1. Load config file
2. Extract: Load source data
3. Validate: Check source data quality
4. Transform: Map fields, clean geometries
5. Validate: Check transformed data
6. Load: Insert into database
7. Report: Summary statistics

**CLI Interface**:
```bash
python pipeline.py --config config/vellore_mapping.yaml
```

## Workflow

### Step 1: Exploration (Notebook)

1. Open `explore_data.ipynb`
2. Load shapefile
3. Inspect columns, types, sample data
4. Understand data structure
5. Generate mapping config template

### Step 2: Configuration

1. Create `config/dataset_mapping.yaml`
2. Map source fields to target fields
3. Define transformations
4. Set required fields

### Step 3: Execution

1. Run pipeline:
   ```bash
   python pipeline.py --config config/dataset_mapping.yaml
   ```
2. Monitor progress
3. Review logs/errors
4. Verify data in database

## Benefits of This Architecture

1. **Flexibility**: Easy to add new datasets (just create new config)
2. **Maintainability**: Clear separation of concerns
3. **Testability**: Each module can be tested independently
4. **Reusability**: Modules work for any dataset
5. **Observability**: Clear logging and error reporting
6. **Scalability**: Can add features (validation, monitoring) without changing core

## Migration Strategy

1. Keep `load_vellore.py` as reference
2. Build new modules incrementally
3. Test with Vellore data first
4. Once validated, mark old script as deprecated
5. Update documentation

## Next Steps

1. Create directory structure
2. Build exploration notebook
3. Create config template
4. Implement extract module
5. Implement transform module
6. Implement load module
7. Build pipeline orchestrator
8. Test with Vellore data
9. Update documentation

