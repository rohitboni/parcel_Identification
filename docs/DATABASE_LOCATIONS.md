# Database Locations Guide

## Overview

This project uses **two separate databases**:

1. **Local Database** - PostgreSQL on your local machine
2. **Neon Database** - Remote cloud PostgreSQL (Neon platform)

---

## Local Database

**Location:** Your local machine  
**Connection:** `localhost:5432`  
**Database Name:** `parcels_db`  
**User:** `postgres`

**How to Connect:**
```bash
psql -U postgres -d parcels_db
```

**Tables:**
- `parcels_master` (160K parcels - Vellore, Tamil Nadu)
- `parcels_simplified` (160K parcels)

**View in psql:**
```bash
psql -U postgres -d parcels_db
\dt  # List tables
```

---

## Neon Database (Remote Cloud)

**Location:** Neon Cloud Platform (AWS ap-southeast-1)  
**Connection:** `ep-shy-king-a1mismh7-pooler.ap-southeast-1.aws.neon.tech:5432`  
**Database Name:** `india_cadastral_production`  
**User:** `neondb_owner`

**Connection String:**
```
postgresql://neondb_owner:npg_KwgtR7LI1qUA@ep-shy-king-a1mismh7-pooler.ap-southeast-1.aws.neon.tech/india_cadastral_production?sslmode=require
```

**How to Connect:**
```bash
psql "postgresql://neondb_owner:npg_KwgtR7LI1qUA@ep-shy-king-a1mismh7-pooler.ap-southeast-1.aws.neon.tech/india_cadastral_production?sslmode=require"
```

**Tables:**
- `cadastrals` (original source table - 1.4M parcels)
- `parcels_master_neon` (partitioned - migrated data)
- `parcels_simplified_neon` (partitioned - migrated data)

**View in psql:**
```bash
psql "postgresql://neondb_owner:npg_KwgtR7LI1qUA@ep-shy-king-a1mismh7-pooler.ap-southeast-1.aws.neon.tech/india_cadastral_production?sslmode=require"
\dt  # List tables
```

---

## Important Notes

### ⚠️ Neon Database is NOT Local

The Neon database is **not** in your local PostgreSQL installation. It's a **remote cloud database** hosted by Neon.

**You won't see it in:**
- `psql -U postgres -l` (local databases only)
- Local PostgreSQL server

**You can only access it via:**
- The connection string with full hostname
- Python scripts using the connection string
- psql with the full connection string

### Why Two Databases?

- **Local DB:** Development/testing with smaller dataset (Vellore)
- **Neon DB:** Production data (Karnataka, 1.4M+ parcels)

Both use the same schema structure but are completely independent.

---

## Quick Connection Commands

### Local Database
```bash
psql -U postgres -d parcels_db
```

### Neon Database
```bash
psql "postgresql://neondb_owner:npg_KwgtR7LI1qUA@ep-shy-king-a1mismh7-pooler.ap-southeast-1.aws.neon.tech/india_cadastral_production?sslmode=require"
```

### Or Create an Alias

Add to your `~/.zshrc` or `~/.bashrc`:
```bash
alias neon-db='psql "postgresql://neondb_owner:npg_KwgtR7LI1qUA@ep-shy-king-a1mismh7-pooler.ap-southeast-1.aws.neon.tech/india_cadastral_production?sslmode=require"'
```

Then use:
```bash
neon-db
```

---

## Verification Queries

### Check Local Database
```bash
psql -U postgres -d parcels_db -c "SELECT COUNT(*) FROM parcels_master;"
```

### Check Neon Database
```bash
psql "postgresql://neondb_owner:npg_KwgtR7LI1qUA@ep-shy-king-a1mismh7-pooler.ap-southeast-1.aws.neon.tech/india_cadastral_production?sslmode=require" -c "SELECT COUNT(*) FROM parcels_master_neon;"
```

