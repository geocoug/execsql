-- ss_compare.sql
--
-- PURPOSE
--	Generate MS-SQL-Server-specific SQL to compare the attributes (non-PK columns)
--	in a staging table to the equivalently-named base table.
--
-- NOTES
--	1. The scripts contained in this file that are intended to be called
--		directly by the user are:
--			COMPARE_COMMON		: Produces SQL that represents comparison
--								  results as categories of "Same", "Different",
--								  "Old", and "New".
--			COMPARE_COMMON_VALS	: Produces SQL that shows both base and
--								  staging values in adjacent columns.
--			COMPARE_CHANGES		: Produces SQL that shows all primary keys in
--								  the staging table plus a column named "changes"
--								  that identifiers whether that row in the
--								  staging table is new, is a changed version of
--								  an existing row, or is identical to an
--								  existing row.
--			COMPARE_CHANGED		: Produces SQL that shows all primary keys in
--								  the base table plus a column named "changed"
--								  that identifiers whether that row exists in
--								  the staging table, has different data in the
--								  staging table, or has identical data in the
--								  staging table.
--	2. These scripts query the information schema to obtain
--		the information needed to generate SQL.
--	3. Temporary tables and views created by these scripts all
--		begin with "cmp_".
--	4. This script requires SQL Server 2017 or later.
--
-- AUTHOR
--	Dreas Nielsen (RDN)
--
-- COPYRIGHT AND LICENSE
-- 	Copyright (c) 2020 R.Dreas Nielsen
-- 	This program is free software: you can redistribute it and/or modify
-- 	it under the terms of the GNU General Public License as published by
-- 	the Free Software Foundation, either version 3 of the License, or
-- 	(at your option) any later version.
-- 	This program is distributed in the hope that it will be useful,
-- 	but WITHOUT ANY WARRANTY; without even the implied warranty of
-- 	MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
-- 	GNU General Public License for more details.
-- 	The GNU General Public License is available at <http://www.gnu.org/licenses/>
--
-- VERSION
--	1.1.1
--
-- HISTORY
--	 Date		 Remarks
--	----------	-----------------------------------------------------
--	2020-02-29	Created from v. 1.1.1 for Postgres.  RDN.
--	2020-03-01	Modified for SQL Server.  RDN.
-- ==================================================================


-- ################################################################
--			Script COMPARE_COMMON
-- ===============================================================
--
-- Generate SQL to compare the attributes of base and staging
-- tables for only those primary keys in common.  This uses an
-- inner join between the tables, and does not include any rows
-- with a primary key that is in one table and not the other.
--
-- The output includes a column for every column in the base
-- table (except those explicitly excluded).  Primary key
-- columns are populated with primary key values.  Attribute
-- columns are populated with one of the following tags:
--		Same		: The value in base and staging tables
--					  are the same.
--		Different	: The values in base and staging tables
--					  are different.
--		Old			: There is a value in the base table but
--					  no value (i.e., null) in the staging table.
--		New			: There is a value in the staging table
--					  but no value (i.e., null) in the base table.
--
-- Required input arguments:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		table			: The name of the table to compare.
--						  The table must have the same name
--						  in base and staging schemas.
--
-- Optional input arguments:
--		include_cols	: Contains a comma-separated list of single-quoted
--						  column names in the base table that are the
--						  *only* attribute columns to be compared.
--		exclude_cols	: Contains a comma-separated list of single-quoted
--						  column names in the base table that are not to
--						  be compared.  If 'include_cols' is provided,
--						  'exclude_cols' is ignored.
--
--	Required output arguments:
--		sql_var			: The name of the variable into which
--						  the generated SQL will be stored
--
-- Notes
-- 	1. The generated SQL is not terminated with a semicolon.
-- ===============================================================
-- !x! BEGIN SCRIPT COMPARE_COMMON with parameters (base_schema, staging, table, sql_var)

-- Create a table of primary key columns for the table
if object_id('tempdb..#cmp_primary_key_columns') is not null drop table #cmp_primary_key_columns;
select k.column_name, k.ordinal_position
into #cmp_primary_key_columns
from information_schema.table_constraints as tc
inner join information_schema.key_column_usage as k
    on tc.constraint_type = 'PRIMARY KEY'
    and tc.constraint_name = k.constraint_name
    and tc.constraint_catalog = k.constraint_catalog
    and tc.constraint_schema = k.constraint_schema
    and tc.table_schema = k.table_schema
    and tc.table_name = k.table_name
	and tc.constraint_name = k.constraint_name
where
	k.table_name = '!!#table!!'
	and k.table_schema = '!!#base_schema!!'
order by k.ordinal_position
;

-- !x! if(not hasrows(#cmp_primary_key_columns)) { halt message "Table !!#table!! has no primary key columns." }

-- Populate a (temporary) table with the names of the attribute columns
-- that are to be compared.
-- Include only those columns from the staging table that are also in the base table.
-- !x! sub_empty ~col_sel
-- !x! if(sub_defined(#include_cols))
	-- !x! sub ~col_sel and s.column_name in (!!#include_cols!!)
-- !x! elseif(sub_defined(#exclude_cols))
	-- !x! sub ~col_sel and s.column_name not in (!!#exclude_cols!!)
-- !x! endif
if object_id('tempdb..#cmp_cols') is not null drop table #cmp_cols;
select s.column_name
into #cmp_cols
from information_schema.columns as s
	inner join information_schema.columns as b on s.column_name=b.column_name
	left join #cmp_primary_key_columns as pk on pk.column_name = s.column_name
where
	s.table_schema = '!!#staging!!'
	and s.table_name = '!!#table!!'
	and b.table_schema = '!!#base_schema!!'
	and b.table_name = '!!#table!!'
	and pk.column_name is null
	!!~col_sel!!
order by s.ordinal_position;

-- Create the SQL to select primary key columns from the base table.
if object_id('tempdb..#cmp_pkexpr') is not null drop table #cmp_pkexpr;
select
	string_agg('b.' + column_name, ', ') as pksel
into
	#cmp_pkexpr
from
	#cmp_primary_key_columns;
-- !x! subdata ~pkcolexpr #cmp_pkexpr


-- Create the SQL for each column to compare the base (b) and staging (s) tables.
alter table #cmp_cols add sqlcmd varchar(max);
update #cmp_cols
set sqlcmd =
'case when b.' + column_name + ' is null then case when s.' + column_name + ' is null then ''Same'' else ''New'' end else case when s.' + column_name + ' is null then ''Old'' else case when b.' + column_name + ' = s.' + column_name + ' then ''Same'' else ''Different'' end end end as ' + column_name
;

-- Create the comparison expression for all columns.
if object_id('tempdb..#cmp_compexpr') is not null drop table #cmp_compexpr;
select
	string_agg(sqlcmd, ', ') as attcomp
into
	#cmp_compexpr
from
	#cmp_cols;
-- !x! subdata ~compexpr #cmp_compexpr

-- Create a join expression for primary key columns of the base (b) and
-- staging (s) tables.
if object_id('tempdb..#cmp_joinexpr') is not null drop table #cmp_joinexpr;
select
	string_agg('b.' + column_name + ' = s.' + column_name, ' and ') as joinexpr
into
	#cmp_joinexpr
from
	#cmp_primary_key_columns;
-- !x! subdata ~joinexpr #cmp_joinexpr


-- Create and assign the entire SQL.
-- !x! sub !!#sql_var!! select !!~pkcolexpr!!, !!~compexpr!! from !!#base_schema!!.!!#table!! as b inner join !!#staging!!.!!#table!! as s on !!~joinexpr!!



-- !x! END SCRIPT COMPARE_COMMON

-- ####################  End of COMPARE_COMMON  ###################
-- ################################################################



-- ################################################################
--			Script COMPARE_COMMON_VALS
-- ===============================================================
--
-- Generate SQL to compare the attributes of base and staging
-- tables for only those primary keys in common.  This uses an
-- inner join between the tables, and does not include any rows
-- with a primary key that is in one table and not the other.
--
-- The output includes two columns for every attribute column in
-- the base table (except those explicitly excluded), plus a column
-- for every primary key column.  Primary key
-- columns are populated with primary key values.  The two output
-- columns for each attribute column in the base table have names that
-- match the base table column name plus a suffix of either "_old",
-- representing the base table, or "_new", representing the staging
-- table.
--
-- Required input arguments:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		table			: The name of the table to compare.
--						  The table must have the same name
--						  in base and staging schemas.
--
-- Optional input arguments:
--		include_cols	: Contains a comma-separated list of single-quoted
--						  column names in the base table that are the
--						  *only* attribute columns to be compared.
--		exclude_cols	: Contains a comma-separated list of single-quoted
--						  column names in the base table that are not to
--						  be compared.  If 'include_cols' is provided,
--						  'exclude_cols' is ignored.
--
--	Required output arguments:
--		sql_var			: The name of the variable into which
--						  the generated SQL will be stored
--
-- Notes
-- 	1. The generated SQL is not terminated with a semicolon.
-- ===============================================================
-- !x! BEGIN SCRIPT COMPARE_COMMON_VALS with parameters (base_schema, staging, table, sql_var)

-- Create a table of primary key columns for the table
if object_id('tempdb..#cmp_primary_key_columns') is not null drop table #cmp_primary_key_columns;
select k.column_name, k.ordinal_position
into #cmp_primary_key_columns
from information_schema.table_constraints as tc
inner join information_schema.key_column_usage as k
    on tc.constraint_type = 'PRIMARY KEY'
    and tc.constraint_name = k.constraint_name
    and tc.constraint_catalog = k.constraint_catalog
    and tc.constraint_schema = k.constraint_schema
    and tc.table_schema = k.table_schema
    and tc.table_name = k.table_name
	and tc.constraint_name = k.constraint_name
where
	k.table_name = '!!#table!!'
	and k.table_schema = '!!#base_schema!!'
order by k.ordinal_position
;

-- !x! if(not hasrows(#cmp_primary_key_columns)) { halt message "Table !!#table!! has no primary key columns." }

-- Populate a (temporary) table with the names of the attribute columns
-- that are to be compared.
-- Include only those columns from the staging table that are also in the base table.
-- !x! sub_empty ~col_sel
-- !x! if(sub_defined(#include_cols))
	-- !x! sub ~col_sel and s.column_name in (!!#include_cols!!)
-- !x! elseif(sub_defined(#exclude_cols))
	-- !x! sub ~col_sel and s.column_name not in (!!#exclude_cols!!)
-- !x! endif
if object_id('tempdb..#cmp_cols') is not null drop table #cmp_cols;
select s.column_name
into #cmp_cols
from information_schema.columns as s
	inner join information_schema.columns as b on s.column_name=b.column_name
	left join #cmp_primary_key_columns as pk on pk.column_name = s.column_name
where
	s.table_schema = '!!#staging!!'
	and s.table_name = '!!#table!!'
	and b.table_schema = '!!#base_schema!!'
	and b.table_name = '!!#table!!'
	and pk.column_name is null
	!!~col_sel!!
order by s.ordinal_position;

-- Create the SQL to select primary key columns from the base table.
if object_id('tempdb..#cmp_pkexpr') is not null drop table #cmp_pkexpr;
select
	string_agg('b.' + column_name, ', ') as pkexpr
into
	#cmp_pkexpr
from
	#cmp_primary_key_columns;
-- !x! subdata ~pkcolexpr #cmp_pkexpr


-- Create the SQL for each column to compare the base (b) and staging (s) tables.
alter table #cmp_cols add sqlcmd varchar(max);
update #cmp_cols
set sqlcmd =
'b.' + column_name + ' as ' + column_name + '_old, s.' + column_name + ' as ' + column_name + '_new'
;

-- Create the comparison expression for all columns.
if object_id('tempdb..#cmp_compexpr') is not null drop table #cmp_compexpr;
select
	string_agg(sqlcmd, ', ') as compexpr
into
	#cmp_compexpr
from
	#cmp_cols;
-- !x! subdata ~compexpr #cmp_compexpr

-- Create a join expression for primary key columns of the base (b) and
-- staging (s) tables.
if object_id('tempdb..#cmp_joinexpr') is not null drop table #cmp_joinexpr;
select
	string_agg('b.' + column_name + ' = s.' + column_name, ' and ') as joinexpr
into
	#cmp_joinexpr
from
	#cmp_primary_key_columns;
-- !x! subdata ~joinexpr #cmp_joinexpr


-- Create and assign the entire SQL.
-- !x! sub !!#sql_var!! select !!~pkcolexpr!!, !!~compexpr!! from !!#base_schema!!.!!#table!! as b inner join !!#staging!!.!!#table!! as s on !!~joinexpr!!



-- !x! END SCRIPT COMPARE_COMMON_VALS

-- ###############  End of COMPARE_COMMON_VALS  ###################
-- ################################################################





-- ################################################################
--			Script COMPARE_CHANGES
-- ===============================================================
--
-- Generate SQL to characterize every row of the staging table
-- data as either a new row, a row with changed data, or a row
-- with data that are unchanged relative to the base table.
--
-- The output includes a column for every primary key plus a
-- column named "changes" with one of the following tags:
--		NewRow		: The primary key is in the staging table
--					  but not in the base table.
--		Changed		: At least one of the attribute values is
--					  different in the staging table.
--		Unchanged	: All attribute values are the same in the
--					  staging and base tables.
--
-- Required input arguments:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		table			: The name of the table to compare.
--						  The table must have the same name
--						  in base and staging schemas.
--
-- Optional input arguments:
--		include_cols	: Contains a comma-separated list of single-quoted
--						  column names in the base table that are the
--						  *only* attribute columns to be compared.
--		exclude_cols	: Contains a comma-separated list of single-quoted
--						  column names in the base table that are not to
--						  be compared.  If 'include_cols' is provided,
--						  'exclude_cols' is ignored.
--
--	Required output arguments:
--		sql_var			: The name of the variable into which
--						  the generated SQL will be stored
--
-- Notes
-- 	1. The generated SQL is not terminated with a semicolon.
-- ===============================================================
-- !x! BEGIN SCRIPT COMPARE_CHANGES with parameters (base_schema, staging, table, sql_var)

-- Create a table of primary key columns for the table
if object_id('tempdb..#cmp_primary_key_columns') is not null drop table #cmp_primary_key_columns;
select k.column_name, k.ordinal_position
into #cmp_primary_key_columns
from information_schema.table_constraints as tc
inner join information_schema.key_column_usage as k
    on tc.constraint_type = 'PRIMARY KEY'
    and tc.constraint_name = k.constraint_name
    and tc.constraint_catalog = k.constraint_catalog
    and tc.constraint_schema = k.constraint_schema
    and tc.table_schema = k.table_schema
    and tc.table_name = k.table_name
	and tc.constraint_name = k.constraint_name
where
	k.table_name = '!!#table!!'
	and k.table_schema = '!!#base_schema!!'
order by k.ordinal_position
;

-- !x! if(not hasrows(#cmp_primary_key_columns)) { halt message "Table !!#table!! has no primary key columns." }

-- Populate a (temporary) table with the names of the attribute columns
-- that are to be compared.
-- Include only those columns from the staging table that are also in the base table.
-- !x! sub_empty ~col_sel
-- !x! if(sub_defined(#include_cols))
	-- !x! sub ~col_sel and s.column_name in (!!#include_cols!!)
-- !x! elseif(sub_defined(#exclude_cols))
	-- !x! sub ~col_sel and s.column_name not in (!!#exclude_cols!!)
-- !x! endif
if object_id('tempdb..#cmp_cols') is not null drop table #cmp_cols;
select s.column_name
into #cmp_cols
from information_schema.columns as s
	inner join information_schema.columns as b on s.column_name=b.column_name
	left join #cmp_primary_key_columns as pk on pk.column_name = s.column_name
where
	s.table_schema = '!!#staging!!'
	and s.table_name = '!!#table!!'
	and b.table_schema = '!!#base_schema!!'
	and b.table_name = '!!#table!!'
	!!~col_sel!!
order by s.ordinal_position;

-- Create the SQL to select primary key columns from the staging table.
if object_id('tempdb..#cmp_pkexpr') is not null drop table #cmp_pkexpr;
select
	string_agg('s.' + column_name, ', ') as pkexpr
into
	#cmp_pkexpr
from
	#cmp_primary_key_columns;
-- !x! subdata ~pkcolexpr #cmp_pkexpr


-- Create the SQL for each column to compare the base (b) and staging (s) tables.
-- This generates a value of 1 when there are differences and 0 when there are not.
alter table #cmp_cols add sqlcmd varchar(max);
update #cmp_cols
set sqlcmd =
'case when b.' + column_name + ' is null then case when s.' + column_name + ' is null then 0 else 1 end else case when s.' + column_name + ' is null then 1 else case when b.' + column_name + ' = s.' + column_name + ' then 0 else 1 end end end'
;

-- Create the expression to determine whether there is a difference for any column.
if object_id('tempdb..#cmp_compexpr') is not null drop table #cmp_compexpr;
select
	string_agg(sqlcmd, ' + ') as compexpr
into
	#cmp_compexpr
from
	#cmp_cols;
-- !x! subdata ~compexpr #cmp_compexpr
-- !x! sub ~diffexpr case when !!~compexpr!! = 0 then 'Unchanged' else 'Changed' end

-- Create a join expression for primary key columns of the base (b) and
-- staging (s) tables.
if object_id('tempdb..#cmp_joinexpr') is not null drop table #cmp_joinexpr;
select
	string_agg('b.' + column_name + ' = s.' + column_name, ' and ') as joinexpr
into
	#cmp_joinexpr
from
	#cmp_primary_key_columns;
-- !x! subdata ~joinexpr #cmp_joinexpr

-- Get the name of a single primary key column, aliased to the base table,
-- to test for row existence in the base table.
-- !x! subdata pkcol1 #cmp_primary_key_columns

-- Create the SQL to display either the row tag or the comparison tag.
-- !x! sub ~changeexpr case when b.!!pkcol1!! is null then 'NewRow' else !!~diffexpr!! end as changes

-- Create and assign the entire SQL.
-- !x! sub !!#sql_var!! select !!~pkcolexpr!!, !!~changeexpr!! from !!#staging!!.!!#table!! as s left join !!#base_schema!!.!!#table!! as b on !!~joinexpr!!



-- !x! END SCRIPT COMPARE_CHANGES

-- ###################  End of COMPARE_CHANGES  ###################
-- ################################################################






-- ################################################################
--			Script COMPARE_CHANGED
-- ===============================================================
--
-- Generate SQL to characterize every row of the base table
-- depending on whether there is a matching row in the staging
-- table, whether a matching row has new data, or whether a
-- matching row has identical data.
--
-- The output includes a column for every primary key plus a
-- column named "changed" with one of the following tags:
--		NoNewRow	: The primary key is in the base table
--					  but not in the staging table.
--		Changed		: At least one of the attribute values is
--					  different in the staging table.
--		Unchanged	: All attribute values are the same in the
--					  staging and base tables.
--
-- Required input arguments:
--		base_schema		: The name of the base table schema.
--		staging			: The name of the staging schema.
--		table			: The name of the table to compare.
--						  The table must have the same name
--						  in base and staging schemas.
--
-- Optional input arguments:
--		include_cols	: Contains a comma-separated list of single-quoted
--						  column names in the base table that are the
--						  *only* attribute columns to be compared.
--		exclude_cols	: Contains a comma-separated list of single-quoted
--						  column names in the base table that are not to
--						  be compared.  If 'include_cols' is provided,
--						  'exclude_cols' is ignored.
--
--	Required output arguments:
--		sql_var			: The name of the variable into which
--						  the generated SQL will be stored
--
-- Notes
-- 	1. The generated SQL is not terminated with a semicolon.
-- ===============================================================
-- !x! BEGIN SCRIPT COMPARE_CHANGED with parameters (base_schema, staging, table, sql_var)

-- Create a table of primary key columns for the table
if object_id('tempdb..#cmp_primary_key_columns') is not null drop table #cmp_primary_key_columns;
select k.column_name, k.ordinal_position
into #cmp_primary_key_columns
from information_schema.table_constraints as tc
inner join information_schema.key_column_usage as k
    on tc.constraint_type = 'PRIMARY KEY'
    and tc.constraint_name = k.constraint_name
    and tc.constraint_catalog = k.constraint_catalog
    and tc.constraint_schema = k.constraint_schema
    and tc.table_schema = k.table_schema
    and tc.table_name = k.table_name
	and tc.constraint_name = k.constraint_name
where
	k.table_name = '!!#table!!'
	and k.table_schema = '!!#base_schema!!'
order by k.ordinal_position
;

-- !x! if(not hasrows(#cmp_primary_key_columns)) { halt message "Table !!#table!! has no primary key columns." }

-- Populate a (temporary) table with the names of the attribute columns
-- that are to be compared.
-- Include only those columns from the staging table that are also in the base table.
-- !x! sub_empty ~col_sel
-- !x! if(sub_defined(#include_cols))
	-- !x! sub ~col_sel and s.column_name in (!!#include_cols!!)
-- !x! elseif(sub_defined(#exclude_cols))
	-- !x! sub ~col_sel and s.column_name not in (!!#exclude_cols!!)
-- !x! endif
if object_id('tempdb..#cmp_cols') is not null drop table #cmp_cols;
select s.column_name
into #cmp_cols
from information_schema.columns as s
	inner join information_schema.columns as b on s.column_name=b.column_name
	left join #cmp_primary_key_columns as pk on pk.column_name = s.column_name
where
	s.table_schema = '!!#staging!!'
	and s.table_name = '!!#table!!'
	and b.table_schema = '!!#base_schema!!'
	and b.table_name = '!!#table!!'
	!!~col_sel!!
order by s.ordinal_position;

-- Create the SQL to select primary key columns from the base table.
if object_id('tempdb..#cmp_pkexpr') is not null drop table #cmp_pkexpr;
select
	string_agg('b.' + column_name, ', ') as pkexpr
into
	#cmp_pkexpr
from
	#cmp_primary_key_columns;
-- !x! subdata ~pkcolexpr #cmp_pkexpr


-- Create the SQL for each column to compare the base (b) and staging (s) tables.
-- This generates a value of 1 when there are differences and 0 when there are not.
alter table #cmp_cols add sqlcmd varchar(max);
update #cmp_cols
set sqlcmd =
'case when b.' + column_name + ' is null then case when s.' + column_name + ' is null then 0 else 1 end else case when s.' + column_name + ' is null then 1 else case when b.' + column_name + ' = s.' + column_name + ' then 0 else 1 end end end'
;

-- Create the expression to determine whether there is a difference for any column.
if object_id('tempdb..#cmp_compexpr') is not null drop table #cmp_compexpr;
select
	string_agg(sqlcmd, ' + ') as compexpr
into
	#cmp_compexpr
from
	#cmp_cols;
-- !x! subdata ~compexpr #cmp_compexpr
-- !x! sub ~diffexpr case when !!~compexpr!! = 0 then 'Unchanged' else 'Changed' end

-- Create a join expression for primary key columns of the base (b) and
-- staging (s) tables.
if object_id('tempdb..#cmp_joinexpr') is not null drop table #cmp_joinexpr;
select
	string_agg('b.' + column_name + ' = s.' + column_name, ' and ') as joinexpr
into
	#cmp_joinexpr
from
	#cmp_primary_key_columns;
-- !x! subdata ~joinexpr #cmp_joinexpr

-- Get the name of a single primary key column to test for row existence in the
-- staging table.
-- !x! subdata pkcol1 #cmp_primary_key_columns

-- Create the SQL to display either the row tag or the comparison tag.
-- !x! sub ~changeexpr case when s.!!pkcol1!! is null then 'NoNewRow' else !!~diffexpr!! end as changed

-- Create and assign the entire SQL.
-- !x! sub !!#sql_var!! select !!~pkcolexpr!!, !!~changeexpr!! from !!#base_schema!!.!!#table!! as b left join !!#staging!!.!!#table!! as s on !!~joinexpr!!



-- !x! END SCRIPT COMPARE_CHANGED

-- ###################  End of COMPARE_CHANGED  ###################
-- ################################################################
