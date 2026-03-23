-- pg_glossary.sql
--
-- PURPOSE
--	ExecSQL scripts to create a custom glossary of column names (or
--	other objects) to accompany a data summary.
--
-- HOW TO USE THESE SCRIPTS
--	1. Use the execsql CONNECT metacommand to connect to the Postgres
--		database containing the master glossary table if the master
--		glossary is not in the current database.
--	2. Call the INIT_GLOSSARY script to describe the master glossary
--		and initialize the custom subset of the master glossary that
--		is to be created.
--	3. Call any of the ADD_GLOSSARY_LIST, ADD_GLOSSARY_ITEM, and
--		ADD_GLOSSARY_TABLE scripts to add entries to the custom
--		glossary.
--	4. Use the "glossary" view to display or export the custom glossary.
--
-- NOTES
--	1. All substitution variables, tables, and views created by these
--		scripts have the prefix "gls_"
--	2. Side effects: a) Creates a temporary table named "gls_glossary"
--		in the 'initial' database; b) creates a temporary view named
--		"glossary" in the 'initial' database.
--
-- COPYRIGHT AND LICENSE
--	Copyright (c) 2019, R. Dreas Nielsen
--	This program is free software: you can redistribute it and/or modify it
--	under the terms of the GNU General Public License as published by the
--	Free Software Foundation, either version 3 of the License, or (at your
--	option) any later version. This program is distributed in the hope that
--	it will be useful, but WITHOUT ANY WARRANTY; without even the implied
--	warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
--	GNU General Public License for more details. The GNU General Public
--	License is available at http://www.gnu.org/licenses/.
--
-- AUTHORS
--	Dreas Nielsen (RDN)
--
-- VERSION
--	1.0.1
--
-- HISTORY
--	 Date		 Remarks
--	----------	---------------------------------------------------------------
--	2019-04-17	Created with INIT_GLOSSARY and ADD_GLOSSARY_LIST scripts.  RDN.
--	2019-04-19	Added ADD_GLOSSARY_ITEM and ADD_GLOSSARY_TABLE scripts.
--				Debugged--functional.  Version 1.0.0.  RDN.
--	2019-04-20	Modified table copying to use different names in case the
--				glossary is in the same database that is used for data
--				summarization.  Modified item addition to do nothing on
--				conflicts.  Modified to use subquery instead of CTE when
--				appending a new item.  Version 1.0.1.  RDN.
-- ============================================================================


-- ################################################################
--			Script INIT_GLOSSARY
-- ===============================================================
--
-- Initialize the custom glossary and describe the master glossary
-- that will provide descriptions to include in the custom glossary.
--
-- Required input arguments:
--		glossary_db_alias	: The execsql alias of the database containing
--								the master glossary table.
--		glossary_table		: The name of the master glossary table.
--		name_col			: The name of the column in the glossary
--								table containing the column (or other
--								object) name.
--		def_col				: The name of the column in the glossary
--								table containing the definition of the
--								column (or other object).
-- Optional input argument:
--		def_url				: The URL of a page that provides additional
--								information about the column (or other object).
-- ===============================================================
-- !x! BEGIN SCRIPT INIT_GLOSSARY with parameters (glossary_db_alias, glossary_table, name_col, def_col)

-- !x! sub gls_alias   !!#glossary_db_alias!!
-- !x! sub gls_table   !!#glossary_table!!
-- !x! sub gls_name    !!#name_col!!
-- !x! sub gls_def     !!#def_col!!
-- !x! if(sub_defined(#def_url))
	-- !x! sub gls_has_url Yes
	-- !x! sub gls_url !!#def_url!!
	-- !x! sub ~url_colspec !!gls_url!! text,
	-- !x! sub gls_collist !!gls_name!!, !!gls_def!!, !!gls_url!!
-- !x! else
	-- !x! sub gls_has_url No
	-- !x! sub_empty ~url_colspec
	-- !x! sub gls_collist !!gls_name!!, !!gls_def!!
-- !x! endif

-- Create a temporary table for the selected glossary entries in the 'initial' database.
-- !x! sub ~entry_alias !!$current_alias!!
-- !x! use initial
drop table if exists gls_glossary cascade;
create temporary table gls_glossary (
	!!gls_name!! text,
	!!gls_def!!  text,
	!!~url_colspec!!
	constraint pk_gls_glossary primary key (!!gls_name!!)
);

drop view if exists glossary cascade;
create temporary view glossary as
select !!gls_collist!!
from gls_glossary order by !!gls_name!!;

-- !x! use !!~entry_alias!!

-- !x! END SCRIPT INIT_GLOSSARY
-- ####################  End of INIT_GLOSSARY  ####################
-- ################################################################





-- ################################################################
--			Script ADD_GLOSSARY_LIST
-- ===============================================================
--
-- Add a specific list of columns to the glossary.
--
-- Required input arguments:
--		column_list		: A string of comma-separated column names.
-- ===============================================================
-- !x! BEGIN SCRIPT ADD_GLOSSARY_LIST with parameters (column_list)

-- !x! sub ~entry_alias !!$current_alias!!
-- !x! use initial

drop table if exists gls_column_list cascade;
select
	trim(regexp_split_to_table('!!#column_list!!', E'\\s*,\\s*')) as !!gls_name!!
into
	gls_column_list;

-- Add any of the column names that are not already in the glossary.
-- 1. Get list of column names not already in the glossary into a temp table.
-- 2. Copy that temp table to the glossary database.
-- 3. In the glossary db, get the glossary information from the master glossary
--		into another temp table.
-- 4. Copy that second temp table to the 'initial' database.
-- 5. In the 'initial' database, append those rows to the gls_glossary table.

-- 1.
drop table if exists gls_newentries;
select gls_column_list.!!gls_name!!
into temporary table gls_newentries
from
	gls_column_list
	left join gls_glossary on gls_glossary.!!gls_name!! = gls_column_list.!!gls_name!!
where
	gls_glossary.!!gls_name!! is null;

-- 2.
-- Change the name in case it's in the same database.
-- !x! copy gls_newentries from initial to replacement gls_newentries2 in !!gls_alias!!

-- 3.
-- !x! use !!gls_alias!!
drop table if exists gls_newglossary2;
select
	!!gls_collist!!
into temporary table gls_newglossary2
from
	!!gls_table!!
where
	!!gls_name!! in (select !!gls_name!! from gls_newentries2);

drop table gls_newentries2 cascade;

-- 4.
-- !x! copy gls_newglossary2 from !!gls_alias!! to replacement gls_newglossary in initial

-- 5.
-- !x! use initial
insert into gls_glossary (!!gls_collist!!)
select !!gls_collist!! from gls_newglossary;

drop table gls_newglossary cascade;

-- !x! use !!~entry_alias!!

-- !x! END SCRIPT ADD_GLOSSARY_LIST
-- ##################  End of ADD_GLOSSARY_LIST  ##################
-- ################################################################





-- ################################################################
--			Script ADD_GLOSSARY_ITEM
-- ===============================================================
--
-- Add an object name and definition to the custom glossary.
-- This does not use the master glossary.
--
-- Required input arguments:
--		item			: The name of a column or other item to be
--							defined in the custom glossary.
--		definition		: The definition of the glossary entry.
--
-- Optional input argument:
--		def_url				: The URL of a page that provides additional
--								information about the item.
-- ===============================================================
-- !x! BEGIN SCRIPT ADD_GLOSSARY_ITEM with parameters (item, definition)

-- !x! sub ~entry_alias !!$current_alias!!
-- !x! use initial

-- !x! if(is_true(gls_has_url))
-- !x! andif(sub_defined(#def_url))
	insert into gls_glossary (!!gls_name!!, !!gls_def!!, !!gls_url!!)
	select
		inp.item, inp.definition, inp.url
	from
		(select '!!#item!!'::text as item, '!!#definition!!'::text as definition, '!!#def_url!!'::text as url) as inp
		left join gls_glossary as g on g.!!gls_name!! = inp.item
	where
		g.!!gls_name!! is null;
-- !x! else
	insert into gls_glossary (!!gls_name!!, !!gls_def!!)
	select
		inp.item, inp.definition
	from
		(select '!!#item!!'::text as item, '!!#definition!!'::text as definition) as inp
		left join gls_glossary as g on g.!!gls_name!! = inp.item
	where
		g.!!gls_name!! is null;
-- !x! endif

-- !x! use !!~entry_alias!!

-- !x! END SCRIPT ADD_GLOSSARY_ITEM
-- ##################  End of ADD_GLOSSARY_ITEM  ##################
-- ################################################################





-- ################################################################
--			Script ADD_GLOSSARY_TABLE
-- ===============================================================
--
-- Add definitions of all columns in a specified table to the
-- custom glossary.
--
-- Required input arguments:
--		schema			: The schema of the table.
--		table			: The table name.
--
-- ===============================================================
-- !x! BEGIN SCRIPT ADD_GLOSSARY_TABLE with parameters (schema, table)

-- !x! sub ~entry_alias !!$current_alias!!

-- Get columns of the specified table into a string.
-- !x! if(is_null("!!#schema!!"))
	-- !x! sub_empty ~schema_sel
-- !x! else
	-- !x! sub ~schema_sel and table_schema = '!!#schema!!'
-- !x! endif
drop view if exists gls_collist cascade;
create temporary view gls_collist as
select
	string_agg(column_name, ', ') as collist
from
	information_schema.columns
where
	table_name = '!!#table!!'
	!!~schema_sel!!
	;
-- !x! subdata ~collist gls_collist

-- Add all column names in the string.
-- !x! execute script ADD_GLOSSARY_LIST with (column_list="!!~collist!!")

-- !x! use !!~entry_alias!!

-- !x! END SCRIPT ADD_GLOSSARY_TABLE
-- #################  End of ADD_GLOSSARY_TABLE  ##################
-- ################################################################
