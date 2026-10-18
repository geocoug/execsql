-- HALT with an exit status.  (HALT "message" opens a GUI dialog upstream, so it is left out.)
create table t (v text);
insert into t values ('before halt');
-- !x! HALT EXIT_STATUS 3
insert into t values ('after halt');
