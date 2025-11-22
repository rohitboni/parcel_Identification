import uuid
import geopandas as gpd
import psycopg2
from shapely.geometry import MultiPolygon

# ------------------------------
# CONFIG
# ------------------------------
SHAPEFILE_PATH = "data/vellore/vellore_cad.shp"
DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "database": "parcels_db",
    "user": "postgres",
    "password": "postgres"
}

# ------------------------------
# CLEAN GEOMETRY FUNCTION
# ------------------------------
def clean_geom(g):
    if g is None:
        return None
    try:
        if not g.is_valid:
            g = g.buffer(0)
        if g.geom_type == "Polygon":
            return MultiPolygon([g])
        return g
    except:
        return None

# ------------------------------
# CONNECT TO DB
# ------------------------------
def connect_db():
    return psycopg2.connect(
        host=DB_CONFIG["host"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"]
    )

# ------------------------------
# ETL PIPELINE
# ------------------------------
def run_etl():
    print("🚀 Loading Vellore shapefile...")
    gdf = gpd.read_file(SHAPEFILE_PATH)
    print("✅ Shapefile loaded:", len(gdf), "rows")

    print("🧼 Cleaning geometry...")
    gdf["clean_geom"] = gdf.geometry.apply(clean_geom)
    gdf = gdf[~gdf["clean_geom"].isnull()]
    print("✅ Valid geometries:", len(gdf))

    # Generate UUID for each parcel
    gdf["parcel_uuid"] = [str(uuid.uuid4()) for _ in range(len(gdf))]
    print("🔑 Generated UUIDs for parcels")

    conn = connect_db()
    cur = conn.cursor()

    # ------------------------------
    # INSERT INTO parcels_raw
    # ------------------------------
    insert_raw = """
    INSERT INTO parcels_raw 
    (parcel_uuid, geom, kide, kide_1, kide_2, survey_num, gp_name, v_name, v_code, district, state, tehsil)
    VALUES (%s, ST_GeomFromEWKB(%s), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
    """

    print("📥 Inserting into parcels_raw...")
    for idx, row in gdf.iterrows():
        geom_wkb = psycopg2.Binary(row["clean_geom"].wkb)
        cur.execute(insert_raw, (
            row["parcel_uuid"],
            geom_wkb,
            str(row.get("kide")) if row.get("kide") is not None else None,
            str(row.get("kide_1")) if row.get("kide_1") is not None else None,
            str(row.get("kide_2")) if row.get("kide_2") is not None else None,
            str(row.get("survey_n_4")),
            row.get("gp_name"),
            row.get("v_name"),
            str(row.get("v_code")) if row.get("v_code") is not None else None,
            row.get("District"),
            row.get("STATE"),
            row.get("TEHSIL")
        ))

    conn.commit()
    print("✅ parcels_raw inserted")

    # ------------------------------
    # INSERT INTO parcels (cleaned)
    # ------------------------------
    insert_clean = """
    INSERT INTO parcels 
    (parcel_uuid, geom, district, tehsil, v_name, survey_num)
    VALUES (%s, ST_GeomFromEWKB(%s), %s, %s, %s, %s);
    """

    print("📥 Inserting into parcels...")
    for _, row in gdf.iterrows():
        cur.execute(insert_clean, (
            row["parcel_uuid"],
            psycopg2.Binary(row["clean_geom"].wkb),
            row["District"],
            row["TEHSIL"],
            row["v_name"],
            row["survey_n_4"]
        ))

    conn.commit()
    print("✅ parcels inserted")

    # ------------------------------
    # INSERT SIMPLIFIED GEOMETRIES
    # ------------------------------
    print("🌀 Generating simplified geometries...")
    simplify_tol = 0.00008
    insert_simplified = """
    INSERT INTO parcels_simplified (parcel_uuid, geom, survey_num, v_code)
    VALUES (%s, ST_GeomFromEWKB(%s), %s, %s);
    """

    for _, row in gdf.iterrows():
        simp = row["clean_geom"].simplify(simplify_tol, preserve_topology=True)
        cur.execute(insert_simplified, (
            row["parcel_uuid"],
            psycopg2.Binary(simp.wkb),
            row.get("survey_n_4"),
            str(row.get("v_code")) if row.get("v_code") is not None else None
        ))

    conn.commit()
    print("✅ parcels_simplified inserted")

    cur.close()
    conn.close()
    print("🎉 ETL COMPLETE — Vellore data loaded successfully ✅")


if __name__ == "__main__":
    run_etl()
