-- ============================================================================
-- SIAMA-Impute: Inicialización de PostgreSQL + PostGIS
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Esquema dedicado para entidades del módulo SIAMA-Impute
CREATE SCHEMA IF NOT EXISTS siama;

-- Verificación rápida de versión PostGIS en logs de arranque
DO $$
BEGIN
    RAISE NOTICE 'PostGIS inicializado correctamente: %', PostGIS_Full_Version();
END $$;
