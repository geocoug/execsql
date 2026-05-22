-- prompt_map_demo.sql
-- Demonstrates PROMPT MAP with SQLite.
-- Creates a table of US cities with lat/lon/label/color/symbol columns,
-- inserts a few rows, then opens an interactive map dialog with markers.
--
-- Run:
--     execsql -t l prompt_map_demo.sql cities.sqlite
--
-- The script creates cities.sqlite in the current directory (or reuses it).
-- Requires a GUI environment (Tkinter desktop or Textual TUI). The map
-- markers are colored/symboled per row.

CREATE TABLE IF NOT EXISTS cities (
    name   TEXT PRIMARY KEY,
    lat    REAL NOT NULL,
    lon    REAL NOT NULL,
    color  TEXT,
    symbol TEXT
);

DELETE FROM cities;

INSERT INTO cities (name, lat, lon, color, symbol) VALUES
    ('Seattle',        47.6062, -122.3321, 'blue',   'circle'),
    ('Portland',       45.5152, -122.6784, 'blue',   'circle'),
    ('San Francisco',  37.7749, -122.4194, 'green',  'square'),
    ('Los Angeles',    34.0522, -118.2437, 'green',  'square'),
    ('Denver',         39.7392, -104.9903, 'orange', 'triangle'),
    ('Chicago',        41.8781,  -87.6298, 'red',    'star'),
    ('New York',       40.7128,  -74.0060, 'red',    'star'),
    ('Miami',          25.7617,  -80.1918, 'purple', 'diamond');

-- PROMPT MESSAGE "<text>" MAP <table>
--   LAT <lat_col> LON <lon_col>
--   [LABEL <label_col>] [COLOR <color_col>] [SYMBOL <symbol_col>]
--
---- !x! PROMPT MESSAGE "US cities — click a marker for details, then Continue to exit." MAP cities LAT lat LON lon LABEL name COLOR color SYMBOL symbol

-- !x! write "!!heythere!!"

-- !x! sub yesno yes
-- !x! if(!!yesno!!)
    -- !x! write "level1"
    -- !x! debug write iflevels
    -- !x! if(true)
        -- !x! write "level2"
        -- !x! debug write iflevels
        -- !x! breakpoint
    -- !x! endif
-- !x! endif


-- !x! debug write COMMANDLISTSTACK

/*
-- !x! debug write subvars
-- !x! debug write user subvars
-- !x! debug write local subvars

-- !x! debug write ODBC_DRIVERS

-- !x! export cities to cities.csv as csv
-- !x! export cities to cities.json as json
-- !x! export_metadata all to stdout as txt
*/


-- Add jsonl as an input/output format with the .jsonl extension
