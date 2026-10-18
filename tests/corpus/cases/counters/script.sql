-- Counter variables advance on every reference.
create table t (n integer);
insert into t values (!!$COUNTER_1!!);
insert into t values (!!$COUNTER_1!!);
insert into t values (!!$COUNTER_2!!);
-- !x! SET COUNTER 1 TO 10
insert into t values (!!$COUNTER_1!!);
-- !x! RESET COUNTER 1
insert into t values (!!$COUNTER_1!!);
-- !x! RESET COUNTERS
insert into t values (!!$COUNTER_2!!);
