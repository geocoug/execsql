-- ss_glossary.sql
--
-- PURPOSE
--	ExecSQL scripts to create a custom glossary of column names (or
--	other objects) to accompany a data summary.
--
-- HOW TO USE THESE SCRIPTS
--	1. Use the execsql CONNECT metacommand to connect to the SQL Server
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
--	2. Side effects: a) Creates a table named "gls_glossary"
--		in the 'initial' database; b) creates a view named
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
--	Elizabeth Shea (ES)
--
-- VERSION
--	1.0.0
--
-- HISTORY
--	 Date		 Remarks
--	----------	---------------------------------------------------------------
--	2019-05-01	Created SQL Server version from 2019-04-20 version for
--				Postgres.  RDN.
--	2019-05-11	Completed conversion to SQL Server.  RDN.
-- ============================================================================



-- ################################################################
--			Script STRING_AGG
-- Code by Elizabeth Shea
-- ===============================================================
--
-- Utility script to perform string aggregation
-- Beginning with 2017 edition, SQL Server *does* include the string_agg()
-- function, but earlier versions do not.
--
-- Input parameters:
--		table_name	: The name of the table containing the column to be aggregated.
--						This may be a temp table containing pre-processed strings.
--		string_col  : The name of the column to be aggregated.
--		order_col   : The name of the column to order by
--      delimiter   : Character to be used as a delimiter
--		string_var  : Name of variable to which aggregated string will be assigned
--
--	Output parameters:
--		string_var	: The name of the variable to receive the aggregated string.
--
--
-- Example:
--		-- !x! execute script string_agg with (table_name=#nonnulcols, string_col=null_errors, order_col=null_errors, delimiter=", ", string_var=+nullcols)
-- ===============================================================
-- !x! BEGIN SCRIPT STRING_AGG with parameters (table_name, string_col, order_col, delimiter, string_var)

if object_id('tempdb..#agg_string') is not null drop table #agg_string;
with enum as
	(
	select
		cast(!!#string_col!! as varchar(max)) as agg_string,
		row_number() over (order by !!#order_col!!) as row_num
	from
		!!#table_name!!
	),
agg as
	(
	select
		one.agg_string,
		one.row_num
	from
		enum as one
	where
		one.row_num=1
	UNION ALL
	select
		agg.agg_string + '!!#delimiter!!' + enum.agg_string as agg_string,
		enum.row_num
	from
		agg, enum
	where
		enum.row_num=agg.row_num+1
	)
select
agg_string
into #agg_string
from agg
where row_num=(select max(row_num) from agg);
-- !x! if(hasrows(#agg_string))
	-- !x! subdata !!#string_var!! #agg_string
-- !x! endif

-- !x! END SCRIPT
-- ##################  End of STRING_AGG  #####################
-- ################################################################



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

-- Create a table for the selected glossary entries in the 'initial' database.
-- !x! sub ~entry_alias !!$current_alias!!
-- !x! use initial
drop table if exists gls_glossary;
create table gls_glossary (
	!!gls_name!! varchar(150),
	!!gls_def!!  text,
	!!~url_colspec!!
	constraint pk_gls_glossary primary key (!!gls_name!!)
);

drop view if exists glossary;
create view glossary as
select !!gls_collist!!
from gls_glossary;
-- No ORDER BY clause on views in SQL Server, so pot luck.

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

drop table if exists gls_column_list;

-- Recursive CTE to parse column list argument
-- NOTE: SQL Server 2017 includes the trim() function, but SQL Server 2016 does not,
-- so a combination of ltrim and rtrim is used here instead.
-- CTE code by Elizabeth Shea.
with itemtable as (
	select
		case when charindex(',',  column_string) = 0
			then rtrim(ltrim(column_string))
			else rtrim(ltrim(substring(column_string, 1,charindex(',', column_string)-1)))
			end as column_name,
		case when charindex(',',  column_string) = 0
			then NULL
			else rtrim(ltrim(substring(column_string, charindex(',', column_string)+1, len(column_string))))
			end as remaining_list
	from
		(select '!!#column_list!!' as column_string) as ts
	UNION ALL
	select
		case when charindex(',', remaining_list) = 0
			then rtrim(ltrim(remaining_list))
			else rtrim(ltrim(substring(remaining_list, 1,charindex(',', remaining_list)-1)))
			end as column_name,
		case when charindex(',',  remaining_list) = 0
			then NULL
			else rtrim(ltrim(substring(remaining_list, charindex(',', remaining_list)+1, len(remaining_list))))
			end as remaining_list
	from
		itemtable
	where
		remaining_list is not null
		--Guards against entries with trailing commas:
		-- e.g,  'column1, column2,'
		and rtrim(ltrim(remaining_list))<>''
	)
select
	column_name as !!gls_name!!
into
	gls_column_list
from
	itemtable;


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
into gls_newentries
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
into gls_newglossary2
from
	!!gls_table!!
where
	!!gls_name!! in (select !!gls_name!! from gls_newentries2);

drop table gls_newentries2;

-- 4.
-- !x! copy gls_newglossary2 from !!gls_alias!! to replacement gls_newglossary in initial

-- 5.
-- !x! use initial
insert into gls_glossary (!!gls_collist!!)
select !!gls_collist!! from gls_newglossary;

drop table gls_newglossary;
drop table gls_newentries;

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
		(select cast('!!#item!!' as varchar(max)) as item, cast('!!#definition!!' as varchar(max)) as definition, cast('!!#def_url!!' as varchar(max)) as url) as inp
		left join gls_glossary as g on g.!!gls_name!! = inp.item
	where
		g.!!gls_name!! is null;
-- !x! else
	insert into gls_glossary (!!gls_name!!, !!gls_def!!)
	select
		inp.item, inp.definition
	from
		(select cast('!!#item!!' as varchar(max)) as item, cast('!!#definition!!' as varchar(max)) as definition) as inp
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
drop view if exists gls_collist;
-- !x! if(is_null("!!#schema!!"))
	create view gls_collist as
	select
		name as column_name
	from
		tempdb.sys.columns
	where
		object_id = object_id('tempdb..!!#table!!')
		;
-- !x! else
	create view gls_collist as
	select
		column_name
	from
		information_schema.columns
	where
		table_name = '!!#table!!'
		and table_schema = '!!#schema!!'
		;
-- !x! endif
-- !x! sub_empty ~collist
-- !x! execute script string_agg with (table_name=gls_collist, string_col=column_name, order_col=column_name, delimiter=", ", string_var=+collist)

-- Add all column names in the string.
-- !x! execute script ADD_GLOSSARY_LIST with (column_list="!!~collist!!")

drop view gls_collist;

-- !x! use !!~entry_alias!!

-- !x! END SCRIPT ADD_GLOSSARY_TABLE
-- #################  End of ADD_GLOSSARY_TABLE  ##################
-- ################################################################
